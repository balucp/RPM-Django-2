from dateutil import tz
import datetime
import numpy as np
import pytz
import sys
import traceback
import os
import requests
import boto3
import json
import sys
import traceback
# from boto3.dynamodb.conditions import Key, Attr
from urllib.parse import urljoin
from dataprocessing import lib_settings as settings
import pandas as pd
import logging
import math
from . import lib_query
from decimal import Decimal
from datetime import  timezone, timedelta
from requests.adapters import HTTPAdapter, Retry
from data_app.models import ( MetricDailyCache, MetricMinutesCache, DataProcessing, 
    MetricHourlyCache, ProcessInProgress, HealthData, DataProcessing, ProcessInProgress,
    OtherDeviceReading)
val_replace_NaN = settings.val_replace_NaN


def convert_utc_to_local(datetimeInput, timezone):
    from_zone = tz.gettz('UTC')
    to_zone = tz.gettz(timezone)

    utc = datetime.datetime.strptime(datetimeInput, '%Y-%m-%d %H:%M:%S')
    utc = utc.replace(tzinfo=from_zone)

    # Convert time zone
    output = utc.astimezone(to_zone)
    outputStr = output.strftime('%Y-%m-%d %H:%M:%S')  # convert to string
    return output, outputStr


def convert_str_to_datetime(datetimeInput, formatdatetime='%Y-%m-%d %H:%M:%S'):
    output = datetime.datetime.strptime(datetimeInput, formatdatetime)
    outputStr = output.strftime(formatdatetime)
    return output, outputStr


def convert_datetime_to_str(datetimeInput, formatdatetime='%Y-%m-%d %H:%M:%S'):
    return datetimeInput.strftime(formatdatetime)


def writeToS3(arrayData, bucketName, filePath, fileName):

    lambdaPath = "/tmp/"+fileName

    np.savetxt(lambdaPath, arrayData, delimiter=',', fmt='%.0f')

    boto3.resource('s3').meta.client.upload_file(
        lambdaPath, bucketName, filePath)
    logging.info({
        "message": f"Uploaded data to {filePath}",
    })

    os.remove(lambdaPath)

    return


def stringToArray(X):
    split_data = X.split('\n')
    row = len(split_data)-1
    col = len(split_data[0].split(','))
    output = np.zeros((row, col))
    for i in range(row):
        output[i, :] = split_data[i].split(',')
    return output


def download_data_from_bucket(bucket_name, filepath):
    obj = boto3.resource('s3').Object(bucket_name, filepath)
    load_data = obj.get()['Body'].read().decode('utf-8')

    output = stringToArray(load_data)
    return output



def check_skin_status_sequence(items, sequence_length, key='sensor_onskin_status'):
    items = list(reversed(items))
    # filter out all skin_contact -1 and keep order as is
    items = [item for item in items if key not in item or item.get(key) not in [-1]]

    # 1- on, off, off, off, 2 - off, off, off, off
    expression_to_match = ([0, 0, 0, 1.0], [0, 0, 0, 0])
    expression = []
    # get the latest 4, need to reverse list to get latest
    if (sequence_length == 4 and len(items) >= sequence_length):
        for index in range(sequence_length):
            if key in items[index]:
                expression.append(
                    float((items[index])[key]))
            else:
                expression.append(None)
        expression = [0 if item is None or math.isnan(
            item) else item for item in expression]
        for expr in expression_to_match:
            if expression == expr:
                return 0
        else:
            # other combinations would have to include 1 so return 1 if there is matching to expression_to_match
            return 1

    elif len(items) == 0:
        return -1

    else:
        # for other sequences - ie - 1, 2, 3
        for item in items:
            if key in item and item[key] == 1:
                return 1
        else:
            return 0


