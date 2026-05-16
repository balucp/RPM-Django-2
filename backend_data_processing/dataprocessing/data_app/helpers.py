import datetime
from datetime import timezone
import numpy as np
import pandas as pd
import copy
import re
import os
import json
import requests
import logging
import pytz
import sys
import traceback
from urllib.parse import urljoin

from dataprocessing import lib_settings as settings
from .models import DataProcessing, HealthData
from . import lib_common as common
from . import lib_query_data_syncing as data_syncing
from .lib_query import (
    get_latest_health_input, EarlyWarningScore, display_battery
    )


def create_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"Create directory {directory}")
    return None


def write_array_to_file(arrayData, filePath):
    np.savetxt(filePath, arrayData, delimiter=",", fmt="%.0f")
    logging.info(f"Save data to {filePath}")
    return


def load_rawdata(filepath):
    read = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.replace("\n", "")
            line = line.split(",")
            line = [int(line[i]) for i in range(len(line))]
            read.append(line)
    return np.array(read)


def convert_str_to_datetime(datetimeInput, set_utc, formatdatetime="%Y-%m-%d %H:%M:%S"):
    output = datetime.datetime.strptime(datetimeInput, formatdatetime)

    if set_utc == True:
        # output = output.astimezone(timezone.utc) # fix datetime field issue (https://github.com/Respiree/hith_data_processisng_backend/issues/108)
        output = output.replace(tzinfo=timezone.utc)
    outputStr = output.strftime(formatdatetime)
    return output, outputStr


def convert_to_datetime_to_utc(
    datetime_input, set_utc, formatdatetime="%Y-%m-%d %H:%M:%S"
):
    output = datetime_input

    if set_utc == True:
        output = datetime_input.replace(tzinfo=timezone.utc)
    else:
        output = datetime_input.replace(tzinfo=None)

    output_str = output.strftime(formatdatetime)
    return output, output_str


def update_backend_latest_vitals(userID, backend_url, backend_auth_key):
    try:
        url = urljoin(backend_url, "/api/data-server/push-latest-vitals")

        payload = {
            "patientVisitIdInt": userID,
        }
        headers = {
            "server-auth-key": backend_auth_key,
            "Content-Type": "application/json",
        }

        response = requests.request(
            "POST", url, headers=headers, json=payload, verify=False
        )
        return response

    except Exception as e:
        logging.error("Unable to update backend on latest vitals: {}".format(e))


def update_sensor_last_connect(sensor_id, host):
    """update sensor last connection time with App backend"""

    backend_url = urljoin(host, settings.UI_URL_REST_API_updateSensorLastConnectionTime)
    last_connection_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload = {"macId": sensor_id, "lastConnectionTime": last_connection_time}
    logging.info(
        {
            "message": "update sensor last connection time in the App server",
            "payload": payload,
            "level": "info",
        }
    )
    auth_key = settings.UI_REST_API_HEADER
    res = requests.request("POST", backend_url, data=payload, headers=auth_key).json()
    return res


def get_gateway_last_connection_time(respiree_id, base_url, path_url):

    gateway_mac_id, gateway_last_connection_time = (
        settings.val_replace_NaN,
        settings.val_replace_NaN,
    )

    try:
        url = urljoin(base_url, path_url)
        input = {
            "id": int(respiree_id),
        }

        resp = requests.get(url, input, verify=False).json()
        logging.info(
            {
                "message": f"Get gateway last connection time from {url}",
                "payload": f"{input}",
                "response": f"{resp}",
            }
        )
    except Exception as e:
        logging.error("get gateway last connection time error ({})".format(e))

    try:
        gateway_mac_id = resp[0]["macId"]
        gateway_last_connection_time = resp[0]["lastConnectionTime"]
    except:
        pass

    return gateway_mac_id, gateway_last_connection_time


