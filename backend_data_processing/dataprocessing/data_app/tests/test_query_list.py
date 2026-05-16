import json
import os
import datetime
import pandas as pd
import numpy as np
import requests
import pytz
import urllib.parse
from decimal import Decimal
from django.test import TestCase

from dataprocessing import lib_settings as settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app.models import *
from data_app.lib_common import check_skin_status_sequence



class PatientListMinuteTestCase(TestCase):

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

    def setUp(self):

        self.url = "/api/v1/query/list"
        self.token = self._get_auth_token()

        # setup code

        user_id = "0"

        # input data

        data_available = [
            {
                "user_id": user_id,
                "datetime": "2002-07-08 13:01:45",
                "bp_sys": None,
                "bp_dia": None,
                "weight": 67,
                "blood_sugar": 5.6,
                "rr": 32,
                "hr": None,
                "spo2": None,
                "body_temp": None,
                "datetime_received": "2002-07-08 13:01:46",
            },
            {
                "user_id": user_id,
                "datetime": "2002-07-08 13:01:44",
                "bp_sys": 100,
                "bp_dia": 60,
                "weight": None,
                "blood_sugar": None,
                "rr": None,
                "hr": 56,
                "spo2": 98,
                "body_temp": 37.2,
                "datetime_received": "2002-07-08 13:01:45",
            },
            {
                "user_id": user_id,
                "datetime": "2002-07-08 13:01:43",
                "bp_sys": 101,
                "bp_dia": 61,
                "weight": None,
                "blood_sugar": None,
                "rr": 33,
                "hr": 56,
                "spo2": 97,
                "body_temp": 37.3,
                "datetime_received": "2002-07-08 13:01:44",
            },
        ]

        for data in data_available:
            data['datetime'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime'], '%Y-%m-%d %H:%M:%S'))
            data['datetime_received'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime_received'], '%Y-%m-%d %H:%M:%S'))
            HealthData.objects.create(**data)

        data_unavailable = [
            {
                "user_id": user_id,
                "datetime": "2003-01-01 13:01:45",
                "bp_sys": None,
                "bp_dia": None,
                "weight": None,
                "blood_sugar": None,
                "rr": None,
                "hr": None,
                "spo2": None,
                "body_temp": None,
                "datetime_received": "2003-01-01 13:01:46",
            },
            {
                "user_id": user_id,
                "datetime": "2003-01-01 13:01:44",
                "bp_sys": None,
                "bp_dia": None,
                "weight": None,
                "blood_sugar": None,
                "rr": None,
                "hr": None,
                "spo2": None,
                "body_temp": None,
                "datetime_received": "2003-01-01 13:01:45",
            },
        ]

        for data in data_unavailable:
            data['datetime'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime'], '%Y-%m-%d %H:%M:%S'))
            data['datetime_received'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime_received'], '%Y-%m-%d %H:%M:%S'))
            HealthData.objects.create(**data)

        data_missing = [
            {
                "user_id": user_id,
                "datetime": "2004-01-01 13:01:45",
                "bp_sys": 168,
                "bp_dia": 89,
                "datetime_received": "2003-01-01 13:01:46",
            },
            {
                "user_id": user_id,
                "datetime": "2004-01-01 13:01:44",
                "bp_sys": 170,
                "bp_dia": 90,
                "datetime_received": "2003-01-01 13:01:45",
            },
        ]

        for data in data_missing:
            data['datetime'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime'], '%Y-%m-%d %H:%M:%S'))
            data['datetime_received'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime_received'], '%Y-%m-%d %H:%M:%S'))
            HealthData.objects.create(**data)

        bp_device_data_available = [
            {
                "user_id": user_id,
                "datetime": "2025-07-08 13:01:44",
                "bp_sys": 101,
                "bp_dia": 61
            }
        ]

        for data in bp_device_data_available:
            data['datetime'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime'], '%Y-%m-%d %H:%M:%S'))
            OtherDeviceReading.objects.create(**data)

        emr_observation_list = [
            {
                "user_id": user_id,
                "datetime": "2025-08-17 07:01:44",
                "bp_sys": 101,
                "bp_dia": 61,
                "weight": 75,
                "blood_sugar": 110,
                "rr": 55,
                "hr": 66,
                "spo2": 90,
                "body_temperature": 90,
            }
        ]

        for data in emr_observation_list:
            data['datetime'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime'], '%Y-%m-%d %H:%M:%S'))
            OtherDeviceReading.objects.create(**data)


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()

    def test_valid_single_id_health_input_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2002-07-08T13:01:46",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["BP_Sys"] == 100, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 60, "incorrect BP_Dia"
        assert metrics["RR_manual"] == 32, "incorrect RR_manual"
        assert metrics["HR_manual"] == 56, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == 98, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == 37.2, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == 67, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 5.6, "incorrect blood_sugar_manual"

    def test_valid_single_id_health_input_is_none(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2003-01-01T13:01:46",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"

    def test_valid_single_id_health_input_unavailble(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2004-07-08T13:01:46",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"

    def test_valid_multiple_id(self):

        list_id = "0,1,2,3"

        user_id = "0"

        params = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-04-03T07:50:59",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        for x in list_id.split(","):
            assert (
                x in response.keys()
            ), f"input user id ({list_id}) is not in the response"

    def test_invalid_single_id_missing_datetime(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_invalid_multiple_id_missing_datetime(self):

        list_id = "0,1,2,3"

        params = {
            "list_of_id": list_id,
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_valid_sequence_on_skin(self):

        user_id = "-1"
        event = [
            {
                "userId": user_id,
                "dateTime": "2024-05-10 08:03:01",
                "dashboardMode": "RR",
                "RR": 10,
                "sensor_onskin_status": 0,
            },
            {
                "userId": user_id,
                "dateTime": "2024-05-10 08:03:02",
                "dashboardMode": "RR",
                "RR": 11,
                "sensor_onskin_status": 0,
            },
            {
                "userId": user_id,
                "dateTime": "2024-05-10 08:03:02",
                "dashboardMode": "RR",
                "RR": 12,
                "sensor_onskin_status": 0,
            },
            {
                "userId": user_id,
                "dateTime": "2024-05-10 08:03:02",
                "dashboardMode": "RR",
                "RR": 13,
                "sensor_onskin_status": 0,
            },
        ]

        assert check_skin_status_sequence(event, 4) == 0, "expected result is 0"

        event[0]["sensor_onskin_status"] = 1
        assert check_skin_status_sequence(event, 4) == 0, "expected result is 0"

    def test_edge_case_single_id_health_input_column_missing(self):
        # not all health input fields are available

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2004-01-01T13:01:50",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["BP_Sys"] == 168, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 89, "incorrect BP_Dia"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"

    def test_valid_single_id_bp_device_data_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2025-07-08T13:03:55",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["activity"] == -1, "incorrect activity"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["bp_sys_device"] == 101, "incorrect bp_sys_device"
        assert metrics["bp_dia_device"] == 61, "incorrect bp_dia_device"

    def test_valid_single_id_emr_observations_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2025-08-17T10:00:00",
            "resolution": "minutes",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["activity"] == -1, "incorrect activity"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["RR_manual"] == -1, "incorrect RR_manual"
        assert metrics["HR_manual"] == -1, "incorrect HR_manual"
        assert metrics["SpO2_manual"] == -1, "incorrect SpO2_manual"
        assert metrics["body_temp_manual"] == -1, "incorrect body_temp_manual"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["RR_emr"] == 55, "incorrect RR_emr"
        assert metrics["HR_emr"] == 66, "incorrect HR_emr"
        assert metrics["SpO2_emr"] == 90, "incorrect SpO2_emr"
        assert metrics["BP_Sys_emr"] == 101, "incorrect BP_Sys_emr"
        assert metrics["BP_Dia_emr"] == 61, "incorrect BP_Dia_emr"
        assert metrics["body_temp_emr"] == 90, "incorrect body_temp_emr"
        assert metrics["weight_emr"] == 75, "incorrect weight_emr"
        assert metrics["blood_sugar_emr"] == 110, "incorrect blood_sugar_emr"


class PatientListDailyTestCase(TestCase):

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

    def setUp(self):

        self.url = "/api/v1/query/list"
        self.token = self._get_auth_token()

        # setup code

        user_id = "0"

        # input data

        data_available = [
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-01 00:00:00",
                "bp_sys": 101,
                "bp_dia": 61,
                "weight": 67,
                "blood_sugar": 5.6,
                "rr": 33,
                "hr": 56,
                "spo2": 97,
                "body_temperature": 37.3,
                "news": 4,
                "activity": 10,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-02 00:00:00",
                "bp_sys": 100,
                "bp_dia": 60,
                "weight": 66,
                "blood_sugar": 4.6,
                "rr": 32,
                "hr": 55,
                "spo2": 96,
                "body_temperature": 36.3,
                "news": 5,
                "activity": 20,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-03 00:00:00",
                "bp_sys": 102,
                "bp_dia": 62,
                "weight": 68,
                "blood_sugar": 6.6,
                "rr": 34,
                "hr": 58,
                "spo2": 98,
                "body_temperature": 38.3,
                "news": 5,
                "activity": 30,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-05 00:00:00",
                "rr": 34,
                "hr": 58,
                "spo2": 98,
                "body_temperature": 38.3,
                "activity": 40,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-06 00:00:00",
                "bp_sys": 102,
                "bp_dia": 62,
                "weight": 68,
                "blood_sugar": 6.6,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-20 00:00:00",
                "rr": 34,
                "hr": 58,
                "spo2": 98,
                "body_temperature": 38.3,
                "activity": 40,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-28 00:00:00",
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-29 00:00:00",
                "bp_sys": 102,
                "bp_dia": 62,
                "weight": 68,
                "blood_sugar": 6.6,
            },
            {
                "user_id": user_id,
                "datetime_updated": "2000-12-30 00:00:00",
            },
        ]

        for data in data_available:
            data['datetime_updated'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime_updated'], '%Y-%m-%d %H:%M:%S'))
            MetricDailyCache.objects.create(**data)

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()

    def test_valid_single_id_health_input_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-01T10:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == 33, "incorrect RR"
        assert metrics["HR"] == 56, "incorrect HR"
        assert metrics["SpO2"] == 97, "incorrect SpO2"
        assert metrics["body_temperature"] == 37.3, "incorrect body_temperature"
        assert metrics["BP_Sys"] == 101, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 61, "incorrect BP_Dia"
        assert metrics["weight_manual"] == 67, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 5.6, "incorrect blood_sugar_manual"
        assert metrics["EWS"] == 4, "incorrect EWS"
        assert metrics["activity"] == 10, "incorrect activity"

    def test_valid_single_id_all_input_unavailble(self):
        '''test case when   no data on single day  during time peroid (7 days)'''

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-04T16:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]
        print(response)

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == 34, "incorrect RR"
        assert metrics["HR"] == 58, "incorrect HR"
        assert metrics["SpO2"] == 98, "incorrect SpO2"
        assert metrics["body_temperature"] == 38.3, "incorrect body_temperature"
        assert metrics["BP_Sys"] == 102, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 62, "incorrect BP_Dia"
        assert metrics["weight_manual"] == 68, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 6.6, "incorrect blood_sugar_manual"
        assert metrics["activity"] == 30, "incorrect activity"

    def test_valid_single_id_all_input_unavailble_in_duration(self):
        '''test case when   no data are availble for time peroid (7 days)'''

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-16T16:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["body_temperature"] == -1, "incorrect body_temperature"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["activity"] == -1, "incorrect activity"

    def test_valid_multiple_id(self):

        list_id = "0,1,2,3"

        user_id = "0"

        params = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-04-03T07:50:59",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        for x in list_id.split(","):
            assert (
                x in response.keys()
            ), f"input user id ({list_id}) is not in the response"

    def test_invalid_single_id_missing_datetime(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_invalid_multiple_id_missing_datetime(self):

        list_id = "0,1,2,3"

        params = {
            "list_of_id": list_id,
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_valid_single_id_sensor_data_only_availble(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-20T16:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        metrics = response[user_id]

        assert metrics["RR"] == 34, "incorrect RR"
        assert metrics["HR"] == 58, "incorrect HR"
        assert metrics["SpO2"] == 98, "incorrect SpO2"
        assert metrics["body_temperature"] == 38.3, "incorrect body_temperature"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["EWS"] == -1, "incorrect EWS"
        assert metrics["activity"] == 40, "incorrect activity"

    def test_valid_single_id_health_input_data_only_availble(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-29T16:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["body_temperature"] == -1, "incorrect body_temperature"
        assert metrics["BP_Sys"] == 102, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 62, "incorrect BP_Dia"
        assert metrics["weight_manual"] == 68, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 6.6, "incorrect blood_sugar_manual"
        assert metrics["EWS"] == -1, "incorrect EWS"
        assert metrics["activity"] == -1, "incorrect activity"


class PatientListHourlyTestCase(TestCase):

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

    def setUp(self):

        self.url = "/api/v1/query/list"
        self.token = self._get_auth_token()

        # setup code
        user_id = "0"

        # input data
        data_available = [
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-01 00:00:00",
            "bp_sys": 101,
            "bp_dia": 61,
            "weight": 67,
            "blood_sugar": 5.6,
            "rr": 33,
            "hr": 56,
            "spo2": 97,
            "body_temperature": 37.3,            
            "activity": 10,           
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-01 01:00:00",
            "bp_sys": 100,
            "bp_dia": 60,
            "weight": 66,
            "blood_sugar": 4.6,
            "rr": 32,
            "hr": 55,
            "spo2": 96,
            "body_temperature": 36.3,
            "activity": 20,                      
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-01 02:00:00",
            "bp_sys": 102,
            "bp_dia": 62,
            "weight": 68,
            "blood_sugar": 6.6,
            "rr": 34,
            "hr": 58,
            "spo2": 98,
            "body_temperature": 38.3,
            "activity": 30,          
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-02 16:00:00",
            "rr": 34,
            "hr": 58,
            "spo2": 98,
            "body_temperature": 38.3,
            "activity": 40,
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-04 19:00:00",
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-04 20:00:00",
            "bp_sys": 102,
            "bp_dia": 62,
            "weight": 68,
            "blood_sugar": 6.6,
        },
        {
            "user_id": user_id,
            "datetime_updated": "2000-12-04 21:00:00",
        },
        ]


        for data in data_available:
            data['datetime_updated'] = pytz.UTC.localize(datetime.datetime.strptime(data['datetime_updated'], '%Y-%m-%d %H:%M:%S'))
            MetricHourlyCache.objects.create(**data)

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        
    def test_valid_single_id_health_input_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-01T00:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]


        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == 33, "incorrect RR"
        assert metrics["HR"] == 56, "incorrect HR"
        assert metrics["SpO2"] == 97, "incorrect SpO2"
        assert metrics["activity"] == 10, "incorrect activity"
        assert metrics["BP_Sys"] == 101, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 61, "incorrect BP_Dia"
        assert metrics["body_temperature"] == 37.3, "incorrect body_temperature"
        assert metrics["weight_manual"] == 67, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 5.6, "incorrect blood_sugar_manual"

    def test_valid_single_id_all_input_unavailble(self):
        '''test case when   no data  available on single hour  during time peroid (24 hours)'''

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-01T16:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == 34, "incorrect RR"
        assert metrics["HR"] == 58, "incorrect HR"
        assert metrics["SpO2"] == 98, "incorrect SpO2"
        assert metrics["activity"] == 30, "incorrect activity"
        assert metrics["BP_Sys"] == 102, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 62, "incorrect BP_Dia"
        assert metrics["body_temperature"] == 38.3, "incorrect body_temperature"
        assert metrics["weight_manual"] == 68, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 6.6, "incorrect blood_sugar_manual"

    def test_valid_single_id_all_input_unavailble_in_duration(self):
        '''test case when   no data are availble for time peroid (24 hours)'''

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-03T20:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["activity"] == -1, "incorrect activity"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["body_temperature"] == -1, "incorrect body_temperature"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"

    def test_valid_multiple_id(self):

        list_id = "0,1,2,3"

        user_id = "0"

        params = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-04-03T07:50:59",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]

        for x in list_id.split(","):
            assert (
                x in response.keys()
            ), f"input user id ({list_id}) is not in the response"

    def test_invalid_single_id_missing_datetime(self):

        user_id = "0"

        params = {
            "list_of_id": user_id,
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_invalid_multiple_id_missing_datetime(self):

        list_id = "0,1,2,3"

        params = {
            "list_of_id": list_id,
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        assert "date_time" in response.json()

    def test_valid_single_id_sensor_data_only_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-02T16:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]


        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == 34, "incorrect RR"
        assert metrics["HR"] == 58, "incorrect HR"
        assert metrics["SpO2"] == 98, "incorrect SpO2"
        assert metrics["body_temperature"] == 38.3, "incorrect body_temperature"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
        assert metrics["EWS"] == -1, "incorrect EWS"
        assert metrics["activity"] == 40, "incorrect activity"

    def test_valid_single_id_health_input_data_only_availble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2000-12-04T20:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]


        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["body_temperature"] == -1, "incorrect body_temperature"
        assert metrics["BP_Sys"] == 102, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == 62, "incorrect BP_Dia"
        assert metrics["weight_manual"] == 68, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == 6.6, "incorrect blood_sugar_manual"
        assert metrics["EWS"] == -1, "incorrect EWS"
        assert metrics["activity"] == -1, "incorrect activity"

    def test_valid_single_id_health_input_unavailble(self):
        user_id = "0"

        params = {
            "list_of_id": user_id,
            "date_time": "2002-12-01T00:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]


        assert (
            user_id in response.keys()
        ), f"input user id ({user_id}) is not in the response"

        metrics = response[user_id]

        assert metrics["RR"] == -1, "incorrect RR"
        assert metrics["HR"] == -1, "incorrect HR"
        assert metrics["SpO2"] == -1, "incorrect SpO2"
        assert metrics["activity"] == -1, "incorrect activity"
        assert metrics["BP_Sys"] == -1, "incorrect BP_Sys"
        assert metrics["BP_Dia"] == -1, "incorrect BP_Dia"
        assert metrics["body_temperature"] == -1, "incorrect body_temperature"
        assert metrics["weight_manual"] == -1, "incorrect weight_manual"
        assert metrics["blood_sugar_manual"] == -1, "incorrect blood_sugar_manual"
