import numpy as np
import datetime
# import json
import pandas as pd
import logging
# from decimal import Decimal
import data_app.lib_common as common
import data_app.lib_query_data_syncing as lib_query_data_syncing
import math
import pytz
from datetime import timedelta
import sys
import traceback
from dataprocessing import lib_settings as settings
from urllib.parse import urljoin

from data_app.models import DataProcessing, MetricDailyCache, MetricHourlyCache, PatientListCache
from gateway.models import GatewayPings
def cache_table_update(user_id, timestamp, key_data_sync):
    try:

        startDateTime = timestamp

        # Get timezone offset
        timezone = common.get_patient_timezone(user_id)
        offset = datetime.datetime.now(pytz.timezone(timezone)).utcoffset()
        org_time = datetime.datetime.now(pytz.timezone(timezone))
        offset_str = f'{org_time.strftime("%z")[0:3]}:{org_time.strftime("%z")[3:]}'
        sign = 1 if offset_str[0] == '+' else -1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[4:6])
        utc_offset = [sign * hours, sign * minutes]

        # Daily time range
        target_datetime = startDateTime + timedelta(hours=utc_offset[0], minutes=utc_offset[1])
        start_of_day = target_datetime.replace(hour=0, minute=0, second=0)
        end_of_day = target_datetime.replace(hour=23, minute=59, second=59)
        dailystartDateTime = start_of_day - timedelta(hours=utc_offset[0], minutes=utc_offset[1])
        dailystopDateTime = end_of_day - timedelta(hours=utc_offset[0], minutes=utc_offset[1])

        # Align time to start of the hour
        startDateTime = startDateTime.replace(minute=0, second=0)
        stopDateTime = (startDateTime + datetime.timedelta(hours=1)).replace(minute=0, second=0)
        
        # Compute data lengths
        hourly_data_length = math.ceil((stopDateTime - startDateTime).total_seconds() / 3600)
        daily_data_length = (dailystopDateTime - dailystartDateTime).days + 1
        
        # Update sync compliance
        update_sync_compliance(user_id, startDateTime, stopDateTime, hourly_data_length, "hourly", key_data_sync, utc_offset, offset_str)
        update_sync_compliance(user_id, dailystartDateTime, dailystopDateTime, daily_data_length, "daily", key_data_sync, utc_offset, offset_str)
    
    except Exception as e:
        logging.error(f'Error updating cache table: {str(e)}')
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(err)
        