def get_devices_data_multiple(list_id):
    url_GET_patient_and_devices_info_multiple = urljoin(
        settings.backend_url, settings.UI_URL_REST_API_getMultiplePatientDevicesInfo)

    list_devices_response = lib_query.get_gateway_and_sensor_status(
        list_id, url_GET_patient_and_devices_info_multiple, settings.UI_REST_API_HEADER)

    response_devices_data_multiple = []
    for user_id in list_id:
        for devices_response in list_devices_response:
            if user_id in devices_response:
                response = {}
                response.setdefault(user_id, {})
                gateway_status, gateway_last_connection, sensor_status, sensor_last_connection, two_sensor_mode = devices_response[
                    user_id]

                device_code = settings.device_code
                sensor_mode = settings.sensor_mode

                response[user_id]['gateway_status'] = next(
                    (value for key, value in device_code.items() if value == gateway_status), None)
                response[user_id]['last_gateway_connect'] = gateway_last_connection.replace('T', ' ') if any(
                    value == gateway_status for key, value in device_code.items() if key not in ["REGISTERING", "NOT_ASSIGNED"]) else val_replace_NaN

                # sensor
                if (two_sensor_mode):
                    # quick fix
                    # if sensor_status == None: assign OFFLINE
                    # if {'RR': 0, 'HR': 0}
                    if sensor_status == None:
                        logging.warning(
                            f"sensor_status is None. Assign 'RR'=None and 'HR'=None")
                        # sensor_status = {'RR': None, 'HR': None}
                        sensor_status = {'RR': 0, 'HR': 0}
                        sensor_last_connection = {}
                        sensor_last_connection['RR'] = False
                        sensor_last_connection['HR'] = False

                    for mode in sensor_status:
                        if (mode in sensor_mode):
                            # sensor status in finger/chest
                            response[user_id][sensor_mode[mode]["sensor_status"]] = next(
                                (value for key, value in device_code.items() if value == sensor_status[mode]), None)

                            # last connection in finger/chest
                            response[user_id][sensor_mode[mode]["last_connect_time"]
                                              ] = val_replace_NaN if not sensor_last_connection[mode] else sensor_last_connection[mode][0].replace('T', ' ')

                    response[user_id][sensor_mode["GEN"]
                                      ["last_connect_time"]] = val_replace_NaN
                    response[user_id][sensor_mode["GEN"]
                                      ["sensor_status"]] = device_code["NOT_ASSIGNED"]

                # one sensor mode
                else:
                    response[user_id][sensor_mode["GEN"]["last_connect_time"]] = sensor_last_connection[0].replace('T', ' ') if any(
                        value == sensor_status for key, value in device_code.items() if key not in ["REGISTERING", "NOT_ASSIGNED"]) else val_replace_NaN

                    response[user_id][sensor_mode["GEN"]["sensor_status"]] = next(
                        (value for key, value in device_code.items() if value == sensor_status), None)

                    response[user_id][sensor_mode["RR"]
                                      ["last_connect_time"]] = val_replace_NaN
                    response[user_id][sensor_mode["RR"]
                                      ["sensor_status"]] = device_code["NOT_ASSIGNED"]

                    response[user_id][sensor_mode["HR"]
                                      ["last_connect_time"]] = val_replace_NaN
                    response[user_id][sensor_mode["HR"]
                                      ["sensor_status"]] = device_code["NOT_ASSIGNED"]
                response_devices_data_multiple.append(response)
                break
    convert_response_devices_data_multiple = {
        k: v for dictionary in response_devices_data_multiple for k, v in dictionary.items()}
    return convert_response_devices_data_multiple


def get_devices_data(response, user_id):
    # devices status, battery, and skin contact should be sent on the fly
    url_GET_patient_and_devices_info = urljoin(
        settings.backend_url, settings.UI_URL_REST_API_getPatientDevicesInfo)

    gateway_status, gateway_last_connection, sensor_status, sensor_last_connection, two_sensor_mode = lib_query.get_gateway_and_sensor_status(
        user_id, url_GET_patient_and_devices_info, settings.UI_REST_API_HEADER)

    device_code = settings.device_code
    sensor_mode = settings.sensor_mode

    response[user_id]['gateway_status'] = next(
        (value for key, value in device_code.items() if value == gateway_status), None)
    response[user_id]['last_gateway_connect'] = gateway_last_connection.replace('T', ' ') if any(
        value == gateway_status for key, value in device_code.items() if key not in ["REGISTERING", "NOT_ASSIGNED"]) else val_replace_NaN

    # sensor
    if (two_sensor_mode):
        # quick fix
        # if sensor_status == None: assign OFFLINE
        # if {'RR': 0, 'HR': 0}
        if sensor_status == None:
            logging.warning(
                f"sensor_status is None. Assign 'RR'=None and 'HR'=None")
            # sensor_status = {'RR': None, 'HR': None}
            sensor_status = {'RR': 0, 'HR': 0}
            sensor_last_connection = {}
            sensor_last_connection['RR'] = False
            sensor_last_connection['HR'] = False

        for mode in sensor_status:
            if (mode in sensor_mode):
                # sensor status in finger/chest
                response[user_id][sensor_mode[mode]["sensor_status"]] = next(
                    (value for key, value in device_code.items() if value == sensor_status[mode]), None)

                # last connection in finger/chest
                response[user_id][sensor_mode[mode]["last_connect_time"]
                                  ] = val_replace_NaN if not sensor_last_connection[mode] else sensor_last_connection[mode][0].replace('T', ' ')

        response[user_id][sensor_mode["GEN"]
                          ["last_connect_time"]] = val_replace_NaN
        response[user_id][sensor_mode["GEN"]
                          ["sensor_status"]] = device_code["NOT_ASSIGNED"]

    # one sensor mode
    else:
        response[user_id][sensor_mode["GEN"]["last_connect_time"]] = sensor_last_connection[0].replace('T', ' ') if any(
            value == sensor_status for key, value in device_code.items() if key not in ["REGISTERING", "NOT_ASSIGNED"]) else val_replace_NaN

        response[user_id][sensor_mode["GEN"]["sensor_status"]] = next(
            (value for key, value in device_code.items() if value == sensor_status), None)

        response[user_id][sensor_mode["RR"]
                          ["last_connect_time"]] = val_replace_NaN
        response[user_id][sensor_mode["RR"]
                          ["sensor_status"]] = device_code["NOT_ASSIGNED"]

        response[user_id][sensor_mode["HR"]
                          ["last_connect_time"]] = val_replace_NaN
        response[user_id][sensor_mode["HR"]
                          ["sensor_status"]] = device_code["NOT_ASSIGNED"]



