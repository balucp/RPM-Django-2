from decimal import Decimal
from celery import shared_task
from .models import DataProcessing, ApiDataSentOut, SpotCache, Staging
from .helpers import *
from . import processing as prepro
from . import lib_update_metric_cache
from . import lib_processing_wavelets
from . import lib_update_spot_cache
from dataprocessing import lib_settings as settings
import logging
import numpy as np
from data_app import lib_update_compliance as compliance
from . import lib_common as common

def reset_dict_values(d):
    for key in d:
        if isinstance(d[key], dict):
            reset_dict_values(d[key])  # Recursively reset nested dictionaries
        else:
            d[key] = None

def send_data(url, headers, payload):
    res = None
    try:
        res = requests.request(url=url, method='POST',
                               json=payload, headers=headers)
        logging.info({
            "message": f"Send data to the client endpoint. Response: {res}",
            "level": "info",
            "payload": payload,
            "url": url,
            "headers": headers,
            "status_code": res.status_code
        })
    except Exception as e:
        logging.info({
            "message": str(e),
            "level": "info",
            "payload": payload,
            "url": url,
            "headers": headers,
        })
    return res


def save_to_staging(data_processing, payload, method):

    if method == 1:
        staging_record = {
        "dateTimeUpdated": data_processing.date_time,
        "patient_id": payload["patient_id"],
        "rr": payload["RR"],
        "hr": payload["HR"],
        "spo2": payload["SpO2"],
        "rr_td": payload["TD"],
        "rr_dc": payload["DC"],
        "skin_temperature": payload["skin_temperature"],
        "activity": payload["activity"],
        "sensor_battery": payload["battery"],
        }
        if 'signal_quality_status'in payload:
            staging_record['chest_signal_quality'] = payload["signal_quality_status"]

    if method == 2:
        staging_record = {
        "dateTimeUpdated": data_processing.date_time,
        "patient_id": payload["patient_id"],
        "rr": payload["RR"],
        "skin_temperature": payload["skin_temperature"],
        "activity": payload["activity"],
        "sensor_battery": payload["battery"],
        }

    if method == 3:
        staging_record = {
        "timestamp": payload["timestamp"],
        "patient_id": payload["patient_id"],
        "rr": payload["data"]["rr"],
        "hr": payload["data"]["hr"],
        "spo2": payload["data"]["spo2"],
        "rr_td": payload["data"]["rr_td"],
        "rr_dc": payload["data"]["rr_dc"],
        "skin_temperature": payload["data"]["skin_temperature"],
        "activity": payload["data"]["activity"],
        "chest_signal_quality": payload["data"]["chest_signal_quality"],
        "finger_signal_quality": payload["data"]["finger_signal_quality"],
        "finger_skin_contact": payload["data"]["finger_skin_contact"],
        "chest_skin_contact": payload["data"]["chest_skin_contact"],
        "sensor_name": payload["device"]["sensor_name"],
        "gateway_name": payload["device"]["gateway_name"],
        "sensor_battery": payload["device"]["sensor_battery"],
        }

    staging_record = {k: v for k, v in staging_record.items() if v not in (None, -1)}
    staging_record['user_id'] = data_processing.user_id
    Staging.objects.create(**staging_record)

    logging.info(
        {
            "message": f"record added to staging",
            "level": "info",
            "data": staging_record,
        }
    )


