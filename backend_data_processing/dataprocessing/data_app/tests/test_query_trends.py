
from django.test import TestCase
import json
import uuid
import os
import pandas as pd
from decimal import Decimal
import numpy as np
from io import StringIO
from dataprocessing import lib_settings as settings
from data_app.models import *
import datetime
from unittest import mock
from rest_framework.test import APIClient
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url, BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES, val_replace_NaN
import requests
from typing import Dict
from django.db import models

from data_app.lib_update_cache_incremental import(
    hourly_start_stop_timeframe,
    handle_update_hourly_cache,
    daily_start_stop_timeframe,
    handle_update_daily_cache
)
from data_app.tests.data.data_test_trends import *

base_path = os.path.dirname(__file__)
val_nan = val_replace_NaN




class QueryTrendsTestCase(TestCase):


    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    def setUp(self):

        self.expected_csv_attribute = {
            "userId": "user_id", "dateTime": "date_time","SpO2": "spo2", "accepted_frame_spo2":"accepted_frame_spo2","SpO2_sd": "spo2_sd","RR_sd": "rr_sd","HR_sd": "hr_sd",
            "accepted_frame": "accepted_frame", "accepted_frame_ratio": "accepted_frame_ratio",
            "accepted_frame_tdomain": "accepted_frame_tdomain", "accepted_frame_tdomain_ratio": "accepted_frame_tdomain_ratio",
            "activity_calories": "activity_calories", "activity_percentage": "activity_percentage", "activity_step": "activity_step",
            "bucket": "bucket", "HR": "hr", "list_onskin_status_stdev_ratio": "list_onskin_status_stdev_ratio",
            "signal_quality_status": "signal_quality_status", "dataColName": "data_col_name",
            "dashboardMode": "dashboard_mode", "dateTimeGatewaySent": "datetime_gateway_sent",
            "dateTimeSensor": "datetime_sensor", "dateTimeServerReceived": "datetime_server_received",
            "recordCollectedBySensor": "record_collected_by_sensor", "recordReceivedByGateway": "record_received_by_gateway",
            "recordServerReceived": "record_server_received", "battery": "battery",
            "hardwareMode": "hardware_mode", "sensorID": "sensor_id",
            "packetNumber": "packet_number", "totalPacket": "total_packet",
            "skin_temperature": "skin_temperature", "body_temperature": "body_temperature",
            "filename": "filename", "filepath": "filepath", "isGenModeFromDashboard": "is_genmode_from_dashboard",
            "list_output_kurtosis": "list_output_kurtosis", "list_output_peakratio": "list_output_peakratio", "list_output_skewness": "list_output_skewness",
            "list_output_stdev": "list_output_stdev", "list_phase_diff": "list_phase_diff", "list_sd_signal_w_sqa": "list_sd_signal_w_sqa",
            "list_sensor_onskin_status_ratio": "list_sensor_onskin_status_ratio", "median_list_output_kurtosis": "median_list_output_kurtosis",
            "median_list_output_peakratio": "median_list_output_peakratio", "median_list_output_skewness": "median_list_output_skewness",
            "median_list_output_stdev": "median_list_output_stdev", "num_record_error": "num_record_error", "num_temperature_out_of_range": "num_temperature_out_of_range",
            "point_awake": "point_awake", "point_sleep": "point_sleep", "RR": "rr", "RR_DC": "rr_dc", "RR_fdomain": "rr_fdomain", "RR_fdomain_w_good_sqa": "rr_fdomain_w_good_sqa",
            "RR_hybrid": "rr_hybrid", "RR_IBI": "rr_ibi", "RR_TD": "rr_td", "RR_tdomain": "rr_tdomain", "sensor_onskin_status": "sensor_onskin_status",
            "sensor_onskin_status_stdev": "sensor_onskin_status_stdev", "sleep_duration_seconds": "sleep_duration_seconds",
            "SQA": "sqa", "SQA_index": "sqa_index", "total_frame": "total_frame", "total_frame_tdomain": "total_frame_tdomain", "val_sd_signal_wo_sqa": "val_sd_signal_wo_sqa",
            "val_sd_signal_w_sqa": "val_sd_signal_w_sqa", "waveletsTransform": "wavelets_transform", "wellness_calmness": "wellness_calmness", "wellness_stress": "wellness_stress"
        }
        self.token = self._get_auth_token()

        filepath_input = os.path.join(
            base_path, 'test_data', 'test_data_main_query_trends', 'test_data.json')
        with open(filepath_input, 'r') as f1:

            input_data = json.load(f1)
            input_data = self.convert_floats_to_decimals(input_data)
            input_data = {self.expected_csv_attribute.get(
                k): v for k, v in input_data.items() if self.expected_csv_attribute.get(k)}
            DataProcessing.objects.get_or_create(**input_data)
        return super().setUp()

    def convert_floats_to_decimals(self, obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self.convert_floats_to_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_floats_to_decimals(elem) for elem in obj]
        elif isinstance(obj, str):
            if obj == 'true':
                return True
            elif obj == 'false':
                return False
            else:
                return obj
        else:
            return obj

    def test_case_1(self):  # minutes

        # test user id is -1
        user_id = '-1'
        list_id = '-1,-2,-3'
        event_single_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={user_id}&resolution=minutes&utc_offset=08:00'

        event_multiple_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={list_id}&resolution=minutes&utc_offset=08:00'

        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}

        response_single_id = self.client.get(event_single_id,**headers).json()
        response_multiple_id = self.client.get(event_multiple_id,**headers).json()
        print(response_single_id)
        print(response_multiple_id)

        assert response_single_id['response'][user_id] == response_multiple_id['response'][user_id]

    def test_case_2(self):  # hourly
        # test user id is -1
        user_id = '-1'
        list_id = '-1, -2, -3'
        event_single_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={user_id}&resolution=hourly&utc_offset=08:00'

        event_multiple_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={list_id}&resolution=hourly&utc_offset=08:00'

        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}

        response_single_id = self.client.get(event_single_id,**headers).json()
        response_multiple_id = self.client.get(event_multiple_id,**headers).json()
        assert response_single_id['response'][user_id] == response_multiple_id['response'][user_id]

    def test_case_3(self):  # daily
        # test user id is -1
        user_id = '-1'
        list_id = '-1, -2, -3'
        event_single_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={user_id}&resolution=daily&utc_offset=08:00'

        event_multiple_id = f'/api/v1/query/trends?start_datetime=2023-04-18T01:59:59&stop_datetime=2023-04-18T03:59:59&id={list_id}&resolution=daily&utc_offset=08:00'

        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}

        response_single_id = self.client.get(event_single_id,**headers).json()
        response_multiple_id = self.client.get(event_multiple_id,**headers).json()
        assert response_single_id['response'][user_id] == response_multiple_id['response'][user_id]

    def test_case_4(self):
        """
        Fix issue: https://github.com/Respiree/rpm_data_processing_backend/issues/280

        Expected
        - remove HR from Chest when displaying minutes trend
        """

        # read raw samples
        path_to_sample = os.path.join(
            base_path, 'test_data', 'test_data_main_query_trends', 'test_data_main_query_trends_004.csv')
        test_data = pd.read_csv(path_to_sample)
        test_data = test_data.sort_values('dateTime')

        test_data["userId"] = test_data["userId"].astype(str)
        # assume all records use same user id
        user_id = test_data["userId"].iloc[0]
        val_nan = settings.val_replace_NaN
        
        for i in range(len(test_data)):
            data = test_data.loc[test_data['sample_number'] == i+1]

            # drop NaN
            data = data.dropna(axis=1, how='all')

            # convert test_data to dict
            input_data = data.to_dict('records')[0]
            input_data = {self.expected_csv_attribute.get(
                k): v for k, v in input_data.items() if self.expected_csv_attribute.get(k)}
            input_data = self.convert_floats_to_decimals(input_data)
            DataProcessing.objects.get_or_create(**input_data)

        # read expected output
        path_to_expected_output = os.path.join(
            base_path, 'test_data', 'test_data_main_query_trends', 'expected_output_case_004.csv')
        expected_data = pd.read_csv(path_to_expected_output)
        expected_data = expected_data.sort_values('dateTime')

        if not settings.BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES:
            expected_data.loc[expected_data['dashboardMode']
                              == 'RR', 'HR'] = val_nan  # convert HR to -1
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}

        event_single_id = f'/api/v1/query/trends?start_datetime=2023-07-26T14:14:50&stop_datetime=2023-07-26T14:24:07&id={user_id}&resolution=minutes&utc_offset=08:00'
        response = self.client.get(event_single_id,**headers).json()['response']
        

        # verify output
        assert (
            response[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "mismatched RR"
        assert (
            response[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "mismatched HR"
        assert (
            response[user_id]["metrics"]["SpO2"] == expected_data["SpO2"]
        ).all(), "mismatched SpO2"
        
        assert (
            response[user_id]["metrics_SD"]["RR"] == expected_data["RR_sd"]
        ).all(), "mismatched RR_sd"
        assert (
            response[user_id]["metrics_SD"]["HR"] == expected_data["HR_sd"]
        ).all(), "mismatched HR_sd"
        assert (
            response[user_id]["metrics_SD"]["SpO2"] == expected_data["SpO2_sd"]
        ).all(), "mismatched SpO2_sd"

        assert (
            response[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"

def load_data(path):
    return pd.read_csv(path)

def load_and_sort_data(path):
    data = load_data(path)
    return data.sort_values("dateTime")

def read_sample_and_expected_data(sample_path, expected_path):
    sample_data = load_and_sort_data(sample_path)
    sample_data["userId"] = sample_data["userId"].astype(str)        
    expected_data = load_and_sort_data(expected_path)
    return sample_data, expected_data

def import_test_data(data):

        for _, row in data.iterrows():
            records = { 
                'user_id' : row['userId'],
                'date_time' : row['dateTime'],
                'rr' : row.get('RR', None),
                'spo2' : row.get('SpO2', None),
                'accepted_frame_spo2' : row.get('accepted_frame_spo2', None),
                'sensor_onskin_status' : row.get('sensor_onskin_status', None),
                'signal_quality_status' : row.get('signal_quality_status', None),
                'activity' : row.get('activity', None),
                'battery' : row.get('battery', None),
                'body_temperature' : row.get('body_temperature', None),
                'dashboard_mode' : row['dashboardMode'],
                'datetime_gateway_sent' : row['dateTimeGatewaySent'],
                'datetime_sensor' : row.get('dateTimeSensor', None),
                'datetime_server_received' : row.get('dateTimeServerReceived', None),
                'hardware_mode' : row.get('hardwareMode', None),
                'hr' : row.get('HR', None),
                'record_collected_by_sensor' : row.get('recordCollectedBySensor', None),
                'record_received_by_gateway' : row.get('recordReceivedByGateway', None),
                'record_server_received' : row.get('recordServerReceived', None),
                'rr_dc' : row.get('RR_DC', None),
                'rr_td' : row.get('RR_TD', None),
                'rr_tdomain' : row.get('RR_tdomain', None),
                'sensor_onskin_status_stdev' : row.get('sensor_onskin_status_stdev', None),
                'sensor_id' : row.get('sensorID', None),
                'skin_temperature' : row.get('skin_temperature', None),
                'sleep_duration_seconds' : row.get('sleep_duration_seconds', None),
                'val_sd_signal_w_sqa' : row.get('val_sd_signal_w_sqa', None),
                'val_sd_signal_wo_sqa' : row.get('val_sd_signal_wo_sqa', None),
                'rr_sd' : row.get('RR_sd', None),
                'hr_sd' : row.get('HR_sd', None),
                'spo2_sd' : row.get('SpO2_sd', None),
                'sensor_contact_status' : row.get('sensor_contact_status', None),
                'accepted_frame' : row.get('accepted_frame', None),
                'accepted_frame_ratio' : row.get('accepted_frame_ratio', None),
                'accepted_frame_spo2_ratio' : row.get('accepted_frame_spo2_ratio', None),
                'accepted_frame_tdomain' : row.get('accepted_frame_tdomain', None),
                'accepted_frame_tdomain_ratio' : row.get('accepted_frame_tdomain_ratio', None),
                'activity_calories' : row.get('activity_calories', None),
                'activity_step' : row.get('activity_step', None),
                'bucket' : row.get('bucket', None),
                'data_col_name' : row.get('dataColName', None),
                'filename' : row.get('filename', None),
                'filepath' : row.get('filepath', None),
                'onskin_2lightsources_median_diff_cv' : row.get('onskin_2lightsources_median_diff_cv', None),
                'onskin_2lightsources_median_diff_mean' : row.get('onskin_2lightsources_median_diff_mean', None),
                'onskin_2lightsources_median_diff_median' : row.get('onskin_2lightsources_median_diff_median', None),
                'onskin_2lightsources_median_diff_sd' : row.get('onskin_2lightsources_median_diff_sd', None),
                'packet_number' : row.get('packetNumber', None),
                'point_awake' : row.get('point_awake', None),
                'point_sleep' : row.get('point_sleep', None),
                'sqa' : row.get('SQA', None),
                'sqa_index' : row.get('SQA_index', None),
                'total_frame' : row.get('total_frame', None),
                'total_frame_spo2' : row.get('total_frame_spo2', None),
                'total_frame_tdomain' : row.get('total_frame_tdomain', None),
                'total_packet' : row.get('totalPacket', None),
                'hr_chest' : row.get('hr_chest', None)
            }


    
            dataprocessing_obj = DataProcessing.objects.create(**records)

            # trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_daily_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_hourly_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


def import_health_data(data):
    data.sort_values("datetime")
    for _, row in data.iterrows():
            records  =  {
                    'user_id' : row["user_id"],
                    'datetime' : row["datetime"],
                    'bp_sys' : row.get("data_bp_sys", None),
                    'bp_dia' : row.get("data_bp_dia", None),
                    'weight' : row.get("data_weight", None),
                    'blood_sugar' : row.get("data_blood_sugar", None),
                    'rr' : row.get("data_rr", None),
                    'hr' : row.get("data_hr", None),
                    'spo2' : row.get("data_spo2", None),
                    'body_temp' : row.get("data_body_temp", None),
            }
        
            mhi_obj = HealthData.objects.create(**records)

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)

            handle_update_daily_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)

            handle_update_hourly_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

def import_bp_data(data):
    data.sort_values("datetime")
    for _, row in data.iterrows():
            records  =  {
                    'user_id' : row["user_id"],
                    'datetime' : row["datetime"],
                    'bp_sys' : row.get("bp_sys", None),
                    'bp_dia' : row.get("bp_dia", None),
                    'source' : 'other'
            }
        
            bp_obj = OtherDeviceReading.objects.create(**records)

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_daily_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_hourly_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


def import_emr_data(data):
    data.sort_values("datetime")
    for _, row in data.iterrows():
            records  =  {
                    'user_id' : row["user_id"],
                    'datetime' : row["datetime"],
                    'bp_sys' : row.get("bp_sys", None),
                    'bp_dia' : row.get("bp_dia", None),
                    'rr' : row.get("rr", None),
                    'hr' : row.get("hr", None),
                    'spo2' : row.get("spo2", None),
                    'body_temperature' : row.get("body_temperature", None),
                    'blood_sugar' : row.get("blood_sugar", None),
                    'datetime_data_collected' : row.get("datetime_data_collected", None),
                    'source' : 'emr'
            }
        
            bp_obj = OtherDeviceReading.objects.create(**records)

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_daily_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_hourly_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

class TestQueryTrendsMinutes(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.sensor_data_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_01_sensor_data.csv")
        self.expected_output_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_01_expected_output.csv")
        self.sensor_data_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_02_sensor_data.csv")
        self.expected_output_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_02_expected_output.csv")
        self.health_data_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_02_health_input.csv")
        self.sensor_data_03_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_03_sensor_data.csv")
        self.expected_output_03_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsMinutes_03_expected_output.csv")
        self.import_data_db()


    def read_dummy_data_04(self):

        test_sensor_data = pd.read_csv(StringIO(minute_test_case_4_sensor_input))
        test_sensor_data = test_sensor_data.sort_values("dateTime")
        test_sensor_data["userId"] = test_sensor_data["userId"].astype(str)
        user_id = test_sensor_data["userId"].iloc[0]

        test_manual_data = pd.read_csv(StringIO(minute_test_case_4_health_input))
        test_manual_data = test_manual_data.sort_values("datetime")

        test_bp_data = pd.read_csv(StringIO(minute_test_case_4_bp_device_input))
        test_bp_data = test_bp_data.sort_values("datetime")

        test_emr_data = pd.read_csv(StringIO(minute_test_case_4_emr_input))
        test_emr_data = test_emr_data.sort_values("datetime")

        test_output = pd.read_csv(StringIO(minute_test_case_4_output))

        import_test_data(test_sensor_data)
        import_health_data(test_manual_data)
        import_bp_data(test_bp_data)
        import_emr_data(test_emr_data)

        return test_sensor_data, test_manual_data, test_bp_data, test_emr_data, test_output


    def import_data_db(self):
        test_data_01, _ = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        import_test_data(test_data_01)
        test_data_02, _ = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
        import_test_data(test_data_02)
        test_data_03 = load_data(self.health_data_path)
        import_health_data(test_data_03)

        test_data_03, _ = read_sample_and_expected_data(self.sensor_data_03_path, self.expected_output_03_path)
        import_test_data(test_data_03)

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    # @classmethod
    # def tearDownClass(self):
    #     DataProcessing.objects.all().delete()
    #     HealthData.objects.all().delete()

    def __assert_output(self, response, expected_data, user_id):
        metrics = response[user_id]["metrics"]
        metrics_sd = response[user_id]["metrics_SD"]

        # print(expected_data["dateTime"])
        # print(metrics["listtime"])


        assert (metrics["RR"] == expected_data["RR"]).all(), "mismatched RR"
        assert (metrics["HR"] == expected_data["HR"]).all(), "mismatched HR"
        assert (metrics["SpO2"] == expected_data["SpO2"]).all(), "mismatched SpO2"
        assert (metrics["BP_Sys"] == expected_data["BP_Sys"]).all(), "mismatched BP_Sys"
        assert (metrics["BP_Dia"] == expected_data["BP_Dia"]).all(), "mismatched BP_Dia"
        assert (
            metrics["RR_manual"] == expected_data["RR_manual"]
        ).all(), "mismatched RR_manual"
        assert (
            metrics["HR_manual"] == expected_data["HR_manual"]
        ).all(), "mismatched HR_manual"
        assert (
            metrics["SpO2_manual"] == expected_data["SpO2_manual"]
        ).all(), "mismatched SpO2_manual"
        assert (
            metrics["body_temp_manual"] == expected_data["body_temp_manual"]
        ).all(), "mismatched body_temp_manual"
        assert (
            metrics["weight_manual"] == expected_data["weight_manual"]
        ).all(), "mismatched weight_manual"
        assert (
            metrics["blood_sugar_manual"] == expected_data["blood_sugar_manual"]
        ).all(), "mismatched blood_sugar_manual"
        assert (
            metrics["has_manual_reading"] == expected_data["has_manual_reading"]
        ).all(), "mismatched has_manual_reading"
        assert (metrics_sd["RR"] == expected_data["RR_sd"]).all(), "mismatched RR_sd"
        assert (metrics_sd["HR"] == expected_data["HR_sd"]).all(), "mismatched HR_sd"
        assert (
            metrics_sd["SpO2"] == expected_data["SpO2_sd"]
        ).all(), "mismatched SpO2_sd"
        assert (
            metrics_sd["BP_Sys"] == expected_data["BP_Sys_sd"]
        ).all(), "mismatched BP_Sys_sd"
        assert (
            metrics_sd["BP_Dia"] == expected_data["BP_Dia_sd"]
        ).all(), "mismatched BP_Dia_sd"
        assert (
            metrics_sd["RR_manual"] == expected_data["RR_manual_sd"]
        ).all(), "mismatched RR_manual_sd"
        assert (
            metrics_sd["HR_manual"] == expected_data["HR_manual_sd"]
        ).all(), "mismatched HR_manual_sd"
        assert (
            metrics_sd["SpO2_manual"] == expected_data["SpO2_manual_sd"]
        ).all(), "mismatched SpO2_manual_sd"
        assert (
            metrics_sd["body_temp_manual"] == expected_data["body_temp_manual_sd"]
        ).all(), "mismatched body_temp_manual_sd"
        assert (
            metrics_sd["weight_manual"] == expected_data["weight_manual_sd"]
        ).all(), "mismatched weight_manual_sd"
        assert (
            metrics_sd["blood_sugar_manual"] == expected_data["blood_sugar_manual_sd"]
        ).all(), "mismatched blood_sugar_manual_sd"

        assert (
            metrics["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time (metrics)"
        assert (
            metrics_sd["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time (metrics_sd)"
        assert (
            metrics_sd["has_manual_reading"] == expected_data["has_manual_reading_sd"]
        ).all(), "mismatched has_manual_reading (sd)"

    def test_query_trend_minutes_valid(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        query_params = {
            "start_datetime": "2022-07-26T14:14:50",
            "stop_datetime": "2022-07-26T14:24:07",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        self.__assert_output(response_data, self.expected_data, query_params['id'])        

    def test_query_trend_minutes_invalid_datetime_format(self):
        query_params = {
            "start_datetime": "2022-07-26 14:14:50",
            "stop_datetime": "2022-07-26 14:24:07",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        expected_response = {
            "start_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]
        }
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected_response)



    def test_query_trend_minutes_hr_chest(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_03_path, self.expected_output_03_path)


        query_params = {
            "start_datetime": "2022-07-26T14:14:50",
            "stop_datetime": "2022-07-26T14:24:07",
            "id": "-21",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        print(response_data[query_params["id"]]['metrics']['listtime'])
        print(response_data[query_params["id"]]['metrics']['hr_chest'])
        print(self.expected_data["hr_chest"])

        assert (response_data[query_params["id"]]['metrics']['hr_chest'] == self.expected_data["hr_chest"]).all(), "mismatched hr_chest"

    def test_query_trend_minutes_valid_with_health_input(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
        query_params = {
            "start_datetime": "2021-07-26T14:14:50",
            "stop_datetime": "2021-07-26T14:30:07",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        # if not BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES:
        #     self.expected_data.loc[self.expected_data["dashboardMode"] == "RR", "HR"] = (val_nan)
        self.__assert_output(response_data, self.expected_data, query_params['id'])        



    def test_query_trend_minutes_valid_with_health_input_and_bp_device_reading(self):

        test_sensor_data, test_manual_data, test_bp_data, test_emr_data, test_output = self.read_dummy_data_04()


        query_params = {
            "id": "-3",
            "start_datetime": "2021-07-26T14:14:50",
            "stop_datetime": "2021-07-26T14:30:07",
            "resolution": "minutes",
            "utc_offset": "+08:00",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        print('***************************************************************************************')
        print(response_data)

        self.__assert_output(response_data, test_output, query_params['id'])



class TestQueryTrendsHourly(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.sensor_data_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsHourly_01_sensor_data.csv")
        self.expected_output_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsHourly_01_expected_data.csv")
        self.sensor_data_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsHourly_02_sensor_data.csv")
        self.expected_output_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsHourly_02_expected_output.csv")
        self.health_data_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsHourly_02_health_input.csv")
        self.import_data_db()


    def read_dummy_data_03(self):

        test_sensor_data = pd.read_csv(StringIO(hourly_test_case_3_sensor_input))
        test_sensor_data = test_sensor_data.sort_values("dateTime")
        test_sensor_data["userId"] = test_sensor_data["userId"].astype(str)
        user_id = test_sensor_data["userId"].iloc[0]

        test_manual_data = pd.read_csv(StringIO(hourly_test_case_3_health_input))
        test_manual_data = test_manual_data.sort_values("datetime")

        test_bp_data = pd.read_csv(StringIO(hourly_test_case_3_bp_device_input))
        test_bp_data = test_bp_data.sort_values("datetime")

        test_output = pd.read_csv(StringIO(hourly_test_case_3_output))

        import_test_data(test_sensor_data)
        import_health_data(test_manual_data)
        import_bp_data(test_bp_data)


        return test_sensor_data, test_manual_data, test_bp_data, test_output



    def import_data_db(self):
        test_data_01, _ = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        import_test_data(test_data_01)
        test_data_02, _ = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
        import_test_data(test_data_02)
        test_data_03 = load_data(self.health_data_path)
        import_health_data(test_data_03)

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    # @classmethod
    # def tearDownClass(self):
    #     DataProcessing.objects.all().delete()
    #     HealthData.objects.all().delete()

    def __assert_output(self, response, expected_data, user_id):
        metrics = response[user_id]["metrics"]
        metrics_sd = response[user_id]["metrics_SD"]

        assert (metrics["RR"] == expected_data["RR"]).all(), "mismatched RR"
        assert (metrics["HR"] == expected_data["HR"]).all(), "mismatched HR"
        assert (metrics["SpO2"] == expected_data["SpO2"]).all(), "mismatched SpO2"
        assert (metrics["BP_Sys"] == expected_data["BP_Sys"]).all(), "mismatched BP_Sys"
        assert (metrics["BP_Dia"] == expected_data["BP_Dia"]).all(), "mismatched BP_Dia"
        assert (
            metrics["weight_manual"] == expected_data["weight_manual"].astype(float)
        ).all(), "mismatched weight_manual"
        assert (
            metrics["has_manual_reading"] == expected_data["has_manual_reading"]
        ).all(), "mismatched has_manual_reading"

        assert (metrics_sd["RR"] == expected_data["RR_sd"]).all(), "mismatched RR_sd"
        assert (metrics_sd["HR"] == expected_data["HR_sd"]).all(), "mismatched HR_sd"
        assert (
            metrics_sd["SpO2"] == expected_data["SpO2_sd"]
        ).all(), "mismatched SpO2_sd"
        assert (
            metrics_sd["BP_Sys"] == expected_data["BP_Sys_sd"]
        ).all(), "mismatched BP_Sys_sd"
        assert (
            metrics_sd["BP_Dia"] == expected_data["BP_Dia_sd"]
        ).all(), "mismatched BP_Dia_sd"
        assert (
            metrics_sd["weight_manual"] == expected_data["weight_manual_sd"]
        ).all(), "mismatched weight_manual_sd"

        assert (
            metrics["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time (metrics)"
        assert (
            metrics_sd["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time (metrics_sd)"

    def __assert_metric_output(self, response, expected_data, user_id):
        metrics = response[user_id]["metrics"]
        metrics_sd = response[user_id]["metrics_SD"]

        assert (metrics["RR"] == expected_data["RR"]).all(), "mismatched RR"
        assert (metrics["HR"] == expected_data["HR"]).all(), "mismatched HR"
        assert (metrics["SpO2"] == expected_data["SpO2"]).all(), "mismatched SpO2"
        assert (metrics["EWS"] == expected_data["EWS"].astype(float)).all(), "mismatched EWS"

        assert (metrics_sd["RR"] == expected_data["RR_sd"]).all(), "mismatched RR_sd"
        assert (metrics_sd["HR"] == expected_data["HR_sd"]).all(), "mismatched HR_sd"
        assert (
            metrics_sd["SpO2"] == expected_data["SpO2_sd"]
        ).all(), "mismatched SpO2_sd"
        assert (metrics_sd["EWS"] == expected_data["EWS_sd"]).all(), "mismatched EWS sd"
        assert (metrics_sd["activity"] == expected_data["activity_sd"]).all(), "mismatched activity sd"

    def test_query_trend_hourly_valid(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        query_params = {
            "start_datetime": "2023-02-17T09:00:00",
            "stop_datetime": "2023-02-17T16:59:59",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "+08:00"
        }

        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        self.__assert_output(response_data, self.expected_data, query_params['id'])        

    def test_query_trend_hourly_invalid_datetime_format(self):
        query_params = {
            "start_datetime": "2022-07-26 14:14:50",
            "stop_datetime": "2022-07-26 14:24:07",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        expected_response = {
            "start_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]
        }
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected_response)


    def test_query_trend_hourly_valid_with_health_input(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
    
        query_params = {
            "start_datetime": "2000-01-01T00:00:00",
            "stop_datetime": "2000-01-01T06:59:59",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        self.__assert_metric_output(response_data, self.expected_data, query_params['id'])        



    def test_query_trend_hourly_valid_with_health_input_and_bp_device_reading(self):
        test_sensor_data, test_manual_data, test_bp_data, test_output = self.read_dummy_data_03()
        query_params = {
            "id": "-3",
            "start_datetime": "2000-01-01T00:00:00",
            "stop_datetime": "2000-01-01T06:59:59",
            "resolution": "hourly",
            "utc_offset": "+08:00",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        print(response_data)

        self.__assert_output(response_data, test_output, query_params['id'])



class TestQueryTrendsDaily(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.sensor_data_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsDaily_01_sensor_data.csv")
        self.expected_output_01_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsDaily_01_expected_data.csv")
        self.sensor_data_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsDaily_02_sensor_data.csv")
        self.expected_output_02_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsDaily_02_expected_output.csv")
        self.health_data_path = os.path.join(base_path, "test_data", "test_data_main_query_trends", "TestQueryTrendsDaily_02_health_input.csv")
        self.import_data_db()

    def read_dummy_data_03(self):

        test_sensor_data = pd.read_csv(StringIO(daily_test_case_3_sensor_input))
        test_sensor_data = test_sensor_data.sort_values("dateTime")
        test_sensor_data["userId"] = test_sensor_data["userId"].astype(str)
        user_id = test_sensor_data["userId"].iloc[0]

        test_manual_data = pd.read_csv(StringIO(daily_test_case_3_health_input))
        test_manual_data = test_manual_data.sort_values("datetime")

        test_bp_data = pd.read_csv(StringIO(daily_test_case_3_bp_device_input))
        test_bp_data = test_bp_data.sort_values("datetime")

        test_output = pd.read_csv(StringIO(daily_test_case_3_output))


        import_test_data(test_sensor_data)
        import_health_data(test_manual_data)
        import_bp_data(test_bp_data)

        return test_sensor_data, test_manual_data, test_bp_data, test_output


    def import_data_db(self):
        test_data_01, _ = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        import_test_data(test_data_01)
        test_data_02, _ = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
        import_test_data(test_data_02)       
        test_data_03 = load_data(self.health_data_path)
        import_health_data(test_data_03)

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    # @classmethod
    # def tearDownClass(self):
    #     DataProcessing.objects.all().delete()
    #     HealthData.objects.all().delete()

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        
    def __assert_output(self, response, expected_data, user_id):
        metrics = response[user_id]["metrics"]
        metrics_sd = response[user_id]["metrics_SD"]

        assert (metrics["RR"] == expected_data["RR"]).all(), "mismatched RR"
        assert (metrics["HR"] == expected_data["HR"]).all(), "mismatched HR"
        assert (metrics["SpO2"] == expected_data["SpO2"]).all(), "mismatched SpO2"
        assert (metrics["EWS"] == expected_data["EWS"]).all(), "mismatched EWS"
        assert (metrics["BP_Sys"] == expected_data["BP_Sys"].astype(float)).all(), "mismatched BP_Sys"
        assert (metrics["BP_Dia"] == expected_data["BP_Dia"].astype(float)).all(), "mismatched BP_Dia"
        assert (
            metrics["listdate"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"
        assert (
            metrics["has_manual_reading"] == expected_data["has_manual_reading"]
        ).all(), "mismatched has_manual_reading"

        assert (metrics_sd["RR"] == expected_data["RR_sd"]).all(), "mismatched RR"
        assert (metrics_sd["HR"] == expected_data["HR_sd"]).all(), "mismatched HR"
        assert (metrics_sd["SpO2"] == expected_data["SpO2_sd"]).all(), "mismatched SpO2"
        assert (metrics_sd["EWS"] == expected_data["EWS_sd"]).all(), "mismatched EWS"

        assert (
            metrics_sd["BP_Sys"] == expected_data["BP_Sys_sd"]
        ).all(), "mismatched BP_Sys"
        assert (
            metrics_sd["BP_Dia"] == expected_data["BP_Dia_sd"]
        ).all(), "mismatched BP_Dia"
        assert (
            metrics_sd["listdate"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"

    def test_query_trend_daily_valid(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_01_path, self.expected_output_01_path)
        query_params = {
            "start_datetime": "1999-02-01T00:00:00",
            "stop_datetime": "1999-02-09T00:00:00",
            "id": "-2",
            "resolution": "daily",
            "utc_offset": "+00:00"
        }

        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        self.__assert_output(response_data, self.expected_data, query_params['id'])        

    def test_query_trend_daily_invalid_datetime_format(self):
        query_params = {
            "start_datetime": "2022-07-26 14:14:50",
            "stop_datetime": "2022-07-26 14:24:07",
            "id": "0",
            "resolution": "daily",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        expected_response = {
            "start_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]
        }
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected_response)

    def test_query_trend_daily_valid_with_health_input(self):
        self.test_data, self.expected_data = read_sample_and_expected_data(self.sensor_data_02_path, self.expected_output_02_path)
        query_params = {
            "start_datetime": "1999-01-01T00:00:00",
            "stop_datetime": "1999-01-07T00:00:00",
            "id": "-2",
            "resolution": "daily",
            "utc_offset": "+00:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        self.__assert_output(response_data, self.expected_data, query_params['id'])



    def test_query_trend_hourly_valid_with_health_input_and_bp_device_reading(self):
        test_sensor_data, test_manual_data, test_bp_data, test_output = self.read_dummy_data_03()
        query_params = {
            "start_datetime": "1999-01-01T00:00:00",
            "stop_datetime": "1999-01-07T00:00:00",
            "id": "-3",
            "resolution": "daily",
            "utc_offset": "+00:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        print(response_data)

        self.__assert_output(response_data, test_output, query_params['id'])


class TestQueryTrendsHealthInput(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.import_test_data()

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    def load_data(self, data_list):
        for entry in data_list:
            mhi_obj =  HealthData.objects.create(
                user_id=entry["user_id"],
                #datetime=datetime.datetime.strptime(entry["datetime"], "%Y-%m-%d %H:%M:%S") if entry.get("datetime") else None,
                datetime=entry["datetime"] if entry.get("datetime") else None,
                request_id=uuid.uuid4(),
                bp_sys=entry.get("data_bp_sys"),
                bp_dia=entry.get("data_bp_dia"),
                weight=entry.get("data_weight"),
                blood_sugar=entry.get("data_blood_sugar"),
                rr=entry.get("data_rr"),
                hr=entry.get("data_hr"),
                spo2=entry.get("data_spo2"),
                body_temp=entry.get("data_body_temp")
            )

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)

            handle_update_daily_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)

            handle_update_hourly_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

    def import_test_data(self):
        user_id = "-2"
        data_input_minutes = [
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:01",
                "data_bp_sys": 100,
                "data_bp_dia": 60,
                "data_weight": 56,
                "data_blood_sugar": 6.6,
                "data_rr": 32,
                "data_hr": 64,
                "data_spo2": 95,
                "data_body_temp": 36.3,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:02",
                "data_bp_sys": 102,
                "data_bp_dia": 62,
                "data_weight": 58,
                "data_blood_sugar": 6.8,
                "data_rr": 34,
                "data_hr": 66,
                "data_spo2": 97,
                "data_body_temp": 36.5,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:03",
                "data_bp_sys": 104,
                "data_bp_dia": 64,
                "data_weight": 60,
                "data_blood_sugar": 7.0,
                "data_rr": 36,
                "data_hr": 68,
                "data_spo2": 99,
                "data_body_temp": 36.7,
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:04",
                "data_bp_sys": 106,
                "data_bp_dia": 66,
                "data_weight": 62,
                "data_blood_sugar": 7.2,
                "data_rr": 38,
                "data_hr": 70,
                "data_spo2": 100,
                "data_body_temp": 36.9,
                "datetime_server_received": "2024-03-19 09:26:04",
            },
        ]

        data_input_minutes_missing_some_data = [
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:07",
                "data_bp_sys": 100,
                "data_bp_dia": 60,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:08",
                "data_bp_sys": 102,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:09",
                "data_bp_dia": 62,
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:10",
                "datetime_server_received": "2024-03-19 09:26:04",
            },
        ]

        data_input_hourly = [
            {
                "user_id": user_id,
                "datetime": "1901-08-01 10:10:01",
                "data_bp_sys": 100,
                "data_bp_dia": 60,
                "data_weight": 50,
                "data_blood_sugar": 5.2,
                "data_rr": 30,
                "data_hr": 70,
                "data_spo2": 86,
                "data_body_temp": 36.2,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 10:10:02",
                "data_bp_sys": 101,
                "data_bp_dia": 61,
                "data_weight": 51,
                "data_blood_sugar": 5.4,
                "data_rr": 31,
                "data_hr": 71,
                "data_spo2": 87,
                "data_body_temp": 36.4,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 11:10:02",
                "data_bp_sys": 102,
                "data_hr": 72,
                "data_rr": 12,
                "data_spo2": 90,
                "data_weight": 80,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 11:10:03",
                "data_bp_sys": 104,
                "data_hr": 74,
                "data_rr": 14,
                "data_spo2": 92,
                "data_weight": 82,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 12:10:03",
                "data_bp_dia": 62,
                "data_blood_sugar": 5.5,
                "data_body_temp": 36.5,
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 12:10:04",
                "data_bp_dia": 64,
                "data_blood_sugar": 5.7,
                "data_body_temp": 36.7,
                "datetime_server_received": "2024-03-19 09:26:04",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 13:10:03",
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1901-08-01 13:10:04",
                "datetime_server_received": "2024-03-19 09:26:04",
            },
        ]

        data_input_daily = [
            {
                "user_id": user_id,
                "datetime": "1901-09-01 16:10:01",
                "data_bp_sys": 100,
                "data_bp_dia": 60,
                "data_weight": 50,
                "data_blood_sugar": 5.2,
                "data_rr": 30,
                "data_hr": 70,
                "data_spo2": 86,
                "data_body_temp": 36.2,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-01 16:10:02",
                "data_bp_sys": 101,
                "data_bp_dia": 61,
                "data_weight": 51,
                "data_blood_sugar": 5.4,
                "data_rr": 31,
                "data_hr": 71,
                "data_spo2": 87,
                "data_body_temp": 36.4,
                "datetime_server_received": "2024-03-19 09:26:01",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-02 11:10:02",
                "data_bp_sys": 102,
                "data_hr": 72,
                "data_rr": 32,
                "data_spo2": 90,
                "data_weight": 52,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-02 11:10:03",
                "data_bp_sys": 103,
                "data_hr": 73,
                "data_rr":33,
                "data_spo2": 92,
                "data_weight": 53,
                "datetime_server_received": "2024-03-19 09:26:02",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-03 12:10:03",
                "data_bp_dia": 62,
                "data_blood_sugar": 5.5,
                "data_body_temp": 36.5,
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-03 12:10:04",
                "data_bp_dia": 64,
                "data_blood_sugar": 5.7,
                "data_body_temp": 36.7,
                "datetime_server_received": "2024-03-19 09:26:04",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-04 13:10:03",
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-04 13:10:04",
                "datetime_server_received": "2024-03-19 09:26:04",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-05 13:10:03",
                "data_bp_sys": 110,
                "datetime_server_received": "2024-03-19 09:26:03",
            },
            {
                "user_id": user_id,
                "datetime": "1901-09-05 13:10:04",
                "data_bp_sys": 112,
                "datetime_server_received": "2024-03-19 09:26:04",
            },
        ]
        self.load_data(data_input_minutes)
        self.load_data(data_input_minutes_missing_some_data)
        self.load_data(data_input_hourly)
        self.load_data(data_input_daily)

    # @classmethod
    # def tearDownClass(self):
    #     HealthData.objects.all().delete()

    def test_minutes_available_health_input_data_valid(self):
        query_params = {
            "start_datetime": "1900-08-01T10:10:01",
            "stop_datetime": "1900-08-01T10:10:05",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        assert metrics["listtime"] == [
            "1900-08-01 10:10:01",
            "1900-08-01 10:10:02",
            "1900-08-01 10:10:03",
            "1900-08-01 10:10:04",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [100, 102, 104, 106], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [60, 62, 64, 66], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["RR_manual"] == [32, 34, 36, 38], "incorrect RR_manual"
        assert metrics["HR_manual"] == [64, 66, 68, 70], "incorrect HR_manual"
        assert metrics["SpO2_manual"] == [95, 97, 99, 100], "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == [ 36.3, 36.5, 36.7, 36.9], "incorrect body_temp_manual"
        assert metrics["weight_manual"] == [56, 58, 60, 62], "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == [ 6.6, 6.8, 7, 7.2], "incorrect blood_sugar_manual"


    def test_minutes_missing_some_health_input_data_valid(self):
        query_params = {
            "start_datetime": "1900-08-01T10:10:07",
            "stop_datetime": "1900-08-01T10:10:11",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        assert metrics["listtime"] == [
            "1900-08-01 10:10:07",
            "1900-08-01 10:10:08",
            "1900-08-01 10:10:09",
            "1900-08-01 10:10:10",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [100, 102, -1, -1], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [60, -1, 62, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics["RR_manual"] == [-1, -1, -1, -1], "incorrect RR_manual"
        assert metrics["HR_manual"] == [-1, -1, -1, -1], "incorrect HR_manual"
        assert metrics["SpO2_manual"] == [-1, -1, -1, -1], "incorrect SpO2_manual"

    def test_minutes_missing_all_health_input_data_valid(self):
        query_params = {
            "start_datetime": "1800-08-01T10:10:01",
            "stop_datetime": "1800-08-01T10:10:05",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        assert metrics["listtime"] == "1800-08-01 10:10:05", "incorrect datetime"
        assert metrics["BP_Sys"] == -1, "incorrect BP Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP Dia"
        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["signal_quality_status"] == -1, "incorrect signal_quality_status"
        assert metrics["has_manual_reading"] == -1, "incorrect has_manual_reading"

        assert (
            metrics_sd["listtime"] == "1800-08-01 10:10:05"
        ), "incorrect datetime (metrics sd)"
        assert metrics_sd["BP_Sys"] == -1, "incorrect BP Sys (metrics sd)"
        assert metrics_sd["BP_Dia"] == -1, "incorrect BP Dia (metrics sd)"
        assert metrics_sd["RR"] == -1, "incorrect RR (metrics sd)"
        assert metrics_sd["HR"] == -1, "incorrect HR (metrics sd)"
        assert metrics_sd["SpO2"] == -1, "incorrect SpO2 (metrics sd)"
        assert metrics_sd["RR_manual"] == -1, "incorrect RR_manual_sd"
        assert metrics_sd["HR_manual"] == -1, "incorrect HR_manual_sd"
        assert metrics_sd["SpO2_manual"] == -1, "incorrect SpO2_manual_sd"
        assert metrics_sd["body_temp_manual"] == -1, "incorrect body_temp_manual_sd"
        assert metrics_sd["weight_manual"] == -1, "incorrect weight_manual_sd"
        assert metrics_sd["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual_sd"
        assert (
            metrics_sd["signal_quality_status"] == -1
        ), "incorrect signal_quality_status"
        assert metrics_sd["has_manual_reading"] == -1, "incorrect has_manual_reading (sd)"

    def test_hourly_available_health_input_data_valid(self):
        query_params = {
            "start_datetime": "1901-08-01T10:10:00",
            "stop_datetime": "1901-08-01T13:59:59",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        assert metrics["listtime"] == [
            "1901-08-01 10:00:00",
            "1901-08-01 11:00:00",
            "1901-08-01 12:00:00",
            "1901-08-01 13:00:00",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [
            101,
            103,
            -1,
            -1,
        ], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [61, -1, 63, -1], "incorrect BP Dia"
        assert metrics["RR"] == [31, 13, -1, -1], "incorrect RR"
        assert metrics["HR"] == [71, 73, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [87, 91, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1], "incorrect activity"
        assert metrics["weight_manual"] == [51, 81, -1, -1], "incorrect weight_manual"
        assert [round(val, 2) for val in metrics["blood_sugar_manual"]] == [
            5.3,
            -1,
            5.6,
            -1,
        ], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [
            1,
            1,
            1,
            1,
        ], "incorrect has_manual_reading"


        assert metrics_sd["listtime"] == [
            "1901-08-01 10:00:00",
            "1901-08-01 11:00:00",
            "1901-08-01 12:00:00",
            "1901-08-01 13:00:00",
        ], "incorrect datetime"
        assert metrics_sd["BP_Sys"] == [
            1,
            1,
            -1,
            -1,
        ], "incorrect BP Sys_sd"

        assert metrics_sd["BP_Dia"] == [1, -1, 1, -1], "incorrect BP_Dia_sd"
        assert metrics_sd["RR"] == [1, 1, -1, -1], "incorrect RR_sd"
        assert metrics_sd["HR"] == [1, 1, -1, -1], "incorrect HR_sd"
        assert metrics_sd["SpO2"] == [1, 1, -1, -1], "incorrect SpO2_sd"
        assert metrics_sd["activity"] == [-1, -1, -1, -1], "incorrect activity_sd"
        assert metrics_sd["weight_manual"] == [
            1,
            1,
            -1,
            -1,
        ], "incorrect weight_manual_sd"
        assert [round(val, 2) for val in metrics_sd["blood_sugar_manual"]] == [
            0,
            -1,
            0,
            -1,
        ], "incorrect blood_sugar_manual_sd"


    def test_hourly_missing_all_health_input_data_valid(self):
        query_params = {
            "start_datetime": "1800-08-01T10:10:01",
            "stop_datetime": "1800-08-01T10:10:05",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "+08:00"
        }



        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        assert metrics["listtime"] == ['1800-08-01 10:00:00'], "incorrect datetime"
        assert metrics["BP_Sys"] == [-1], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [-1], "incorrect BP Dia"
        assert metrics["RR"] == [-1], "incorrect RR"
        assert metrics["HR"] == [-1], "incorrect HR"
        assert metrics["SpO2"] == [-1], "incorrect SpO2"
        assert metrics["activity"] == [-1], "incorrect activity"
        assert metrics["weight_manual"] == [-1], "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == [-1], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [-1], "incorrect has_manual_reading"

        assert (
            metrics_sd["listtime"] == ['1800-08-01 10:00:00']
        ), "incorrect datetime (metrics sd)"
        assert metrics_sd["BP_Sys"] == [-1], "incorrect BP Sys (metrics sd)"
        assert metrics_sd["BP_Dia"] == [-1], "incorrect BP Dia (metrics sd)"
        assert metrics_sd["RR"] == [-1], "incorrect RR (metrics sd)"
        assert metrics_sd["HR"] == [-1], "incorrect HR (metrics sd)"
        assert metrics_sd["SpO2"] == [-1], "incorrect SpO2 (metrics sd)"
        assert metrics_sd["activity"] == [-1], "incorrect activity (metrics sd)"
        assert metrics_sd["weight_manual"] == [-1], "incorrect weight_manual_sd"
        assert metrics_sd["blood_sugar_manual"] == [-1], "incorrect blood_sugar_manual_sd"



    def test_daily_available_health_input_data_valid(self):
        query_params = {
            "id": "-2",
            "start_datetime": "1901-09-01T00:00:00",
            "stop_datetime": "1901-09-05T00:00:00",
            "resolution": "daily",
            "utc_offset": "00:00",

        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        print(metrics)

        assert metrics["listdate"] == [
            "1901-09-01 00:00:00",
            "1901-09-02 00:00:00",
            "1901-09-03 00:00:00",
            "1901-09-04 00:00:00",
            "1901-09-05 00:00:00",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [101, 103, -1, -1, 111], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [61, -1, 63, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [31, 33, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [71, 73, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [87, 91, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1, -1], "incorrect activity"
        assert metrics["weight_manual"] == [
            51,
            53,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual"
        assert [round(val, 2) for val in metrics["blood_sugar_manual"]] == [
            5.3,
            -1,
            5.6,
            -1,
            -1,
        ], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [
            1,
            1,
            1,
            1,
            1,
        ], "incorrect has_manual_reading"

        assert metrics_sd["listdate"] == [
            "1901-09-01 00:00:00",
            "1901-09-02 00:00:00",
            "1901-09-03 00:00:00",
            "1901-09-04 00:00:00",
            "1901-09-05 00:00:00",
        ], "incorrect datetime"
        assert [round(val, 2) for val in metrics_sd["BP_Sys"]] == [1, 1, -1, -1, 1], "incorrect BP_Sys_sd"
        assert metrics_sd["BP_Dia"] == [1, -1, 1, -1, -1], "incorrect BP Dia"
        assert metrics_sd["RR"] == [1, 1, -1, -1, -1], "incorrect RR"
        assert metrics_sd["HR"] == [1, 1, -1, -1, -1], "incorrect HR"
        assert metrics_sd["SpO2"] == [1, 1, -1, -1, -1], "incorrect SpO2"
        assert metrics_sd["activity"] == [-1, -1, -1, -1, -1], "incorrect activity"
        assert [round(val, 2) for val in metrics_sd["weight_manual"]] == [
            1,
            1,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual_sd"
        assert [round(val, 2) for val in metrics_sd["blood_sugar_manual"]] == [
            0,
            -1,
            0,
            -1,
            -1,
        ], "incorrect blood_sugar_manual_sd"

    def test_daily_missing_all_health_input_data_valid(self):
        query_params = {
            "id": "-2",
            "start_datetime": "1701-09-01T00:00:00",
            "stop_datetime": "1701-09-05T00:00:00",
            "resolution": "daily",
            "utc_offset": "00:00",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        assert metrics["listdate"] == [
            "1701-09-01 00:00:00",
            "1701-09-02 00:00:00",
            "1701-09-03 00:00:00",
            "1701-09-04 00:00:00",
            "1701-09-05 00:00:00",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [-1, -1, -1, -1, -1], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [-1, -1, -1, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1, -1], "incorrect activity"
        assert metrics["weight_manual"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect has_manual_reading"

        assert metrics_sd["listdate"] == [
            "1701-09-01 00:00:00",
            "1701-09-02 00:00:00",
            "1701-09-03 00:00:00",
            "1701-09-04 00:00:00",
            "1701-09-05 00:00:00",
        ], "incorrect datetime (metrics sd)"
        assert metrics_sd["BP_Sys"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect BP Sys (metrics sd)"
        assert metrics_sd["BP_Dia"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect BP Dia (metrics sd)"
        assert metrics_sd["RR"] == [-1, -1, -1, -1, -1], "incorrect RR (metrics sd)"
        assert metrics_sd["HR"] == [-1, -1, -1, -1, -1], "incorrect HR (metrics sd)"
        assert metrics_sd["SpO2"] == [-1, -1, -1, -1, -1], "incorrect SpO2 (metrics sd)"
        assert metrics_sd["activity"] == [-1, -1, -1, -1, -1], "incorrect activity (metrics sd)"
        assert metrics_sd["weight_manual"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual_sd"
        assert metrics_sd["blood_sugar_manual"] == [
            -1,
            -1,
            -1,
            -1,
            -1,
        ], "incorrect blood_sugar_manual_sd"



class TestQueryTrendsBPDevice(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.import_test_data()

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    def load_data(self, data_list):
        for entry in data_list:
            bp_obj =  OtherDeviceReading.objects.create(
                user_id=entry["user_id"],
                datetime=entry["datetime"] if entry.get("datetime") else None,
                bp_sys=entry.get("bp_sys"),
                bp_dia=entry.get("bp_dia"),
                source='bp-device'
            )


            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_daily_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_hourly_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

    def import_test_data(self):


        user_id = "-22"

        # input data for minutes test
        bp_device_minutes_inputs = [
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:01",
                "bp_sys": 100,
                "bp_dia": 60,
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:02",
                "bp_sys": 102,
                "bp_dia": 62,
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:03",
                "bp_sys": 104,
                "bp_dia": 64,
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:04",
                "bp_sys": 106,
                "bp_dia": 66,
            },
        ]

        self.load_data(bp_device_minutes_inputs)


        # input data for hourly test
        bp_device_hourly_inputs = [
            {
                "user_id": user_id,
                "datetime": "1901-08-02 10:10:01",
                "bp_sys": 100,
                "bp_dia": 60,

            },
            {
                "user_id": user_id,
                "datetime": "1901-08-02 10:10:02",
                "bp_sys": 101,
                "bp_dia": 61,

            },
            {
                "user_id": user_id,
                "datetime": "1901-08-02 11:11:01",
                "bp_sys": 102,
                "bp_dia": 62,

            },
            {
                "user_id": user_id,
                "datetime": "1901-08-02 11:11:02",
                "bp_sys": 102,
                "bp_dia": 62,

            },
            {
                "user_id": user_id,
                "datetime": "1901-08-02 11:12:00",
                "bp_sys": 103,
                "bp_dia": 63,

            },

        ]

        self.load_data(bp_device_hourly_inputs)


        # input data for daily test
        bp_device_daily_inputs = [
            {
                "user_id": user_id,
                "datetime": "1901-07-01 10:10:01",
                "bp_sys": 100,
                "bp_dia": 60,

            },
            {
                "user_id": user_id,
                "datetime": "1901-07-01 10:10:02",
                "bp_sys": 101,
                "bp_dia": 61,

            },
            {
                "user_id": user_id,
                "datetime": "1901-07-02 11:11:01",
                "bp_sys": 102,
                "bp_dia": 62,

            },
            {
                "user_id": user_id,
                "datetime": "1901-07-02 11:11:02",
                "bp_sys": 103,
                "bp_dia": 63,

            },
            {
                "user_id": user_id,
                "datetime": "1901-07-02 11:12:00",
                "bp_sys": 104,
                "bp_dia": 64,

            },

        ]
        self.load_data(bp_device_daily_inputs)


    # @classmethod
    # def tearDownClass(self):
    #     OtherDeviceReading.objects.all().delete()

    def test_minutes_available_bp_device_input(self):


        query_params = {
            "id": "-22",
            "start_datetime": "1900-08-01T10:10:01",
            "stop_datetime": "1900-08-01T10:10:05",
            "resolution": "minutes",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]


        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        assert metrics["listtime"] == [
            "1900-08-01 10:10:01",
            "1900-08-01 10:10:02",
            "1900-08-01 10:10:03",
            "1900-08-01 10:10:04",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [-1, -1, -1, -1], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [-1, -1, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1], "incorrect activity"
        assert metrics["RR_manual"] == [-1, -1, -1, -1], "incorrect RR_manual"
        assert metrics["HR_manual"] == [-1, -1, -1, -1], "incorrect HR_manual"
        assert metrics["SpO2_manual"] == [-1, -1, -1, -1], "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == [-1, -1, -1, -1], "incorrect body_temp_manual"
        assert metrics["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == [-1, -1, -1, -1], "incorrect blood_sugar_manual"
        assert metrics["signal_quality_status"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect signal_quality_status"
        assert metrics["has_manual_reading"] == [-1, -1, -1, -1], "incorrect has_manual_reading"

        assert metrics_sd["listtime"] == [
            "1900-08-01 10:10:01",
            "1900-08-01 10:10:02",
            "1900-08-01 10:10:03",
            "1900-08-01 10:10:04",
        ], "incorrect datetime"
        assert metrics_sd["BP_Sys"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect BP Sys"
        assert metrics_sd["BP_Dia"] == [-1, -1, -1, -1], "incorrect BP Dia"
        assert metrics_sd["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics_sd["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics_sd["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics_sd["activity"] == [-1, -1, -1, -1], "incorrect activity sd"
        assert metrics_sd["RR_manual"] == [-1, -1, -1, -1], "incorrect RR_manual_sd"
        assert metrics_sd["HR_manual"] == [-1, -1, -1, -1], "incorrect HR_manual_sd"
        assert metrics_sd["SpO2_manual"] == [-1, -1, -1, -1], "incorrect SpO2_manual_sd"
        assert metrics_sd["body_temp_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect body_temp_manual_sd"
        assert metrics_sd["weight_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual_sd"
        assert metrics_sd["blood_sugar_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect blood_sugar_manual_sd"
        assert metrics_sd["signal_quality_status"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect signal_quality_status"
        assert metrics_sd["has_manual_reading"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect has_manual_reading (sd)"
        assert metrics["bp_sys_device"] == [100,102,104,106,], "incorrect BP bp_sys_device"
        assert metrics["bp_dia_device"] == [60, 62, 64, 66], "incorrect bp_dia_device"
        assert metrics["has_valid_other_reading"] == [1, 1, 1, 1], "incorrect metrics"


    def test_hourly_available_bp_device_input(self):


        query_params = {
            "id": "-22",
            "start_datetime": "1901-08-02T10:10:00",
            "stop_datetime": "1901-08-02T13:59:59",
            "resolution": "hourly",
            "utc_offset": "+08:00",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]


        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]
        print('metrics>.',metrics)
        print('metrics_sd>.',metrics_sd)

        assert metrics["listtime"] == [
            "1901-08-02 10:00:00",
            "1901-08-02 11:00:00",
            "1901-08-02 12:00:00",
            "1901-08-02 13:00:00",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [
            101,
            102,
            -1,
            -1,
        ], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [61, 62, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1], "incorrect activity"
        assert metrics["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual"
        assert [round(val, 2) for val in metrics["blood_sugar_manual"]] == [-1, -1, -1, -1], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [-1, -1, -1, -1], "incorrect has_manual_reading"
        assert metrics["has_valid_other_reading"] == [1, 1, -1, -1], "incorrect has_valid_other_reading"

        assert metrics_sd["listtime"] == [
            "1901-08-02 10:00:00",
            "1901-08-02 11:00:00",
            "1901-08-02 12:00:00",
            "1901-08-02 13:00:00",
        ], "incorrect datetime"
        assert metrics_sd["BP_Sys"] == [
            1,
            1,
            -1,
            -1,
        ], "incorrect BP Sys_sd"

        assert metrics_sd["BP_Dia"] == [1, 1, -1, -1], "incorrect BP_Dia_sd"
        assert metrics_sd["RR"] == [-1, -1, -1, -1], "incorrect RR_sd"
        assert metrics_sd["HR"] == [-1, -1, -1, -1], "incorrect HR_sd"
        assert metrics_sd["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2_sd"
        assert metrics_sd["activity"] == [-1, -1, -1, -1], "incorrect activity_sd"
        assert metrics_sd["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual_sd"
        assert [round(val, 2) for val in metrics_sd["blood_sugar_manual"]] == [-1, -1, -1, -1], "incorrect blood_sugar_manual_sd"




    def test_daily_available_bp_device_input(self):


        query_params = {
            "id": "-22",
            "start_datetime": "1901-07-01T00:00:00",
            "stop_datetime": "1901-07-04T00:00:00",
            "resolution": "daily",
            "utc_offset": "00:00",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]


        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]

        print('metrics>.',metrics)
        print('metrics_sd>.',metrics_sd)

        assert metrics["listdate"] == [
            "1901-07-01 00:00:00",
            "1901-07-02 00:00:00",
            "1901-07-03 00:00:00",
            "1901-07-04 00:00:00",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [
            101,
            103,
            -1,
            -1,
        ], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [61, 63, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1], "incorrect activity"
        assert metrics["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual"
        assert [round(val, 2) for val in metrics["blood_sugar_manual"]] == [-1, -1, -1, -1], "incorrect blood_sugar_manual"
        assert metrics["has_manual_reading"] == [-1, -1, -1, -1], "incorrect has_manual_reading"
        assert metrics["has_valid_other_reading"] == [1, 1, -1, -1], "incorrect has_valid_other_reading"

        assert metrics_sd["listdate"] == [
            "1901-07-01 00:00:00",
            "1901-07-02 00:00:00",
            "1901-07-03 00:00:00",
            "1901-07-04 00:00:00",
        ], "incorrect datetime"
        assert metrics_sd["BP_Sys"] == [
            1,
            1,
            -1,
            -1,
        ], "incorrect BP Sys_sd"

        assert metrics_sd["BP_Dia"] == [1, 1, -1, -1], "incorrect BP_Dia_sd"
        assert metrics_sd["RR"] == [-1, -1, -1, -1], "incorrect RR_sd"
        assert metrics_sd["HR"] == [-1, -1, -1, -1], "incorrect HR_sd"
        assert metrics_sd["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2_sd"
        assert metrics_sd["activity"] == [-1, -1, -1, -1], "incorrect activity_sd"
        assert metrics_sd["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual_sd"
        assert [round(val, 2) for val in metrics_sd["blood_sugar_manual"]] == [-1, -1, -1, -1], "incorrect blood_sugar_manual_sd"







class TestQueryTrendsEMR(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.import_test_data()

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    def load_data(self, data_list):
        for entry in data_list:
            bp_obj =  OtherDeviceReading.objects.create(
                user_id=entry["user_id"],
                datetime=entry["datetime"] if entry.get("datetime") else None,
                datetime_data_collected=entry["datetime_data_collected"] if entry.get("datetime_data_collected") else None,
                bp_sys=entry.get("bp_sys"),
                bp_dia=entry.get("bp_dia"),
                rr=entry.get("rr"),
                hr=entry.get("hr"),
                spo2=entry.get("spo2"),
                weight=entry.get("weight"),
                body_temperature=entry.get("body_temperature"),
                blood_sugar=entry.get("blood_sugar"),
                source='emr'
            )


            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_daily_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


            start_date, stop_date = hourly_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)

            handle_update_hourly_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

    def import_test_data(self):


        user_id = "-20"
        # input data for minutes test
        emr_minutes_inputs = [
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:01",
                "bp_sys": 100,
                "bp_dia": 60,
                "rr": 60,
                "hr": 20,
                "spo2": 70,
                "weight": 70,
                "body_temperature": 36.0,
                "blood_sugar": 90,
                "datetime_data_collected": "1900-08-01 10:10:01"
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:02",
                "bp_sys": 102,
                "bp_dia": 62,
                "rr": 62,
                "hr": 22,
                "spo2": 72,
                "weight": 72,
                "body_temperature": 38.0,
                "blood_sugar": 92,
                "datetime_data_collected": "1900-08-01 10:10:02"
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:03",
                "bp_sys": 104,
                "bp_dia": 64,
                "rr": 64,
                "hr": 24,
                "spo2": 74,
                "weight": 74,
                "body_temperature": 40.0,
                "blood_sugar": 94,
                "datetime_data_collected": "1900-08-01 10:10:03"
            },
            {
                "user_id": user_id,
                "datetime": "1900-08-01 10:10:04",
                "bp_sys": 106,
                "bp_dia": 66,
                "rr": 66,
                "hr": 26,
                "spo2": 76,
                "weight": 76,
                "body_temperature": 42.0,
                "blood_sugar": 96,
                "datetime_data_collected": "1900-08-01 10:10:04"                
            },
        ]


        self.load_data(emr_minutes_inputs)


    # @classmethod
    # def tearDownClass(self):
    #     OtherDeviceReading.objects.all().delete()

    def test_minutes_available_emr_input(self):


        query_params = {
           "id": "-20",
            "start_datetime": "1900-08-01T10:10:01",
            "stop_datetime": "1900-08-01T10:10:05",
            "resolution": "minutes",
        }
        url = (
            f"{self.base_url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']
        metrics = response_data[query_params['id']]["metrics"]


        metrics = response_data[query_params['id']]["metrics"]
        metrics_sd = response_data[query_params['id']]["metrics_SD"]
        print('metrics.',metrics)
        print('metrics_sd.',metrics_sd)
        
        assert metrics["listtime"] == [
            "1900-08-01 10:10:01",
            "1900-08-01 10:10:02",
            "1900-08-01 10:10:03",
            "1900-08-01 10:10:04",
        ], "incorrect datetime"
        assert metrics["BP_Sys"] == [-1, -1, -1, -1], "incorrect BP Sys"
        assert metrics["BP_Dia"] == [-1, -1, -1, -1], "incorrect BP Dia"
        assert metrics["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics["activity"] == [-1, -1, -1, -1], "incorrect activity"
        assert metrics["RR_manual"] == [-1, -1, -1, -1], "incorrect RR_manual"
        assert metrics["HR_manual"] == [-1, -1, -1, -1], "incorrect HR_manual"
        assert metrics["SpO2_manual"] == [-1, -1, -1, -1], "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == [-1, -1, -1, -1], "incorrect body_temp_manual"
        assert metrics["weight_manual"] == [-1, -1, -1, -1], "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == [-1, -1, -1, -1], "incorrect blood_sugar_manual"
        assert metrics["signal_quality_status"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect signal_quality_status"
        assert metrics["has_manual_reading"] == [-1, -1, -1, -1], "incorrect has_manual_reading"
        assert metrics_sd["listtime"] == [
            "1900-08-01 10:10:01",
            "1900-08-01 10:10:02",
            "1900-08-01 10:10:03",
            "1900-08-01 10:10:04",
        ], "incorrect datetime"
        assert metrics_sd["BP_Sys"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect BP Sys"
        assert metrics_sd["BP_Dia"] == [-1, -1, -1, -1], "incorrect BP Dia"
        assert metrics_sd["RR"] == [-1, -1, -1, -1], "incorrect RR"
        assert metrics_sd["HR"] == [-1, -1, -1, -1], "incorrect HR"
        assert metrics_sd["SpO2"] == [-1, -1, -1, -1], "incorrect SpO2"
        assert metrics_sd["activity"] == [-1, -1, -1, -1], "incorrect activity sd"
        assert metrics_sd["RR_manual"] == [-1, -1, -1, -1], "incorrect RR_manual_sd"
        assert metrics_sd["HR_manual"] == [-1, -1, -1, -1], "incorrect HR_manual_sd"
        assert metrics_sd["SpO2_manual"] == [-1, -1, -1, -1], "incorrect SpO2_manual_sd"
        assert metrics_sd["body_temp_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect body_temp_manual_sd"
        assert metrics_sd["weight_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect weight_manual_sd"
        assert metrics_sd["blood_sugar_manual"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect blood_sugar_manual_sd"
        assert metrics_sd["signal_quality_status"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect signal_quality_status"
        assert metrics_sd["has_manual_reading"] == [
            -1,
            -1,
            -1,
            -1,
        ], "incorrect has_manual_reading (sd)"
        assert metrics["bp_sys_emr"] == [100,102,104,106,], "incorrect BP bp_sys_emr"
        assert metrics["bp_dia_emr"] == [60, 62, 64, 66], "incorrect bp_dia_emr"
        assert metrics["RR_emr"] == [60, 62, 64, 66], "incorrect RR_emr"
        assert metrics["HR_emr"] == [20, 22, 24, 26], "incorrect HR_emr"
        assert metrics["SpO2_emr"] == [70, 72, 74, 76], "incorrect SpO2_emr"
        assert metrics["body_temp_emr"] == [36.0, 38.0, 40.0, 42.0], "incorrect body_temp_emr"
        assert metrics["weight_emr"] == [70.0, 72.0, 74.0, 76.0], "incorrect weight_emr"
        assert metrics["blood_sugar_emr"] == [90.0, 92.0, 94.0, 96.0], "incorrect blood_sugar_emr"