def get_scm_vital(respiree_id, current_time, base_url, path_url):

    output = {"bp_sys": settings.val_replace_NaN, "bp_dia": settings.val_replace_NaN}

    try:
        url = urljoin(base_url, path_url)
        logging.info(url)

        start_datetime = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_datetime = start_datetime + datetime.timedelta(days=1)
        logging.info(
            "user_id = {}, start_datetime = {}, end_datetime = {}".format(
                respiree_id, start_datetime, end_datetime
            )
        )

        input = {
            "respireePatientVisitId": int(respiree_id),
            "startDateTime": start_datetime,
            "endDateTime": end_datetime,
        }

        resp = requests.get(url, input, verify=False).json()
        logging.info(resp)

        if len(resp) > 0:
            latest_record = resp[-1]
            bp_sys = latest_record["nibp_s"]
            bp_dia = latest_record["nibp_d"]

            output["bp_sys"] = bp_sys
            output["bp_dia"] = bp_dia

    except Exception as e:
        logging.error("get_scm_vital error ({})".format(e))

    return output


def check_device_status(
    device_last_connection,
    online_if_connection_within,
    datetime_format="%Y-%m-%dT%H:%M:%S.%fZ",
):

    datetimne_device_last_connection = datetime.datetime.strptime(
        device_last_connection, datetime_format
    )

    if (
        datetime.datetime.utcnow() - datetimne_device_last_connection
    ).total_seconds() > online_if_connection_within:
        status = 0
    else:
        status = 1
    return status


def get_object_attribute(obj, attr, default_value):
    value = getattr(obj, attr)
    if value:
        return value
    else:
        return default_value


class Beautify:
    # beautify and and explode a dictionary so it can be used with . (Dot) attributes names
    def __init__(self, entries):
        for key, value in entries.items():
            if isinstance(value, dict):
                self.__dict__.update({key: Beautify(value)})
            else:
                self.__dict__.update({key: value})


def convert_data_datetime_to_str(data, user_id):
    output_converted = {"patientIdInt": int(user_id), "data": {}}
    # Iterate over the keys in the original dictionary and add them to the simplified dictionary
    for key, value in data[user_id].items():
        if isinstance(value, datetime.datetime):
            output_converted["data"][key] = value.strftime("%Y-%m-%d %H:%M:%S")
        else:
            output_converted["data"][key] = value

    return output_converted

def filter_old_entries(item, datetime_treshold):
    mapping = {
        "datetime_latest_valid_chest": ["rr", "body_temperature", "skin_temperature"],
        "datetime_latest_valid_finger": ["hr", "spo2"],
        "datetime_manual_data_hr": ["manual_data_hr"],
        "datetime_manual_data_rr": ["manual_data_rr"],
        "datetime_manual_data_spo2": ["manual_data_spo2"],
        "datetime_manual_data_bp_sys": ["manual_data_bp_sys"],
        "datetime_manual_data_bp_dia": ["manual_data_bp_dia"],
        "datetime_manual_data_blood_sugar": ["manual_data_blood_sugar"],
        "datetime_manual_data_body_temp": ["manual_data_body_temp"],
        "datetime_manual_data_weight": ["manual_data_weight"],
        "datetime_external_data_bp_sys": ["external_bp_sys"],
        "datetime_external_data_bp_dia": ["external_bp_dia"],
    }

    filtered_item = copy.deepcopy(item)

    # if the value originates from earlier then the treshold time, set it to val_NAN
    for datetime_key, key_list in mapping.items():
        if (
            (datetime_key in item)
            and (item[datetime_key] not in [None])
            and (item[datetime_key] < datetime_treshold)
        ):
            for key in key_list:
                filtered_item[key] = settings.val_replace_NaN
    return filtered_item