def execute(data_processing, config, extra_data_dict):

    # init config for the test env client
    URL = config["URL"]
    HEADERS = config["HEADERS"]
    VALID_MODE = config["VALID_MODE"]
    payload = config["PAYLOAD_TEMPLATE"].copy()
    VAL_NAN = config["VAL_NAN"]
    METHOD = config["METHOD"]
    CERTIFICATE = config.get("CERTIFICATE")
    JSON_DUMPS_PAYLOAD = config.get("JSON_DUMPS_PAYLOAD")

    dashboard_mode = data_processing.dashboard_mode

    # check if mode is valid
    if dashboard_mode in VALID_MODE:

        if METHOD == 1:  # default
            payload.update({
                "sensor_id": data_processing.sensor_id,
                "battery": int(data_processing.battery) if data_processing.battery else VAL_NAN,
                "flag": 0
            })

            if dashboard_mode == "RR":
                payload.update({
                    "activity": data_processing.activity_percentage,
                    "skin_temperature": float(data_processing.skin_temperature) if data_processing.skin_temperature else VAL_NAN,
                    "signal_quality": data_processing.signal_quality_status,
                    "datetime_chest": data_processing.date_time.strftime('%Y-%m-%d %H:%M:%S')
                })

                if str(data_processing.rr) not in ["nan"]:
                    payload.update({
                        "RR": int(data_processing.rr) if data_processing.rr else VAL_NAN,
                        "TD": data_processing.rr_td,
                        "DC": data_processing.rr_dc,
                    })

                # if off skin, set flag and mask RR
                if data_processing.sensor_onskin_status == 0:
                    payload.update({
                        "flag": 1,
                        "RR": VAL_NAN,
                        "TD": VAL_NAN,
                        "DC": VAL_NAN,
                    })

            if dashboard_mode == "HR":

                payload["datetime_finger"] = data_processing.date_time.strftime('%Y-%m-%d %H:%M:%S')

                if str(data_processing.hr) not in ["nan"]:
                    payload["HR"] = int(
                        data_processing.hr) if data_processing.hr else VAL_NAN

                if str(data_processing.spo2) not in ["nan"]:
                    payload["SpO2"] = int(
                        data_processing.spo2) if data_processing.spo2 else VAL_NAN

                # if off skin, set flag and mask RR
                if data_processing.sensor_onskin_status == 0:
                    payload.update({
                        "flag": 1,
                        "HR": VAL_NAN,
                        "SpO2": VAL_NAN
                    })

        if METHOD == 2:  # customized
            # update payload
            payload.update({
                "datetime": data_processing.date_time.strftime('%Y-%m-%d %H:%M:%S'),
                "activity": data_processing.activity_percentage,
                "skin_temperature": float(data_processing.skin_temperature) if data_processing.skin_temperature else VAL_NAN,
                "sensor_id": data_processing.sensor_id,
                "battery": int(data_processing.battery) if data_processing.battery else VAL_NAN,
                "flag": 0
            })

            if str(data_processing.rr) not in ["nan"]:
                payload["RR"] = int(
                    data_processing.rr) if data_processing.rr else VAL_NAN

            # if off skin, set flag and mask RR
            if data_processing.sensor_onskin_status == 0:
                payload["flag"] = 1
                payload["RR"] = VAL_NAN


        elif METHOD == 3:  # customized

            reset_dict_values(payload)

            # update payload
            payload["timestamp"] = data_processing.date_time.strftime('%Y-%m-%d %H:%M:%S')
            payload["patient_id"] = extra_data_dict["patient_id"]
            payload["device"]["sensor_name"] = extra_data_dict["sensor_name"]
            payload["device"]["gateway_name"] = extra_data_dict["gateway_name"]
            payload["device"]["sensor_battery"] = data_processing.battery
            payload["data"]["risk_probability"] = None

            if dashboard_mode == "RR":

                payload["data"]["skin_temperature"] = data_processing.skin_temperature
                payload["data"]["activity"] = data_processing.activity
                payload["data"]["chest_signal_quality"] = data_processing.signal_quality_status
                payload["data"]["chest_skin_contact"] = data_processing.sensor_onskin_status

                if (data_processing.rr not in [None, "nan"]) and (
                    data_processing.sensor_onskin_status == 1
                ):
                    payload["data"]["rr"] = data_processing.rr
                    payload["data"]["rr_td"] = data_processing.rr_td
                    payload["data"]["rr_dc"] = data_processing.rr_dc

            elif dashboard_mode == "HR":

                payload["data"]["finger_skin_contact"] = data_processing.sensor_onskin_status

                if item["display_label"] == 1:  # indicate that finger data is good
                    payload["data"]["hr"] = data_processing.hr
                    payload["data"]["spo2"] = data_processing.spo2
                    payload["data"]["finger_signal_quality"] = "Good"
                else:
                    payload["data"]["finger_signal_quality"] = "Bad"

        save_to_staging(data_processing, payload, METHOD)

        if JSON_DUMPS_PAYLOAD:
            payload = json.dumps(payload)

        # send to client
        res = send_data(URL, HEADERS, payload)
        res_status_code = res.status_code if res else VAL_NAN

        logging.info({
            "message": f"attemp to send data to the defined endpoint",
            "level": "info",
            "payload": payload,
            "config": config,
        })

    else:
        res_status_code = VAL_NAN
        logging.info({
            "message": f"data is not forwarded to any endpoint. invalid sensor mode",
            "level": "info"
        })

    return payload, res_status_code