def get_last_index_with_key_value(objects, key, value):
    try:
        obj_idx_pairs = ((obj, len(objects) - i - 1)
                         for i, obj in enumerate(reversed(objects)))
        obj_idx_pairs_with_value = (
            (obj, idx) for obj, idx in obj_idx_pairs if obj.get(key) == value)
        last_4_pairs_with_value = list(obj_idx_pairs_with_value)[:4]
        last_4_indexes_with_value = [
            idx for obj, idx in last_4_pairs_with_value]
        return last_4_indexes_with_value if last_4_indexes_with_value else None

    except:
        return None

# battery level and skin contact must be on the fly as well


def get_other_spot_data(response, user_id, list_resolution, dateTime, data_processing):

    stop_date = dateTime
    if (list_resolution == 'minutes'):
        start_date = stop_date - timedelta(minutes=settings.list_timedelta['MINUTES'])
    elif (list_resolution == 'hourly'):
        start_date = stop_date - timedelta(hours=settings.list_timedelta['HOURS'])
    else:
        start_date = stop_date - timedelta(days=settings.list_timedelta['DAYS'])

    vital_signs_items = []

    vital_signs_items = data_processing.filter(date_time__range=[start_date, stop_date], datetime_sensor__range=[start_date, stop_date]).values(
        "sensor_onskin_status", "dashboard_mode", "battery", "accepted_frame_spo2_ratio", "accepted_frame_spo2", "val_sd_signal_w_sqa", "hr", "spo2", "skin_temperature", "rr", "datetime_sensor", "date_time", "signal_quality_status")
    
    if len(vital_signs_items) > 0:
        # vital_signs_items = remove_bad_data(vital_signs_items, True)
        vital_signs_items = list(vital_signs_items)

        rr_idx_latest = get_last_index_with_key_value(
            vital_signs_items, 'dashboard_mode', 'RR')
        if rr_idx_latest is not None:
            rr_idx_latest = rr_idx_latest[-1]

        hr_idx_latest = get_last_index_with_key_value(
            vital_signs_items, 'dashboard_mode', 'HR')

        if hr_idx_latest is not None:
            hr_idx_latest = hr_idx_latest[-1]

        rr_idx_sequence = get_last_index_with_key_value(
            vital_signs_items, 'dashboard_mode', 'RR')

        hr_idx_sequence = get_last_index_with_key_value(
            vital_signs_items, 'dashboard_mode', 'HR')

        on_skin = check_skin_status_sequence(vital_signs_items, 4)

        # inclusive of minute and daily calculation
        response[user_id]['skin_contact'] = 'Bad' if on_skin == 0 or on_skin == val_replace_NaN else 'Good'
        if (rr_idx_latest is not None):
            rr_items = [vital_signs_items[i] for i in rr_idx_sequence][::-1]
            on_skin_rr = check_skin_status_sequence(
                rr_items, len(rr_idx_sequence))
            response[user_id]['skin_contact_chest'] = - \
                1 if on_skin_rr == val_replace_NaN else 'Bad' if on_skin_rr == 0 else 'Good'

        else:
            response[user_id]['skin_contact_chest'] = val_replace_NaN

        if (hr_idx_latest is not None):
            hr_items = [vital_signs_items[i] for i in hr_idx_sequence][::-1]
            on_skin_hr = check_skin_status_sequence(
                hr_items, len(hr_idx_sequence))
            response[user_id]['skin_contact_finger'] = - \
                1 if on_skin_hr == val_replace_NaN else 'Bad' if on_skin_hr == 0 else 'Good'

        else:
            response[user_id]['skin_contact_finger'] = val_replace_NaN

        # adding battery for daily
        if list_resolution in ['daily','hourly']:
            
            response[user_id]['battery'] = float(
                vital_signs_items[-1]['battery'])
            if (rr_idx_latest is not None):
                response[user_id]['battery_chest'] = float(
                    vital_signs_items[rr_idx_latest]['battery'])
            else:
                response[user_id]['battery_chest'] = val_replace_NaN
            if (hr_idx_latest is not None):
                response[user_id]['battery_finger'] = float(
                    vital_signs_items[hr_idx_latest]['battery'])
            else:
                response[user_id]['battery_finger'] = val_replace_NaN

    else:
        response[user_id]['skin_contact'] = val_replace_NaN
        response[user_id]['skin_contact_chest'] = val_replace_NaN
        response[user_id]['skin_contact_finger'] = val_replace_NaN


