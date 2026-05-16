import pytz
import datetime
import sys
import traceback
import logging
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter, Retry
# from django.utils.timezone import make_aware

from urllib.parse import urljoin
from data_app.helpers import get_patient_timezone
from data_app.models import ( HealthData, DataProcessing, MetricHourlyCache, 
        StagingHourlyCache , MetricDailyCache, OtherDeviceReading, MetricMinutesCache, PatientDetail, PatientListCache)
import dataprocessing.lib_settings as settings
import data_app.lib_common as common
from data_app.lib_query import EarlyWarningScore


val_nan = settings.val_replace_NaN

def roundNumber(x):
    if x%1>=0.5:
        y = np.ceil(x)
    else:
        y = np.floor(x)
    return y

def hourly_start_stop_timeframe(user_id, time_utc_str):
    timezone = get_patient_timezone(user_id)
    timezone = pytz.timezone(timezone)

    ## If we didn't get start date, default is same day 00:00:00
    ## Set start date in the patient's timezone then convert both to UTC timezone
    # stop_date = datetime.datetime.now().astimezone(timezone)
    start_date = pytz.utc.localize(datetime.datetime.strptime(time_utc_str, "%Y-%m-%d %H:%M:%S")).astimezone(timezone).replace( minute=0, second=0).astimezone(pytz.utc)
    stop_date = pytz.utc.localize(datetime.datetime.strptime(time_utc_str, "%Y-%m-%d %H:%M:%S")).astimezone(timezone).replace(minute=59, second=59).astimezone(pytz.utc)

    if (stop_date - start_date).seconds/3600 > 24:
        raise ValueError(f"Start and end times are not on the same day.")
    
    return (start_date, stop_date)

def daily_start_stop_timeframe(user_id, time_utc_str):
    timezone = get_patient_timezone(user_id)
    timezone = pytz.timezone(timezone)

    ## If we didn't get start date, default is same day 00:00:00
    ## Set start date in the patient's timezone then convert both to UTC timezone
    # stop_date = datetime.datetime.now().astimezone(timezone)
    start_date = pytz.utc.localize(datetime.datetime.strptime(time_utc_str, "%Y-%m-%d %H:%M:%S")).astimezone(timezone).replace(hour=0, minute=0, second=0).astimezone(pytz.utc)
    stop_date = pytz.utc.localize(datetime.datetime.strptime(time_utc_str, "%Y-%m-%d %H:%M:%S")).astimezone(timezone).replace(hour=23, minute=59, second=59).astimezone(pytz.utc)

    if (stop_date - start_date).seconds/3600 > 24:
        raise ValueError(f"Start and end times are not on the same day.")
    
    return (start_date, stop_date)


def handle_update_hourly_cache(user_id: int, start_datetime: datetime.datetime, stop_datetime: datetime.datetime):

    metric_cache = MetricHourlyCache.objects.filter(
        user_id=user_id, datetime_updated=start_datetime
    )
    staging_cache = StagingHourlyCache.objects.filter(
        user_id=user_id, datetime_updated=start_datetime
    )
    item = {"user_id": user_id, "datetime_updated": start_datetime}

    medians = get_hourly_medians(
        user_id=user_id,
        start_datetime_utc=start_datetime,
        stop_datetime_utc=stop_datetime,
    )

    if len(medians):
        item.update(medians)
        item.update({"datetime_updated": start_datetime})
    if metric_cache.exists():
        metric_cache.update(**item)
        logging.info(f"Hourly cache data updated for user {user_id}. Data : {item}")
    else:
        MetricHourlyCache.objects.create(**item)
        logging.info(f"Hourly cache data created for user {user_id}. Data : {item}")

    if staging_cache.exists():
        staging_cache.update(**item)
        logging.info(f"HourlyStaging data updated for user {user_id}. Data : {item}")
    else:
        StagingHourlyCache.objects.create(**item)
        logging.info(f"HourlyStaging data created for user {user_id}. Data : {item}")

    return item


