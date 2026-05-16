import numpy as np
import datetime
from datetime import timezone, timedelta
import pandas as pd
import logging
import pytz
import requests
import sys
import traceback
import re

from urllib.parse import urljoin
from requests.adapters import HTTPAdapter, Retry

from django.db.models import Q
from .helpers import get_utc_offset, convert_small_to_caps, get_patient_timezone
from .lib_common import (
    get_devices_data_multiple,
    load_from_cache,
    get_other_spot_data,
    remove_bad_data,
    convert_datetime_to_start_or_end_of_the_day,
)
from .models import (
    DataProcessing,
    HealthData,
    SpotCache,
    MetricDailyCache,
    MetricMinutesCache,
    MetricHourlyCache,
    OtherDeviceReading,
    Staging,
    PatientListCache,
    PatientDetail,
    StagingHourlyCache
)
from .lib_query import (
    EarlyWarningScore,
    generate_dummy,
    get_spot_data,
    convert_spot_table_to_string,
    get_spot_data_from_cache_v2,
    query_health_input,
    cal_data_length,
    get_trends,
    handle_spot_trend_query,
    generate_dummy_mgh_data,
    generate_demo_data,
    get_user_metrics,
    display_battery,
    query_observations_data_input,
)
from .serializers import (
    CachePatientListSerializer
)
from dataprocessing import lib_settings as settings
from data_app.staging_hourly import compute_news_score as compute_news_score_staging_hourly
from data_app.staging_hourly import remove_processing_records_from_df

PATIENT_PREDICTION_SCORE_URL = urljoin(
    settings.AI_BACKEND_URL, settings.UI_URL_REST_API_getPredictionScore
)

HEADERS = {
    "accept": "*/*",
    "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
    "Content-Type": "application/json",
}

def handle_spot_query(user_id, date_time):
    stop_date_time = date_time
    start_date_time = stop_date_time - datetime.timedelta(
        minutes=settings.spot_lookback_window
    )
    val_replace_NaN = settings.val_replace_NaN
    list_demo_id = settings.list_demo_id

    if user_id in list_demo_id:
        return generate_dummy("spot")
    else:
        response = get_spot_data(
            DataProcessing.objects,
            user_id,
            str(start_date_time),
            str(stop_date_time),
            val_replace_NaN,
        )

    return convert_spot_table_to_string(response)