def load_from_cache(response, user_id, list_resolution, dateTime):


    stop_date = dateTime

    if list_resolution == "minutes":
        list_timedelta_resolution = "MINUTES"
        denominator_convert_seconds = 60  # convert to minute
        start_date = stop_date - datetime.timedelta(
            minutes=settings.list_timedelta[list_timedelta_resolution]
        )
    elif list_resolution == "hourly":
        list_timedelta_resolution = "HOURS"
        denominator_convert_seconds = 60 * 60  # convert to hour
        start_date = stop_date - datetime.timedelta(
            hours=settings.list_timedelta[list_timedelta_resolution]
        )
    elif list_resolution == "daily":
        list_timedelta_resolution = "DAYS"
        denominator_convert_seconds = 60 * 60 * 24  # convert to day
        start_date = stop_date - datetime.timedelta(
            days=settings.list_timedelta[list_timedelta_resolution]
        )

    # start_date_str = convert_datetime_to_str(start_date)
    # stop_date_str = convert_datetime_to_str(stop_date)

    if list_resolution == "minutes":
        metric_minute_cache = MetricMinutesCache.objects.filter(
            user_id=user_id#, datetime_updated__range=[start_date, stop_date]
        ).order_by("datetime_updated")

        queryItems = list(
            metric_minute_cache.values(
                "date_time",
                "datetime_updated",
                "datetime_latest_valid_chest",
                "datetime_latest_valid_finger",
                "rr",
                "rr_dc",
                "bp_sys",
                "last_sync",
                "hr",
                "rr_td",
                "flag",
                "spo2",
                "bp_dia",
                "user_id",
                "flag_notification",
                "skin_temperature",
                "body_temperature",
                "battery",
                "battery_finger",
                "battery_chest",
                "activity",
            )
        )
    elif list_resolution == "hourly":
        metric_hourly_cache = MetricHourlyCache.objects.filter(
            user_id=user_id, datetime_updated__range=[start_date, stop_date]
        ).order_by("datetime_updated")
        queryItems = list(
            metric_hourly_cache.values(
                "datetime_updated",
                "datetime_latest_valid_chest",
                "datetime_latest_valid_finger",
                "rr",
                "rr_dc",
                "bp_sys",
                "last_sync",
                "hr",
                "rr_td",
                "flag",
                "spo2",
                "bp_dia",
                "user_id",
                "flag_notification",
                "skin_temperature",
                "body_temperature",
                "battery",
                "battery_finger",
                "battery_chest",
                "activity",
            )
        )
    else:
        metric_cache = MetricDailyCache.objects.filter(
            user_id=user_id, datetime_updated__range=[start_date, stop_date]
        ).order_by("datetime_updated")
        queryItems = list(
            metric_cache.values(
                "datetime_updated",
                "datetime_latest_valid_chest",
                "datetime_latest_valid_finger",
                "rr",
                "rr_dc",
                "bp_sys",
                "last_sync",
                "hr",
                "rr_td",
                "flag",
                "spo2",
                "bp_dia",
                "user_id",
                "flag_notification",
                "skin_temperature",
                "body_temperature",
                "battery",
                "battery_finger",
                "battery_chest",
                "activity",

            )
        )
    if len(queryItems) > 0:

        newest_entry = queryItems[-1]

        for field, val in {'rr': 'RR', 'rr_dc': 'RR_DC', 'rr_td': 'RR_TD', 'hr': 'HR', 'spo2': 'SpO2', 'bp_sys': 'BP_Sys', 'bp_dia': 'BP_Dia', 'skin_temperature': 'skinTemp', 'body_temperature': 'bodyTemp'}.items():
            newest_entry[val] = newest_entry[field]
            if field not in ['skin_temperature','body_temperature']:
                del newest_entry[field]


        if (newest_entry.get('datetime_updated', 0)):
            del newest_entry['datetime_updated']

        for k, v in newest_entry.items():
            if isinstance(v, Decimal):
                newest_entry[k] = float(v)
            if str(v) == "nan":
                newest_entry[k] = -1

        if newest_entry.get('datetime_latest_valid_chest') is not None:
            dateTime_chest_obj = newest_entry.get(
                'datetime_latest_valid_chest').replace(tzinfo=stop_date.tzinfo)
            if ((stop_date - dateTime_chest_obj).total_seconds()) / denominator_convert_seconds > settings.list_timedelta[list_timedelta_resolution]:
                newest_entry['RR'] = val_replace_NaN

        else:
            newest_entry['RR'] = val_replace_NaN
        if newest_entry.get('datetime_latest_valid_finger') is not None:

            dateTime_finger_obj = newest_entry.get(
                'datetime_latest_valid_finger').replace(tzinfo=stop_date.tzinfo)
            if ((stop_date - dateTime_finger_obj).total_seconds()) / denominator_convert_seconds > settings.list_timedelta[list_timedelta_resolution]:
                newest_entry['HR'] = val_replace_NaN
                newest_entry['SpO2'] = val_replace_NaN
        else:
            newest_entry['HR'] = val_replace_NaN
            newest_entry['SpO2'] = val_replace_NaN


        if newest_entry.get("body_temperature") is not None:
            newest_entry["bodyTemp"] = newest_entry["body_temperature"]
        
        if newest_entry.get("skin_temperature") is not None:
            newest_entry["skinTemp"] = newest_entry["skin_temperature"]


        # apply same cutoff window to temperatures
        temperature_condition = (
            "HR" not in newest_entry or "RR" not in newest_entry
        ) or (
            newest_entry["HR"] == val_replace_NaN
            and newest_entry["RR"] == val_replace_NaN
        )

        if newest_entry.get("skinTemp") is None or temperature_condition:
            newest_entry["skinTemp"] = val_replace_NaN

        if newest_entry.get("bodyTemp") is None or temperature_condition:
            newest_entry["bodyTemp"] = val_replace_NaN

        response[user_id] = newest_entry

    else:
        response[user_id] = {
            'RR': val_replace_NaN,
            'RR_TD':val_replace_NaN,
            'HR': val_replace_NaN,
            'SpO2': val_replace_NaN,
            'BP_Sys': val_replace_NaN,
            'BP_Dia': val_replace_NaN,
            'flag': val_replace_NaN,
            'last_sync': val_replace_NaN,
            'flag_notification': '--',
            'temperature': val_replace_NaN,
            'skinTemp': val_replace_NaN,
            'bodyTemp': val_replace_NaN,
            'battery': val_replace_NaN,
            'battery_chest': val_replace_NaN,
            'battery_finger': val_replace_NaN,
            "activity": val_replace_NaN,

        }


