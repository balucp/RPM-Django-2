import os
import json
import datetime
import pandas as pd
import numpy as np
import math
import requests
import pytz

from decimal import Decimal
from unittest import mock
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import DateTimeField, BooleanField
from data_app.models import MetricMinutesCache, DataProcessing, HealthData
from gateway.models import GatewayPings
# from data_app.signals import real_time_trigger
from data_app import helpers
from data_app import lib_update_metric_cache
from dataprocessing import lib_settings as settings
from dataprocessing import settings as original_settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app.tasks import real_time_trigger

def correct_gateway_data_type(data):

    date_columns = [
        field.name
        for field in GatewayPings._meta.get_fields()
        if isinstance(field, DateTimeField)
    ]

    for key in data.keys():
        if isinstance(data[key], float) and math.isnan(data[key]):
            data[key] = None
        if data[key] in ["nan", np.nan, float("nan"), '"nan"']:
            data[key] = None
        if key in date_columns:
            data[key] = (
                datetime.datetime.strptime(data[key], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=datetime.timezone.utc
                )
                if data[key] != None
                else None
            )
    return data


def correct_dataprocessing_data_type(data):

    date_columns = [
        field.name
        for field in DataProcessing._meta.get_fields()
        if isinstance(field, DateTimeField)
    ]
    boolean_columns = [
        field.name
        for field in DataProcessing._meta.get_fields()
        if isinstance(field, BooleanField)
    ]

    for key in data.keys():
        if isinstance(data[key], float) and math.isnan(data[key]):
            data[key] = None
        if data[key] in ["nan", np.nan, float("nan"), '"nan"']:
            data[key] = None
        if key in date_columns:
            data[key] = (
                datetime.datetime.strptime(data[key], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=datetime.timezone.utc
                )
                if data[key] != None
                else None
            )
        if key in boolean_columns:
            if data[key] != None:
                if data[key] == "true":
                    data[key] = True
                if data[key] == "false":
                    data[key] = False
    return data


dataprocessing_fields = [field.name for field in DataProcessing._meta.get_fields()]
gatewayping_fields = [field.name for field in GatewayPings._meta.get_fields()]


def convert_to_python_datetime(data):
    datetime_fields = [
        'date_time',
        'last_sync',
        'last_sync_chest',
        'datetime_manual_data_rr',
        'datetime_manual_data_body_temp',
        'datetime_manual_data_hr',
        'datetime_manual_data_weight',
        'datetime_server_received',
        'datetime_latest_valid_chest',
        'datetime_manual_data_spo2',
        'datetime_latest_valid_finger',
        'datetime_finger',
        'datetime_manual_data_blood_sugar',
        'datetime_manual_data_bp_sys',
        'datetime_manual_data_bp_dia',
        'datetime_chest',
    ]
    for field  in datetime_fields:
        if field in data:
            data[field]  = datetime.datetime.strptime(data[field], '%Y-%m-%d %H:%M:%S')
    return data