def convert_floats_to_decimals(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(elem) for elem in obj]
    else:
        return obj


def get_patient_organization_detail(user_id, **api_config):

    url = f"{api_config['url_base']}{api_config['url_path']}"

    headers = {
        "accept": "*/*",
        "server-auth-key": api_config['headers']['server-auth-key'],
        "Content-Type": "application/json"
    }
    url_resp = None

    try:
        url_resp = requests.get(url, params={"patientIds": user_id}, headers=headers)
    except Exception as e:
        logging.info({
            "message": str(e),
            "level": "error",
            "url": url
        })


    output = {}

    try:
        url_resp = url_resp.json()[0]

        output.update({
            'organization_name': url_resp["patient"]["organization"]["name"],
            'organization_api_enabled': url_resp["patient"]["organization"]["organizationSettings"]["enableClientApi"],
            'data_push_url': url_resp["patient"]["organization"]["organizationSettings"]["clientApiPostRegistrationDataPushUrl"],
            'data_push_token': url_resp["patient"]["organization"]["organizationSettings"]["clientApiAuthToken"],
        })
    except Exception as e:
        output.update({
            'organization_name': "",
            'organization_api_enabled': None,
            'data_push_url': None,
            'data_push_token': None,
        })
        logging.error({
            "message": f"Fail to extract organization settings from the API response. Exception error message is {e}",
            "level": "error"
        })
    return output


def get_patient_info(user_id, dashboard_mode):
    url_get_devices = urljoin(
        settings.UI_URL_REST_API_BASE,
        settings.UI_URL_REST_API_getMultiplePatientDevicesInfo,
    )

    res = requests.get(
        url_get_devices,
        headers=settings.UI_REST_API_HEADER,
        params={"patientIdArray": [user_id]},
    )
    res = res.json()

    res_sensors = res[user_id][0]["sensors"]

    if dashboard_mode == res_sensors[0]["sensorType"]:
        res_sensor = res_sensors[0]
    elif dashboard_mode == res_sensors[1]["sensorType"]:
        res_sensor = res_sensors[1]

    sensor_name = res_sensor["name"]
    gateway_name = res[user_id][0]["gateways"][0]["name"]
    patient_id = res[user_id][0]["userId"]

    return sensor_name, gateway_name, patient_id


def send_data_to_client(data_processing):

    bool_data_is_sent = False
    # check config of the user's organization
    response_org = get_patient_organization_detail(user_id=data_processing.user_id, url_base=settings.backend_url,
                                                   url_path=settings.UI_URL_REST_API_getPatientDetails, headers=settings.UI_REST_API_HEADER)
    # check if API is enabled
    if response_org.get("organization_api_enabled"):

        try:
            # use customized config for the organization
            config = integration_organization_config_dict[response_org["organization_name"]]
        except:
            config = integration_organization_config_dict['default']

        config['URL'] = response_org.get('data_push_url')
        config['HEADERS']['Authorization'] = response_org.get(
            'data_push_token')

        logging.info({
            "message": f"organization_api_enabled is True. start processing the payload",
            "level": "info",
            "load_config": config
        })

        try:
            sensor_name, gateway_name, patient_id = get_patient_info(
                data_processing.user_id, data_processing.dashboard_mode
            )
        except Exception as e:
            sensor_name, gateway_name, patient_id = None, None, None

        extra_data_dict = {}
        extra_data_dict["sensor_name"] = sensor_name
        extra_data_dict["gateway_name"] = gateway_name
        extra_data_dict["patient_id"] = patient_id
        
        payload, res_status_code = execute(data_processing, config,extra_data_dict)

        if res_status_code in [200, 204]:
            bool_data_is_sent = True
            ApiDataSentOut.objects.get_or_create(
                user_id=data_processing.user_id, datetime_server_received=data_processing.datetime_server_received,
                config=convert_floats_to_decimals(config), date_time=data_processing.date_time,
                datetime_data_sent=generate_timenow(), organization_setting=response_org,
                payload=convert_floats_to_decimals(payload), response_status_code=res_status_code
            )
    else:
        logging.info({
            "message": f"API integration is not enabled for this user id.",
            "level": "info"
        })
    return bool_data_is_sent