def remove_bad_data(items, bool_keep_bad_data_as_NaN=False, finger_method=2):
    """
    if bool_keep_bad_data_as_NaN==True ; replace bad data row with NaN
    if False ; remove the entire row

    finger_method 1: using accepted_frame_spo2_ratio
    finger_method 2: using accepted_frame_spo2
    """

    cleaned_list = [
        {k: v for k, v in row.items() if not (k in ['hr', 'spo2'] and v is None)}
        for row in items
    ]
    df = pd.DataFrame(cleaned_list)

    # remove bad skin contact from finger data
    try:
        if finger_method == 1:
            signal_validity = (df['dashboard_mode'] == 'RR') | (
                (df['dashboard_mode'] == 'HR') &
                (df['accepted_frame_spo2_ratio'] >= settings.threshold_accepted_frame_spo2_ratio) &
                (df['val_sd_signal_w_sqa'] >= settings.threshold_signal_sd) &
                (df['hr'].notnull()) &
                (df['hr'] != 'nan') &
                (df['hr'] != None) &
                (df['spo2'].notnull()) &
                (df['spo2'] != 'nan') &
                (df['spo2'] != None) &
                (df['sensor_onskin_status'] == 1)
            )
        elif finger_method == 2:
            signal_validity = (df['dashboard_mode'] == 'RR') | (
                (df['dashboard_mode'] == 'HR') &
                (df['accepted_frame_spo2'] >= settings.threshold_accepted_frame_spo2_frame_number) &
                (df['val_sd_signal_w_sqa'] >= settings.threshold_signal_sd) &
                (df['hr'].notnull()) &
                (df['hr'] != 'nan') &
                (df['hr'] != None) &
                (df['spo2'].notnull()) &
                (df['spo2'] != 'nan') &
                (df['spo2'] != None) &
                (df['sensor_onskin_status'] == 1)
            )

        if bool_keep_bad_data_as_NaN:  # replace bad data with NaN

            temp_dateTime = df['date_time'].copy()
            temp_dashboardMode = df['dashboard_mode'].copy()
            temp_battery = df['battery'].copy()
            temp_sensor_onskin_status = df['sensor_onskin_status'].copy()
            temp_display_label = df['display_label'].copy()

            df.loc[~signal_validity, df.columns.difference(
                ['debug_data_length_too_short', 'display_label'])] = np.nan

            df['date_time'] = temp_dateTime
            df['dashboard_mode'] = temp_dashboardMode
            df['battery'] = temp_battery
            df['display_label'] = temp_display_label
            df["sensor_onskin_status"] = temp_sensor_onskin_status

            is_data_shorter_than_threshold = df['debug_data_length_too_short'].apply(
                lambda x: x.get('is_shorter_than_threshold'))

            # Update 'sensor_onskin_status' based on conditions
            # df['sensor_onskin_status'] = np.where((is_data_shorter_than_threshold == 1) & (df['display_label'] == 0), -1,
            #                                       np.where((is_data_shorter_than_threshold == 0) & (df['display_label'] == 0), 0,
            #                                                temp_sensor_onskin_status))
            df['sensor_onskin_status'] = np.where(is_data_shorter_than_threshold == 1, -1, temp_sensor_onskin_status)

        else:  # remove bad data
            df = df[signal_validity]

    except Exception as e:
        logging.error("ERROR (remove bad data - finger): {}".format(e))
        pass



    # remove bad skin contact from chest data
    try:

        signal_validity = (df['dashboard_mode'] == 'HR') | (
            (df['dashboard_mode'] == 'RR') &
            (df['rr'].notnull()) &
            (df['rr'] != 'nan') &
            (df['sensor_onskin_status'] == 1)
        )

        if bool_keep_bad_data_as_NaN:  # replace bad data with NaN
            temp_dateTime = df['date_time'].copy()
            temp_dashboardMode = df['dashboard_mode'].copy()
            temp_battery = df['battery'].copy()
            temp_signal_quality_status = df['signal_quality_status'].copy()
            temp_sensor_onskin_status = df['sensor_onskin_status'].copy()
            temp_display_label = df['display_label'].copy()

            df.loc[~signal_validity, df.columns.difference(
                ['debug_data_length_too_short'])] = np.nan

            df['date_time'] = temp_dateTime
            df['dashboard_mode'] = temp_dashboardMode
            df['battery'] = temp_battery
            df['signal_quality_status'] = temp_signal_quality_status
            df['display_label'] = temp_display_label

            is_data_shorter_than_threshold = df['debug_data_length_too_short'].apply(
                lambda x: x.get('is_shorter_than_threshold'))
            df['sensor_onskin_status'] = np.where(
                is_data_shorter_than_threshold, -1, temp_sensor_onskin_status)
        else:  # remove bad data
            df = df[signal_validity]

    except Exception as e:
        logging.error("ERROR (remove bad data - chest): {}".format(e))
        pass

    output = df.to_dict('records')

    # TODO: Need to implement a similar logic to logic_display_latest_spot_data() as used inside spot query for the filters to be fully complete
    # items = logic_display_latest_spot_data(output_response['history'], items, 3)

    return output


