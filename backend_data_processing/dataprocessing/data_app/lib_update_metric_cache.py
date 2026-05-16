import numpy as np
from decimal import Decimal

from . import lib_common
from .models import MetricMinutesCache
from dataprocessing import lib_settings as settings

import logging
if len(logging.getLogger().handlers) > 0:
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)


def update(item, res):
    if res == 'minutes':
        logging.info(f"Update metric minutes cache. resolution = {res}, items = {item}")
        is_trigger_cache = handle_update_minutes(item)
    else:
        is_trigger_cache = False
    return is_trigger_cache


def handle_update_minutes(item, decimal_place=2):
    """
    Update the metric minutes cache using the latest sensor payload.
    Args:
        item (dict): Incoming sensor payload already enriched with cache-friendly
            fields such as `dashboardMode`, `dateTime`, `RR`, `HR`, `SpO2`, etc.
            The payload is expected to represent a single minute level record.
        decimal_place (int, optional): Precision used when converting numeric
            temperature and activity values to `Decimal`. Defaults to 2.
    Returns:
        bool: `True` when the cache is written and downstream lambda is triggered.
    Notes:
        - Filters out bad quality readings for RR mode before updating vitals.
        - Maintains battery, sync timestamps, latest valid timestamps, and skin
          contact history per modality (chest/finger).
        - Persists the consolidated record to DynamoDB and triggers the AI
          prediction lambda when applicable.
    """

    vital_signs_items = lib_common.remove_bad_data([item], True)
    filtered_item = vital_signs_items[0] # output will be list of 1 item

    dashboard_mode = item['dashboard_mode']
    new_skin_contact_data = []
    for data in vital_signs_items:
        skin_data = {
        "date_time": data['date_time'].strftime('%Y-%m-%d:%H:%M:%S'),
        "dashboard_mode": data['dashboard_mode'],
        "sensor_onskin_status": {0: 0, '0': 0, 1: 1, '1': 1, -1: -1, '-1': -1}.get(data['sensor_onskin_status'], -1),
        "display_label": data.get("display_label")
        }
        if skin_data["sensor_onskin_status"] in [0, 1]:
            new_skin_contact_data.append(skin_data)

    logging.info(f"Logging new_skin_contact_data = {new_skin_contact_data}")

    if dashboard_mode in ['RR']:
        filtered_item = lib_common.filter_data_based_on_quality_status(
            [filtered_item], settings.list_quality_to_keep)

        if len(filtered_item) == 1:
            filtered_item = filtered_item[0]

        try:
            signal_quality = filtered_item["signal_quality_status"]
        except:
            signal_quality = -1

        signal_quality_match = any(
            element == signal_quality for element in settings.list_quality_to_keep)

    else:
        signal_quality_match = True

    queryItems = MetricMinutesCache.objects.filter(
        user_id=item['user_id']).values()

    # Create new item to be inserted in cache
    new_item = {
        "user_id": item["user_id"],
        "datetime_server_received": item["datetime_server_received"],
        "date_time": item["date_time"],
        "battery": item['battery'],
        "dashboard_mode": item["dashboard_mode"],
        "sensor_id": item["sensor_id"],
        "hardware_mode": item["hardware_mode"],
        "last_sync": item["datetime_gateway_sent"]
    }

    if 'utc_offset' in item:
        new_item['utc_offset'] = item['utc_offset']

    # If cache record exists, update the new item with existing values
    if len(queryItems) > 0:
        first_item = queryItems[0]
        first_item.update(**new_item)
        new_item = first_item.copy()
        del new_item["id"]

    # Update cache with latest value (chest and finger)
    if dashboard_mode=="RR":
        new_item["battery_chest"] = item["battery"]
        new_item["last_sync_chest"] = item["datetime_gateway_sent"]
        new_item["datetime_chest"] = item["date_time"]
    elif dashboard_mode=="HR":
        new_item["battery_finger"] = item["battery"]
        new_item["last_sync_finger"] = item["datetime_gateway_sent"]
        new_item["datetime_finger"] = item["date_time"]

    # check if it returns NaN
    # try:
    #     bool_is_response_nan = np.isnan(filtered_item["user_id"])
    # except:
    #     bool_is_response_nan = True

    # update only if signal quality >= moderate
    # if signal_quality_match:
    #     is_trigger_cache = True  # update table
    # else:
    #     is_trigger_cache = False
    is_trigger_cache = True

    # update cache dict values
    if len(filtered_item)>0:  # this record is GOOD data
        print('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',filtered_item)

        print(filtered_item["user_id"])
        if not np.isnan(float(filtered_item["user_id"])):
        # if  filtered_item["user_id"] != None:
            print('AAAAA 111')

            cache_skin_contact = 0

            if dashboard_mode == "RR":
                try:
                    new_rr = int(item["rr"])
                    cache_skin_contact = 1
                    skin_contact_chest = 1
                    new_item["datetime_latest_valid_chest"] = item["date_time"]
                except Exception as e:
                    new_rr = settings.val_replace_NaN
                    skin_contact_chest = 0
                    logging.error(f"Cannot convert RR to INT type. Error message is {e}")

                new_item['rr'] = new_rr
                new_item["skin_contact_chest"] = skin_contact_chest

            elif dashboard_mode == "HR":
                try: 
                    new_hr = int(item["hr"])
                    new_spo2 = int(item["spo2"])
                    cache_skin_contact = 1
                    skin_contact_finger = 1
                    new_item["datetime_latest_valid_finger"] = item["date_time"]
                except Exception as e:
                    new_hr = settings.val_replace_NaN
                    new_spo2 = settings.val_replace_NaN
                    skin_contact_finger = 0
                    logging.error(f"Cannot convert HR or SpO2 to INT type. Error message is {e}")

                new_item["hr"] = new_hr
                new_item["spo2"] = new_spo2
                new_item["skin_contact_finger"] = skin_contact_finger

            new_item["skin_contact"] = cache_skin_contact

        if dashboard_mode == "RR":
            # new_item['rr'] = new_rr
            new_item["skin_temperature"] = Decimal("{:.{}f}".format(
                item["skin_temperature"], decimal_place))
            new_item["body_temperature"] = Decimal("{:.{}f}".format(
                item["body_temperature"], decimal_place))
            # new_item["dateTime_latest_valid_chest"] = item["dateTime"]
        # elif dashboard_mode == "HR":
        #     new_item["dateTime_latest_valid_finger"] = item["dateTime"]

    else:
        new_item["skin_contact"] = 0  # BAD

        if dashboard_mode == "RR":
            new_item["skin_contact_chest"] = 0
        elif dashboard_mode == "HR":
            new_item["skin_contact_finger"] = 0

    # if 'skin_contact_data' in new_item:
    #     old_skin_contact_data = new_item['skin_contact_data']
    #     if old_skin_contact_data == None:
    #         old_skin_contact_data = []
    #     hr_list = [d for d in old_skin_contact_data if d.get("dashboard_mode") == "HR"]
    #     rr_list = [d for d in old_skin_contact_data if d.get("dashboard_mode") == "RR"]
    #     latest_entry = new_skin_contact_data[0]
    #     dashboardmode = latest_entry.get("dashboard_mode")
    #     if dashboardmode == "RR":
    #         rr_list.append(new_skin_contact_data[0])
    #         rr_list = rr_list[-4:]
    #     elif dashboardmode == "HR":
    #         hr_list.append(new_skin_contact_data[0])
    #         hr_list = hr_list[-4:]
    #     new_item['skin_contact_data'] = hr_list + rr_list
    # else:
    #     new_item['skin_contact_data'] = new_skin_contact_data


    on_skin = lib_common.check_skin_status_sequence(new_skin_contact_data, 1, 'display_label')
    if on_skin in [0,1]: #  0 -> BAD skin contact  1 -> GOOD skin contact
        if 'latest_skin_contact' in new_item:
            old_skin_contact_data = new_item['latest_skin_contact']
            if old_skin_contact_data == None:
                old_skin_contact_data = []

            hr_list = [d for d in old_skin_contact_data if d.get("dashboard_mode") == "HR"]
            rr_list = [d for d in old_skin_contact_data if d.get("dashboard_mode") == "RR"]


            if new_skin_contact_data:
                latest_entry = new_skin_contact_data[0]
                dashboardmode = latest_entry.get("dashboard_mode")
                if dashboardmode == "RR":
                    rr_list.append(new_skin_contact_data[0])
                    rr_list = rr_list[-4:]
                elif dashboardmode == "HR":
                    hr_list.append(new_skin_contact_data[0])
                    hr_list = hr_list[-4:]
                new_item['latest_skin_contact'] = hr_list + rr_list
        else:
            new_item['latest_skin_contact'] = new_skin_contact_data


    new_item = lib_common.update_skin_contact_data(
        latest_item = new_skin_contact_data,
        new_item=new_item,
        latest_datetime=new_item["date_time"]
    )


    new_item['source'] = settings.DATA_SOURCE["Sensor"]
    
    if 'utc_offset' in item:
        new_item['utc_offset'] = item['utc_offset']
        
    logging.info(f"Logging new_item after update skin_contact_data = {new_item}")


    if is_trigger_cache:

        minute_cache_obj = MetricMinutesCache.objects.filter(user_id=new_item['user_id'])
        if minute_cache_obj.exists():
            minute_cache_obj = minute_cache_obj.first()
            for key, value in new_item.items():
                setattr(minute_cache_obj, key, value)
            minute_cache_obj.save()  # This triggers pre_save and post_save signals
        else:
            minute_cache_obj = MetricMinutesCache(**new_item)
            minute_cache_obj.save() # This triggers pre_save and post_save signals


        # message = lib_common_ai.generate_ai_prediction_minute(new_item)
        # logging.info(f" Generated AI prediction message for user_id={new_item['user_id']}: {message}")

        old_skin_contact_data = minute_cache_obj.skin_contact_data
        if old_skin_contact_data == None:
            old_skin_contact_data = []
        if len(old_skin_contact_data) < 4:
            old_skin_contact_data.extend(new_skin_contact_data)
        else:
            old_skin_contact_data.extend(new_skin_contact_data)
            old_skin_contact_data.pop(0)
        minute_cache_obj.skin_contact_data = old_skin_contact_data
        minute_cache_obj.save()
    else:
        logging.info(f"This input item does not trigger update {item}")

    return is_trigger_cache
