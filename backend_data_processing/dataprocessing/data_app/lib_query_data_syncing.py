import numpy as np
import datetime
import pandas as pd
from dataprocessing import lib_settings as settings
from data_app.models import *
from data_app import lib_common as common
# import logging
replace_empty_val = 0

def calculate_sensor_duration(queryItemsSensorDuration,key_dataSync,  key_recordReceivedByGateway,key_dashboardMode,  df_selected, key_dateTimeServerReceived, data_length, startDateTime, stopDateTime, resolution, utc_offset):
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
        ## Convert item to DataFrame
        df = pd.DataFrame(queryItemsSensorDuration)
        if not df.empty:
            df = df.sort_values('date_time', ascending=True).drop_duplicates(subset=['date_time'],keep='last')

        required_keys = [key_dataSync, key_recordReceivedByGateway, key_dashboardMode, key_dateTimeServerReceived]
        
        if all(key in df.columns for key in required_keys):
            df_selected = df[required_keys]        
            list_datetime = np.array([])
            list_minutesServerReceived = np.array([])    
            for i in range(1, len(listTimeOutput)):
                timeLowerDateTime = listTimeOutput[i-1]
                timeUpperDateTime = listTimeOutput[i]

                timeLower = str(timeLowerDateTime)
                timeUpper = str(timeUpperDateTime)
        
                df_selected_filtered = df_selected[(df_selected[key_dateTimeServerReceived] >= timeLower) & (df_selected[key_dateTimeServerReceived] < timeUpper)]    
                dateTimeServerReceivedList = df_selected[(df_selected[key_dateTimeServerReceived] >= timeLower) & (df_selected[key_dateTimeServerReceived] < timeUpper)]
                dateTimeServerDateObjList=np.array([])
                sensor_online = 0
                dateTimeServerReceivedList = dateTimeServerReceivedList[key_dateTimeServerReceived].tolist()

                for j in range(0, len(dateTimeServerReceivedList)):
                    # date_object = dateTimeServerReceivedList[j]
                    # date_object = dateTimeServerReceivedList[j].to_pydatetime()
                    date_object = datetime.datetime.strptime(dateTimeServerReceivedList[j], "%Y-%m-%d %H:%M:%S")
                    dateTimeServerDateObjList = np.append(dateTimeServerDateObjList, date_object)
                
                for m in range(len(dateTimeServerDateObjList)-1, -1, -1):
                    if(len(dateTimeServerDateObjList)!=0):
                        diff = dateTimeServerDateObjList[m] - dateTimeServerDateObjList[m-1]
                        diff_min = (abs(diff).total_seconds())/60
                        if(diff_min <= 10 and dateTimeServerDateObjList[m-1] != dateTimeServerDateObjList[m]): 
                            sensor_online += diff_min
                        else:
                            sensor_online += 5
                    #only one data point
                    else:
                        sensor_online+=5

                """
                save timestamp
                convert daily datetime to local date
                """
                if resolution=='daily':
                    
                    timeLowerConverted = timeLowerDateTime + datetime.timedelta(hours=utc_offset[0]) + datetime.timedelta(minutes=utc_offset[1])
                    timeUpperConverted = timeUpperDateTime + datetime.timedelta(hours=utc_offset[0]) + datetime.timedelta(minutes=utc_offset[1])

                    timeLower = str(timeLowerConverted)
                    timeUpper = str(timeUpperConverted)

                    timeLower = timeLower.split(' ')[0]
                    timeUpper = timeUpper.split(' ')[0]

                elif resolution=='hourly':
                    
                    timeLower = timeLower.split(':')[0]
                    timeUpper = timeUpper.split(':')[0]

                    timeLower = timeLower + ":00:00"
                    timeUpper = timeUpper + ":00:00"
                

                list_datetime = np.append(list_datetime, timeLower)
                dateTimeServerReceivedList.extend(df_selected_filtered[key_dateTimeServerReceived].tolist())
                list_minutesServerReceived = np.append(list_minutesServerReceived, sensor_online)
            return list_minutesServerReceived

        else:
            list_minutesServerReceived = np.array([0] * len(listTimeOutput))
            return list_minutesServerReceived