def check_valid_bearer(func):

    def is_valid_bearer(auth_key):
        backend_url = urljoin(settings.backend_url,
                              'api/data-server/verify/user')
        res = requests.get(backend_url, headers=auth_key)
        return res.status_code == requests.codes.ok

    def wrapper(*args, **kwargs):
        try:
            event = args[0]
            auth_key = {
                'Authorization': event['headers']['Authorization']
            }
        except Exception as e:
            message = 'Unable to obtain bearer token'
            logging.error(message)
            return {
                'statusCode': requests.codes.internal_server_error,
                'body': json.dumps({
                    'response': message,
                })
            }

        if is_valid_bearer(auth_key):
            return func(*args, **kwargs)
        else:
            message = 'Client is not authorized to perform this function'
            logging.info(message)
            return {
                'statusCode': requests.codes.unauthorized,
                'body': json.dumps({
                    'response': message,
                })
            }

    return wrapper


def check_valid_server_server_auth(func):

    def is_valid_server_server_auth(auth_key):
        return auth_key == settings.UI_REST_API_HEADER

    def wrapper(*args, **kwargs):
        try:
            event = args[0]
            auth_key = {
                'server-auth-key': event['headers']['server-auth-key']
            }
        except Exception as e:
            message = 'Unable to obtain bearer token'
            logging.error(message)
            return {
                'statusCode': requests.codes.internal_server_error,
                'body': json.dumps({
                    'response': message,
                })
            }

        if is_valid_server_server_auth(auth_key):
            return func(*args, **kwargs)
        else:
            message = 'Client is not authorized to perform this function'
            logging.info(message)
            return {
                'statusCode': requests.codes.unauthorized,
                'body': json.dumps({
                    'response': message,
                })
            }

    return wrapper


def get_utc_offset(utc_offset):
    if utc_offset[0] == '-':  # negative offset
        utc_offset = utc_offset.replace('-', '')  # remove - sign
        utc_offset = utc_offset.split(':')

        utc_offset_hour = -int(utc_offset[0])
        utc_offset_minute = -int(utc_offset[1])
    else:
        utc_offset = utc_offset.replace('+', '')  # remove + sign
        utc_offset = utc_offset.split(':')

        utc_offset_hour = int(utc_offset[0])
        utc_offset_minute = int(utc_offset[1])

    utc_offset = [utc_offset_hour, utc_offset_minute]
    return utc_offset


def convert_decimals_to_floats(obj):
    if isinstance(obj, Decimal):
        return float(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_decimals_to_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_floats(elem) for elem in obj]
    else:
        return obj


def convert_floats_to_decimals(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(elem) for elem in obj]
    else:
        return obj


def filter_data_based_on_quality_status(items, list_status_to_keep, accept_signal_quality_status_nan=True, return_input_if_error=True):

    if accept_signal_quality_status_nan:
        list_status_to_keep = list_status_to_keep + [np.nan, 'nan', None]

    output = []

    if len(items) > 0:
        # convert dict to dataframe
        df = pd.DataFrame(items)

        try:
            # filter data from signal quality
            df = df[df['signal_quality_status'].isin(list_status_to_keep)]
            output = df.to_dict('records')
        except Exception as e:
            logging.error(
                f"error when filter data quality in dataframe. error message is {e}. return input as output")

            if return_input_if_error:
                # if no signal_quality_status, return input as output
                output = df.to_dict('records')

    return output


def remove_hr_from_chest(items):
    """
    remove HR data if sensor is in chest mode
    """
    output = []
    if len(items) > 0:
        df = pd.DataFrame(items)  # convert dict to dataframe
        try:
            # check chest row and set HR as NaN
            df.loc[df['dashboard_mode'] == 'RR', 'hr'] = np.nan
            output = df.to_dict('records')
        except Exception as e:
            logging.error(
                f"error when removing HR from chest data. error message is {e}. return input as output")
            # handle error. if HR is not available in chest data
            output = df.to_dict('records')
    return output