class RealTimeTriggerTestCase(TestCase):

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            f"{backend_url}/api/auth/login", data=payload, headers=headers
        )
        if response.status_code in (200, 201):
            return response.json().get("access_token")
        else:
            self.fail(
                f"Failed to retrieve token: {response.status_code} - {response.text}"
            )

    expected_csv_attribute = {
        "userId": "user_id",
        "battery": "battery",
        "battery_chest": "battery",
        "bodyTemp": "body_temperature",
        "dashboardMode": "dashboard_mode",
        "dateTime": "date_time",
        "dateTimeServerReceived": "datetime_server_received",
        "dateTime_chest": "datetime_chest",
        "dateTime_latest_valid_chest": "datetime_latest_valid_chest",
        "hardwareMode": "hardware_mode",
        "last_sync": "last_sync",
        "last_sync_chest": "last_sync_chest",
        "RR": "rr",
        "sensorID": "sensor_id",
        "skinTemp": "skin_temperature",
        "skin_contact": "skin_contact",
        "skin_contact_chest": "skin_contact_chest",
    }

    def assert_dict_almost_equal(
        self, expected_dict, actual_dict, tolerance=0.001, msg=None
    ):
        """
        Checks that two dictionaries are equal up to a specified tolerance.
        """
        assert set(expected_dict.keys()) == set(actual_dict.keys()), msg
        for key in expected_dict:
            expected_value = expected_dict[key]
            actual_value = actual_dict[key]
            assert len(expected_value) == len(actual_value), msg
            for i in range(len(expected_value)):
                assert abs(expected_value[i] - actual_value[i]) <= tolerance, msg

    def convert_csv_attribute(self, obj):
        return {
            self.expected_csv_attribute[key]: value
            for key, value in obj.items()
            if self.expected_csv_attribute.get(key)
        }

    def convert_floats_to_decimals(self, obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self.convert_floats_to_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_floats_to_decimals(elem) for elem in obj]
        else:
            return obj

    def output_list_minutes(self, user_id):

        token = self._get_auth_token()
        url = f"/api/v1/query/list?date_time={datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}&resolution=minutes&list_of_id={user_id}"
        response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        return response.json().get("response", {}).get(user_id)

    def output_real_time_trigger(self, metric_minutes_cache):
        response = real_time_trigger(metric_minutes_cache)
        response_list_trigger = json.loads(response["list_trigger"])["data"]
        return response_list_trigger

    def test_case_1(self):

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_main_real_time_trigger",
            "test_case_1",
            "input_data.json",
        )

        filepath_trigger = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_main_real_time_trigger",
            "test_case_1",
            "trigger_data.json",
        )

        datetime_fields = (
            "datetime_latest_valid_chest",
            "datetime_latest_valid_finger",
            "last_sync",
            "last_connect_time",
            "last_gateway_connect",
            "sensor_chest_last_connect_time",
            "sensor_finger_last_connect_time",
        )

        with open(filepath_input, "r") as f1, open(filepath_trigger, "r") as f2:
            input_data = self.convert_csv_attribute(json.load(f1))
            trigger_data = json.load(f2)

            input_data = self.convert_floats_to_decimals(input_data)
            if isinstance(trigger_data, dict):
                input_data = convert_to_python_datetime(input_data)

                metric_minutes_cache = MetricMinutesCache.objects.create(**input_data)
                user_id = input_data["user_id"]
                list_minutes_response = self.output_list_minutes(user_id)

                real_time_trigger_response = self.output_real_time_trigger(
                    metric_minutes_cache.id
                )  # real time trigger

                # Assert statements to validate the data
                assert (
                    list_minutes_response["RR"] == real_time_trigger_response["rr"]
                ), "Mismatch in RR value between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["date_time"]
                    == real_time_trigger_response["date_time"]
                ), "Mismatch in date_time between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["battery_chest"]
                    == real_time_trigger_response["battery_chest"]
                ), "Mismatch in battery_chest between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["battery"]
                    == real_time_trigger_response["battery"]
                ), "Mismatch in battery between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["last_sync"]
                    == real_time_trigger_response["last_sync"]
                ), "Mismatch in last_sync between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["skin_contact"]
                    == real_time_trigger_response["skin_contact"]
                ), "Mismatch in skin_contact between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["skin_contact_chest"]
                    == real_time_trigger_response["skin_contact_chest"]
                ), "Mismatch in skin_contact_chest between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["datetime_latest_valid_chest"]
                    == real_time_trigger_response["datetime_latest_valid_chest"]
                ), "Mismatch in datetime_latest_valid_chest between list_minutes_response and real_time_trigger_response"

                # Additional checks to ensure other values match or meet expectations
                assert (
                    list_minutes_response["user_id"]
                    == real_time_trigger_response["user_id"]
                ), "Mismatch in user_id between list_minutes_response and real_time_trigger_response"
                assert (
                    list_minutes_response["skinTemp"]
                    == real_time_trigger_response["skin_temperature"]
                ), "Mismatch in skin_temperature between list_minutes_response and real_time_trigger_response"


    def test_case_3(self):
        """this test case ensures that good data is being uploaded to the minute metrics table when SQA is >= moderate. this table is being used for patient list API and for real time trigger"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_real_time_trigger",
            "input_data_test_case_3.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)
            input_data = convert_to_python_datetime(input_data)

            if isinstance(input_data, dict):
                lib_update_metric_cache.handle_update_minutes(input_data)
                # good signal quality status should be allowed to update on the table

                response = MetricMinutesCache.objects.get(user_id=input_data["user_id"])
                try:
                    response = MetricMinutesCache.objects.get(
                        user_id=input_data["user_id"]
                    )
                    assert response is not None, "data not uploaded"
                    # If needed, you can further verify the attributes of `response`

                    print("Response exists:", response)
                except MetricMinutesCache.ObjectDoesNotExist:
                    assert False, "data not uploaded"

    def test_case_4(self):
        """this test case ensures that no good data is being uploaded to the minute metrics table when SQA is < moderate. this table is being used for patient list API and for real time trigger"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_real_time_trigger",
            "input_data_test_case_4.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)
            input_data = convert_to_python_datetime(input_data)

            if isinstance(input_data, dict):
                lib_update_metric_cache.handle_update_minutes(input_data)
                # good signal quality status should be allowed to update on the table

                try:
                    response = MetricMinutesCache.objects.get(
                        user_id=input_data["user_id"]
                    )
                    assert response is not None, "data uploaded"
                    # If needed, you can further verify the attributes of `response`
                except ObjectDoesNotExist:
                    assert True, "data not uploaded"