def update_sync_compliance(userID, startDateTime, stopDateTime, data_length, resolution, key_dataSync, utc_offset, offset_str):

    key_recordReceivedByGateway = 'record_received_by_gateway'
    key_dashboardMode = 'dashboard_mode'
    key_dateTimeServerReceived='datetime_server_received'
    """
    need to sort by gateway datetime
    """
    df_selected = []

    if key_dataSync == 'datetime_sensor':
        queryItems = DataProcessing.objects.filter(user_id = userID,datetime_sensor__range = (startDateTime,stopDateTime)).values()
    if  key_dataSync == 'datetime_gateway_sent':
        queryItems = DataProcessing.objects.filter(user_id = userID,datetime_gateway_sent__range = (startDateTime,stopDateTime)).values()


    queryItemsSensorDuration = DataProcessing.objects.filter(user_id = userID,datetime_server_received__range = (startDateTime,stopDateTime)).values()

    queryItemsGateway = GatewayPings.objects.filter(user_id = userID,ping_timestamp__range = (startDateTime,stopDateTime)).values()

    output = {}
   
 
    #online duration of gateway
    if len(queryItemsGateway) > 0:
        ## Convert item to DataFrame
        df = pd.DataFrame(queryItemsGateway)

        df_selected = df.sort_values('ping_timestamp', ascending=True).drop_duplicates(subset=['ping_timestamp'],keep='last') # remove duplicates
        if key_dataSync == 'datetime_sensor':
            df_selected['ping_timestamp'] = pd.to_datetime(df_selected['ping_timestamp']).dt.tz_localize(None)
        listTimeOutput = []

        #hourly
        if resolution=='hourly':
            for i in range(0, data_length):
                tempDateTime = startDateTime + datetime.timedelta(hours=i)
                listTimeOutput.append(tempDateTime)
        #daily
        if resolution=='daily':
            for i in range(data_length, 0, -1):
                offset = datetime.timedelta(hours=utc_offset[0], minutes=utc_offset[1])
                tempDateTime = (stopDateTime + offset).replace(hour=0, minute=0, second=0) - datetime.timedelta(days=i - 1)
                tempDateTime = tempDateTime - offset
                listTimeOutput.append(tempDateTime)
        
        listTimeOutput = listTimeOutput+[stopDateTime]
        list_datetime = np.array([])
        list_recordReceivedByGateway_to_duration_hrs = np.array([])
        list_recordReceivedByGateway_to_duration_hrs_rr = np.array([])
        list_recordReceivedByGateway_to_duration_hrs_hr = np.array([])       
        list_minutesGatewayReceived = np.array([])
        
        for i in range(1, len(listTimeOutput)):
            timeLowerDateTime = listTimeOutput[i-1]
            timeUpperDateTime = listTimeOutput[i]
            timeLower = str(timeLowerDateTime)
            timeUpper = str(timeUpperDateTime)
            
            # df_selected_filtered = df_selected[(df_selected['ping_timestamp'] >= timeLowerDateTime.isoformat()[:-3]+'Z') & (df_selected['ping_timestamp'] < timeUpperDateTime.isoformat()[:-3]+'Z')]
            df_selected_filtered = df_selected[(df_selected['ping_timestamp'] >= timeLowerDateTime) & (df_selected['ping_timestamp'] < timeUpperDateTime)]
         
            dateTimeGatewayDateObjList=np.array([])
            gateway_online = 0
            dateTimeGatewayReceivedList = df_selected_filtered['ping_timestamp'].tolist()
          
            for j in range(0, len(dateTimeGatewayReceivedList)):
                # date_object = datetime.datetime.strptime(dateTimeGatewayReceivedList[j], "%Y-%m-%dT%H:%M:%S.%fZ")
                # dateTimeGatewayDateObjList = np.append(dateTimeGatewayDateObjList, date_object)
                dateTimeGatewayDateObjList = np.append(dateTimeGatewayDateObjList, dateTimeGatewayReceivedList[j])
          
            for m in range(len(dateTimeGatewayDateObjList)-1, -1, -1):
                if(len(dateTimeGatewayDateObjList)!=0):
                    diff = dateTimeGatewayDateObjList[m] - dateTimeGatewayDateObjList[m-1]
                    diff_min = (abs(diff).total_seconds())/60
            
                    if(diff_min <= 10):
                        gateway_online += diff_min
                    else:
                        gateway_online += 5
                #only one data point
                else:
                    gateway_online+=5

            """
            save timestamp
            convert daily datetime to local date
            """
            timeLowerDateTime = listTimeOutput[i-1]
            timeUpperDateTime = listTimeOutput[i]
            
            if resolution == 'daily':
                timeLower = str(timeLowerDateTime)
                timeUpper = str(timeUpperDateTime)

            elif resolution == 'hourly':
                timeLower = timeLower.split(':')[0]
                timeUpper = timeUpper.split(':')[0]
                timeLower = timeLower + ':00:00'
                timeUpper = timeUpper + ':00:00'

            # list_datetime = np.append(list_datetime, timeLower)
            list_datetime = np.append(list_datetime, timeLowerDateTime)
            dateTimeGatewayReceivedList.extend(df_selected_filtered['ping_timestamp'].tolist())
            list_minutesGatewayReceived = np.append(list_minutesGatewayReceived, gateway_online)
    
        recordDateMinuteGateway = list_minutesGatewayReceived.tolist()
        recordDateHourGateway = [a/60 for a in recordDateMinuteGateway]
        
        if resolution == 'hourly':
            output['listtime'] = list_datetime.tolist()
            output['listtimehr']  = list_datetime.tolist()
        elif resolution == 'daily':
            output['listdate'] = list_datetime.tolist()
            
        output['recordDateHourGateway'] = recordDateHourGateway
     
    #online duration of sensor
    if len(queryItemsSensorDuration) > 0:

        #finger (two sensor mode)
        rr_items = [d for d in queryItemsSensorDuration if d.get("dashboard_mode") == "RR"]       
        rr_items = sorted(rr_items, key=lambda x: x[key_dateTimeServerReceived])   
        list_minutes_rr = lib_query_data_syncing.calculate_sensor_duration(rr_items, key_dataSync, key_recordReceivedByGateway, key_dashboardMode, df_selected, key_dateTimeServerReceived, data_length, startDateTime, stopDateTime, resolution, utc_offset)
        list_minutes_rr = list_minutes_rr.tolist()
        list_hour_rr = [a/60 for a in list_minutes_rr]

        #chest (two sensor mode)
        hr_items = [d for d in queryItemsSensorDuration if d.get("dashboard_mode") == "HR"]      
        hr_items = sorted(hr_items, key=lambda x: x[key_dateTimeServerReceived])                             
        list_minutes_hr = lib_query_data_syncing.calculate_sensor_duration(hr_items, key_dataSync, key_recordReceivedByGateway, key_dashboardMode, df_selected, key_dateTimeServerReceived, data_length, startDateTime, stopDateTime, resolution, utc_offset)        
        list_minutes_hr = list_minutes_hr.tolist()
        list_hour_hr = [a/60 for a in list_minutes_hr]

        #all or one sensor mode
        list_minutes_all = lib_query_data_syncing.calculate_sensor_duration(queryItemsSensorDuration, key_dataSync, 
        key_recordReceivedByGateway, key_dashboardMode, df_selected, key_dateTimeServerReceived, data_length, startDateTime, stopDateTime, resolution, utc_offset)        
        list_minutes_all = list_minutes_all.tolist()     
        list_hour_all = [a/60 for a in list_minutes_all]           

        output['recordDateHourServer'] = list_hour_all
        output['recordDateHourServerRR'] = list_hour_rr
        output['recordDateHourServerHR'] = list_hour_hr
        
    #data collection
    if len(queryItems) > 0:
      
        ## Convert item to DataFrame
        df = pd.DataFrame(queryItems)

        df = df.sort_values('date_time', ascending=True).drop_duplicates(subset=['date_time'],keep='last') # remove duplicates
        try:
            df_selected = df[[key_dataSync, key_recordReceivedByGateway, key_dashboardMode, key_dateTimeServerReceived]]
            df_selected['duration_hrs'] = 0.0
            df_selected['duration_hrs_hr'] = 0.0
            df_selected['duration_hrs_rr'] = 0.0
            df_selected.loc[df_selected[key_dashboardMode] == 'RR', 'duration_hrs'] = df_selected.loc[df_selected[key_dashboardMode] == 'RR', key_recordReceivedByGateway].astype(float)*(0.06/60/60)
            df_selected.loc[df_selected[key_dashboardMode] == 'HR', 'duration_hrs'] = df_selected.loc[df_selected[key_dashboardMode] == 'HR', key_recordReceivedByGateway].astype(float)*(0.04/60/60)
            df_selected.loc[df_selected[key_dashboardMode] == 'HR', 'duration_hrs_hr'] = df_selected.loc[df_selected[key_dashboardMode] == 'HR', key_recordReceivedByGateway].astype(float)*(0.04/60/60)
            df_selected.loc[df_selected[key_dashboardMode] == 'RR', 'duration_hrs_rr'] = df_selected.loc[df_selected[key_dashboardMode] == 'RR', key_recordReceivedByGateway].astype(float)*(0.06/60/60)
            logging.info('userID {} found {} items between [{}] and [{}]'.format(userID, len(queryItems), str(startDateTime), str(stopDateTime)))

            listTimeOutput = []
            #hourly
            if resolution=='hourly':
                for i in range(0, data_length):
                    tempDateTime = startDateTime + datetime.timedelta(hours=i)
                    listTimeOutput.append(tempDateTime)
    
            #daily
            if resolution=='daily':
                for i in range(data_length, 0, -1):
                    offset = datetime.timedelta(hours=utc_offset[0], minutes=utc_offset[1])
                    tempDateTime = (stopDateTime + offset).replace(hour=0, minute=0, second=0) - datetime.timedelta(days=i - 1)
                    tempDateTime = tempDateTime - offset
                    listTimeOutput.append(tempDateTime)
            
            listTimeOutput = listTimeOutput+[stopDateTime]
            list_datetime = np.array([])
            list_recordReceivedByGateway_to_duration_hrs = np.array([])
            list_recordReceivedByGateway_to_duration_hrs_rr = np.array([])
            list_recordReceivedByGateway_to_duration_hrs_hr = np.array([])
        
            for i in range(1, len(listTimeOutput)):
       
                timeLowerDateTime = listTimeOutput[i-1]
                timeUpperDateTime = listTimeOutput[i]    
                timeLower = str(timeLowerDateTime)
                timeUpper = str(timeUpperDateTime)
          
                df_selected_filtered = df_selected[(df_selected[key_dataSync] >= timeLower) & (df_selected[key_dataSync] < timeUpper)]
                df_selected_filtered_hr =  df_selected[(df_selected[key_dataSync] >= timeLower) & (df_selected[key_dataSync] < timeUpper) & (df_selected[key_dashboardMode]=='HR')]
                df_selected_filtered_rr = df_selected[(df_selected[key_dataSync] >= timeLower) & (df_selected[key_dataSync] < timeUpper) & (df_selected[key_dashboardMode]=='RR')]
                recordReceivedByGateway_to_duration_hrs = df_selected_filtered['duration_hrs'].sum()
                recordReceivedByGateway_to_duration_hrs_hr = df_selected_filtered_hr['duration_hrs_hr'].sum()
                recordReceivedByGateway_to_duration_hrs_rr = df_selected_filtered_rr['duration_hrs_rr'].sum()
                
                """
                save timestamp
                convert daily datetime to local date
                """
                if resolution=='daily':                   
                    timeLower = str(timeLowerDateTime)
                    timeUpper = str(timeUpperDateTime)
    
                elif resolution=='hourly':
                    timeLower = timeLower.split(':')[0]
                    timeUpper = timeUpper.split(':')[0] 
                    timeLower = timeLower + ":00:00"
                    timeUpper = timeUpper + ":00:00"
                
                # list_datetime = np.append(list_datetime, timeLower)
                list_datetime = np.append(list_datetime, timeLowerDateTime)
                list_recordReceivedByGateway_to_duration_hrs = np.append(list_recordReceivedByGateway_to_duration_hrs, recordReceivedByGateway_to_duration_hrs)
                list_recordReceivedByGateway_to_duration_hrs_hr = np.append(list_recordReceivedByGateway_to_duration_hrs_hr, recordReceivedByGateway_to_duration_hrs_hr)
                list_recordReceivedByGateway_to_duration_hrs_rr = np.append(list_recordReceivedByGateway_to_duration_hrs_rr, recordReceivedByGateway_to_duration_hrs_rr)
             
            if resolution == 'hourly':
                output['listtime'] = list_datetime.tolist()
            elif resolution == 'daily':
                output['listdate'] = list_datetime.tolist()
            
            output['recordReceivedByGateway_to_duration_hrs'] = list_recordReceivedByGateway_to_duration_hrs.tolist()
            output['recordReceivedByGateway_to_duration_hrs_finger'] = list_recordReceivedByGateway_to_duration_hrs_hr.tolist()
            output['recordReceivedByGateway_to_duration_hrs_chest'] = list_recordReceivedByGateway_to_duration_hrs_rr.tolist()
        
        except KeyError:
            pass
      


    # Create or Update metric cache
    if len(output) > 0:

        if resolution == "hourly":
            cache_table = MetricHourlyCache
            key = "listtime"
        else:
            cache_table = MetricDailyCache
            key = "listdate"

        output['datetime_local'] = [dt + timedelta(hours=utc_offset[0], minutes=utc_offset[1]) for dt in output[key]]
        output['utc_offset'] = [offset_str] * len(output[key])

        # output_updated = common.convert_floats_to_decimals(output)
        for index, value in enumerate(output[key]):
            output_entry = {
                "user_id": userID,
                key: value,
                "datetime_updated": value,
                "datetime_local" : output["datetime_local"][index],
                "utc_offset" : output["utc_offset"][index],
            }
            if len(queryItemsGateway) > 0:
                if resolution == "hourly":
                    output_entry["listtimehr"] = output["listtimehr"][index]
                if output["recordDateHourGateway"][index] != 0:
                    output_entry["recordDateHourGateway"] = output["recordDateHourGateway"][index]
            if len(queryItemsSensorDuration) > 0:
                if output["recordDateHourServer"][index] != 0:
                    output_entry["recordDateHourServer"] = output["recordDateHourServer"][index]
                if output["recordDateHourServerRR"][index] != 0:
                    output_entry["recordDateHourServerRR"] = output["recordDateHourServerRR"][index]
                if output["recordDateHourServerHR"][index] != 0:
                    output_entry["recordDateHourServerHR"] = output["recordDateHourServerHR"][index]
            if len(queryItems) > 0:
                if output["recordReceivedByGateway_to_duration_hrs"][index] != 0:
                    output_entry["recordReceivedByGateway_to_duration_hrs"] = output["recordReceivedByGateway_to_duration_hrs"][index]
                if output["recordReceivedByGateway_to_duration_hrs_finger"][index] != 0:
                    output_entry["recordReceivedByGateway_to_duration_hrs_finger"] = output["recordReceivedByGateway_to_duration_hrs_finger"][index]
                if output["recordReceivedByGateway_to_duration_hrs_chest"][index] != 0:
                    output_entry["recordReceivedByGateway_to_duration_hrs_chest"] = output["recordReceivedByGateway_to_duration_hrs_chest"][index]

            if resolution == 'daily':
                try:
                    latest_record = cache_table.objects.filter(user_id=userID).order_by('-datetime_updated').first()
                    if latest_record:
                        latest_utc_offset = latest_record.utc_offset
                        incoming_utc_offset = output_entry.get("utc_offset")
                        latest_local_time = latest_record.datetime_local
                        incoming_local_time = output_entry.get("datetime_local")
                        logging.info(f"latest_utc_offset {latest_utc_offset}, incoming_utc_offset {incoming_utc_offset}, latest_local_time {latest_local_time}, incoming_local_time {incoming_local_time}") 
                        if latest_utc_offset != incoming_utc_offset and latest_local_time == incoming_local_time:
                            remove_key_dict = {
                                "user_id": latest_record.user_id,
                                "datetime_updated": latest_record.datetime_updated,
                            }
                            cache_table.objects.filter(**remove_key_dict).delete()
                            logging.info(f"Entry existing for same date, Removing to avoid duplication. {remove_key_dict}")
                except Exception as e:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    err = "\n".join(traceback.format_exception(*sys.exc_info()))
                    logging.error(f"Error while checking and removing duplicate entries: {err}")

            cache_records = cache_table.objects.filter(user_id = userID, datetime_updated = value)
            if cache_records.exists():
                cache_records.update(**output_entry)
            else:
                try:
                    cache_table.objects.create(**output_entry)
                except Exception as e:
                    logging.error(f'Error creating cache table record: {str(e)}')

            if resolution=='daily': 

                data_sync_cache_limit = 2
                cache_end_datetime = value
                cache_start_datetime = value - timedelta(days=data_sync_cache_limit)
                logging.info(f"cache_start_datetime =  {cache_start_datetime} &  cache_end_datetime = {cache_end_datetime}")
                response = cache_table.objects.filter(user_id = userID,datetime_updated__range =(cache_start_datetime,cache_end_datetime)).order_by('datetime_updated').values('listdate','recordReceivedByGateway_to_duration_hrs_finger','recordReceivedByGateway_to_duration_hrs_chest','datetime_local')

                new_data_sync_list = []

                for item in response:
                    new_data_sync_dict = {}
                    if 'recordReceivedByGateway_to_duration_hrs_chest' in item:
                        new_data_sync_dict['amount_data_in_hrs_chest'] = item['recordReceivedByGateway_to_duration_hrs_chest']
                    if 'recordReceivedByGateway_to_duration_hrs_finger' in item:
                        new_data_sync_dict['amount_data_in_hrs_finger'] = item['recordReceivedByGateway_to_duration_hrs_finger']
                    if 'datetime_local' in item:
                        new_data_sync_dict['timestamp'] = item['datetime_local'].strftime("%Y-%m-%d")
                    if new_data_sync_dict:
                        new_data_sync_list.append(new_data_sync_dict)

                PatientListCache.objects.filter(user_id = userID).update(data_sync = new_data_sync_list)


                # sending the data upload data to BE master cache
                try:

                    backend_master_cache_keys = ["timestamp",
                            "amount_data_in_hrs_chest",
                            "amount_data_in_hrs_finger"]
                    master_cache_data = {k: [d.get(k) for d in new_data_sync_list] for k in backend_master_cache_keys}

                    data = {
                        "timestamp": master_cache_data['timestamp'],
                        "amountDataInHrsChest": master_cache_data['amount_data_in_hrs_chest'],
                        "amountDataInHrsFinger": master_cache_data['amount_data_in_hrs_finger']
                    }
                    payload = {
                        "data": [
                            {
                                "userId": int(userID),
                                "source": settings.datasource_to_payload_mapping.get("sensor"),
                                "data_collection" : data
                            }
                        ]
                    }

                    mastercache_post_url = urljoin(
                        settings.backend_url, settings.UI_URL_REST_API_MASTER_CACHE
                    )
                    status_code, message = common.backend_service_post_request(mastercache_post_url, payload)
                    if status_code in range(200, 300):
                        logging.info(f"Master cache API called from compliance is success. User ID =  {userID}. Response = {message} Payload = {payload}")
                    else:
                        logging.info(f"Master cache API called from compliance is failed. User ID =  {userID}. Response = {message} Payload = {payload}")
                except Exception as e:
                    logging.error(f"Error while preparing payload for Master Cache update for user {userID}. Error: {str(e)}")

    return output