def convert_datetime_to_start_or_end_of_the_day(input_datetime, offset_hour, offset_minute, convert_to, fmt="%Y-%m-%dT%H:%M:%S"):
    """Convert the input datetime string to either start (00:00:00) or end (23:59:59) in the UTC

    Args:
        input_datetime (str): input datetime
        offset_hour (int): utc offset (hour)
        offset_minute (init): utc offset (minute)
        convert_to (str): "start" or "end"
        fmt (str, optional): datetime format. Defaults to "%Y-%m-%dT%H:%M:%S".

    Returns:
        dateime.datetime: datetime output
    """
    output_datetime = (datetime.datetime.strptime(input_datetime, fmt)) + datetime.timedelta(hours=offset_hour, minutes=offset_minute)

    if convert_to == "start":
        output_datetime = output_datetime.replace(hour=0, minute=0, second=0)
    elif convert_to == "end":
        output_datetime = output_datetime.replace(hour=23, minute=59, second=59)

    output_datetime = output_datetime - datetime.timedelta(hours=offset_hour, minutes=offset_minute)
    return output_datetime


def get_patient_timezone(user_id):
    url_GET_patient_utc_offset = urljoin(
        settings.backend_url, settings.UI_URL_REST_API_getPatientDetails
    )

    headers = {
        "accept": "*/*",
        "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
        "Content-Type": "application/json",
    }
    url_resp = requests.get(url_GET_patient_utc_offset, params={"patientIds": user_id}, headers=headers)

    try:
        timezone = url_resp.json()[0]["patient"]["organization"]["timezone"]
        return timezone

    except Exception as e:
        logging.error(e)
        timezone = "UTC"
        return timezone


def remove_processing_records(user_id: str, timestamp: str = None) -> None:
    """
    Removes entries from the DynamoDB processing_in_progress_table for a specific user and data source
    where the 'timestamp' matches the given value.
    Args:
        user_id (str): The user ID whose data needs to be cleaned.
        timestamp (str): The timestamp value to match against.
    Returns:
        None
    """
    data_source = ['sensor', 'health_input', 'other', 'emr']
    date_time_updated = pd.to_datetime(timestamp)
    try:
        for source in data_source:
            filter_dict = {
                "user_id": user_id,
                "data_source": source,
            }
            if date_time_updated is not None:
                filter_dict["timestamp_hourly"] = date_time_updated
            ProcessInProgress.objects.filter(**filter_dict).delete()
            logging.info(f"Deleted ProcessInProgress records of user {user_id} at {date_time_updated} souce {source}")
    except Exception as e:
        logging.error(f"Error while deleting records for '{user_id}' with timestamp '{timestamp}' souce {source} : {e}", exc_info=True)


def insert_to_process_cache(item, source):

    '''insert record to process-in-progress table when new sensor data  or health input comes
    item -> new sensor data  or health input data
    source -> source of data (sensor or health_input or other)
    '''
    try:

        logging.info(f'Received  data {source}. Id is : {item}')

        if source == 'sensor':
            item =  DataProcessing.objects.get(id = item)
            item = vars(item)

        if source == 'other':
            item =  OtherDeviceReading.objects.get(id = item)
            item = vars(item)

        if source == 'emr':
            item =  OtherDeviceReading.objects.get(id = item)
            item = vars(item)

        if source == 'health_input':
            item =  HealthData.objects.get(id = item)
            item = vars(item)

        source_configs = {
            "sensor": {
                "user_id": "user_id",
                "timestamp_server_received": "datetime_server_received",
                "data_source": "sensor",
                "cache_timestamp": "date_time",
            },
            "health_input": {
                "user_id": "user_id",
                "timestamp_server_received": "datetime_received",
                "data_source": "health_input",
                "cache_timestamp": "datetime",
            },
            "other": {
                "user_id": "user_id",
                "timestamp_server_received": "datetime",
                "data_source": "other",
                "cache_timestamp": "datetime",
            },
            "emr": {
                "user_id": "user_id",
                "timestamp_server_received": "datetime",
                "data_source": "emr",
                "cache_timestamp": "datetime",
            },
        }

        current_timestamp = datetime.datetime.now() 
        config = source_configs[source]
        process_item = {}
        process_item["user_id"] = item[config["user_id"]]
        process_item["data_source"] = config["data_source"]
        process_item["timestamp_server_received"] = item[
            config["timestamp_server_received"]
        ]
        process_item["datetime"] = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        timezone = get_patient_timezone(process_item["user_id"])
        timezone_obj = pytz.timezone(timezone)
        now = datetime.datetime.now(timezone_obj)
        utc_offset = now.utcoffset()
        hours = utc_offset.total_seconds() // 3600
        minutes = (abs(utc_offset.seconds) // 60) % 60
        formatted_offset = f"{int(hours):+03}:{int(minutes):02}"
        process_item["utc_offset"] = formatted_offset


        local_datetime = item[config["cache_timestamp"]].astimezone(timezone_obj)
        local_datetime_replaced = local_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        timestamp_daily = local_datetime_replaced.astimezone(pytz.utc)


        local_datetime_replaced = local_datetime.replace(minute=0, second=0, microsecond=0)
        timestamp_hourly = local_datetime_replaced.astimezone(pytz.utc)



        process_item["timestamp_daily"] = timestamp_daily
        process_item["timestamp_hourly"] = timestamp_hourly

        obj = ProcessInProgress.objects.create(**process_item)
        logging.info(f'record inserted to progress table  for patient {process_item["user_id"]} on {str(datetime.datetime.now())}')
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(f"Error in insert_to_process_cache. Error : {err}")
        

def update_device_last_connection(device_id, url_endpoint, auth_key, user_id):
    """
    Update device last connection time with App backend.

    Args:
        device_id (str): Device MAC ID.
        url_endpoint (str): API endpoint URL.
        auth_key (dict): Authorization headers.
        user_id (str, optional): User ID for logging.

    Returns:
        dict: JSON response from the server, or error info.
    """
    payload = {
        "macId": device_id,
        "lastConnectionTime": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    }
    try:
        response = requests.post(url_endpoint, json=payload, headers=auth_key, timeout=10)
        # response.raise_for_status()
        result = response.json()
        logging.info({
            "user_id": user_id,
            "message": "Updated sensor last connection time in the App server",
            "payload": payload,
            "level": "info",
            "status_code": response.status_code,
        })
        return result
    except Exception as e:
        logging.error({
            "user_id": user_id,
            "message": f"Failed to update device last connection: {e}",
            "payload": payload,
            "level": "error",
        })
        return {"error": str(e)}


def get_utc_timenow():
    """get UTC time now

    Returns:
        tuple[datetime, str]: dateand time in datetime format and string
    """
    # Get the current UTC datetime
    utc_now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)

    # Format the UTC datetime as a string
    utc_now_str = convert_datetime_to_str(utc_now)
    return utc_now, utc_now_str