def handle_list_trigger(output_response_list, user_id, list_resolution, dateTime):

    dt_now_utc = datetime.datetime.now(pytz.utc)
    dt_treshold_utc = dt_now_utc - datetime.timedelta(
        minutes=settings.list_timedelta["MINUTES"]
    )

    data = filter_old_entries(output_response_list[user_id], dt_treshold_utc)
    output_response_list[user_id] = data

    data_processing = DataProcessing.objects.filter(user_id=user_id)
    # common.load_from_cache(output_response_list, user_id,
    #                        list_resolution, dateTime)
    common.get_devices_data(output_response_list, user_id)
    common.get_other_spot_data(
        output_response_list, user_id, list_resolution, dateTime, data_processing
    )

    try:

        current_metric = output_response_list[user_id].copy()

        datetime_start = dateTime - datetime.timedelta(hours=24)

        query_items = HealthData.objects.filter(
            user_id=user_id, datetime__range=[datetime_start, dateTime]
        ).order_by("datetime")
        query_items = list(query_items.values())

        try:
            map_heath_input_metrics_config = {
                "RR_manual": "rr",
                "HR_manual": "hr",
                "SpO2_manual": "spo2",
                "BP_Sys": "bp_sys",
                "BP_Dia": "bp_dia",
                "body_temp_manual": "body_temp",
                "weight_manual": "weight",
                "blood_sugar_manual": "blood_sugar",
            }

            for metric_key, data_key in map_heath_input_metrics_config.items():
                current_metric[metric_key] = get_latest_health_input(
                    query_items, data_key
                )

        except Exception as e:
            logging.error(f"failed to get health input. error message is {e}")

        # compute EWS score (NEWS)
        try:
            input_for_ews = {
                "rr": current_metric["RR"],
                "hr": current_metric["HR"],
                "spo2": current_metric["SpO2"],
                "temp": current_metric["bodyTemp"],
            }
            class_ews = EarlyWarningScore(input_for_ews)
            current_metric["EWS"] = class_ews.get_score("NEWS")
        except Exception as e:
            logging.warning(f"error when computing ews. error message is {e}.")

        output_response_list[user_id] = current_metric

        url_POST_patient_update_trigger_list = urljoin(
            settings.backend_url, settings.UI_URL_REST_API_patientUpdateTriggerList
        )

        output_converted = convert_data_datetime_to_str(output_response_list, user_id)
        output_converted = json.dumps(output_converted)
        logging.info(
            {
                "message": url_POST_patient_update_trigger_list,
                "payload": output_converted,
                "level": "info",
            }
        )
        headers = {
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }
        url_resp = requests.request(
            "POST",
            url_POST_patient_update_trigger_list,
            headers=headers,
            data=output_converted,
        )
        return output_converted

    except requests.exceptions.RequestException as e:
        logging.error("An error occurred:", e)


def convert_data_datetime_to_str1(data, user_id):
    output_converted = {}
    # Iterate over the keys in the original dictionary and add them to the simplified dictionary
    for key, value in data.items():
        if isinstance(value, datetime.datetime):
            output_converted[key] = value.strftime("%Y-%m-%d %H:%M:%S")
        else:
            output_converted[key] = value

    return output_converted

def get_latest_vitals(data: dict, latest_vital_mapping: dict, val_NaN=settings.val_replace_NaN):
    """
    Selects the most recent value for each vital based on mapped datetime fields.
    Adds `latest_<vital>` keys to the result; uses `val_NaN` if no valid data is found.
    """
    def parse_datetime_field(value):
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if isinstance(value, str) else None
        except Exception:
            return None
    result = dict(data)
    for vital, mapping in latest_vital_mapping.items():
        valid_times = []
        for src_field, dt_field in mapping.items():
            try:
                dt = parse_datetime_field(result.get(dt_field))
                reading = result.get(src_field)
                if dt and reading:
                    valid_times.append((dt, src_field))
            except Exception as e:
                logging.error(f"Error parsing datetime for field {dt_field}: {e}")
                continue
        latest = max(valid_times, key=lambda x: x[0], default=(None, None))
        result[f"latest_{vital}"] = result.get(latest[1], val_NaN) if latest[0] else val_NaN
    return result