@shared_task(name="calculate_metric")
def calculate_metric(user_id, date_time, previous_packet_size,
                     total_packet, packet_number, datetime_server_received,
                     dashboard_mode, hardware_mode):
    data_processing = DataProcessing.objects.filter(
        user_id=user_id, date_time=date_time)
    query_value = data_processing.values()

    if len(query_value) > 0:
        updated_packet_size = query_value[0]['packet_number']
        updated_packet_size = len(updated_packet_size.split(','))

        is_calculated = query_value[0]['is_calculated']

        current_data = {
            "user ID": user_id,
            "date_time": date_time,
            "datetime_server_received": datetime_server_received,
            "dashboard_mode": dashboard_mode,
            "hardware_mode": hardware_mode,
            "previous_packet_size": previous_packet_size,
            "updated_packet_size": updated_packet_size,
            "packet_number": packet_number,
            "total_packet": total_packet,
            "is_calculated": is_calculated
        }

        logging.info(f"Received data --> {current_data}")

        flag_calculation = False
        if is_calculated: #TODO: check if this is needed
            logging.info('Skip (this record has already been calculated)')
        else:
            if updated_packet_size >= total_packet:
                logging.info('start calculation (alr received all packets)')
                flag_calculation = True
            elif updated_packet_size == previous_packet_size:
                logging.info('start calculation (as no new packet coming)')
                flag_calculation = True
            else:
                logging.info(
                    'Received new packet ===> do not proceed to calcaulate metric')

        if flag_calculation:
            logging.info('RUN CALCULATION FUNCTION')

            filePath = query_value[0]['filepath']
            data = load_rawdata(filePath)
            item_update = {}

            """ Handle ACCL issue (value is 0)"""
            if dashboard_mode=="RR":

                try:
                    data, is_error_detected_0 = prepro.handle_accl_issue(data, 0)
                    # item["is_accl_issue_detected"] = is_error_detected

                    data, is_error_detected_2048 = prepro.handle_accl_issue(data, value_to_detect=4096/2)
                    # item["is_accl_issue_detected"] = is_error_detected

                    if (is_error_detected_0 == 1) or (is_error_detected_2048 == 1):
                        is_error_detected = 1
                    else:
                        is_error_detected = 0

                    if is_error_detected:
                        logging.warning({
                            "message": f"ACCL issue detected and handled in RR mode",
                            "level": "warning",
                        })

                        euclidean_distances = prepro.calculate_euclidean_distance(data[:, 3], data[:, 4], data[:, 5])
                        data[:, 2] = euclidean_distances

                except Exception as e:
                    logging.error({
                        "message": f"Fail to calculate euclidean distance after handling ACCL issue. Exception error message is {e}",
                        "level": "error",
                    })

            try:
                item_update['filename'] = filePath
                item_update = prepro.pipeline_calculation(
                    dashboard_mode, hardware_mode, data, filePath, item_update, query_value)

                logging.info(
                    'PROCESSED: {} --> {}'.format(filePath, current_data))

            except Exception as e:
                logging.error(
                    'pipeline_calculation Failed: {} --> {}'.format(e, current_data))

                if dashboard_mode == "RR":
                    item_update["skin_temperature"] = -1  # off skin
                    item_update["rr"] = str(np.nan)
                    item_update["sensor_onskin_status"] = 0
                    item_update["rr_sd"] = str(np.nan)
                elif dashboard_mode == "HR":
                    item_update["accepted_frame_spo2_ratio"] = -1  # off skin
                    item_update["val_sd_signal_w_sqa"] = -1
                    item_update["hr"] = str(np.nan)
                    item_update["spo2"] = str(np.nan)
                    item_update["sensor_onskin_status"] = 0
                    item_update["hr_sd"] = str(np.nan)
                    item_update["spo2_sd"] = str(np.nan)

                item_update["error_pipeline_calculation"] = 1

            try:
                
                # check data length. if data length is lesser than threshold, set it as invalid
                # get data length (record server received)
                data_length = len(data)

                # get threshold accoirding to mode
                threshold_min_length_compute_metric = settings.threshold_min_length_compute_metric

                item_update["debug_data_length_too_short"] = {
                    "threshold": threshold_min_length_compute_metric,
                    "is_shorter_than_threshold": 0
                }

                val_nan = settings.val_replace_NaN
                is_data_shorter_than_threshold = False

                # compare threshold with data length
                if (dashboard_mode == "RR") and (data_length < threshold_min_length_compute_metric["RR"]):
                    item_update["rr"] = "nan"
                    item_update["sensor_onskin_status"] = val_nan
                    is_data_shorter_than_threshold = True

                # compare threshold with data length
                if (dashboard_mode == "HR"):

                    if data_length < threshold_min_length_compute_metric["HR"]:
                        item_update["hr"] = "nan"
                        is_data_shorter_than_threshold = True

                    if data_length < threshold_min_length_compute_metric["SpO2"]:
                        item_update["spo2"] = "nan"
                        is_data_shorter_than_threshold = True

                    if data_length < threshold_min_length_compute_metric["finger_on_skin_algo"]:
                        item_update["sensor_onskin_status"] = val_nan
                        is_data_shorter_than_threshold = True

                if is_data_shorter_than_threshold:
                    item_update["debug_data_length_too_short"]["is_shorter_than_threshold"] = 1
                    item_update["debug_data_length_too_short"]["data_length"] = data_length
                    logging.warning(
                        f"data {dashboard_mode} lenght is {data_length}. shorter than threshold {threshold_min_length_compute_metric}")

            except:
                logging.error("error when verifying data length")

            if dashboard_mode == 'RR' and settings.BOOL_COMPUTE_HR_FROM_CHEST:  # if RR mode, extract HR from chest
                # Wavelets Transform To Extract Heart Rate From Chest (RR mode)

                logging.info({
                    "message": f"Start computing HR from the chest using Wavelets Transform",
                    "level": "info"
                })

                if hardware_mode == 'respiratory-rate':
                    params_wt = settings.initParameters('wavelets_HR_60ms')
                elif hardware_mode == 'pulse-oximetry':
                    params_wt = settings.initParameters('wavelets_HR_40ms')

                try:
                    data_pd = data[:, 1]
                    timestamp = np.arange(len(data_pd)) * \
                        params_wt['sampling_time']

                    data_input = np.array([timestamp, data_pd]).T

                    waveletsTransform = lib_processing_wavelets.calculate_bpm_using_dwt(
                        data_input, params_wt)
                    waveletsTransform.run_calculation_wt()

                    temp_output_wt = waveletsTransform.output_feature
                    output_wt = {}
                    for key in temp_output_wt.keys():
                        if key in ['cwt_time', 'time']:
                            continue

                        output_wt[key] = prepro.process_output(
                            temp_output_wt[key], 2)

                    item_update.update({
                        'wavelets_transform': output_wt,
                        'hr_chest': output_wt['maxPeak mean + median']
                    })

                except Exception as e:
                    logging.error({
                        "message": f"Extracting HR from chest using Wavelets Transform failed. Exception error message is {e}",
                        "level": "error",
                    })

                    item_update['hr'] = str(np.nan)

            if dashboard_mode == 'RR':
                data_accl = data[:, 2]

                # Step Count
                try:
                    logging.info({
                        "message": f"Start calculating step count",
                        "level": "info",
                    })
                    stepcount = prepro.calculate_stepcount(
                        data_accl,
                        delta=settings.stepcount_algo_delta,
                        wsize=settings.stepcount_algo_mva_wsize
                    )
                    item_update['activity_step'] = stepcount

                except Exception as e:
                    logging.error({
                        "message": f"Fail to calculate step count. Exception error message is {e}",
                        "level": "error",
                    })

                """ Start calculating sleep and awake """
                try:
                    logging.info({
                        "message": f"Start calculating sleep and awake",
                        "level": "info",
                    })

                    params_activeness = settings.initParameters('RR-60ms')
                    params_activeness['window_mva'] = settings.activeness_wsize_mva
                    params_activeness['window_bl'] = settings.activeness_wsize_bl

                    point_sleep, point_awake = prepro.calculate_activeness(
                        data_accl, settings.activeness_threshold, params_activeness, settings.activeness_mask_size_seconds)

                    item_update['point_sleep'] = point_sleep
                    item_update['point_awake'] = point_awake

                    # calculate activity percentage
                    try:
                        total_point_activity = point_sleep + point_awake
                        percentage_activity = int(
                            (point_awake/total_point_activity)*100)
                        percentage_sleep = 100 - percentage_activity
                    except:
                        percentage_activity = settings.val_replace_NaN
                        percentage_sleep = settings.val_replace_NaN

                    item_update['activity'] = percentage_activity

                    # calculate sleep duration (seconds)
                    if percentage_sleep > 5:  # assume no motion when sleeping
                        sleep_duration_seconds = int(
                            item_update['record_received_by_gateway']) * params_activeness['sampling_time']
                    else:
                        sleep_duration_seconds = 0
                    item_update['sleep_duration_seconds'] = Decimal("{:.2f}".format(sleep_duration_seconds))

                except Exception as e:
                    logging.error({
                        "message": f"Fail to calculate sleep and awake. Exception error message is {e}",
                        "level": "error",
                    })

                # calculate calories burned
                try:
                    logging.info({
                        "message": f"Start calculating calories burned",
                        "level": "info"
                    })

                    calories = prepro.calories_burned(stepcount)

                    item_update['activity_calories'] = calories

                except Exception as e:
                    logging.error({
                        "message": f"Fail to calculate calories_burned. Exception error message is {e}",
                        "level": "error"
                    })

            item_update['date_time'] = query_value[0]['datetime_sensor']
            item_update['record_server_received'] = len(data)
            item_update['is_calculated'] = True
            
            # calculate body temperature
            #TODO:Than. this should be excecute before entering this if else
            try:
                if dashboard_mode == 'RR':
                    
                    skin_temperature, num_temperature_out_of_range = prepro.extract_temperature(
                        data[:,6], 
                        settings.error_handling_minmax_skin_temperature_value_bool, 
                        settings.error_handling_minmax_skin_temperature_value
                        )

                    item_update['skin_temperature'] = Decimal('{:.2f}'.format(skin_temperature))
                    item_update['num_temperature_out_of_range'] = num_temperature_out_of_range

                    if skin_temperature < 35:
                        body_temperature = skin_temperature + 2
                    elif (skin_temperature >= 35) and (skin_temperature <= 36):
                        body_temperature = skin_temperature + 1.3
                    elif skin_temperature > 36:
                        body_temperature = skin_temperature + 1
                    else:
                        body_temperature = skin_temperature

                    item_update['body_temperature'] = Decimal('{:.2f}'.format(body_temperature))
                    
            except Exception as e:
                logging.error({
                        "message": f"Fail to extract temperature. Exception error message is {e}",
                        "level": "error"
                    })

            query_value.update(**item_update)
            if item_update.get('date_time'):
                data_processing = DataProcessing.objects.filter(
                    user_id=user_id, date_time=item_update.get('date_time'))
                query_value = data_processing.values()
            # Flag the socket io that the database has changed
            update_backend_latest_vitals(
                user_id, settings.backend_url, settings.backend_auth_key)

            try:
                bool_data_is_sent = send_data_to_client(data_processing.first())
                query_value.update(**{'data_is_sent_to_client': bool_data_is_sent})
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                err = "\n".join(traceback.format_exception(*sys.exc_info()))
                logging.error(f"Error in send_data_to_client() for sending sensor data of userId {data_processing.first()['user_id']} at datetime {data_processing.first()['date_time']}. error message is {err}")


            item = query_value[0]
            del item['id']
            lib_update_spot_cache.spot_cache_update(item,'sensor')
            lib_update_metric_cache.update(item, res='minutes')


        compliance.cache_table_update(query_value[0]['user_id'],query_value[0]['datetime_sensor'],'datetime_sensor')
        common.insert_to_process_cache(query_value[0]['id'],'sensor')