def backend_service_post_request(url: str, payload: dict,):
    """
    Generic POST request wrapper with optional retry support.
    """

    try:
        HEADERS = {
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }

        session = requests.Session()
        retries = Retry(
            total = settings.max_retry,
            backoff_factor = settings.retry_delay_seconds,
            status_forcelist = settings.status_forcelist,
            allowed_methods = ["POST"],
            raise_on_status = False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        logging.info(f"[POST] URL: {url}, Payload: {payload}")
        response = session.post(
            url,
            headers=HEADERS,
            json=payload,
            timeout=settings.max_timeout
        )
        return response.status_code, response.text

    except Exception as e:
        logging.exception(f"[POST] Exception while calling URL: {url}")
        return 500, str(e)


def update_skin_contact_data(latest_item, new_item, latest_datetime):
    """
    Update or initialize the 'latest_skin_contact' field in a data record.

    This function merges the latest skin contact data with previously cached data,
    keeping only recent and valid entries within the defined cache window.
    It also ensures that HR and RR mode data are separately capped to the latest 4 entries each.

    Args:
        new_item (dict): The existing data record to be updated.
        latest_datetime (str): The latest datetime string in "%Y-%m-%d %H:%M:%S" format.
    """
    logging.info(f"Updating skin contact data {new_item} at {latest_datetime}. Incoming data {latest_item}")

    if 'latest_skin_contact' in new_item:
        skin_contact_data = new_item['latest_skin_contact']
        if skin_contact_data == None:
            skin_contact_data = []
        cutoff_time = latest_datetime - timedelta(minutes=settings.skin_contact_cache_window_minutes)

        latest_skin_contact_data = []
        for skin_contact in skin_contact_data:
            try:
                skin_contact_status = int(skin_contact.get("sensor_onskin_status", -1))
                skin_contact_datetime = datetime.datetime.strptime(
                    skin_contact.get("date_time"), "%Y-%m-%d %H:%M:%S"
                )
                if skin_contact_status in (0, 1) and skin_contact_datetime >= cutoff_time:
                    latest_skin_contact_data.append(skin_contact)
            except Exception:
                continue

        new_item['latest_skin_contact'] = latest_skin_contact_data
    else:
        new_item['latest_skin_contact'] = latest_item

    return new_item

def fetch_patient_attributes(user_id, fields=None):

    """
        Fetch patient details from the API and optionally extract specific fields.

        Args:
            user_id (list): The patient userId(s). Can be a single ID or a list of IDs.
            fields (list of str, optional): List of fields to extract from each patient record.
                - If None, the function returns full records.
                - Supports nested keys using dot notation, e.g., "patient.firstName" or "aiSolutionSetting.probabilityThreshold".
                - If a nested field is missing, the value will be set to an empty string "".
                - The result dictionary will use only the **last key** of the dot notation as the key.

        Returns:
            dict: A dictionary keyed by `patientId` (as string), where each value is:
                - A dict of extracted fields if `fields` is provided.
                - The full patient record if `fields` is None.
    """

    def extract_fields(record, fields):
        result = {}
        for field in fields:

            if not isinstance(field, str):
                continue

            keys = field.split(".")
            value = record
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = ""
                    break
            last_key = keys[-1] if keys[-1] else field
            result[last_key] = value
        return result

    PATIENT_DETAILS_GET_URL = urljoin(settings.UI_URL_REST_API_BASE, settings.UI_URL_REST_API_getPatientDetails)
    HEADERS = { 
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }

    url = f"{PATIENT_DETAILS_GET_URL}?patientIds={user_id}" 
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logging.error(f"Failed to fetch patient details: {e}")
        return {}
    
    if not fields:
        return data

    result_dict = {}
    for i in range(len(data)):
        user_key = str(data[i].get("patientId", ""))
        if fields:
            result_dict[user_key] = extract_fields(data[i], fields)
        else:
            result_dict[user_key] = data[i]

    return result_dict