def handle_list_trigger1(data, user_id, list_resolution, dateTime):

    dt_now_utc = datetime.datetime.now(pytz.utc)
    dt_treshold_utc = dt_now_utc - datetime.timedelta(
        minutes=settings.list_timedelta["MINUTES"]
    )

    data = filter_old_entries(data, dt_treshold_utc)


    # get sensor info
    sensor_data = {user_id: {}}

    # get_devices_data(sensor_data, user_id)
    common.get_devices_data(sensor_data, user_id)

    data_processing = DataProcessing.objects.filter(user_id=user_id)
    # get_other_spot_data(sensor_data, user_id, "minutes", dt_now_utc)
    common.get_other_spot_data(
        sensor_data, user_id, list_resolution, dateTime, data_processing
    )

    data.update(sensor_data[user_id])
    display_battery(data,'realtime-trigger',sensor_data[user_id])

    latest_vital_mapping = {
        "rr": {
            "RR": "dateTime_latest_valid_chest",
            "manual_data_rr": "datetime_manual_data_rr",
            "emr_rr": "datetime_emr_rr"
        },
        "hr": {
            "HR": "dateTime_latest_valid_finger",
            "manual_data_hr": "datetime_manual_data_hr",
            "emr_hr": "datetime_emr_hr"
        },
        "spo2": {
            "SpO2": "dateTime_latest_valid_finger",
            "manual_data_spo2": "datetime_manual_data_spo2",
            "emr_spo2": "datetime_emr_spo2"
        },
        "skinTemp": {
            "skinTemp": "dateTime_latest_valid_chest"
        },
        "bodyTemp": {
            "manual_data_body_temp": "datetime_manual_data_body_temp",
            "emr_body_temperature": "datetime_emr_body_temperature"
        },
        "activity": {
            "activity": "dateTime_latest_valid_chest"
        },
        "bpDia": {
            "manual_data_bp_dia": "datetime_manual_data_bp_dia",
            "emr_bp_dia": "datetime_emr_bp_dia",
            "other_bp_dia": "datetime_other_bp_dia"
        },
        "bpSys": {
            "manual_data_bp_sys": "datetime_manual_data_bp_sys",
            "emr_bp_sys": "datetime_emr_bp_sys",
            "other_bp_sys": "datetime_other_bp_sys"
        }
    }
    data = get_latest_vitals(data, latest_vital_mapping)

    try:
        url_POST_patient_update_trigger_list = urljoin(
            settings.backend_url, settings.UI_URL_REST_API_patientUpdateTriggerList
        )

        output_converted = convert_data_datetime_to_str1(data, user_id)
        output_converted = json.dumps(
            {"patientIdInt": int(user_id), "data": output_converted}
        )

        logging.info(
            {
                "message": url_POST_patient_update_trigger_list,
                "payload": output_converted,
                "level": "info",
            }
        )
        headers = {
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }
        url_resp = requests.request(
            "POST",
            url_POST_patient_update_trigger_list,
            headers=headers,
            data=output_converted,
        )

        return output_converted

    except requests.exceptions.RequestException as e:
        logging.error("An error occurred:", e)


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