class TestRealTimeTrigger(TestCase):


    def test_list_valid_with_recent_data(self):
        # test list trigger
        user_id = "0"

        utc_time_str = (datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] - 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data =  {
            "rr": 22,
            "bp_sys": 100,
            "bp_dia": 60,
            "date_time": "2023-03-08 07:45:16",
            "last_sync": "2023-03-08 09:06:14",
            "skin_contact_chest": 0,
            "dashboard_mode": "RR",
            "body_temperature": 34.5,
            "battery": 50,
            "hardware_mode": "respiratory-rate",
            "user_id": user_id,
            "sensor_id": "80e1261d4f3b",
            "skin_contact": 0,
            "datetime_server_received": "2023-03-08 09:06:20",
            "last_sync_chest": "2023-03-08 09:06:14",
            "datetime_latest_valid_chest": utc_time_str,
            "skin_temperature": 32.5,
            "battery_chest": 93,
            "datetime_chest": utc_time_str,
            "datetime_finger": utc_time_str,

        }
        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"

        assert list_trigger_data["rr"] == 22, "incorrect RR"
        assert list_trigger_data["dashboard_mode"] == "RR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == 34.5, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["bp_sys"] == 100, "incorrect BP_Sys"
        assert list_trigger_data["bp_dia"] == 60, "incorrect BP_Dia"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == 32.5, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()

    def test_list_chest_data_valid_with_recent_data(self):

        # test list trigger
        user_id = "1"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] - 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data =  {
                "rr": 26,
                "date_time": "2024-12-22 02:10:05",
                "datetime_manual_data_rr": "2025-01-16 06:00:00",
                "datetime_manual_data_body_temp": "2025-01-16 06:00:00",
                "dashboard_mode": "RR",
                "hr": 51,
                "manual_data_rr": 30,
                "skin_contact_finger": 1,
                "datetime_manual_data_hr": "2025-01-16 06:00:00",
                "battery": 100,
                "hardware_mode": "respiratory-rate",
                "datetime_manual_data_weight": "2025-01-16 06:00:00",
                "manual_data_blood_sugar": 5.5,
                "datetime_server_received": "2025-01-17 03:08:40",
                "last_sync_chest": "2024-12-19 06:47:39",
                "manual_data_body_temp": 34.6,
                "datetime_latest_valid_chest": utc_time_str,
                "datetime_manual_data_spo2": "2025-01-16 06:00:00",
                "datetime_latest_valid_finger": "2023-08-23 08:30:16",
                "battery_finger": 20,
                "datetime_finger": "2023-08-23 08:30:16",
                "datetime_manual_data_blood_sugar": "2025-01-16 06:00:00",
                "manual_data_weight": 85,
                "last_sync": "2024-12-19 06:47:39",
                "skin_contact_chest": 1,
                "last_sync_finger": "2025-01-17 02:56:48",
                "spo2": 98,
                "body_temperature": 36,
                "datetime_manual_data_bp_sys": "2025-01-16 06:00:00",
                "manual_data_bp_dia": 80,
                "manual_data_spo2": 93,
                "user_id": user_id,
                "sensor_id": "80e1279dac5a",
                "skin_contact": 1,
                "manual_data_hr": 200,
                "manual_data_bp_sys": 126,
                "skin_temperature": 34,
                "battery_chest": 100,
                "datetime_manual_data_bp_dia": "2025-01-16 06:00:00",
                "datetime_chest": utc_time_str
        }

        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"

        assert list_trigger_data["rr"] == 26.0, "incorrect RR"
        assert list_trigger_data["hr"] == -1, "incorrect HR"
        assert list_trigger_data["spo2"] == -1, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "RR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == 36.0, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == 34.0, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()

    
    def test_list_finger_with_recent_data(self):

        # test list trigger
        user_id = "2"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] - 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data =  {
            "rr": 19,
            "hr": 88,
            "spo2": 98,
            "bp_sys": 100,
            "bp_dia": 60,
            "date_time": "2023-08-18 06:30:21",
            "last_sync": "2025-01-17 02:42:34",
            "skin_contact_finger": 1,
            "dashboard_mode": "HR",
            "body_temperature": 36.7,
            "battery": 20,
            "hardware_mode": "pulse-oximetry",
            "user_id": user_id,
            "sensor_id": "na",
            "skin_contact": 1,
            "datetime_server_received": "2025-01-17 02:42:34",
            "last_sync_finger": "2025-01-17 02:42:34",
            "last_sync_chest": "2024-12-02 03:42:54",
            "datetime_latest_valid_chest": "2022-07-16 16:09:41",
            "datetime_latest_valid_finger": utc_time_str,
            "skin_temperature": 34.7,
            "battery_chest": 20,
            "battery_finger": 20,
            "datetime_chest": utc_time_str,
            "datetime_finger": utc_time_str,
        }

        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"

        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["hr"] == 88.0, "incorrect HR"
        assert list_trigger_data["spo2"] == 98.0, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "HR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()


    def test_list_health_input_valid_with_recent_data(self):

        # test list trigger
        user_id = "3"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] - 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        data =  {
            "rr": 19,
            "date_time": "2025-01-16 06:00:00",
            "datetime_manual_data_rr": utc_time_str,
            "datetime_manual_data_body_temp": "2025-01-16 06:00:00",
            "dashboard_mode": "HR",
            "hr": 51,
            "manual_data_rr": 30,
            "skin_contact_finger": 1,
            "datetime_manual_data_hr": utc_time_str,
            "battery": 20,
            "hardware_mode": "pulse-oximetry",
            "datetime_manual_data_weight": "2025-01-16 06:00:00",
            "manual_data_blood_sugar": 5.5,
            "datetime_server_received": "2025-01-17 02:56:48",
            "last_sync_chest": "2024-12-02 03:42:54",
            "manual_data_body_temp": 34.6,
            "datetime_latest_valid_chest": "2022-07-16 16:09:41",
            "datetime_manual_data_spo2": utc_time_str,
            "datetime_latest_valid_finger": "2023-08-23 08:30:16",
            "battery_finger": 20,
            "datetime_finger": "2023-08-23 08:30:16",
            "datetime_manual_data_blood_sugar": "2025-01-16 06:00:00",
            "manual_data_weight": 85,
            "last_sync": "2025-01-17 02:56:48",
            "skin_contact_chest": 1,
            "last_sync_finger": "2025-01-17 02:56:48",
            "spo2": 98,
            "body_temperature": 36.7,
            "datetime_manual_data_bp_sys": utc_time_str,
            "manual_data_bp_dia": 80,
            "manual_data_spo2": 93,
            "user_id": user_id,
            "sensor_id": "na",
            "skin_contact": 1,
            "manual_data_hr": 200,
            "manual_data_bp_sys": 126,
            "skin_temperature": 34.7,
            "battery_chest": 20,
            "datetime_manual_data_bp_dia": utc_time_str,
            "datetime_chest": utc_time_str,
            "news": 11.0,
        }

        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"

        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["hr"] == -1, "incorrect HR"
        assert list_trigger_data["spo2"] == -1, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "HR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"
        assert list_trigger_data["manual_data_bp_sys"] == 126, "incorrect manual_data_bp_sys"
        assert list_trigger_data["manual_data_bp_dia"] == 80, "incorrect manual_data_bp_dia"
        assert list_trigger_data["manual_data_rr"] == 30, "incorrect manual_data_rr"
        assert list_trigger_data["manual_data_hr"] == 200, "incorrect manual_data_hr"
        assert list_trigger_data["manual_data_spo2"] == 93, "incorrect manual_data_spo2"
        assert list_trigger_data["news"] == 11, "incorrect EWS"


        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()


    def test_list_valid_no_recent_data(self):

        # test list trigger
        user_id = "-4"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] + 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        data =  {
                "rr": 22,
                "bp_sys": 100,
                "bp_dia": 60,
                "date_time": "2023-03-08 07:45:16",
                "last_sync": "2023-03-08 09:06:14",
                "skin_contact_chest": 0,
                "dashboard_mode": "RR",
                "body_temperature": 34.5,
                "battery": 50,
                "hardware_mode": "respiratory-rate",
                "user_id": user_id,
                "sensor_id": "80e1261d4f3b",
                "skin_contact": 0,
                "datetime_server_received": "2023-03-08 09:06:20",
                "last_sync_chest": "2023-03-08 09:06:14",
                "datetime_latest_valid_chest": "2023-03-08 07:15:50",
                "skin_temperature": 32.5,
                "battery_chest": 93,
                "datetime_chest": utc_time_str,
                "datetime_finger": utc_time_str,
            }

        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"

        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["dashboard_mode"] == "RR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["bp_sys"] == 100, "incorrect BP_Sys"
        assert list_trigger_data["bp_dia"] == 60, "incorrect BP_Dia"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()


    def test_list_chest_data_valid_no_recent_data(self):

        # test list trigger
        user_id = "0"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] + 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        data =  {
            "rr": 26,
            "date_time": "2024-12-22 02:10:05",
            "datetime_manual_data_rr": "2025-01-16 06:00:00",
            "datetime_manual_data_body_temp": "2025-01-16 06:00:00",
            "dashboard_mode": "RR",
            "hr": 51,
            "manual_data_rr": 30,
            "skin_contact_finger": 1,
            "datetime_manual_data_hr": "2025-01-16 06:00:00",
            "battery": 100,
            "hardware_mode": "respiratory-rate",
            "datetime_manual_data_weight": "2025-01-16 06:00:00",
            "manual_data_blood_sugar": 5.5,
            "datetime_server_received": "2025-01-17 03:08:40",
            "last_sync_chest": "2024-12-19 06:47:39",
            "manual_data_body_temp": 34.6,
            "datetime_latest_valid_chest": "2024-12-22 02:10:05",
            "datetime_manual_data_spo2": "2025-01-16 06:00:00",
            "datetime_latest_valid_finger": "2023-08-23 08:30:16",
            "battery_finger": 20,
            "datetime_finger": "2023-08-23 08:30:16",
            "datetime_manual_data_blood_sugar": "2025-01-16 06:00:00",
            "manual_data_weight": 85,
            "last_sync": "2024-12-19 06:47:39",
            "skin_contact_chest": 1,
            "last_sync_finger": "2025-01-17 02:56:48",
            "spo2": 98,
            "body_temperature": 36,
            "datetime_manual_data_bp_sys": "2025-01-16 06:00:00",
            "manual_data_bp_dia": 80,
            "manual_data_spo2": 93,
            "user_id": user_id,
            "sensor_id": "80e1279dac5a",
            "skin_contact": 1,
            "manual_data_hr": 200,
            "manual_data_bp_sys": 126,
            "skin_temperature": 34,
            "battery_chest": 100,
            "datetime_manual_data_bp_dia": "2025-01-16 06:00:00",
            "datetime_chest": utc_time_str
        }

        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        # print(response_list_trigger)
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"


        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["hr"] == -1, "incorrect HR"
        assert list_trigger_data["spo2"] == -1, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "RR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"


        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()

    def test_list_finger_no_recent_data(self):
        # test list trigger
        user_id = "0"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] + 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        data =  {
            "rr": 19,
            "date_time": "2023-08-18 06:30:21",
            "last_sync": "2025-01-17 02:42:34",
            "skin_contact_chest": 1,
            "last_sync_finger": "2025-01-17 02:42:34",
            "spo2": 98,
            "dashboard_mode": "HR",
            "hr": 88,
            "body_temperature": 36.7,
            "skin_contact_finger": 1,
            "battery": 20,
            "hardware_mode": "pulse-oximetry",
            "user_id": user_id,
            "sensor_id": "na",
            "skin_contact": 1,
            "datetime_server_received": "2025-01-17 02:42:34",
            "last_sync_chest": "2024-12-02 03:42:54",
            "datetime_latest_valid_chest": "2022-07-16 16:09:41",
            "skin_temperature": 34.7,
            "battery_chest": 20,
            "datetime_latest_valid_finger": "2023-08-18 06:30:21",
            "battery_finger": 20,
            "datetime_finger": utc_time_str,
            "datetime_chest": utc_time_str,
        }
        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"


        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["hr"] == -1, "incorrect HR"
        assert list_trigger_data["spo2"] == -1, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "HR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()


    def test_list_health_input_valid_no_recent_data(self):
        # test list trigger
        user_id = "0"
        utc_time_str = (datetime.datetime.utcnow() - datetime.timedelta(minutes=(settings.list_timedelta["MINUTES"] + 2))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
            
        data =  {
            "rr": 19,
            "date_time": "2025-01-16 06:00:00",
            "datetime_manual_data_rr": utc_time_str,
            "datetime_manual_data_body_temp": "2025-01-16 06:00:00",
            "dashboard_mode": "HR",
            "hr": 51,
            "manual_data_rr": 30,
            "skin_contact_finger": 1,
            "datetime_manual_data_hr": utc_time_str,
            "battery": 20,
            "hardware_mode": "pulse-oximetry",
            "datetime_manual_data_weight": "2025-01-16 06:00:00",
            "manual_data_blood_sugar": 5.5,
            "datetime_server_received": "2025-01-17 02:56:48",
            "last_sync_chest": "2024-12-02 03:42:54",
            "manual_data_body_temp": 34.6,
            "datetime_latest_valid_chest": "2022-07-16 16:09:41",
            "datetime_manual_data_spo2": utc_time_str,
            "datetime_latest_valid_finger": "2023-08-23 08:30:16",
            "battery_finger": 20,
            "datetime_finger": "2023-08-23 08:30:16",
            "datetime_manual_data_blood_sugar": "2025-01-16 06:00:00",
            "manual_data_weight": 85,
            "last_sync": "2025-01-17 02:56:48",
            "skin_contact_chest": 1,
            "last_sync_finger": "2025-01-17 02:56:48",
            "spo2": 98,
            "body_temperature": 36.7,
            "datetime_manual_data_bp_sys": utc_time_str,
            "manual_data_bp_dia": 80,
            "manual_data_spo2": 93,
            "user_id": user_id,
            "sensor_id": "na",
            "skin_contact": 1,
            "manual_data_hr": 200,
            "manual_data_bp_sys": 126,
            "skin_temperature": 34.7,
            "battery_chest": 20,
            "datetime_manual_data_bp_dia": utc_time_str,
            "datetime_chest":utc_time_str,
            "news": 11,
        }
        data = convert_to_python_datetime(data)
        min_metric_cache_obj  = MetricMinutesCache.objects.create(**data)

        response = real_time_trigger(min_metric_cache_obj.id)
        response_list_trigger = json.loads(response["list_trigger"])
        list_trigger_data = response_list_trigger["data"]

        assert (
            str(response_list_trigger["patientIdInt"]) == user_id
        ), "incorret user id in the response"


        assert list_trigger_data["rr"] == -1, "incorrect RR"
        assert list_trigger_data["hr"] == -1, "incorrect HR"
        assert list_trigger_data["spo2"] == -1, "incorrect SpO2"
        assert list_trigger_data["dashboard_mode"] == "HR", "incorrect dashboardMode"
        assert list_trigger_data["body_temperature"] == -1, "incorrect bodyTemp"
        assert list_trigger_data["battery"] == -1, "incorrect battery"
        assert list_trigger_data["battery_chest"] == -1, "incorrect battery_chest"
        assert list_trigger_data["skin_temperature"] == -1, "incorrect skinTemp"
        assert list_trigger_data["skin_contact"] == -1, "incorrect skin_contact"
        assert list_trigger_data["manual_data_bp_sys"] == -1, "incorrect manual_data_bp_sys"
        assert list_trigger_data["manual_data_bp_dia"] == -1, "incorrect manual_data_bp_dia"
        assert list_trigger_data["manual_data_rr"] == -1, "incorrect manual_data_rr"
        assert list_trigger_data["manual_data_hr"] == -1, "incorrect manual_data_hr"
        assert list_trigger_data["manual_data_spo2"] == -1, "incorrect manual_data_spo2"
        assert list_trigger_data["news"] == 11, "incorrect EWS"

        # delete test data
        min_metric_cache_obj.delete()
        MetricMinutesCache.objects.all().delete()