def get_data_syncing_trends(
    userID, startDateTime, stopDateTime, resolution, utc_offset, fmt="%Y-%m-%d %H:%M:%S"
):

    if resolution == "daily":
        timestamp_field = "listdate"
        startDateTime = common.convert_datetime_to_start_or_end_of_the_day(startDateTime.strftime("%Y-%m-%d %H:%M:%S"), utc_offset[0], utc_offset[1], "start", fmt)
        stopDateTime = common.convert_datetime_to_start_or_end_of_the_day(stopDateTime.strftime("%Y-%m-%d %H:%M:%S"), utc_offset[0], utc_offset[1], "end", fmt)

        query_set = MetricDailyCache.objects.filter(user_id = userID, datetime_updated__range = (startDateTime,stopDateTime)).values('recordDateHourServer', 'recordDateHourServerRR', 'recordDateHourServerHR', 'recordDateHourGateway', 'recordReceivedByGateway_to_duration_hrs', 'recordReceivedByGateway_to_duration_hrs_finger', 'recordReceivedByGateway_to_duration_hrs_chest','listdate')
    else:
        startDateTime = startDateTime + datetime.timedelta(minutes=0, seconds=0)
        query_set = MetricHourlyCache.objects.filter(user_id = userID, datetime_updated__range = (startDateTime,stopDateTime)).values('recordDateHourServer', 'recordDateHourServerRR', 'recordDateHourServerHR', 'recordDateHourGateway', 'recordReceivedByGateway_to_duration_hrs', 'recordReceivedByGateway_to_duration_hrs_finger', 'recordReceivedByGateway_to_duration_hrs_chest','listtime','listtimehr')

    output_data = pd.DataFrame(query_set)
    if (len(output_data) > 0) and (resolution == 'hourly'):
        output_data['listtime'] = output_data['listtime'].dt.strftime('%Y-%m-%d %H:%M:%S')
        output_data['listtimehr'] = output_data['listtime']

    output_data = output_data.fillna(replace_empty_val)

    if (len(output_data) > 0) and (resolution == 'daily'):
        output_data["listdate"] = pd.to_datetime(output_data["listdate"], errors="coerce")
        date_range = pd.date_range(output_data["listdate"].min(), output_data["listdate"].max(), freq='D')
        output_data = output_data[output_data["listdate"].isin(date_range)]     
        offset = datetime.timedelta(hours=utc_offset[0], minutes=utc_offset[1])
        output_data[timestamp_field] = pd.to_datetime(output_data[timestamp_field])  + offset
        output_data[timestamp_field] = output_data[timestamp_field].dt.strftime("%Y-%m-%d")

    output_df = output_data.to_dict(orient="list")

    return output_df


def get_data_syncing_trends_list(
    listOfIds, startDateTime, stopDateTime, resolution, utc_offset, fmt="%Y-%m-%d %H:%M:%S"
):
    output_list_ids = []
    if resolution == "daily":
        timestamp_field = "listdate"
        startDateTime = common.convert_datetime_to_start_or_end_of_the_day(startDateTime.strftime("%Y-%m-%d %H:%M:%S"), utc_offset[0], utc_offset[1], "start", fmt)
        stopDateTime = common.convert_datetime_to_start_or_end_of_the_day(stopDateTime.strftime("%Y-%m-%d %H:%M:%S"), utc_offset[0], utc_offset[1], "end", fmt)
    else:
        startDateTime = startDateTime + datetime.timedelta(minutes=0, seconds=0)


    for userID in listOfIds:

        if resolution == "daily":
            query_set = MetricDailyCache.objects.filter(user_id = userID, datetime_updated__range = (startDateTime,stopDateTime)).values('recordDateHourServer', 'recordDateHourServerRR', 'recordDateHourServerHR', 'recordDateHourGateway', 'recordReceivedByGateway_to_duration_hrs', 'recordReceivedByGateway_to_duration_hrs_finger', 'recordReceivedByGateway_to_duration_hrs_chest','listdate')
        else:
            query_set = MetricHourlyCache.objects.filter(user_id = userID, datetime_updated__range = (startDateTime,stopDateTime)).values('recordDateHourServer', 'recordDateHourServerRR', 'recordDateHourServerHR', 'recordDateHourGateway', 'recordReceivedByGateway_to_duration_hrs', 'recordReceivedByGateway_to_duration_hrs_finger', 'recordReceivedByGateway_to_duration_hrs_chest','listtime','listtimehr')

        output_data = pd.DataFrame(query_set)
        if (len(output_data) > 0) and (resolution == 'hourly'):
            output_data['listtime'] = output_data['listtime'].dt.strftime('%Y-%m-%d %H:%M:%S')
            output_data['listtimehr'] = output_data['listtime']


        output_data = output_data.fillna(replace_empty_val)

        if (len(output_data) > 0) and (resolution == 'daily'):
            output_data["listdate"] = pd.to_datetime(output_data["listdate"], errors="coerce")
            date_range = pd.date_range(output_data["listdate"].min(), output_data["listdate"].max(), freq='D')
            output_data = output_data[output_data["listdate"].isin(date_range)]     
            offset = datetime.timedelta(hours=utc_offset[0], minutes=utc_offset[1])
            output_data[timestamp_field] = pd.to_datetime(output_data[timestamp_field])  + offset
            output_data[timestamp_field] = output_data[timestamp_field].dt.strftime("%Y-%m-%d")

        output_df = output_data.to_dict(orient="list")
        if len(output_df) > 0:
            output_df["id"] = userID
            output_list_ids.append(output_df)

    return output_list_ids