def handle_trend_trigger(output_response_trend, user_id, dateTime):

    timezone = get_patient_timezone(user_id)
    timezone = pytz.timezone(timezone)

    # round off to end of day for the stoptime
    stop_datetime = dateTime
    stop_datetime = stop_datetime.astimezone(pytz.utc).replace(tzinfo=None)
    start_datetime = dateTime - datetime.timedelta(days=3)

    # Get the midnight time in the UTC timezone for the patient timezone
    dt_timezone = start_datetime
    midnight_timezone = datetime.time(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc_timezone = timezone.localize(
        datetime.datetime.combine(dt_timezone.date(), midnight_timezone)
    ).astimezone(pytz.utc)

    # Replace the time in dt with midnight_utc_timezone's time
    start_datetime = start_datetime.replace(
        hour=midnight_utc_timezone.hour,
        minute=midnight_utc_timezone.minute,
        second=midnight_utc_timezone.second,
    )

    data_length = (stop_datetime - start_datetime).days + 1

    # Get the timezone offset as a timedelta object
    date_time_now = datetime.datetime.utcnow()
    offset = timezone.utcoffset(date_time_now)

    # Calculate the offset hours and minutes
    offset_hours = int(offset.total_seconds() / 3600)
    offset_minutes = int((offset.total_seconds() % 3600) / 60)

    # Format the output as a tuple [x, y]
    utc_offset = [offset_hours, offset_minutes]
    output_response_trend = data_syncing.get_data_syncing_trends(
        user_id,
        start_datetime,
        stop_datetime,
        data_length,
        "daily",
        settings.val_replace_NaN,
        "datetime_sensor",
        utc_offset,
    )

    url_POST_patient_update_trigger_trend = urljoin(
        settings.backend_url, settings.UI_URL_REST_API_patientUpdateTriggerTrend
    )

    try:
        output_response_trend = {user_id: output_response_trend}
        output_converted = convert_data_datetime_to_str(output_response_trend, user_id)
        output_converted = json.dumps(output_converted)
        logging.info(
            {
                "message": url_POST_patient_update_trigger_trend,
                "payload": output_converted,
                "level": "info",
            }
        )
        headers = {
            "accept": "*/*",
            "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
            "Content-Type": "application/json",
        }

        url_resp = requests.request(
            "POST",
            url_POST_patient_update_trigger_trend,
            headers=headers,
            data=output_converted,
        )
        return output_converted

    except requests.exceptions.RequestException as e:
        logging.error("An error occurred:", e)


def check_if_utc_format(utc_offset):
    pattern = r"^[+\-]?\d{2}:\d{2}$"

    if re.match(pattern, utc_offset.strip()):
        return True
    else:
        return False


def get_utc_offset(utc_offset):
    if utc_offset[0] == "-":  # negative offset
        utc_offset = utc_offset.replace("-", "")  # remove - sign
        utc_offset = utc_offset.split(":")

        utc_offset_hour = -int(utc_offset[0])
        utc_offset_minute = -int(utc_offset[1])
    else:
        utc_offset = utc_offset.replace("+", "")  # remove + sign
        utc_offset = utc_offset.split(":")

        utc_offset_hour = int(utc_offset[0])
        utc_offset_minute = int(utc_offset[1])

    utc_offset = [utc_offset_hour, utc_offset_minute]
    return utc_offset


def convert_datetime_format(timesatmp):
    # convert to 'yyyy-mm-ddThh:mm:ss+0000'
    output = timesatmp.replace(" ", "T")
    output = f"{output}+0000"
    return output


def generate_timenow():
    timenow = str(datetime.datetime.utcnow())
    timenow = timenow.split(".")[0]
    return timenow


default_template = {
    "URL": None,
    "HEADERS": {
        "Content-Type": "application/json",
        # "Content-Encoding": "utf-8",
        "Authorization": None,
    },
    "VALID_MODE": ["RR", "HR"],
    "PAYLOAD_TEMPLATE": {
        "datetime_chest": None,
        "datetime_finger": None,
        "RR": None,
        "TD": None,
        "DC": None,
        "SpO2": None,
        "HR": None,
        "signal_quality": None,
        "activity": None,
        "skin_temperature": None,
        "sensor_id": None,
        "battery": None,
        "flag": None,
    },
    "VAL_NAN": -1,
    "METHOD": 1,  # default
}


integration_organization_config_dict = {
    "default": default_template,
    "TEMUS Test": {
        "URL": "https://SafeOpsDevIOTHub.azure-devices.net/devices/dover123/messages/events?api-version=2018-04-01",
        "HEADERS": {
            "Content-Type": "application/json",
            "Content-Encoding": "utf-8",
            "Authorization": "SharedAccessSignature sr=SafeOpsDevIOTHub.azure-devices.net%2Fdevices%2Fdover123&sig=fEG1XNypz4jVKYpLhYg4%2B5fZajajbfiHttW7AwmbOHI%3D&se=1711784419",
        },
        "VALID_MODE": ["RR"],
        "PAYLOAD_TEMPLATE": {
            "datetime": None,
            "RR": None,
            "activity": None,
            "skin_temperature": None,
            "sensor_id": None,
            "battery": None,
            "flag": None,
            "cid": "Fac-0dec",
        },
        "VAL_NAN": -1,
        "METHOD": 2,
    },  # config for Temus integration
}


default_template = {
        "URL": None,
        "HEADERS": {
            "Content-Type": "application/json",
            # "Content-Encoding": "utf-8",
            "Authorization": None
        },
        "VALID_MODE": ["RR", "HR"],
        "PAYLOAD_TEMPLATE": {
            "datetime_chest": None,
            "datetime_finger": None,
            "RR": None,
            "TD": None,
            "DC": None,
            "SpO2": None,
            "HR": None,
            "signal_quality": None,
            "activity": None,
            "skin_temperature": None,
            "sensor_id": None,
            "battery": None,
            "flag": None,
        },
        "VAL_NAN": -1,
        "METHOD": 1, # default
        "JSON_DUMPS_PAYLOAD": False
    }


integration_organization_config_dict = {
    "default": default_template,
    "TEMUS Test": {
        "URL": "https://SafeOpsDevIOTHub.azure-devices.net/devices/dover123/messages/events?api-version=2018-04-01",
        "HEADERS": {
            "Content-Type": "application/json",
            "Content-Encoding": "utf-8",
            "Authorization": "SharedAccessSignature sr=SafeOpsDevIOTHub.azure-devices.net%2Fdevices%2Fdover123&sig=fEG1XNypz4jVKYpLhYg4%2B5fZajajbfiHttW7AwmbOHI%3D&se=1711784419"
        },
        "VALID_MODE": ["RR"],
        "PAYLOAD_TEMPLATE": {
            "datetime": None, #
            "RR": None,
            "activity": None,
            "skin_temperature": None,
            "sensor_id": None,
            "battery": None,
            "flag": None,
            "cid": "Fac-0dec" #
        },
        "VAL_NAN": -1,
        "METHOD": 2,
        "JSON_DUMPS_PAYLOAD": False
    }, # config for Temus integration
    "Intellibridge": {
        "HEADERS": {
            "Content-Type": "application/json",
            "Content-Encoding": "utf-8",
        },
        "VALID_MODE": ["RR", "HR"],
        "PAYLOAD_TEMPLATE": {
            "timestamp": None,
            "patient_id": None,
            "data": {
                "rr": None,
                "hr": None,
                "spo2": None,
                "rr_td": None,
                "rr_dc": None,
                "skin_temperature": None,
                "activity": None,
                "chest_signal_quality": None,
                "finger_signal_quality": None,
                "finger_skin_contact": None,
                "chest_skin_contact": None,
                "risk_probability": None,
            },
            "device": {
                "sensor_name": None,
                "gateway_name": None,
                "sensor_battery": None,
            },
        },
        "VAL_NAN": -1,
        "METHOD": 3,
        "JSON_DUMPS_PAYLOAD": True,
        "CERTIFICATE": {
            "BUCKET_NAME": None,
            "CERT_KEY": "certs/client_cert.pem",
            "PRIVATE_KEY": "certs/client_key.pem",
            "CA_KEY": "certs/ca_bundle.pem",
            "CERT_PATH": "/tmp/client_cert.pem", # Temporary file paths in AWS Lambda
            "KEY_PATH": "/tmp/client_key.pem",
            "CA_PATH": "/tmp/ca_bundle.pem",
        }
    },
}

def convert_small_to_caps(data: dict, field_reference: dict):
    """
    data: data dictionary where fields need to convert
    field_refernce: dictionary contain primary to secondary field reference
                    for eg: {"hr": HR, "rr_td": "RR_TD"}
    """

    data_copy = copy.deepcopy(data)
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                data_copy[key] = convert_small_to_caps(value, field_reference)
            elif field_reference.get(key):
                del data_copy[key]
                data_copy[field_reference.get(key)] = value
    return data_copy

def merge_dataframes_allow_empty(df1, df2, key, merge_method='outer'):
    """
    Safely merge two pandas DataFrames using an outer join.

    This function handles cases where either or both DataFrames may be empty:
    - If both DataFrames are empty, returns an empty DataFrame containing only the merge key.
    - If one DataFrame is empty, returns a copy of the non-empty DataFrame.
    - Otherwise, performs a standard outer merge on the specified key.
    """
    combined_cols = list(set(df1.columns).union(df2.columns))
    if df1.empty and df2.empty:
        return pd.DataFrame(columns=combined_cols)

    if df1.empty:
        return df2.copy().reindex(columns=combined_cols, fill_value=pd.NA)

    if df2.empty:
        return df1.copy().reindex(columns=combined_cols, fill_value=pd.NA)

    return pd.merge(df1, df2, on=key, how=merge_method)