def handle_spot_query_via_cache(user_id, date_time):
    if int(user_id) in settings.list_demo_id:
        response = generate_dummy("spot")
    elif int(user_id) in settings.list_demo_id_data_from_db:
        response = handle_spot_query(user_id, date_time)
    else:
        response = get_spot_data_from_cache_v2(user_id, SpotCache.objects)

    display_battery(response,'spot',None)

    # get health input data to latest spot
    val_nan = settings.val_replace_NaN

    response["latest"]["is_manual_submission_rr"] = 0
    response["latest"]["is_manual_submission_hr"] = 0
    response["latest"]["is_manual_submission_spo2"] = 0
    response["latest"]["is_manual_submission_body_temp"] = 0
    response["latest"]["is_manual_submission_bp_sys"] = 0
    response["latest"]["is_manual_submission_bp_dia"] = 0

    response["latest"]["BP_Sys"] = val_nan
    response["latest"]["BP_Dia"] = val_nan

    if "last_connection_chest" not in response["latest"]:
        response["latest"]["last_connection_chest"] = val_nan

    if "last_connection_finger" not in response["latest"]:
        response["latest"]["last_connection_finger"] = val_nan

    response["latest"]["timestamp_rr"] = response["latest"]["last_connection_chest"]
    response["latest"]["timestamp_hr"] = response["latest"]["last_connection_finger"]
    response["latest"]["timestamp_spo2"] = response["latest"]["last_connection_finger"]
    response["latest"]["timestamp_body_temperature"] = response["latest"][
        "last_connection_chest"
    ]
    response["latest"]["timestamp_bp_sys"] = val_nan
    response["latest"]["timestamp_bp_dia"] = val_nan

    latest_spot = response["latest"].copy()

    def search_latest_health_input(df, key):

        # filter the df where value is not -1 (nan)
        df_filtered = df[df[key] != -1]

        # sort by 'listtime' in descending order to get the latest entry
        df_filtered_sorted = df_filtered.sort_values(by="listtime", ascending=False)

        # select the first row (latest 'listtime' where value is not -1 (nan))
        if not (df_filtered_sorted.empty):
            latest_record = df_filtered_sorted.iloc[0]
        else:
            latest_record = df_filtered_sorted
        return latest_record

    def __compare_and_update_latest_spot_with_manual_health_input(
        df,
        df_key_vital,
        df_key_timestamp,
        latest_spot,
        latest_spot_key_vital,
        latest_spot_key_timestamp,
        latest_spot_key_is_manual_submission,
        latest_spot_key_timestamp_to_update,
    ):
        latest_record = search_latest_health_input(df, df_key_vital)
        if not (latest_record.empty):
            if (latest_spot[latest_spot_key_vital] == val_nan) or ( latest_spot[latest_spot_key_timestamp] != val_nan and
                datetime.datetime.strptime(
                    latest_spot[latest_spot_key_timestamp], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                < datetime.datetime.strptime(
                    latest_record[df_key_timestamp], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
            ):  # no RR from sensor
                latest_spot[latest_spot_key_vital] = latest_record[df_key_vital]

                latest_spot[latest_spot_key_is_manual_submission] = 1
                latest_spot[latest_spot_key_timestamp_to_update] = latest_record[
                    df_key_timestamp
                ]
            else:
                if latest_spot[latest_spot_key_timestamp] != val_nan:
                    latest_spot[latest_spot_key_timestamp_to_update] = (
                        latest_spot[latest_spot_key_timestamp]
                    )
    def __update_latest_spot_with_latest_input(
        df,
        df_key_vital,
        df_key_timestamp,
        latest_spot,
        latest_spot_key_vital,
        latest_spot_key_is_manual_submission,
        latest_spot_key_timestamp_to_update,
    ):
        latest_record = search_latest_health_input(df, df_key_vital)
        if len(latest_record) > 0:
            latest_spot[latest_spot_key_vital] = latest_record[df_key_vital]
            latest_spot[latest_spot_key_timestamp_to_update] = latest_record[
                df_key_timestamp
            ]
            latest_spot[latest_spot_key_is_manual_submission] = latest_record['is_manual']

    # compare sensor and health input spot and update latest spot
    if user_id not in settings.list_demo_id:
        # get health input
        table_health_input = HealthData.objects.all()

        # get health input data from the DynamoDB
        df_query_health_input = query_health_input(
            user_id, None, None, "minutes", None
        )
        df_query_health_input.fillna(-1, inplace=True)


        #fetch bp device data

        df_bp_device_inputs = query_observations_data_input(
            "bp-device",
            user_id,
            None,
            None,
            "minutes",
            None
        )
        map_bp_columns_rename = {
                    "bp_sys_device": "BP_Sys",
                    "bp_dia_device": "BP_Dia"
                }

        df_bp_device_inputs = df_bp_device_inputs.rename(
            columns = map_bp_columns_rename
        )

        df_bp_device_inputs.fillna(-1, inplace=True)

        combined_input_df = pd.concat(
            [
                df_query_health_input.assign(is_manual=1),
                df_bp_device_inputs.assign(is_manual=0)
            ],
            ignore_index=True
        )

        if len(df_query_health_input) > 0:

            metrics_config_compare_and_update_output = [
                {
                    "df_key_vital": "RR_manual",
                    "df_key_timestamp": "listtime",
                    "latest_spot_key_vital": "RR",
                    "latest_spot_key_timestamp": "last_connection_chest",
                    "latest_spot_key_is_manual_submission": "is_manual_submission_rr",
                    "latest_spot_key_timestamp_to_update": "timestamp_rr",
                },
                {
                    "df_key_vital": "HR_manual",
                    "df_key_timestamp": "listtime",
                    "latest_spot_key_vital": "HR",
                    "latest_spot_key_timestamp": "last_connection_finger",
                    "latest_spot_key_is_manual_submission": "is_manual_submission_hr",
                    "latest_spot_key_timestamp_to_update": "timestamp_hr",
                },
                {
                    "df_key_vital": "SpO2_manual",
                    "df_key_timestamp": "listtime",
                    "latest_spot_key_vital": "SpO2",
                    "latest_spot_key_timestamp": "last_connection_finger",
                    "latest_spot_key_is_manual_submission": "is_manual_submission_spo2",
                    "latest_spot_key_timestamp_to_update": "timestamp_spo2",
                },
                {
                    "df_key_vital": "body_temp_manual",
                    "df_key_timestamp": "listtime",
                    "latest_spot_key_vital": "body_temperature",
                    "latest_spot_key_timestamp": "last_connection_chest",
                    "latest_spot_key_is_manual_submission": "is_manual_submission_body_temp",
                    "latest_spot_key_timestamp_to_update": "timestamp_body_temperature",
                },
            ]

            for config in metrics_config_compare_and_update_output:
                __compare_and_update_latest_spot_with_manual_health_input(
                    df_query_health_input,
                    config["df_key_vital"],
                    config["df_key_timestamp"],
                    latest_spot,
                    config["latest_spot_key_vital"],
                    config["latest_spot_key_timestamp"],
                    config["latest_spot_key_is_manual_submission"],
                    config["latest_spot_key_timestamp_to_update"],
                )

        metrics_config_update_output = [
            {
                "df_key_vital": "BP_Sys",
                "df_key_timestamp": "listtime",
                "latest_spot_key_vital": "BP_Sys",
                "latest_spot_key_is_manual_submission": "is_manual_submission_bp_sys",
                "latest_spot_key_timestamp_to_update": "timestamp_bp_sys",
            },
            {
                "df_key_vital": "BP_Dia",
                "df_key_timestamp": "listtime",
                "latest_spot_key_vital": "BP_Dia",
                "latest_spot_key_is_manual_submission": "is_manual_submission_bp_dia",
                "latest_spot_key_timestamp_to_update": "timestamp_bp_dia",
            },
        ]


        for config in metrics_config_update_output:
            __update_latest_spot_with_latest_input(
                combined_input_df,
                config["df_key_vital"],
                config["df_key_timestamp"],
                latest_spot,
                config["latest_spot_key_vital"],
                config["latest_spot_key_is_manual_submission"],
                config["latest_spot_key_timestamp_to_update"],
            )


        for key in latest_spot.keys():
            if isinstance(latest_spot[key], (np.int8, np.int16, np.int32, np.int64)):
                latest_spot[key] = int(latest_spot[key])  # Convert to Python int

        response["latest"] = latest_spot
    return response


def append_list_date(
    response, user_id, start_datetime, utc_offset, resolution, data_length
):
    """Add list of date in text for daily trends"""

    info = []
    ret_key = "listtime" if resolution in ["hourly", "minutes"] else "listdate"
    offset = datetime.timedelta(
        hours=utc_offset["hours"], minutes=utc_offset["minutes"]
    )
    trends_vital_sign_minutes_resolution = settings.trends_vital_sign_minutes_resolution

    # TODO:QH currently this behavior does not take into account utc_offset
    for i in range(0, data_length):
        if resolution == "daily":
            if not (
                i == data_length
                and (start_datetime + offset).hour == 0
                and (start_datetime + offset).minute == 0
            ):
                tmp_date = str(start_datetime + datetime.timedelta(days=i))
                info.append(tmp_date)

        elif resolution == "hourly":
            tmp_time = (start_datetime + datetime.timedelta(hours=i)).replace(
                minute=0, second=0, microsecond=0
            )
            info.append(str(tmp_time)[0:-3])
        elif resolution == "minutes":
            if (
                hasattr(settings, "list_nuh_demo_id")
                and user_id in settings.list_nuh_demo_id
            ):
                info.append(
                    str(
                        start_datetime
                        + datetime.timedelta(
                            minutes=i * trends_vital_sign_minutes_resolution
                        )
                    )
                )
            else:
                info.append(
                    str(
                        start_datetime
                        + datetime.timedelta(
                            minutes=i * trends_vital_sign_minutes_resolution
                        )
                    )
                )
    response["metrics"][ret_key] = info
    response["metrics_SD"][ret_key] = info


def append_overall_mean(response):
    """Add the overall mean of the statistics"""

    val_replace_NaN = settings.val_replace_NaN
    for key in response["metrics"].keys():
        if key in ["xaxis", "listdate", "listtime"]:
            continue

        temp = np.array(response["metrics"][key])
        temp = temp[temp != val_replace_NaN]

        if len(temp) == 0:
            temp = val_replace_NaN

        if key in ["RR_TD"]:
            response["metrics_overall_mean"][key] = np.mean(temp)
        else:
            response["metrics_overall_mean"][key] = int(np.mean(temp))


def merge_df_data_with_health_input(df_data, df_health, df_other, df_emr, merge_on):

    # merge two df together
    if ((len(df_health) == 0) and (len(df_data) == 0)) or (
        (len(df_health) == 0) and (len(df_data) > 0)
    ):
        merged_df = pd.concat([df_data, df_health], ignore_index=True)
    else:
        merged_df = pd.merge(df_data, df_health, on=merge_on, how="outer")

    merged_df = pd.merge(merged_df, df_other, on=merge_on, how="outer")
    merged_df = pd.merge(merged_df, df_emr, on=merge_on, how="outer")

    # sort datetime
    merged_df = merged_df.sort_values(merge_on)

    # fill in NaN with -1
    merged_df.fillna(-1, inplace=True)

    return merged_df


def handle_trend_query(start_datetime, date_time, user_id, resolution, utc_offset=None):

    response_dict = {}
    utc_offset_str = utc_offset
    try:
        utc_offset = get_utc_offset(utc_offset)
        utc_offset = {"hours": utc_offset[0], "minutes": utc_offset[1]}
    except Exception as e:
        utc_offset_str = "00:00"
        utc_offset = {"hours": 0, "minutes": 0}
    val_replace_NaN = settings.val_replace_NaN
    list_demo_id = settings.list_demo_id

    # Step 1 - Calculate the data length and the actual start/stop period
    start_datetime, stop_date_time, data_length = cal_data_length(
        date_time, resolution, start_datetime
    )

    # Step 2 - Generate the initial data structure
    temp_metrics = generate_dummy("trends-{}".format(resolution), data_length)

    ids = [i.strip() for i in user_id.split(",")]
    id_list_length = len(ids)
    # Step 4: Calculate the metrics and std dev information
    desired_attr = [
        "rr",
        "hr",
        "spo2",
        "rr_td",
        "rr_dc",
        "body_temperature",
        "skin_temperature",
        "activity",
    ]

    if resolution == "minutes":
        desired_attr.append("dashboard_mode")
        desired_attr.append("hr_chest")
    cond_attr = ["RR", "HR", "HR", "RR", "RR", "RR", "RR"]
    attr_required = {
        "rr": ["rr", "rr_td", "rr_dc", "body_temperature", "skin_temperature"],
        "hr": ["hr", "spo2"],
    }  # TODO: if this is not needed, remove it

    options = {
        "data_length": data_length,
        "resolution": resolution,
        "valReplaceNaN": val_replace_NaN,
        "min_hr_finger_required_within_hour": settings.min_hr_finger_required_within_hour,
        "min_hr_finger_required_within_day": settings.min_hr_finger_required_within_day,
        "trends_vital_sign_minutes_resolution": settings.trends_vital_sign_minutes_resolution,
        "utc_offset": utc_offset,
    }
    data_processing_objs = DataProcessing.objects.filter(
        user_id__in=ids, date_time__range=[start_datetime, stop_date_time]
    ).order_by("date_time")

    for id in ids:
        response = {}
        response[id] = {"metrics": {}, "metrics_SD": {}, "metrics_overall_mean": {}}
        response[id]["metrics"] = temp_metrics

        response[id]["metrics_overall_mean"] = {}
        if not id in list_demo_id:

            # reset value to -1 and update it
            for key in response[id]["metrics"].keys():
                response[id]["metrics"][key] = (
                    val_replace_NaN * np.ones(data_length)
                ).tolist()
                response[id]["metrics_SD"][key] = (
                    val_replace_NaN * np.ones(data_length)
                ).tolist()
            data_processing = data_processing_objs.filter(user_id=id)
            if resolution != "minutes":

                append_list_date(
                    response[id],
                    user_id,
                    start_datetime,
                    utc_offset,
                    resolution,
                    data_length,
                )
    
                response = get_trend_from_cache(
                    response.copy(),
                    start_datetime.strftime('%Y-%m-%dT%H:%M:%S'),
                    stop_date_time.strftime('%Y-%m-%dT%H:%M:%S'),options
                )

                append_overall_mean(response[id])

            """
            quick fix for spot trend
            if it is minutes trend query, overwrite the response with spot trend
            """
            if resolution == "minutes":
                response[id] = handle_spot_trend_query(
                    data_processing, desired_attr, True, False, True, True
                )

                """add health input data to minutes trend"""

                df_query_health_input = query_health_input(
                    id, start_datetime, stop_date_time, resolution, "median"
                )
                df_query_health_input_sd = query_health_input(
                    id, start_datetime, stop_date_time, resolution, "sd"
                )


                # get other input data
                df_query_external_input = query_observations_data_input(
                    "bp-device",
                    id,
                    start_datetime,
                    stop_date_time,
                    resolution,
                    "median",
                )

                df_query_external_input['has_other_readings_from_bp_device'] = 1
                
                df_query_external_input_sd = query_observations_data_input(
                    "bp-device",
                    id,
                    start_datetime,
                    stop_date_time,
                    resolution,
                    "sd",
                )

                df_query_emr_input = query_observations_data_input(
                    "emr",
                    id,
                    start_datetime,
                    stop_date_time,
                    resolution,
                    "median",
                )

                df_query_emr_input_sd = query_observations_data_input(
                    "emr",
                    id,
                    start_datetime,
                    stop_date_time,
                    resolution,
                    "sd",
                )

                df_query_emr_input['has_other_readings_from_emr'] = 1

                def add_manual_health_input_indicator_to_df(df, val_nan):
                    col_timestamp_to_drop = []
                    if "listtime" in df.columns:
                        col_timestamp_to_drop = col_timestamp_to_drop + ["listtime"]
                    if "listdate" in df.columns:
                        col_timestamp_to_drop = col_timestamp_to_drop + ["listdate"]
                    df["has_manual_reading"] = np.where(
                        df.drop(col_timestamp_to_drop, axis=1).notna().any(axis=1),
                        1,
                        val_nan,
                    )
                    return df

                # Add manual health input indicator
                df_query_health_input = add_manual_health_input_indicator_to_df(
                    df_query_health_input, val_replace_NaN
                )
                df_query_health_input_sd = add_manual_health_input_indicator_to_df(
                    df_query_health_input_sd, val_replace_NaN
                )


                # Convert list to DataFrame
                df_metrics = pd.DataFrame(response[id]["metrics"])
                df_metrics_sd = pd.DataFrame(response[id]["metrics_SD"])


                # remove health input columns in the sensor data df before merging (daily and hourly trends)
                columns_to_drop = ["bp_sys", "bp_dia"]
                df_metrics, df_metrics_sd = [
                    x_df.drop(
                        columns=[col for col in columns_to_drop if col in x_df.columns]
                    )
                    for x_df in [df_metrics, df_metrics_sd]
                ]


                # merge dataframes
                # TODO: consider standardize timestamp variable name
                merge_on = "listtime" if resolution in ["hourly", "minutes"] else "listdate"
                merge_df_metrics = merge_df_data_with_health_input(
                    df_metrics, df_query_health_input,df_query_external_input, df_query_emr_input, merge_on
                )
                merge_df_metrics_sd = merge_df_data_with_health_input(
                    df_metrics_sd, df_query_health_input_sd,df_query_external_input_sd, df_query_emr_input_sd, merge_on
                )

                if not merge_df_metrics.empty:
                    merge_df_metrics['has_valid_other_reading'] = merge_df_metrics.apply(lambda row: 1 if (row['has_other_readings_from_bp_device'] == 1 or row['has_other_readings_from_emr'] == 1 or row['has_manual_reading'] == 1) else -1, axis=1)
                else:
                    merge_df_metrics['has_valid_other_reading'] = -1

                if resolution == "minutes":
                    # assign signal_quality status if col is missing
                    if "signal_quality_status" not in merge_df_metrics.columns:
                        merge_df_metrics["signal_quality_status"] = val_replace_NaN

                    if "signal_quality_status" not in merge_df_metrics_sd.columns:
                        merge_df_metrics_sd["signal_quality_status"] = val_replace_NaN

                    # assign sd to minute resolution response
                    merge_df_metrics_sd["BP_Sys"] = val_replace_NaN
                    merge_df_metrics_sd["BP_Dia"] = val_replace_NaN
                    merge_df_metrics_sd["RR_manual"] = val_replace_NaN
                    merge_df_metrics_sd["HR_manual"] = val_replace_NaN
                    merge_df_metrics_sd["SpO2_manual"] = val_replace_NaN
                    merge_df_metrics_sd["body_temp_manual"] = val_replace_NaN
                    merge_df_metrics_sd["weight_manual"] = val_replace_NaN
                    merge_df_metrics_sd["blood_sugar_manual"] = val_replace_NaN
                    merge_df_metrics_sd["has_manual_reading"] = val_replace_NaN
                    merge_df_metrics_sd["bp_dia_device"] = val_replace_NaN
                    merge_df_metrics_sd["bp_sys_device"] = val_replace_NaN
                    merge_df_metrics_sd["has_valid_other_reading"] = val_replace_NaN

                # TODO standardize the timestmap variable
                if resolution == "daily":
                    merge_df_metrics = merge_df_metrics.drop(columns=["listtime"])
                    merge_df_metrics_sd = merge_df_metrics_sd.drop(columns=["listtime"])

                response[id]["metrics"] = merge_df_metrics.to_dict("list")
                response[id]["metrics_SD"] = merge_df_metrics_sd.to_dict("list")

            """
            quick fix
            if empty array, return one data point
            """
            if len(response[id]["metrics"]["rr"]) == 0:
                for key in response[id]["metrics"]:
                    response[id]["metrics"][key] = val_replace_NaN

                for key in response[id]["metrics_SD"]:
                    response[id]["metrics_SD"][key] = val_replace_NaN

                for key in response[id]["metrics_overall_mean"]:
                    response[id]["metrics_overall_mean"][key] = val_replace_NaN

                response[id]["metrics"]["listtime"] = stop_date_time.strftime('%Y-%m-%d %H:%M:%S')
                response[id]["metrics_SD"]["listtime"] = stop_date_time.strftime('%Y-%m-%d %H:%M:%S')

            # temperature_keys = ['temperature','body_temperature','skin_temperature']
            # for key  in temperature_keys:
            #     if key in response[id]["metrics"]:
            #         del response[id]["metrics"][key]
            #     if key in response[id]["metrics_SD"]:
            #         del response[id]["metrics_SD"][key]
            #     if key in response[id]["metrics_overall_mean"]:
            #         del response[id]["metrics_overall_mean"][key]

            excluded_temperature_keys = []
            if resolution == 'minutes':            
                excluded_temperature_keys.extend(['temperature','body_temperature','skin_temperature'])
                rename_map = {
                    # "body_temp_emr": "emr_body_temperature",
                    # "body_temp_manual": "manual_body_temperature",
                }

                for metric_group in ("metrics", "metrics_SD", "metrics_overall_mean"):
                    data_group = response[id][metric_group]
                    for old_key, new_key in rename_map.items():
                        if old_key in data_group:
                            data_group[new_key] = data_group.pop(old_key)
            elif resolution in ('hourly', 'daily'):
                excluded_temperature_keys.extend(['temperature', 'skin_temperature'])

            for key in excluded_temperature_keys:
                for metric_group in ("metrics", "metrics_SD", "metrics_overall_mean"):
                    response[id][metric_group].pop(key, None)

            response[id] = convert_small_to_caps(
                response[id],
                {
                    "rr": "RR",
                    "hr": "HR",
                    "spo2": "SpO2",
                    "rr_td": "RR_TD",
                    "rr_dc": "RR_DC",
                    "dashboard_mode": "dashboardMode",
                    # "news": "EWS",
                    "bp_dia": "BP_Dia",
                    "bp_sys": "BP_Sys",

                },
            )

            # Fetch prediction score
            if resolution in ['hourly','minutes']:
                listtime = response[id]['metrics']['listtime']
                if isinstance(listtime, str):
                    date_times = [datetime.datetime.strptime(listtime, "%Y-%m-%d %H:%M:%S")]
                else:
                    date_times = [datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S") for dt in listtime]
                min_time_formatted = min(date_times).strftime("%Y-%m-%dT%H:%M:%S")
                max_time_formatted = max(date_times).strftime("%Y-%m-%dT%H:%M:%S")
                prediction_score = fetch_predictions(id, min_time_formatted, max_time_formatted, resolution, utc_offset_str)
                df = pd.DataFrame(prediction_score)
                if not df.empty:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    df.drop(columns=['created_at', 'model_config'], inplace=True, errors='ignore')
                else:
                    df = pd.DataFrame(columns=['datetime', 'outcome_rr', 'outcome_rr_hr',
                        'outcome_rr_hr_spo2', 'outcome_rr_hr_spo2_bp_sys',
                        'outcome_dynamic_model', 'dynamic_model'])
 
                if isinstance(listtime, str):
                    expected_df = pd.DataFrame({'datetime': [listtime]})
                else:
                    expected_df = pd.DataFrame({'datetime': listtime})
                merged_df = expected_df.merge(df, on='datetime', how='left')
                for col in ['outcome_rr', 'outcome_rr_hr', 'outcome_rr_hr_spo2', 'outcome_rr_hr_spo2_bp_sys']:
                    merged_df[col] = merged_df[col].apply(lambda x: round(float(x) * 100, 1) if pd.notna(x) else settings.val_replace_NaN)

                # Create dynamic model list of dicts
                merged_df['dynamic_predictions'] = merged_df.apply(
                    lambda row: (
                        {
                            "model": '' if pd.isna(row['dynamic_model']) else row['dynamic_model'], 
                            "outcome": (
                                    settings.val_replace_NaN if pd.isna(row['outcome_dynamic_model']) 
                                    else round(float(row['outcome_dynamic_model']) * 100, 1)
                                )
                            } if row['dynamic_model'] and row['outcome_dynamic_model'] not in [None, '', -1]
                        else []
                    ),
                    axis=1
                )
                prediction_dict = {}
                if isinstance(listtime, str):
                    prediction_dict['prediction_rr'] = merged_df['outcome_rr'].iloc[0]
                    prediction_dict['prediction_rr_hr'] = merged_df['outcome_rr_hr'].iloc[0]
                    prediction_dict['prediction_rr_hr_spo2'] = merged_df['outcome_rr_hr_spo2'].iloc[0]
                    prediction_dict['prediction_rr_hr_spo2_bp_sys'] = merged_df['outcome_rr_hr_spo2_bp_sys'].iloc[0]
                    prediction_dict['prediction_dynamic_model'] = merged_df['dynamic_predictions'].iloc[0]
                else:
                    prediction_dict['prediction_rr'] = merged_df['outcome_rr'].tolist()
                    prediction_dict['prediction_rr_hr'] = merged_df['outcome_rr_hr'].tolist()
                    prediction_dict['prediction_rr_hr_spo2'] = merged_df['outcome_rr_hr_spo2'].tolist()
                    prediction_dict['prediction_rr_hr_spo2_bp_sys'] = merged_df['outcome_rr_hr_spo2_bp_sys'].tolist()
                    prediction_dict['prediction_dynamic_model'] = merged_df['dynamic_predictions'].tolist()
                response[id]['metrics']['prediction'] = prediction_dict   


        # TODO:QH demo_id should be decoupled from the actual logic. Find a way to do this...
        else:
            response = {
                id: {"metrics": {}, "metrics_SD": {}, "metrics_overall_mean": {}}
            }
            response[id]["metrics"] = temp_metrics
            data_length = len(response[id]["metrics"]["RR"])

            response[id]["metrics_SD"] = {
                "RR": (np.random.randint(low=0, high=10, size=data_length)).tolist(),
                "HR": (np.random.randint(low=0, high=25, size=data_length)).tolist(),
                "SpO2": (np.random.randint(low=0, high=5, size=data_length)).tolist(),
                "RR_TD": (np.random.uniform(0.1, 0.2, size=data_length)).tolist(),
                "RR_DC": (np.random.randint(low=3, high=10, size=data_length)).tolist(),
                "BP_Sys": (np.random.randint(low=1, high=5, size=data_length)).tolist(),
                "BP_Dia": (np.random.randint(low=1, high=5, size=data_length)).tolist(),
                "temperature": (
                    np.random.randint(low=1, high=100, size=data_length) / 100.0
                ).tolist(),
                "EWS": (np.random.randint(low=1, high=5, size=data_length)).tolist(),
            }

            response[id]["metrics_overall_mean"] = {}
            for key in response[id]["metrics"].keys():
                if key in ["xaxis", "listdate"]:
                    continue
                if len(response[id]["metrics"][key]) > 0:
                    response[id]["metrics_overall_mean"][key] = int(
                        np.mean(np.array(response[id]["metrics"][key]))
                    )
                else:
                    response[id]["metrics_overall_mean"][key] = val_replace_NaN

            append_list_date(
                response[id],
                user_id,
                start_datetime,
                utc_offset,
                resolution,
                data_length,
            )

            # # mgh demo data
            # # this will return a pre-defined dummy data with fixed date, regardless of the query
            if (
                hasattr(settings, "list_mgh_demo_id_02")
                | hasattr(settings, "list_mgh_demo_id_03")
                | hasattr(settings, "list_mgh_demo_id_10")
                | hasattr(settings, "list_mgh_demo_id_04")
                | hasattr(settings, "list_mgh_demo_id_13")
            ) & (resolution == "daily"):

                if id in settings.list_mgh_demo_id_02:
                    response[id] = generate_dummy_mgh_data(
                        response[id], utc_offset, "mgh_02"
                    )
                elif id in settings.list_mgh_demo_id_03:
                    response[id] = generate_dummy_mgh_data(
                        response[id], utc_offset, "mgh_03"
                    )
                elif id in settings.list_mgh_demo_id_10:
                    response[id] = generate_dummy_mgh_data(
                        response[id], utc_offset, "mgh_10"
                    )
                elif id in settings.list_mgh_demo_id_04:
                    response[id] = generate_dummy_mgh_data(
                        response[id], utc_offset, "mgh_04"
                    )
                elif id in settings.list_mgh_demo_id_13:
                    response[id] = generate_dummy_mgh_data(
                        response[id], utc_offset, "mgh_13"
                    )

            # other dummy data
            if hasattr(settings, "list_dover_demo_IP234028"):
                if user_id in settings.list_dover_demo_IP234028:
                    if resolution == "daily":
                        response[id] = generate_demo_data(
                            response[id], "IP234028", "trends_daily", utc_offset
                        )
                    elif resolution == "hourly":
                        response[id] = generate_demo_data(
                            response[id], "IP234028", "trends_hourly"
                        )
                    elif resolution == "minutes":
                        response[id] = generate_demo_data(
                            response[id], "IP234028", "trends_minutes"
                        )

            # NUH demo data
            if (
                hasattr(settings, "list_nuh_demo_id")
                and user_id in settings.list_nuh_demo_id
            ):
                response[id]["metrics"] = generate_dummy(
                    "trends-minutes-nuh-demo", data_length
                )
                append_list_date(
                    response[id],
                    user_id,
                    start_datetime,
                    utc_offset,
                    resolution,
                    data_length,
                )

            # demo ai prediction
            if (hasattr(settings, "list_demo_prediction") and user_id in settings.list_demo_prediction):
                if resolution == "hourly":
                    response[id] = generate_demo_data(
                        response[id], "ai_pred", "trends_hourly", utc_offset
                    )
                    response[id]["metrics"]["EWS"] = [0,2,0,0,2,2,0,1,0,1,1,2,1,3,1,1,4,4,1,2,2,2,7,7]
                    response[id]["metrics"]["EWS"] = [0,2,0,0,2,2,0,1,0,1,1,2,1,3,1,1,4,4,1,2,2,2,7,7]
                #TODO: Than. This is a quick fix to add prediction to demo data
                elif (resolution == "minutes") or (resolution == "daily"):
                    response[id]["metrics"]["prediction"] = (np.random.randint(low=30, high=80,size=len(response[id]["metrics"]["RR"]))).tolist()

                    if resolution == "daily":
                        response[id]["metrics_SD"]["prediction"] = (np.random.randint(low=3, high=10,size=len(response[id]["metrics"]["prediction"]))).tolist()

            response[id]["metrics"]["signal_quality_status"] = ["Good"] * len(
                response[id]["metrics_SD"]["RR"]
            )
            #TODO: Than. This is a quick fix to remove decompensation from demo data
            if "decompensation" in response[id]["metrics"].keys():
                del response[id]["metrics"]["decompensation"]
        
        excluded_temperature_keys = []
        if resolution == 'minutes':            
            excluded_temperature_keys.extend(['temperature','body_temperature','skin_temperature'])
        elif resolution in ('hourly', 'daily'):
            excluded_temperature_keys.extend(['temperature', 'skin_temperature'])

        for key in excluded_temperature_keys:
            for metric_group in ("metrics", "metrics_SD", "metrics_overall_mean"):
                response[id][metric_group].pop(key, None)

        response_dict.update(response)

    first_key, first_value = next(iter(response_dict.items()))
    return {first_key: first_value} if id_list_length == 1 else response_dict


def handle_list_query(list_id, date_time):
    windowsize_baseline = settings.windowsize_baseline
    startDateTime = date_time - datetime.timedelta(
        minutes=windowsize_baseline
    )  # last N minutes
    stopDateTime = date_time
    logging.info(
        "patient list lookback config is {} minutes (from [{}] to [{}])".format(
            windowsize_baseline, startDateTime, stopDateTime
        )
    )
    val_replace_NaN = settings.val_replace_NaN
    list_demo_id = settings.list_demo_id
    response = {}
    list_id = [i.strip() for i in list_id]
    data_processing_objs = DataProcessing.objects.filter(
        user_id__in=list_id, date_time__range=[startDateTime, stopDateTime]
    ).order_by("date_time")
    for user_id in list_id:

        if user_id in list_demo_id:
            response[user_id] = generate_dummy("list_of_patient")
        else:
            data_processing = data_processing_objs.filter(user_id=user_id)
            response[user_id] = get_user_metrics(
                data_processing, user_id, startDateTime, stopDateTime, val_replace_NaN
            )
            temp_metrics = generate_dummy("metrics")
            try:
                for key in temp_metrics.keys():
                    del response[user_id][key]
            except Exception as e:
                logging.error(
                    "error while trying to delete key in patient list. error message is {}".format(
                        e
                    )
                )

    return response


def has_recent_data(data_processing, date_time):
    timeframe_seconds = 24 * 60 * 60
    if data_processing:
        if (date_time - data_processing.date_time).total_seconds() < timeframe_seconds:
            return True
    return False


def is_all_valid_medians(metrics):
    key_attrs = ["RR", "HR", "SpO2", "skinTemp", "bodyTemp"]
    for attr in key_attrs:
        if (
            attr not in metrics
            or metrics[attr]
            or metrics[attr] == settings.val_replace_NaN
        ):
            return False

    return True


def handle_list_query_via_cache(list_id, list_resolution, date_time):

    windowsize_baseline = settings.windowsize_baseline
    val_replace_NaN = settings.val_replace_NaN

    response = {}
    list_id = [i.strip() for i in list_id]
    data_processing_objs = DataProcessing.objects.filter(user_id__in=list_id).order_by(
        "date_time"
    )
    metric_minute_cache = MetricMinutesCache.objects.filter(user_id__in=list_id)
    metric_cache = MetricDailyCache.objects.filter(user_id__in=list_id).order_by(
        "datetime_updated"
    )
    dict_devices = get_devices_data_multiple(list_id)
    for user_id in list_id:
        # Case 1 - If user is to generate dummy data on the fly
        data_processing = data_processing_objs.filter(user_id=user_id)

        if user_id in settings.list_demo_id:
            response[user_id] = generate_dummy("list_of_patient")
        # Case 2a - If user is to generate dummy data from the vital signs table directly, without going through cache
        # Case 2b - If user is to be loaded from cache, BUT there is data in the past 24 hours => calculate the median on the fly with these data. If the ANY of the calculated median is invalid, it will proceed to use Case 3 instead.
        elif user_id in settings.list_demo_id_data_from_db or has_recent_data(
            data_processing.first(), date_time
        ):
            startDateTime = date_time - datetime.timedelta(
                minutes=windowsize_baseline
            )  # last N minutes
            stopDateTime = date_time
            data_processing = data_processing.filter(
                date_time__range=[startDateTime, stopDateTime]
            )
            response[user_id] = get_user_metrics(
                data_processing, user_id, startDateTime, stopDateTime, val_replace_NaN
            )

            if is_all_valid_medians(response[user_id]):
                temp_metrics = generate_dummy("metrics")
                try:
                    for key in temp_metrics.keys():
                        del response[user_id][key]
                except Exception as e:
                    logging.error(
                        "error while trying to delete key in patient list. error messsage is {}".format(
                            e
                        )
                    )
            else:
                load_from_cache(
                    response,
                    user_id,
                    list_resolution,
                    date_time,
                    metric_minute_cache,
                    metric_cache,
                )
                response[user_id].update(dict_devices[user_id])
                get_other_spot_data(
                    response, user_id, list_resolution, date_time, data_processing
                )

        # Case 3 - If user is to be loaded from the cache
        else:
            load_from_cache(
                response,
                user_id,
                list_resolution,
                date_time,
                metric_minute_cache,
                metric_cache,
            )
            response[user_id].update(dict_devices[user_id])
            get_other_spot_data(
                response, user_id, list_resolution, date_time, data_processing
            )

    return response


def collect_same_key_from_list_of_dict_into_array(
    Xlist, cond_key, cond_value, attr_key
):
    y = []
    if attr_key not in ["sensor_onskin_status", "ews", "flag"]:
        for i in range(len(Xlist)):
            temp = Xlist[i]
            if (cond_key == None) and (cond_value == None):
                try:
                    y.append(float(temp[attr_key]))
                except Exception as e:
                    pass
                continue

            if temp[cond_key] == cond_value:
                try:
                    y.append(float(temp[attr_key]))
                except Exception as e:
                    pass

        return np.array(y)
    else:
        for i in range(len(Xlist)):
            temp = Xlist[i]
            y.append(temp[attr_key] if attr_key in temp else None)
        return y


def roundNumber(x):
    if x % 1 >= 0.5:
        y = np.ceil(x)
    else:
        y = np.floor(x)
    return y


def calculate_stat_np1Darray(X, val_replace_NaN, round_number, method="median"):

    try:
        X = X[~np.isnan(X)]
    except:
        pass

    if len(X) == 0:
        y_val = val_replace_NaN
        y_sd = val_replace_NaN
    else:
        if method == "mean":
            y_val = np.mean(X)
        elif method == "sum":
            y_val = np.sum(X)
        elif method == "median":
            y_val = np.median(X)

        y_sd = np.std(X)

    if round_number and y_val and y_sd:
        y_val = roundNumber(y_val)
        y_sd = roundNumber(y_sd)
    return y_val, y_sd


def extract_items_in_range_and_remove_from_original(X, startdate, stopdate):
    y = []
    index_deleted = []
    for i in range(len(X)):
        tempX_datetime = X[i]["date_time"]
        if (
            pytz.UTC.localize(startdate)
            <= tempX_datetime
            <= pytz.UTC.localize(stopdate)
        ):
            y.append(X[i])
            index_deleted.append(i)

    if len(index_deleted) > 0:
        Xnew = []
        for j in range(len(X)):
            if j not in index_deleted:
                Xnew.append(X[j])
    else:
        Xnew = X

    return Xnew, y


def get_trends_export(
    queryItems, startDateTime, stopDateTime, desired_attr, cond_attr, options
):

    assert len(desired_attr) == len(cond_attr)

    data_length = options["data_length"]
    resolution = options["resolution"]
    valReplaceNaN = None
    min_hr_finger_required_within_hour = options["min_hr_finger_required_within_hour"]
    min_hr_finger_required_within_day = options["min_hr_finger_required_within_day"]
    trends_vital_sign_minutes_resolution = options[
        "trends_vital_sign_minutes_resolution"
    ]
    utc_offset = options["utc_offset"]

    listTimeOutput = []
    for i in range(data_length, 0, -1):
        if resolution == "hourly":
            min_hr_finger_required = min_hr_finger_required_within_hour
            tempDateTime = startDateTime + datetime.timedelta(hours=data_length - i)

        elif resolution == "daily":
            offset = datetime.timedelta(hours=utc_offset['hours'], minutes=utc_offset['minutes'])
            min_hr_finger_required = min_hr_finger_required_within_day
            tempDateTime = (stopDateTime + offset).replace(
                hour=0, minute=0, second=0
            ) - datetime.timedelta(days=i - 1)
            tempDateTime = tempDateTime - offset

        elif resolution == "minutes":
            min_hr_finger_required = 1
            tempDateTime = stopDateTime - datetime.timedelta(
                minutes=i * trends_vital_sign_minutes_resolution
            )

        listTimeOutput.append(tempDateTime)

    if not (len(listTimeOutput) > 0 and listTimeOutput[-1] == stopDateTime):
        listTimeOutput = listTimeOutput + [stopDateTime]
    output = {}

    mean_val = {}
    for i, attr in enumerate(desired_attr):
        mean_val[attr] = []

    for i in range(1, len(listTimeOutput)):
        timeLower = listTimeOutput[i - 1]
        if i != len(listTimeOutput) - 1:
            timeUpper = listTimeOutput[i] - datetime.timedelta(seconds=1)
        else:
            timeUpper = listTimeOutput[i]
        queryItems, tempItem = extract_items_in_range_and_remove_from_original(
            queryItems, timeLower, timeUpper
        )
        tempItem = remove_bad_data(tempItem) if tempItem else tempItem
        for i, attr in enumerate(desired_attr):
            # Step 1 - Extract from Sensor information
            attr_val = collect_same_key_from_list_of_dict_into_array(
                tempItem, "dashboard_mode", cond_attr[i], attr
            )

            if attr not in ["sensor_onskin_status", "ews", "flag"]:
                # combine HR from finger with chest if number of HR from finger is lesser than threshold
                if attr == "hr" and len(attr_val) < min_hr_finger_required:
                    tempValHR_from_chest = (
                        collect_same_key_from_list_of_dict_into_array(
                            tempItem, "dashboard_mode", "rr", "hr"
                        )
                    )
                    attr_val = np.append(attr_val, tempValHR_from_chest)

                    # logging.warning('not enough HR from finger({}) less than {}. combine it with HR from chest ({})'.format(len(attr_val), min_hr_finger_required, len(tempValHR_from_chest)))

                # Step 2 - Calculate the statistics
                temp_median, _ = calculate_stat_np1Darray(attr_val, valReplaceNaN, True)
            else:
                # If it is not a variable that can be aggregated, take the latest value
                temp_median = attr_val[-1] if len(attr_val) != 0 else valReplaceNaN

            # Step 3 - Add it into the list
            mean_val[attr] = np.append(mean_val[attr], temp_median)
            output[attr] = mean_val[attr].tolist()

        output["dateTime"] = listTimeOutput

    return output


def append_list_date_export(response, startDateTime, utc_offset, resolution, data_length):
    info = []
    ret_key = "dateTime"
    trends_vital_sign_minutes_resolution = settings.trends_vital_sign_minutes_resolution

    for i in range(0, data_length):
        offset = datetime.timedelta(hours=utc_offset['hours'], minutes=utc_offset['minutes'])
        if resolution == "daily":

            if not (
                i == data_length
                and (startDateTime + offset).hour == 0
                and (startDateTime + offset).minute == 0
            ):
                if not (i == data_length - 1):
                    tmp_date = str(startDateTime + offset + datetime.timedelta(days=i))
                    info.append(tmp_date)

        elif resolution == "hourly":
            tmp_date = str(
                (startDateTime + offset + datetime.timedelta(hours=i)).replace(
                    minute=0, second=0, microsecond=0
                )
            )[0:-3]
            info.append(tmp_date)
        elif resolution == "minutes":
            tmp_date = str(
                startDateTime
                + offset
                + datetime.timedelta(minutes=i * trends_vital_sign_minutes_resolution)
            )
            info.append(tmp_date)

    response[ret_key] = info

def get_manual_health_input(user_id, start_datetime, stop_datetime, utc_offsets, attrbute_list):
    try:
        mhi_items = HealthData.objects.filter(user_id = user_id, datetime__range=(start_datetime,stop_datetime)).order_by('datetime').values()

        required_cols = ['datetime'] + attrbute_list
        if len(mhi_items) <= 0:
            # Create empty DataFrame
            df = pd.DataFrame(columns= required_cols)
        else:
            df = pd.DataFrame(mhi_items)

            # # Add missing columns with NaN values
            # for col in  ['datetime'] + attrbute_list:
            #     if col not in df.columns:
            #         df[col] = np.nan  # or None, depending on your logic


        if not df.empty:
            # filter row having values in desired column
            valid_rows = df[attrbute_list].apply(
                lambda row: any(pd.notna(val) and val != '' for val in row),
                axis=1
            )
            filtered_df = df[valid_rows]
        else:
            # Create empty DataFrame but keep columns
            filtered_df = pd.DataFrame(columns=df.columns)


        temp_utc_offset = utc_offsets
        filtered_df['datetime'] = pd.to_datetime(filtered_df['datetime']) + datetime.timedelta(hours=int(temp_utc_offset['hours'])) + datetime.timedelta(minutes=int(temp_utc_offset['minutes']))
        filtered_df['datetime'] = filtered_df['datetime'].dt.tz_localize(None)

        filtered_df = filtered_df.fillna(np.nan)
        filtered_df = filtered_df[required_cols]

        return filtered_df

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(err)


def get_bp_device_data(user_id, start_datetime, stop_datetime, utc_offsets, attrbute_list):
    try:
        bp_items = OtherDeviceReading.objects.filter(user_id = user_id, datetime__range=(start_datetime,stop_datetime)).order_by('datetime').values()

        if len(bp_items) <= 0:
            df = pd.DataFrame(columns= ['datetime'] + attrbute_list)
        else:
            df = pd.DataFrame(bp_items)

        if not df.empty:
            valid_rows = df[attrbute_list].apply(
                lambda row: any(pd.notna(val) and val != '' for val in row),
                axis=1
            )
            filtered_df = df[valid_rows]
        else:
            filtered_df = pd.DataFrame(columns=df.columns)

        temp_utc_offset = utc_offsets
        filtered_df['datetime'] = pd.to_datetime(filtered_df['datetime']) + datetime.timedelta(hours=int(temp_utc_offset['hours'])) + datetime.timedelta(minutes=int(temp_utc_offset['minutes']))
        filtered_df['datetime'] = filtered_df['datetime'].dt.tz_localize(None)
        filtered_df = filtered_df.fillna(np.nan)

        return filtered_df

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(err)


def fetch_predictions(user_id, start_datetime_str, end_datetime_str, resolution, utc_offset):
    start_datetime = datetime.datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M:%S')
    end_datetime = datetime.datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M:%S')
    if ':' not in utc_offset:
        hours = int(utc_offset)
        minutes = 0
    else:
        parts = utc_offset.split(':')
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
    utc_offset_str = f'{hours:02}:{minutes:02}'
    offset = datetime.timedelta(hours=hours, minutes=minutes)
    start_datetime_with_offset = start_datetime + offset
    end_datetime_with_offset = end_datetime + offset
    start_datetime_str_with_offset = start_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
    end_datetime_str_with_offset = end_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
    params = {
        "user_ids[]": user_id,
        "start_datetime": start_datetime_str_with_offset,
        "end_datetime": end_datetime_str_with_offset,
        "resolution": resolution,
        "utc_offset": utc_offset_str
    }

    retry_strategy = Retry(
            total=settings.max_retry,
            status_forcelist=settings.status_forcelist,
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=settings.retry_delay_seconds,
            raise_on_status=False
        )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    with requests.Session() as session:
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        try:
            response = session.get(PATIENT_PREDICTION_SCORE_URL, params=params, headers=HEADERS, timeout=settings.max_timeout)
            response.raise_for_status()
            data = response.json().get('data', [])
            return data[0].get('prediction_data', []) if data else []
        except Exception as e:
            logging.error(f"Error fetching predictions: {e}")
            return []


def get_trend_from_cache(
    input_response, start_date_time_utc_str, stop_date_time_utc_str, options
):
    
    def apply_utc_offset(row):
        offset = str(row['utc_offset']).strip()
        offset = offset if offset[0] in "+-" else "+" + offset
        sign = -1 if offset[0] == "-" else 1
        hours, minutes = map(int, offset[1:].split(":"))
        delta = timedelta(hours=sign * hours, minutes=sign * minutes)
        local_dt = row['dateTimeUpdated'] + delta
        return local_dt.replace(tzinfo=None)

    def offset_to_timedelta(offset_str: str) -> pd.Timedelta:
        s = offset_str.strip()
        m = re.match(r'^([+-]?)(\d{1,2})(?::?(\d{2}))?(?::?(\d{2}))?$', s)
        if not m:
            raise ValueError(f"Bad offset format: {offset_str}")
        sign = -1 if m.group(1) == '-' else 1
        h = int(m.group(2))
        m_ = int(m.group(3) or 0)
        sec = int(m.group(4) or 0)
        return pd.Timedelta(hours=sign*h, minutes=sign*m_, seconds=sign*sec)

    response = input_response.copy()

    resolution = options["resolution"]
    if resolution == "daily":
        cache_table = MetricDailyCache

        # Sample start_date_time_utc_str: '2025-02-23T16:00:00' (utc), utc offset is +08:00 -> local datetime is 2025-02-24T00:00:00
        # Sample stop_date_time_utc_str: '2025-03-05T05:27:00' (utc), utc offset is +08:00 -> local datetime is 2025-03-05T13:27:00
        # Normalize start dateime to 00:00:00 UTC by using utc offset and set to 00:00:00. Then, remove the offset
        # Normalize stop dateime to 23:59:59 UTC by using utc offset and set to 23:59:59. Then, remove the offset

        offset_hour = options["utc_offset"]['hours']
        offset_minute = options["utc_offset"]['minutes']

        start_date = convert_datetime_to_start_or_end_of_the_day(start_date_time_utc_str, offset_hour, offset_minute, "start", fmt="%Y-%m-%dT%H:%M:%S")
        stop_date = convert_datetime_to_start_or_end_of_the_day(stop_date_time_utc_str, offset_hour, offset_minute, "end", fmt="%Y-%m-%dT%H:%M:%S")

        timestamp_field = "listdate"
        timestamp_format = "%Y-%m-%d %H:%M:%S"

        frequency = 'D'

    if resolution == "hourly":
        cache_table = MetricHourlyCache

        start_date = datetime.datetime.strptime(
            start_date_time_utc_str, "%Y-%m-%dT%H:%M:%S"
        ).replace(minute=0, second=0)

        stop_date = datetime.datetime.strptime(
            stop_date_time_utc_str, "%Y-%m-%dT%H:%M:%S"
        ).replace(minute=0, second=0)

        timestamp_field = "listtime"
        timestamp_format = "%Y-%m-%d %H:%M:%S"

        frequency = 'H'


    required_cols_metrics = [timestamp_field, "hr", "rr", "rr_td", "rr_dc", "spo2", "body_temperature", "skin_temperature", "bp_dia", "bp_sys", "weight", "blood_sugar", "news","activity", "has_manual_reading","has_valid_other_reading"]
    required_cols_metrics_sd = [timestamp_field, "hr_SD", "rr_SD", "rr_td_SD", "rr_dc_SD", "spo2_SD", "body_temperature_SD", "bp_dia_SD", "bp_sys_SD", "weight_SD", "blood_sugar_SD", "news_SD","activity_SD"]

    # required_cols = list(set(required_cols_metrics))
    required_cols = list(set(required_cols_metrics) | set(required_cols_metrics_sd))

    map_columns_type = {
        "hr": int,
        "rr": int,
        "rr_td": float,
        "rr_dc": float,
        "spo2": int,
        "body_temperature": float,
        "skin_temperature": float,
        "news": int,
        "blood_sugar": float,
        "weight": int,
        "BP_Dia": int,
        "BP_Sys": int,
    }

    map_columns_rename_metrics = {
        "news": "EWS",
        "blood_sugar": "blood_sugar_manual",
        "weight": "weight_manual",
    }

    map_columns_rename_metrics_sd = {
        "hr_SD": 'HR',
        "rr_SD": "RR",
        "rr_td_SD": "RR_TD",
        "rr_dc_SD": "RR_DC",
        "spo2_SD": "SpO2",
        "body_temperature_SD": "body_temperature",
        "skin_temperature_SD": "skin_temperature",
        "news_SD": "EWS",
        "blood_sugar": "blood_sugar_manual",
        "blood_sugar_SD": "blood_sugar_manual",
        "weight": "weight_manual",
        "weight_SD": "weight_manual",
        "bp_dia_SD": "BP_Dia",
        "bp_sys_SD": "BP_Sys",
        "activity_SD": 'activity',
    }

    map_columns_rename_metrics_sd = {
        "hr_SD": 'hr',
        "rr_SD": "rr",
        "rr_td_SD": "rr_td",
        "rr_dc_SD": "rr_dc",
        "spo2_SD": "spo2",
        "body_temperature_SD": "body_temperature",
        "skin_temperature_SD": "skin_temperature",
        "news_SD": "EWS",
        "blood_sugar": "blood_sugar_manual",
        "blood_sugar_SD": "blood_sugar_manual",
        "weight": "weight_manual",
        "weight_SD": "weight_manual",
        "bp_dia_SD": "bp_dia",
        "bp_sys_SD": "bp_sys",
        "activity_SD": 'activity',
    }
    for patient_data in response:

        start_date_str = str(start_date.strftime("%Y-%m-%d %H:%M:%S"))
        stop_date_str = str(stop_date.strftime("%Y-%m-%d %H:%M:%S"))

        query_items = cache_table.objects.filter(user_id=patient_data,datetime_updated__range = (start_date,stop_date))

        df_query = pd.DataFrame.from_records(query_items.values())

        # Check if any missing columns for metrics and metrics SD
        # Add missing columns with NaN values
        for col in required_cols:
            if col not in df_query.columns:
                df_query[col] = np.nan
        
        if "datetime_updated" not in df_query.columns:
            df_query["datetime_updated"] = np.nan
            
        df_query['datetime_updated'] = pd.to_datetime(df_query['datetime_updated'])


        df_query['has_manual_reading'] = df_query['has_manual_reading'].map({True: 1, False: -1})
        df_query['has_valid_other_reading'] = df_query['has_valid_other_reading'].map({True: 1, False: -1})

        # Step 2: Generate full expected daily datetime range
        expected_times = pd.date_range(start=start_date, end=stop_date, freq=frequency)

        # Step 3: Merge and fill missing records
        df_all_datetimes = pd.DataFrame({'datetime_updated': expected_times})
        df_all_datetimes['datetime_updated'] = df_all_datetimes['datetime_updated'].dt.tz_localize('UTC')

        # if resolution == "daily":
        #     try:
        #         org_timezone = get_patient_timezone(patient_data)
        #         org_tz = pytz.timezone(org_timezone)
        #         org_time = datetime.datetime.now(org_tz)
        #         tz = org_time.strftime("%z")
        #         offset_str = f"{tz[:3]}:{tz[3:]}"
        #         print('/////////////////')
        #         print(df_query.columns)
        #         if not all(df_query['utc_offset'] == offset_str):
        #             df_query['localtime'] = df_query.apply(apply_utc_offset, axis=1)
        #             offset = offset_to_timedelta(offset_str)
        #             df_query["localtime"] = pd.to_datetime(df_query["localtime"])
        #             df_query["utc_time"] = df_query["localtime"] - offset
        #             df_query['datetime_updated'] = df_query['utc_time']
        #             df_query.drop(columns=['localtime', 'utc_time'], inplace=True)
        #     except Exception as e:
        #         logging.error(f"Error converting datetimes for daily resolution: {e}", exc_info=True)

        if df_query['datetime_updated'].duplicated().any():
            df_query = df_query.drop_duplicates(subset=['datetime_updated'], keep='last')
            df_query = df_query.reset_index(drop=True)

        df_query_items = df_all_datetimes.merge(df_query, on='datetime_updated', how='left')

        # # if dateTimeUpdated exists, check missing timestamp and insert the missing datetime
        # df_query_items = impute_missing_times(start_date_str, stop_date_str, resolution, df_query_items.copy(), "dateTimeUpdated")

        # if timestamp_field not in df_query_items.columns:
        #     df_query_items[timestamp_field] = df_query_items["datetime_updated"]

        df_query_items[timestamp_field] = df_query_items["datetime_updated"]

        # fill NaN values in column timestamp_field with values from column dateTimeUpdated
        df_query_items[timestamp_field].fillna(df_query_items["datetime_updated"], inplace=True)

        # Convert columns based on the map
        for col, dtype in map_columns_type.items():
            if col not in df_query_items.columns: # impute missing columns with NaN
                df_query_items[col] = np.nan
            else:
                df_query_items[col] = pd.to_numeric(df_query_items[col], downcast='integer' if dtype == int else 'float', errors='coerce')
            
            # If dtype is float, round to 1 decimal place
            if dtype == float:
                df_query_items[col] = df_query_items[col].apply(lambda x: round(x, 1))

        # Fill NaN values with -1
        df_query_items.fillna(settings.val_replace_NaN, inplace=True)

        # sort date and time
        df_query_items = df_query_items.sort_values(timestamp_field)

        df_query_items[timestamp_field] = df_query_items[timestamp_field].dt.strftime('%Y-%m-%d %H:%M:%S')
        ##NOTE the below is to convert utc datetime to local date
        # if resolution == 'daily':
        #     # create UTC format of listtime and convert into local
        #     df_query_items[timestamp_field] = pd.to_datetime(df_query_items[timestamp_field]).dt.tz_localize("UTC")
        #     offset = datetime.timedelta(hours=offset_hour, minutes=offset_minute)
        #     df_query_items[timestamp_field] = df_query_items[timestamp_field] + offset
        #     df_query_items[timestamp_field] = df_query_items[timestamp_field].dt.strftime(timestamp_format)

        # df metric
        df_metrics = df_query_items[required_cols_metrics]
        # rename columns
        df_metrics = df_metrics.rename(
            columns = map_columns_rename_metrics
        )

        # df metric sd
        df_metrics_sd = df_query_items[required_cols_metrics_sd]
        # rename columns
        df_metrics_sd = df_metrics_sd.rename(
            columns = map_columns_rename_metrics_sd
        )

        response[patient_data]["metrics"].update(df_metrics.to_dict("list"))
        response[patient_data]["metrics_SD"].update(df_metrics_sd.to_dict("list"))

        if 'body_temperature' in response[patient_data]["metrics"]:
            response[patient_data]["metrics"]['temperature'] = response[patient_data]["metrics"]['body_temperature']
            response[patient_data]["metrics_SD"]['temperature'] = response[patient_data]["metrics_SD"]['body_temperature']
    return response


def get_bp_device_spot(user_id,source):
    val_nan = settings.val_replace_NaN
    output_response = {}
    queryset = SpotCache.objects.filter(user_id=user_id,source=source).order_by('-datetime_server_received').values('bp_sys','bp_dia','date_time')
    result = {}
    result['bp_sys'] = list(queryset.values_list('bp_sys',flat = True))
    result['bp_dia'] = list(queryset.values_list('bp_dia',flat = True))
    result['datetime'] = [
                                dt.strftime('%Y-%m-%dT%H:%M:%S')
                                for dt in queryset.values_list('date_time', flat=True)
                        ]
    return result


def paginate_list(data, page=1, limit=10):
    total_items = len(data)
    total_pages = (total_items + limit - 1) // limit

    start = (page - 1) * limit
    end = start + limit
    items = data[start:end]

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def handle_query_vital_readings(user_list, start, end, page, limit):
    try:
        user_list = user_list.split(",")
        readings = []
        output_response = {"data": [], "totalCount": 0}
        val_nan = settings.val_replace_NaN

        queryset = Staging.objects.filter(user_id__in=user_list,timestamp__range=(start, end)).order_by('-timestamp').values()

        paginated_result = paginate_list(queryset, page, limit)
        page_data = paginated_result["items"]
        output_response["totalCount"] = queryset.count()

        for data in page_data:

            data_dict = {
            "timestamp": data["timestamp"].strftime('%Y-%m-%d %H:%M:%S'),
            "patient_id": data["patient_id"] if "patient_id" in data else val_nan,
            "data": {
                "rr": data["rr"] if "rr" in data else val_nan,
                "hr": data["hr"] if "hr" in data else val_nan,
                "spo2": data["spo2"] if "spo2" in data else val_nan,
                "rr_td": data["rr_td"] if "rr_td" in data else val_nan,
                "rr_dc": data["rr_dc"] if "rr_dc" in data else val_nan,
                "skin_temperature": data["skin_temperature"] if "skin_temperature" in data else val_nan,
                "activity": data["activity"] if "activity" in data else val_nan,
                "chest_signal_quality": data["chest_signal_quality"] if "chest_signal_quality" in data else val_nan,
                "finger_signal_quality": data["finger_signal_quality"] if "finger_signal_quality" in data else val_nan,
                "finger_skin_contact": data["finger_skin_contact"] if "finger_skin_contact" in data else val_nan,
                "chest_skin_contact": data["chest_skin_contact"] if "chest_skin_contact" in data else val_nan,
                "risk_probability": val_nan,
            },
            "device": {
                "sensor_name": data["sensor_name"] if "sensor_name" in data else val_nan,
                "gateway_name": data["gateway_name"] if "gateway_name" in data else val_nan,
                "sensor_battery": data["sensor_battery"] if "sensor_battery" in data else val_nan
            }
            }

            output_response["data"].append(data_dict)
        return output_response,False
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(f"Error in handle_query_vital_readings(). error message is {err}")
        return err,True


def handle_query_monitoring_data(datetime, user_id, source):
    try:

        val_nan = settings.val_replace_NaN

        if not user_id:
            return {
                "error": "Missing required parameters: user_id is required."
            }

        required_fields = [
            "date_time", "bp_sys", "bp_dia", "hr", "rr", 
            "spo2", "weight", "blood_sugar", "body_temperature"
        ]
        field_type = {"bp_sys": int, "bp_dia": int, "hr": int, "rr": int, "spo2": int, "weight": int, "blood_sugar": float, "body_temperature": float}

        queryItems = SpotCache.objects.filter(user_id=user_id,source=source).order_by('-datetime_server_received').values(*required_fields)
        df = pd.DataFrame(queryItems)
        if df.empty:
            output_response = {}
        else:
            df = df.astype(field_type, errors="ignore")
            df = df.fillna(val_nan).replace({None: val_nan})
            output_response = df.to_dict(orient="list")
        return output_response


    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(
            "Error occurred during bp device data fetch. error message is {}".format(
                err
            )
        )

def handle_query_master_cache_patient_list(organisation_id, user_list, resolution_list, timestamp, device_data):
    try:
        result = {}
        queryset = PatientListCache.objects.filter(user_id__in = user_list,
            organization = organisation_id,
            resolution__in = resolution_list
            ).values()

        patient_details = PatientDetail.objects.filter(organization_id = organisation_id, user_id__in =user_list ).values('user_id','resolution')
        q_object = Q()
        for item in patient_details:
            q_object  = q_object | Q(user_id = item['user_id'], resolution = item['resolution'])
        queryset = queryset.filter(q_object)
        for resolution in resolution_list:
            context_dict = {}

            if resolution == 'minutes':
                context_dict['denominator'] = 60
                context_dict['timedelta'] = settings.list_timedelta["MINUTES"]
                context_dict['threshold_date'] =  timestamp - datetime.timedelta(minutes=context_dict['timedelta'])

            if resolution == 'hourly':
                context_dict['denominator'] = 60 * 60
                context_dict['timedelta'] = settings.list_timedelta["HOURS"]
                context_dict['threshold_date'] =  timestamp - datetime.timedelta(hours=context_dict['timedelta'])

            if resolution == 'daily':
                context_dict['denominator'] = 60 * 60 * 24
                context_dict['timedelta'] = settings.list_timedelta["DAYS"]
                context_dict['threshold_date'] =  timestamp - datetime.timedelta(days=context_dict['timedelta'])
            context_dict['device_data'] = device_data
            context_dict['timestamp'] = timestamp

            resolution_queryset = queryset.filter(resolution = resolution)
            if resolution_queryset.exists():
                obj = resolution_queryset.first()
                organization_resolution = obj.get('organization_resolution', '')
                context_dict['organization_resolution'] = organization_resolution
                if organization_resolution == resolution:
                    patient_data = CachePatientListSerializer(resolution_queryset,many = True, context ={"context_dict": context_dict}).data
                    result[resolution] = patient_data

        return result


    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(
            "Error occurred handle_query_master_cache_patient_list(). error message is {}".format(
                err
            )
        )

def run_manual_hourly_job(user_ids, timestamp):
    """
        Manually processes hourly NEWS scores for given user_ids at the specified timestamp.
    """
        
    def fetch_records_for_users(user_ids, timestamp):
        """
            Fetch staging hourly records for provided user_ids within the given hour.
        """ 
        try:
            dt_obj = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            start_time = dt_obj.strftime("%Y-%m-%d %H:00:00")
            stop_time = dt_obj.strftime("%Y-%m-%d %H:59:59")
            logging.info(f"Fretching records updated between {start_time} and {stop_time} UTC.")

            staging_hourly_records = StagingHourlyCache.objects.filter(user_id__in=user_ids, datetime_updated__range = (start_time, stop_time)).values()
            if not staging_hourly_records.exists():
                logging.info("No staging hourly records found for the given timestamp.")
                return [], 200, "No data to process"
            logging.info(f"Retrieved {len(staging_hourly_records)} records.")
            return staging_hourly_records, 200, None
        except Exception as e:
            logging.error(f"Error fetching staging hourly records: {e}")
            return None, 500, str(e)

    def delete_records_from_staging_table(records):
        try:
            user_ids = [record['user_id'] for record in records]
            deleted_count, _ = StagingHourlyCache.objects.filter(user_id__in=user_ids).delete()
            logging.info(f"Deleted {deleted_count} records from StagingHourlyCache.")
        except Exception as e:
            logging.error(f"Error deleting records from StagingHourlyCache: {e}", exc_info=True)

    try:
        records, status, error_message = fetch_records_for_users(user_ids, timestamp)
        if error_message:
            return {"status": 200, "message": "No records found"}

        # Compute NEWS for each record in the DataFrame
        df = pd.DataFrame(records)
        df["user_id"] = pd.to_numeric(df["user_id"], errors="coerce").astype("Int64")
        logging.info(f"Process record {len(df)} in staging. Content {df}")
        cols_to_convert = ["rr", "hr", "spo2", "body_temperature", "bp_sys", "bp_dia"]
        for col in cols_to_convert:
            if col not in df.columns:
                df[col] = None
        df[cols_to_convert] = (
            df[cols_to_convert].apply(pd.to_numeric, errors="coerce").astype("Float64")
        )
        logging.info("Calculating NEWS scores for each record.")
        df["news"] = df.apply(lambda row: compute_news_score_staging_hourly(row), axis=1)
        for organization_id, user_id, news in zip(df['organization_id'], df['user_id'], df['news']):
            if news != None:
                try:
                    updated_rows = PatientListCache.objects.filter(
                            organization_id=organization_id, user_id=user_id, resolution='hourly'
                        ).update(news=news)
                    if updated_rows:
                        logging.info(f"[{organization_id}#{user_id}#hourly] NEWS score updated in patient list cache")
                    else:
                        logging.warning(f"[{organization_id}#{user_id}#hourly] No matching record found to update")
                except Exception as e:
                    logging.error(f"[{organization_id}#{user_id}#hourly] Failed to update NEWS score: {e}", exc_info=True)

        remove_processing_records_from_df(df)
        delete_records_from_staging_table(records)
        logging.info("Manual Hourly Trigger Completed")
        return {"status": 200, "message": "Manual hourly job completed successfully"}
    except Exception as e:
        logging.error(f"Error in run_manual_hourly_job: {e}", exc_info=True)
        return {"status": 500, "message": str(e)}