def get_hourly_medians( user_id: int, start_datetime_utc: datetime.datetime, stop_datetime_utc: datetime.datetime):

    attribute_sources = {
        "bp_sys": {
            "health_input": "bp_sys",
            "other": "bp_sys",
            "emr": "bp_sys",
            "dtype": int
        },
        "bp_dia": {
            "health_input": "bp_dia",
            "other": "bp_dia",
            "emr": "bp_dia",
            "dtype": int
        },
        "rr": {
            "health_input": "rr",
            "data_table": "rr",
            "emr": "rr",
            "dtype": int
        },
        "hr": {
            "health_input": "hr",
            "data_table": "hr",
            "emr": "hr",
            "dtype": int
        },
        "spo2": {
            "health_input": "spo2",
            "data_table": "spo2",
            "emr": "spo2",
            "dtype": int
        },
        "body_temperature": {
            "health_input": "body_temp",
            "emr": "body_temperature",
            "dtype": float
        },
        "skin_temperature": {
            "data_table": "skin_temperature",
            "dtype": float
        },
        "weight": {
            "health_input": "weight",
            "emr": "weight",
            "dtype": int
        },
        "blood_sugar": {
            "health_input": "blood_sugar",
            "emr": "blood_sugar",
            "dtype": float
        },
        "rr_dc": {
            "data_table": "rr_td",
            "dtype": float
        },
        "rr_td": {
            "data_table": "rr_dc",
            "dtype": float
        },
        "activity": {
            "data_table": "activity",
            "dtype": float
        },
    }

    dataprocessing_df_cols = {}
    healthinput_df_cols = {}
    other_readings_df_cols = {}
    bp_readings_df_cols = {}
    emr_readings_df_cols = {}

    dataprocessing_fields = []
    healthinput_fields = []
    other_readings_fields = []
    bp_readings_fields = []
    emr_readings_fields = []

    has_valid_other_reading   = False

    for attr in attribute_sources:
        if 'data_table' in attribute_sources[attr]:
            dataprocessing_df_cols[attribute_sources[attr]['data_table']] = attr
            dataprocessing_fields.append(attribute_sources[attr]['data_table'])
        if 'health_input' in attribute_sources[attr]:
            healthinput_df_cols[attribute_sources[attr]['health_input']] = attr
            healthinput_fields.append(attribute_sources[attr]['health_input'])
        if 'other' in attribute_sources[attr]:
            bp_readings_df_cols[attribute_sources[attr]['other']] = attr
            bp_readings_fields.append(attribute_sources[attr]['other'])
        if 'emr' in attribute_sources[attr]:
            emr_readings_df_cols[attribute_sources[attr]['emr']] = attr
            emr_readings_fields.append(attribute_sources[attr]['emr'])

    other_readings_fields = bp_readings_fields + emr_readings_fields
    other_readings_df_cols = {**bp_readings_df_cols, **emr_readings_df_cols}

    dataprocessing_instances = DataProcessing.objects.filter(
        user_id=user_id, date_time__range=(start_datetime_utc, stop_datetime_utc)
    ).values()
    dataprocessing_instances_copy = dataprocessing_instances


    # removing bad items --> hence the required extra fields

    dataprocessing_instances = common.remove_bad_data(dataprocessing_instances)

    # filter items by signal quality status

    dataprocessing_instances = common.filter_data_based_on_quality_status(
        dataprocessing_instances, settings.list_quality_to_keep
    )

    dataprocessing_data = [
        {key: d[key] for key in dataprocessing_fields if key in d}
        for d in dataprocessing_instances
    ]


    # convert items to df

    dataprocessing_df = pd.DataFrame(dataprocessing_data)

    dataprocessing_df.rename(columns=dataprocessing_df_cols,errors='ignore', inplace=True)

    healthinput_instances = HealthData.objects.filter(
            user_id=user_id, datetime__range=(start_datetime_utc, stop_datetime_utc)
        )
    if healthinput_instances.exists():
        has_manual_reading  = True
        has_valid_other_reading  = True
    else:
        has_manual_reading  = False

    healthinput_instances = healthinput_instances.values(*healthinput_fields)

    healthinput_instances_df = pd.DataFrame(healthinput_instances)

    healthinput_instances_df.rename(columns=healthinput_df_cols,errors='ignore', inplace=True)

    other_readings_instances = OtherDeviceReading.objects.filter(
            user_id=user_id, datetime__range=(start_datetime_utc, stop_datetime_utc)
        )
    print('other_readings_instances>>>',other_readings_instances,user_id,start_datetime_utc,stop_datetime_utc)

    if other_readings_instances.exists():
        has_valid_other_reading  = True

    other_readings_instances = other_readings_instances.values(*other_readings_fields)

    other_readings_instances_df = pd.DataFrame(other_readings_instances)

    other_readings_instances_df.rename(columns=other_readings_df_cols,errors='ignore', inplace=True)

    # Convert column types
    if not dataprocessing_df.empty:
        for col in dataprocessing_df.columns:
            dataprocessing_df[col] = pd.to_numeric(dataprocessing_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                dataprocessing_df[col] = dataprocessing_df[col].apply(lambda x: round(x, 1))

    # Convert column types
    if not healthinput_instances_df.empty:
        for col in healthinput_instances_df.columns:
            healthinput_instances_df[col] = pd.to_numeric(healthinput_instances_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                healthinput_instances_df[col] = healthinput_instances_df[col].apply(lambda x: round(x, 1))

    # Convert column types
    if not other_readings_instances_df.empty:
        for col in other_readings_instances_df.columns:
            other_readings_instances_df[col] = pd.to_numeric(other_readings_instances_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                other_readings_instances_df[col] = other_readings_instances_df[col].apply(lambda x: round(x, 1))

    df_final = pd.concat([dataprocessing_df, healthinput_instances_df, other_readings_instances_df], ignore_index=True)

    # temperatures should be rounded to 0.1 if they are updated
    df_temp = pd.DataFrame()
    if "body_temperature" in df_final:
        df_temp["body_temperature"] = df_final["body_temperature"]
    if "skin_temperature" in df_final:
        df_temp["skin_temperature"] = df_final["skin_temperature"]

    float_fields = {"body_temperature", "blood_sugar"}

    # .5 always rounds up (DataFrame and Series round function follows banker's rounding - round to closest even number)

    ret = {
        col: (val if col in float_fields else int(val + 0.5))
        for col, val in df_final.median().dropna().items()
    }

    # round the same way to 0.1 precision

    ret.update({
        col: (val if col in float_fields else int(val * 10 + 0.5) / 10)
        for col, val in df_temp.median().dropna().items()
    })


    df_final_sd = df_final.std().dropna().apply(roundNumber)
    df_final_sd.index = df_final_sd.index + "_SD"
    final_sd_dict = df_final_sd.to_dict()
    ret.update(final_sd_dict)

    df_temp_sd = df_temp.std().dropna().apply(roundNumber)
    df_temp_sd.index = df_temp_sd.index + "_SD"
    df_temp_sd_dict = df_temp_sd.to_dict()
    ret.update(df_temp_sd_dict)
    ret.update({'has_manual_reading':has_manual_reading})
    ret.update({'has_valid_other_reading':has_valid_other_reading})

    return ret

def handle_update_daily_cache(user_id: int, start_datetime: datetime.datetime, stop_datetime: datetime.datetime):

    metric_cache = MetricDailyCache.objects.filter(
        user_id=user_id, datetime_updated=start_datetime
    )

    item = {"user_id": user_id, "datetime_updated": start_datetime}
    org_timezone = get_patient_timezone(user_id)
    org_tz = pytz.timezone(org_timezone)
    item['datetime_local'] = start_datetime.astimezone(org_tz).strftime('%Y-%m-%d %H:%M:%S')
    medians = get_daily_medians(
        user_id=user_id,
        start_datetime_utc=start_datetime,
        stop_datetime_utc=stop_datetime,
    )

    if len(medians):
        item.update(medians)
        item.update({"datetime_updated": start_datetime})

        # compute EWS score (NEWS)
        if any(key in ['rr','hr','spo2','bp_sys','body_temperature'] for key in item) :
            try:
                input_for_ews = {
                    "rr": item.get("rr", None),
                    "hr": item.get("hr", None),
                    "spo2": item.get("spo2", None),
                    "bp_sys": item.get("bp_sys", None),
                    "temp": item.get("body_temperature", None),
                }
                class_ews = EarlyWarningScore(input_for_ews)
                item["news"] = class_ews.get_score("NEWS")
            except Exception as e:
                logging.warning(f"error when computing ews. error message is {e}.")
                pass

        # Set the patient's current UTC offset based on their organization timezone
        org_timezone = common.get_patient_timezone(user_id)
        org_tz = pytz.timezone(org_timezone)
        org_time = datetime.datetime.now(org_tz)
        offset_str = f'{org_time.strftime("%z")[0:3]}:{org_time.strftime("%z")[3:]}'
        item["utc_offset"] = offset_str

    if metric_cache.exists():
        metric_cache.update(**item)
        logging.info(f"Daily cache data updated for user {user_id}. Data : {item}")
    else:
        MetricDailyCache.objects.create(**item)
        logging.info(f"Daily cache data created for user {user_id}. Data : {item}")

    if "news" in item:
        news_value = int(item["news"])
        try:
            organization_data = common.fetch_patient_attributes(user_id, ['patient.organization.id'])
            logging.info(f"Fetched organization data for user {user_id}: {organization_data}")
            organization_id = organization_data.get(str(user_id), {}).get('id', "")
            for resolution in ("daily", "minutes"):
                updated_rows = PatientListCache.objects.filter(
                        organization=organization_id, user_id=user_id, resolution=resolution
                    ).update(news=news_value)
                if updated_rows:
                    logging.info(f"[{organization_id}#{user_id}#{resolution}] NEWS score updated in patient list cache")
                else:
                    logging.warning(f"[{organization_id}#{user_id}#{resolution}] No matching record found to update")
        except Exception as e:
            logging.error(f"[{user_id}] NEWS score update in patient list cache failed for daily and minutes, {e}")

        try:
            payload = {
                "data": [
                    {
                        "userId": int(user_id),
                        "source": settings.datasource_to_payload_mapping.get("sensor"),
                        "latestVitals": {
                            "minutes": {"news": news_value},
                            "daily": {"news": news_value},
                        },
                    }
                ]
            }
            mastercache_post_url = urljoin(
                settings.backend_url, settings.UI_URL_REST_API_MASTER_CACHE
            )
            status_code, message = common.backend_service_post_request(mastercache_post_url, payload)
            if status_code in range(200, 300):
                logging.info(f"[NEWS] Master Cache updated successfully for user {user_id}. {message}")
            else:
                logging.warning(f"[NEWS] Failed to update Master Cache for user {user_id}. {message}")
        except Exception as e:
            logging.error(f"Error while preparing payload for Master Cache update for user {user_id}. Error: {str(e)}")

    return item


def get_daily_medians( user_id: int, start_datetime_utc: datetime.datetime, stop_datetime_utc: datetime.datetime):

    attribute_sources = {
        "bp_sys": {
            "health_input": "bp_sys",
            "other": "bp_sys",
            "emr": "bp_sys",
            "dtype": int
        },
        "bp_dia": {
            "health_input": "bp_dia",
            "other": "bp_dia",
            "emr": "bp_dia",
            "dtype": int
        },
        "rr": {
            "health_input": "rr",
            "data_table": "rr",
            "emr": "rr",
            "dtype": int
        },
        "hr": {
            "health_input": "hr",
            "data_table": "hr",
            "emr": "hr",
            "dtype": int
        },
        "spo2": {
            "health_input": "spo2",
            "data_table": "spo2",
            "emr": "spo2",
            "dtype": int
        },
        "body_temperature": {
            "health_input": "body_temp",
            "emr": "body_temperature",
            "dtype": float
        },
        "skin_temperature": {
            "data_table": "skin_temperature",
            "dtype": float
        },
        "weight": {
            "health_input": "weight",
            "emr": "weight",
            "dtype": int
        },
        "blood_sugar": {
            "health_input": "blood_sugar",
            "emr": "blood_sugar",
            "dtype": float
        },
        "rr_dc": {
            "data_table": "rr_td",
            "dtype": float
        },
        "rr_td": {
            "data_table": "rr_dc",
            "dtype": float
        },
        "activity": {
            "data_table": "activity",
            "dtype": float
        },
    }

    dataprocessing_df_cols = {}
    healthinput_df_cols = {}
    other_readings_df_cols = {}
    bp_readings_df_cols = {}
    emr_readings_df_cols = {}

    dataprocessing_fields = []
    healthinput_fields = []
    other_readings_fields = []
    bp_readings_fields = []
    emr_readings_fields = []

    has_valid_other_reading   = False

    for attr in attribute_sources:
        if 'data_table' in attribute_sources[attr]:
            dataprocessing_df_cols[attribute_sources[attr]['data_table']] = attr
            dataprocessing_fields.append(attribute_sources[attr]['data_table'])
        if 'health_input' in attribute_sources[attr]:
            healthinput_df_cols[attribute_sources[attr]['health_input']] = attr
            healthinput_fields.append(attribute_sources[attr]['health_input'])
        if 'other' in attribute_sources[attr]:
            bp_readings_df_cols[attribute_sources[attr]['other']] = attr
            bp_readings_fields.append(attribute_sources[attr]['other'])
        if 'emr' in attribute_sources[attr]:
            emr_readings_df_cols[attribute_sources[attr]['emr']] = attr
            emr_readings_fields.append(attribute_sources[attr]['emr'])


    other_readings_fields = bp_readings_fields + emr_readings_fields
    other_readings_df_cols = {**bp_readings_df_cols, **emr_readings_df_cols}


    dataprocessing_instances = DataProcessing.objects.filter(
        user_id=user_id, date_time__range=(start_datetime_utc, stop_datetime_utc)
    ).values()
    dataprocessing_instances_copy = dataprocessing_instances


    # removing bad items --> hence the required extra fields

    dataprocessing_instances = common.remove_bad_data(dataprocessing_instances)

    # filter items by signal quality status

    dataprocessing_instances = common.filter_data_based_on_quality_status(
        dataprocessing_instances, settings.list_quality_to_keep
    )

    dataprocessing_data = [
        {key: d[key] for key in dataprocessing_fields if key in d}
        for d in dataprocessing_instances
    ]


    # convert items to df

    dataprocessing_df = pd.DataFrame(dataprocessing_data)

    dataprocessing_df.rename(columns=dataprocessing_df_cols,errors='ignore', inplace=True)


    healthinput_instances = HealthData.objects.filter(
            user_id=user_id, datetime__range=(start_datetime_utc, stop_datetime_utc)
        )
    if healthinput_instances.exists():
        has_manual_reading  = True
        has_valid_other_reading   = True
    else:
        has_manual_reading  = False

    healthinput_instances = healthinput_instances.values(*healthinput_fields)

    healthinput_instances_df = pd.DataFrame(healthinput_instances)

    healthinput_instances_df.rename(columns=healthinput_df_cols,errors='ignore', inplace=True)


    other_readings_instances = OtherDeviceReading.objects.filter(
            user_id=user_id, datetime__range=(start_datetime_utc, stop_datetime_utc)
        )

    if other_readings_instances.exists():
        has_valid_other_reading   = True

    other_readings_instances = other_readings_instances.values(*other_readings_fields)

    other_readings_instances_df = pd.DataFrame(other_readings_instances)

    other_readings_instances_df.rename(columns=other_readings_df_cols,errors='ignore', inplace=True)


    # Convert column types
    if not dataprocessing_df.empty:
        for col in dataprocessing_df.columns:
            dataprocessing_df[col] = pd.to_numeric(dataprocessing_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                dataprocessing_df[col] = dataprocessing_df[col].apply(lambda x: round(x, 1))

    # Convert column types
    if not healthinput_instances_df.empty:
        for col in healthinput_instances_df.columns:
            healthinput_instances_df[col] = pd.to_numeric(healthinput_instances_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                healthinput_instances_df[col] = healthinput_instances_df[col].apply(lambda x: round(x, 1))

    # Convert column types
    if not other_readings_instances_df.empty:
        for col in other_readings_instances_df.columns:
            other_readings_instances_df[col] = pd.to_numeric(other_readings_instances_df[col], downcast='integer' if attribute_sources[col]["dtype"] == int else 'float', errors='coerce')

            # If dtype is float, round to 1 decimal place
            if attribute_sources[col]["dtype"] == float:
                other_readings_instances_df[col] = other_readings_instances_df[col].apply(lambda x: round(x, 1))

    df_final = pd.concat([dataprocessing_df, healthinput_instances_df,other_readings_instances_df], ignore_index=True)

    # temperatures should be rounded to 0.1 if they are updated
    df_temp = pd.DataFrame()
    if "body_temperature" in df_final:
        df_temp["body_temperature"] = df_final["body_temperature"]
    if "skin_temperature" in df_final:
        df_temp["skin_temperature"] = df_final["skin_temperature"]


    float_fields = {"body_temperature", "blood_sugar"}

    # .5 always rounds up (DataFrame and Series round function follows banker's rounding - round to closest even number)

    ret = {
        col: (val if col in float_fields else int(val + 0.5))
        for col, val in df_final.median().dropna().items()
    }

    # round the same way to 0.1 precision

    ret.update({
        col: (val if col in float_fields else int(val * 10 + 0.5) / 10)
        for col, val in df_temp.median().dropna().items()
    })

    df_final_sd = df_final.std().dropna().apply(roundNumber)
    df_final_sd.index = df_final_sd.index + "_SD"
    final_sd_dict = df_final_sd.to_dict()
    ret.update(final_sd_dict)

    df_temp_sd = df_temp.std().dropna().apply(roundNumber)
    df_temp_sd.index = df_temp_sd.index + "_SD"
    df_temp_sd_dict = df_temp_sd.to_dict()
    ret.update(df_temp_sd_dict)
    ret.update({'has_manual_reading':has_manual_reading})
    ret.update({'has_valid_other_reading':has_valid_other_reading})

    return ret


def update_cache(user_id, date_time):

    logging.info(f"Starting cache update for user {user_id} at {date_time}.")

    minute_cache_record = MetricMinutesCache.objects.get(user_id = user_id)
    update_patient_list_cache(minute_cache_record,'minutes',None)

    start_date, stop_date = daily_start_stop_timeframe(user_id, date_time)
    daily_response = handle_update_daily_cache(
        user_id= user_id,
        start_datetime=start_date,
        stop_datetime=stop_date,
    )
    update_patient_list_cache(minute_cache_record,'daily',daily_response)

    start_date, stop_date = hourly_start_stop_timeframe(user_id, date_time)
    hourly_response = handle_update_hourly_cache(
        user_id=user_id,
        start_datetime=start_date,
        stop_datetime=stop_date,
    )
    update_patient_list_cache(minute_cache_record,'hourly',hourly_response)

    update_master_cache(minute_cache_record, hourly_response, daily_response)


def update_patient_list_cache(minute_cache_record, resolution, item=None):

    try:
        logging.info(f"Updating patient list cache for user {minute_cache_record.user_id} at {resolution} resolution. Data : {item}")

        if resolution == 'minutes':
            item = vars(minute_cache_record)
        
        logging.info(f"{resolution} cache record data: {item}")

        PATIENT_DETAILS_GET_URL = urljoin(
            settings.UI_URL_REST_API_BASE, settings.UI_URL_REST_API_getPatientDetails
        )
        HEADERS = {
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }
        user_id = item['user_id']

        url = f"{PATIENT_DETAILS_GET_URL}?patientIds={user_id}"

        # Initialize a reusable HTTP session with retry capability.
        # Retry up to `settings.max_retry` times with exponential backoff (`settings.retry_delay_seconds`)
        # for transient server errors defined in `settings.status_forcelist` (e.g., 502, 503, 504, 429)
        # on safe GET requests. Each request will timeout after `settings.max_timeout` seconds.
        session = requests.Session()
        retries = Retry(
            total=settings.max_retry,
            backoff_factor=settings.retry_delay_seconds,
            status_forcelist=settings.status_forcelist,
            allowed_methods=["GET"],
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        response = session.get(url, headers=HEADERS, timeout=settings.max_timeout)

        if response.status_code == 200:
            patient_details = response.json()
            organization_id = patient_details[0]["patient"]["organization"]["id"]
            patient_resolution = patient_details[0]["patient"]["patientResolution"]["resolution"]

            patient_detail = PatientDetail.objects.filter(user_id = user_id)
            if patient_detail.exists():
                patient_detail.update(organization_id = organization_id, resolution = patient_resolution)
            else:
                PatientDetail.objects.create(user_id = user_id,
                    organization_id = organization_id,
                    resolution = patient_resolution
                    )

            cache_dict = {}
            cache_dict["user_id"] = user_id
            cache_dict["organization"] = organization_id
            cache_dict["resolution"] = resolution
            cache_dict["organization_resolution"] = patient_resolution

            if resolution == 'minutes':

                caching_fields = [
                    'hr',
                    'rr',
                    'spo2',
                    'skin_temperature',
                    'activity',
                    'datetime_manual_data_rr',
                    'datetime_manual_data_body_temp',
                    'datetime_manual_data_hr',
                    'datetime_manual_data_weight',
                    'datetime_manual_data_spo2',
                    'datetime_manual_data_blood_sugar',
                    'datetime_manual_data_bp_sys',
                    'datetime_manual_data_bp_dia',
                    'manual_data_rr',
                    'manual_data_blood_sugar',
                    'manual_data_body_temp',
                    'manual_data_weight',
                    'manual_data_bp_dia',
                    'manual_data_spo2',
                    'manual_data_hr',
                    'manual_data_bp_sys',
                    'emr_rr',
                    'emr_blood_sugar',
                    'emr_body_temperature',
                    'emr_weight',
                    'emr_bp_dia',
                    'emr_spo2',
                    'emr_hr',
                    'emr_bp_sys',
                    'datetime_emr_rr',
                    'datetime_emr_body_temperature',
                    'datetime_emr_hr',
                    'datetime_emr_weight',
                    'datetime_emr_spo2',
                    'datetime_emr_blood_sugar',
                    'datetime_emr_bp_sys',
                    'datetime_emr_bp_dia',
                    'other_bp_sys',
                    'other_bp_dia',
                    'datetime_other_bp_sys',
                    'datetime_other_bp_dia',
                    'datetime_latest_valid_chest',
                    'datetime_latest_valid_finger'
                ]

                for field in caching_fields:
                    if field in item:
                        cache_dict[field] = item[field]


            if resolution in  ['daily', 'hourly']:

                caching_fields = ['hr', 'rr', 'spo2', 'skin_temperature', 'activity'] 

                for field in caching_fields:
                    if field in item:
                        cache_dict[field] = item[field]
                        cache_dict[f'datetime_{field}'] = item['datetime_updated']


                cache_dict["user_id"] = user_id
                cache_dict["resolution"] = resolution
                cache_dict["battery"] = minute_cache_record.battery
                cache_dict["battery_chest"] = minute_cache_record.battery_chest
                cache_dict["battery_finger"] = minute_cache_record.battery_finger
                cache_dict["skin_contact_data"] = minute_cache_record.skin_contact_data
                cache_dict["display_label"] = getattr(minute_cache_record, "display_label", val_nan)

            patient_list_cache_record = PatientListCache.objects.filter(user_id = cache_dict['user_id'],resolution=resolution)
            if patient_list_cache_record.exists():
                patient_list_cache_record.update(**cache_dict)
            else:
                PatientListCache.objects.create(**cache_dict)

        else:
            logging.error(f"Backend API {url} failed. Status code is {response.status_code}")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(f"Error in update_patient_list_cache(). error message is {err}")




# def update_master_cache(minute_response, hourly_response, daily_response, minute_cache_record):
def update_master_cache(minute_cache_record, hourly_response, daily_response):
    """
        Update the Master Cache with the latest vitals for a user
        at three resolutions: minutes, hourly, and daily.
    """

    def has_good_skin(skin_contact_list, key='sensor_onskin_status'):
        return any(int(item.get(key, -1)) == 1 for item in skin_contact_list)

    minute_response = minute_cache_record.__dict__.copy()
    minute_response.pop('_state', None)  # Remove Django internal state

    hourly_response = {k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v) for k, v in hourly_response.items()}
    daily_response = {k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v) for k, v in daily_response.items()}
    minute_response = {k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v) for k, v in minute_response.items()}


    logging.info(
        "update_master_cache() called with payloads "
        f"hourly_response : {hourly_response}"
        f"daily_response : {daily_response}"
        f"minute_response : {minute_response}"
    )


    manual_data_mapping = {
        'manual_data_hr' : 'hr',
        'manual_data_rr' : 'rr',
        'manual_data_spo2' : 'spo2',
        'manual_data_bp_dia' : 'bp_dia',
        'manual_data_bp_sys' : 'bp_sys',
        'manual_data_body_temp' : 'body_temp',
        'manual_data_weight' : 'weight',
        'manual_data_blood_sugar' : 'blood_sugar',
        'datetime_manual_data_hr' : 'datetime_hr',
        'datetime_manual_data_rr' : 'datetime_rr',
        'datetime_manual_data_spo2' : 'datetime_spo2',
        'datetime_manual_data_bp_dia' : 'datetime_bp_dia',
        'datetime_manual_data_bp_sys' : 'datetime_bp_sys',
        'datetime_manual_data_body_temp' : 'datetime_body_temp',
        'datetime_manual_data_weight' : 'datetime_weight',
        'datetime_manual_data_blood_sugar' : 'datetime_blood_sugar',
    }


    emr_data_mapping = {
        'emr_hr' : 'hr',
        'emr_rr' : 'rr',
        'emr_spo2' : 'spo2',
        'emr_bp_dia' : 'bp_dia',
        'emr_bp_sys' : 'bp_sys',
        'emr_body_temperature' : 'body_temp',
        'emr_weight' : 'weight',
        'emr_blood_sugar' : 'blood_sugar',
        'datetime_emr_hr' : 'datetime_hr',
        'datetime_emr_rr' : 'datetime_rr',
        'datetime_emr_spo2' : 'datetime_spo2',
        'datetime_emr_bp_dia' : 'datetime_bp_dia',
        'datetime_emr_bp_sys' : 'datetime_bp_sys',
        'datetime_emr_body_temperature' : 'datetime_body_temp',
        'datetime_emr_weight' : 'datetime_weight',
        'datetime_emr_blood_sugar' : 'datetime_blood_sugar',
    }



    other_data_mapping = {
        'other_bp_dia' : 'bp_dia',
        'other_bp_sys' : 'bp_sys',
        'datetime_other_bp_dia' : 'datetime_bp_dia',
        'datetime_other_bp_sys' : 'datetime_bp_sys',
    }

    sensor_data_mapping_minute = {
        'hr' : 'hr',
        'rr' : 'rr',
        'spo2' : 'spo2',
        'skin_temperature' : 'skin_temp',
        'datetime_latest_valid_chest' : 'datetime_latest_valid_chest',
        'datetime_latest_valid_finger' : 'datetime_latest_valid_finger',
        'activity' : 'activity',
    }

    sensor_data_mapping = {
        'hr' : 'hr',
        'rr' : 'rr',
        'spo2' : 'spo2',
        'skin_temperature' : 'skin_temp',
        'body_temperature' : 'body_temp',
        'bp_dia' : 'bp_dia',
        'bp_sys' : 'bp_sys',
        'activity' : 'activity',
    }  

    datasource_mapping = {
        "sensor" : sensor_data_mapping_minute,
        "mhi" : manual_data_mapping,
        "emr" : emr_data_mapping,
        "other" : other_data_mapping,
    }

    datasource_to_payload_mapping = settings.datasource_to_payload_mapping
    resolution_list = ['minutes','hourly','daily']
    minute_vital_keys = ['hr', 'rr', 'spo2', 'skin_temperature', 'activity']



    responses = [minute_response, hourly_response, daily_response]
    latestvital_dict = {
        "userId": None,
        "source": None,
        "latestVitals": {}
    }

    vital_fields_to_convert = ['hr', 'rr', 'spo2', 'skin_temp', 'body_temp', 'bp_dia', 'bp_sys', 'activity', 'weight', 'blood_sugar']

    for resolution, item in zip(resolution_list, responses):
        try:
            is_minute = (resolution == "minutes")
            is_hourly_daily = resolution in ("daily", "hourly")


            user_id = int(item['user_id'])
            if latestvital_dict["userId"] is None:
                latestvital_dict["userId"] = user_id

            if is_minute:
                datasource = (item.get("source") or "").lower()
                latestvital_dict["source"] = datasource_to_payload_mapping.get(datasource, "")
                caching_fields_mapping_dict = datasource_mapping.get(datasource, {})
            else:
                caching_fields_mapping_dict = sensor_data_mapping

            master_cache_dict = {}
            for key, val in caching_fields_mapping_dict.items():
                if key in item:
                    master_cache_dict[val] = float(item[key]) if val in vital_fields_to_convert and item[key] !=None  else item[key]
                    if is_hourly_daily and key != "listdate":
                        master_cache_dict[f"datetime_{val}"] = item.get("datetime_updated")#.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    if is_minute:
                        master_cache_dict[val] = None
                if is_minute and key in minute_vital_keys:
                    if key in ['rr', 'skin_temperature', 'activity']:
                        if item.get("datetime_latest_valid_chest") != None:
                            master_cache_dict[f"datetime_{val}"] = item.get("datetime_latest_valid_chest")#.strftime('%Y-%m-%d %H:%M:%S')
                    if key in ['hr', 'spo2']:
                        if item.get("datetime_latest_valid_finger") != None:
                            master_cache_dict[f"datetime_{val}"] = item.get("datetime_latest_valid_finger")#.strftime('%Y-%m-%d %H:%M:%S')
            latestvital_dict["latestVitals"][resolution] = master_cache_dict
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err = "\n".join(traceback.format_exception(*sys.exc_info()))
            logging.error(f"Error while processing latestvital_dict for user {user_id}, resolution {resolution}, Error: {err}")

    sensor_data = {}
    sensor_data['battery'] = minute_response['battery']
    sensor_data['batteryChest'] = minute_response['battery_chest']
    sensor_data['batteryFinger'] = minute_response['battery_finger']   
   
    skin_contact_data = minute_response['latest_skin_contact']
    skin_contact_dict = {}
    try:
        if skin_contact_data:
            skin_contact_data.sort(key=lambda x: datetime.datetime.strptime(x['date_time'], "%Y-%m-%d %H:%M:%S"), reverse=False)

            hr_list = [d for d in skin_contact_data if d.get("dashboardMode") == "HR"]
            rr_list = [d for d in skin_contact_data if d.get("dashboardMode") == "RR"]

            has_hr_on_skin = has_good_skin(hr_list)
            has_rr_on_skin = has_good_skin(rr_list)
            skin_contact_dict["skinContactFinger"] = "Good" if has_hr_on_skin else "Bad"
            skin_contact_dict["skinContactChest"] = "Good" if has_rr_on_skin else "Bad"
            skin_contact_dict["skinContactGen"] = ("Good" if (has_hr_on_skin or has_rr_on_skin) else "Bad")

        else:
            skin_contact_dict["skinContactGen"] = 'Unknown'
            skin_contact_dict["skinContactChest"] = 'Unknown'
            skin_contact_dict["skinContactFinger"] = 'Unknown'
    except Exception as e:
        logging.error(f"Error while processing skin_contact_data for entry, Error {e}")
        skin_contact_dict["skinContactGen"] = 'Unknown'
        skin_contact_dict["skinContactChest"] = 'Unknown'
        skin_contact_dict["skinContactFinger"] = 'Unknown'


    sensor_data.update(skin_contact_dict)
    latestvital_dict.setdefault("sensorData", {})
    latestvital_dict["sensorData"] = sensor_data

    mastercache_post_url = urljoin(
        settings.backend_url, settings.UI_URL_REST_API_MASTER_CACHE
    )
    output = latestvital_dict
    payload = {"data":[output]}

    status_code, message = common.backend_service_post_request(mastercache_post_url, payload)
    logging.info(f"Sending payload to Master Cache API {mastercache_post_url} for patient {user_id}. Payload: {payload}")
    if status_code in range(200, 300):
        logging.info(f"Master cache post success API {mastercache_post_url} for patient {user_id}.")
    else:
        logging.error(
            f"Master cache post FAILED API {mastercache_post_url} for patient {user_id}."
            f"Status: {status_code}, Response: {message}"
        )
