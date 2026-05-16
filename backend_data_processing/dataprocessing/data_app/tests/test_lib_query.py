import os
import pandas as pd
import json
import numpy as np
import csv
import requests
from io import StringIO
from decimal import Decimal
from datetime import datetime, timedelta, timezone


from django.test import TestCase
from django.utils.dateparse import parse_datetime


from data_app.lib_query import EarlyWarningScore
from data_app.views import QueryTrendView
from data_app.models import DataProcessing, SpotCache, MetricDailyCache, MetricMinutesCache, MetricHourlyCache,StagingHourlyCache,HealthData
from data_app.lib_common import get_devices_data_multiple, get_devices_data, load_from_cache,get_other_spot_data
from dataprocessing.lib_settings import (val_replace_NaN, 
    BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES, min_hr_finger_required_within_day, 
    min_hr_finger_required_within_hour, trends_vital_sign_minutes_resolution,
    list_timedelta)
from data_app.lib_query import (get_spot_data, get_spot_data_from_cache_v2, 
        handle_spot_trend_query, cal_data_length, get_trends,
        display_battery)
from data_app.tests.data.data_lib_query import *
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from dataprocessing import lib_settings as settings
from data_app.lib_update_cache_incremental import(
    hourly_start_stop_timeframe,
    handle_update_hourly_cache,
    daily_start_stop_timeframe,
    handle_update_daily_cache
)




base_path = os.path.dirname(__file__)

class TestEarlyWarningScore(TestCase):
    """Test NEWS early warning score"""

    # Test Scope
    # * test - only required vitals
    # * test - only required vitals, except rr
    # * test - only required vitals, except hr
    # * test - only required vitals, except spo2
    # * test - only required vitals, except temp
    # * test - only required vitals and bp_sys
    # * test - only required vitals and supplemental_oxygen
    # * test - only required vitals and avpu
    #
    # Out-of-scope
    # * wrong input type

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()
        
    def error_message_incorrect_score(self):
        """Incorrect score error message"""
        return "incorrect score"

    def error_message_missing_input(self):
        """Error message when required input is missing"""
        return "Not all required elements are available"

    def error_message_no_vitals(self):
        """error message when not vitals are present"""
        return "At least one required element must be present"
    
    def __get_ews_score(self, x: dict, ews_type: str) -> int:
        """Get EWS score
        Args:
            x (dict): Dict of vitals input
        Returns:
            int: EWS score
        """
        ews = EarlyWarningScore(x)
        score = ews.get_score(ews_type)
        return score

    def test_news_valid_required_input(self):
        """Test - only required vitals"""
        score = self.__get_ews_score(
            {"rr": 5, "spo2": 90, "temp": 33.7, "hr": 30}, "NEWS"
        )
        self.assertEqual(score, 12, self.error_message_incorrect_score())

    def test_news_valid_required_input_w_bpsys(self):
        """Test - only required vitals and bp_sys"""
        score = self.__get_ews_score(
            {"rr": 5, "spo2": 90, "temp": 33.7, "hr": 30, "bp_sys": 95}, "NEWS"
        )
        self.assertEqual(score, 14, self.error_message_incorrect_score())

    def test_news_valid_required_input_w_supplemental_oxygen(self):
        """Test - only required vitals and supplemental_oxygen"""
        score = self.__get_ews_score(
            {"rr": 5, "spo2": 90, "temp": 33.7, "hr": 30, "supplemental_oxygen": "Yes"},
            "NEWS",
        )
        self.assertEqual(score, 14, self.error_message_incorrect_score())

    def test_news_valid_required_input_w_avpu(self):
        """Test - only required vitals and avpu"""
        score = self.__get_ews_score(
            {"rr": 5, "spo2": 90, "temp": 33.7, "hr": 30, "avpu": "P"}, "NEWS"
        )
        self.assertEqual(score, 15, self.error_message_incorrect_score())

    def test_news_valid_required_input_w_bpsys_supplemental_oxygen_avpu(self):
        """Test - only required vitals and bp_sys, supplemental_oxygen, avpu"""
        score = self.__get_ews_score(
            {
                "rr": 5,
                "spo2": 90,
                "temp": 33.7,
                "hr": 30,
                "bp_sys": 95,
                "supplemental_oxygen": "Yes",
                "avpu": "P",
            },
            "NEWS",
        )
        self.assertEqual(score, 19, self.error_message_incorrect_score())

    def test_news_valid_required_input_wo_rr(self):
        """test - only required vitals, except rr"""
        score = self.__get_ews_score({"spo2": 100, "temp": 36.1, "hr": 51}, "NEWS")
        assert score == 0

    def test_news_valid_required_input_wo_hr(self):
        """test - only required vitals, except hr"""
        score = self.__get_ews_score({"rr": 5, "spo2": 100, "temp": 36.1}, "NEWS")
        assert score == 3

    def test_news_valid_required_input_wo_spo2(self):
        """test - only required vitals, except spo2"""
        score = self.__get_ews_score({"rr": 5, "temp": 36.1, "hr": 51}, "NEWS")
        assert score == 3

    def test_news_valid_required_input_wo_temp(self):
        """test - only required vitals, except temp"""
        score = self.__get_ews_score({"rr": 5, "spo2": 100, "hr": 51}, "NEWS")
        assert score == 3

    def test_news_valid_w_rr(self):
        """test - only required vitals, except temp"""
        score = self.__get_ews_score({"rr": 5}, "NEWS")
        assert score == 3

    def test_news_valid_w_hr(self):
        """test - only required vitals, except temp"""
        score = self.__get_ews_score({"hr": 95}, "NEWS")
        assert score == 1

    def test_news_no_vitals(self):
        """test - no vitals"""

        with self.assertRaises(ValueError) as context:
            score = self.__get_ews_score({}, "NEWS")
            self.assertIn(self.error_message_no_vitals(), str(context.exception))


class TestFunctionLoadFromCache(TestCase):

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()
        
    def test_patient_list_cache_daily(self):

        item = {
            "user_id": "-1",
            "datetime_updated": "2024-03-13 00:00:00",
            "body_temperature": 35,
            "hr": 60,
            "rr": 18,
            "rr_dc": 48,
            "rr_td": 46,
            "skin_temperature": 33,
            "spo2": 98,
            "bp_dia": 90,
            "bp_sys": 126,
            "has_manual_reading": 1,
            "news": 4,
            "weight": 85,
            "activity": 45,
        }
        MetricDailyCache.objects.create(**item)

        user_id = "-1"
        response = {user_id: None}
        load_from_cache(
            response,
            user_id,
            "daily",
            datetime.strptime("2024-03-13T16:00:00", "%Y-%m-%dT%H:%M:%S"),
        )
        response = response[user_id]

        assert response["RR"] == -1, 'mismatch RR'
        assert response["HR"] == -1, 'mismatch HR'
        assert response["SpO2"] == -1, 'mismatch SpO2'
        assert response["skin_temperature"] == 33.0, 'mismatch skinTemp'
        assert response["body_temperature"] == 35.0, 'mismatch bodyTemp'
        assert response["BP_Dia"] == 90, 'mismatch BP_Dia'
        assert response["BP_Sys"] == 126, 'mismatch BP_Sys'
        assert response["activity"] == 45, 'mismatch activity'


    def test_patient_list_cache_hourly(self):

        item = {
          "user_id": "-1",
          "datetime_updated": "2025-02-04 16:00:00",
          "body_temperature": 35.3,
          "body_temperature_SD": 1,
          "bp_dia": 90,
          "bp_sys": 126,
          "has_manual_reading": 1,
          "hr": 69,
          "hr_SD": 1,
          "listtime": "2025-02-04 16:00:00",
          "news": 4,
          "rr": 27,
          "rr_dc": 50,
          "rr_SD": 2,
          "rr_td": 28,
          "skin_temperature": 34.1,
          "spo2": 98,
          "spo2_SD": 1,
          "weight": 85,
          "activity": 45,
        }
        MetricHourlyCache.objects.create(**item)

        user_id = "-1"
        response = {user_id: None}
        load_from_cache(
            response,
            user_id,
            "hourly",
            datetime.strptime("2025-02-04T16:00:00", "%Y-%m-%dT%H:%M:%S"),
        )
        response = response[user_id]

        assert response["RR"] == -1, 'mismatch RR'
        assert response["HR"] == -1, 'mismatch HR'
        assert response["SpO2"] == -1, 'mismatch SpO2'
        assert response["skin_temperature"] == 34.1, 'mismatch skinTemp'
        assert response["body_temperature"] == 35.3, 'mismatch bodyTemp'
        assert response["BP_Dia"] == 90, 'mismatch BP_Dia'
        assert response["BP_Sys"] == 126, 'mismatch BP_Sys'
        assert response["activity"] == 45, 'mismatch activity'


    def test_patient_list_cache_minutes(self):

        item=  {
            "user_id": "-1",
            "battery": 100,
            "battery_chest": 100,
            "battery_finger": 100,
            "body_temperature": 36.5,
            "dashboard_mode": "RR",
            "date_time": datetime(2025,3,8,16,0,0),
            "datetime_updated": "2025-03-08 16:00:00",
            "datetime_server_received": "2025-03-08 15:59:00",
            "datetime_chest": "2025-03-08 15:56:00",
            "datetime_finger": "2025-03-08 15:54:00",
            "datetime_latest_valid_chest": "2025-03-08 15:55:00",
            "datetime_latest_valid_finger": "2025-03-08 15:53:00",
            "datetime_manual_data_blood_sugar": "2025-03-08 15:52:00",
            "datetime_manual_data_body_temp": "2025-03-08 15:52:00",
            "datetime_manual_data_bp_dia": "2025-03-08 15:52:00",
            "datetime_manual_data_bp_sys": "2025-03-08 15:52:00",
            "datetime_manual_data_hr": "2025-03-08 15:52:00",
            "datetime_manual_data_rr": "2025-03-08 15:52:00",
            "datetime_manual_data_spo2": "2025-03-08 15:52:00",
            "datetime_manual_data_weight": "2025-03-08 15:52:00",
            "hr": 68,
            "last_sync": "2025-03-08 15:59:00",
            "last_sync_chest": "2025-03-08 15:59:00",
            "last_sync_finger": "2025-03-08 15:58:00",
            "manual_data_blood_sugar": 5.5,
            "manual_data_body_temp": 34.6,
            "manual_data_bp_dia": 90,
            "manual_data_bp_sys": 126,
            "manual_data_hr": 70,
            "manual_data_rr": 28,
            "manual_data_spo2": 99,
            "manual_data_weight": 85,
            "rr": 26,
            "skin_temperature": 34.1,
            "skin_contact": 1,
            "skin_contact_chest": 1,
            "skin_contact_finger": 1,
            "spo2": 97,
            "activity": 45
        }
        MetricMinutesCache.objects.create(**item)

        user_id = "-1"
        response = {user_id: None}

        load_from_cache(
            response,
            user_id,
            "minutes",
            datetime.strptime("2025-03-08T16:42:30", "%Y-%m-%dT%H:%M:%S"),
        )
        response = response[user_id]

        assert response["RR"] == 26, 'mismatch RR'
        assert response["HR"] == 68, 'mismatch HR'
        assert response["SpO2"] == 97, 'mismatch SpO2'
        assert response["skinTemp"] == 34.1, 'mismatch skinTemp'
        assert response["bodyTemp"] == 36.5, 'mismatch bodyTemp'
        assert response["activity"] == 45, 'mismatch activity'
        assert (
            response["datetime_latest_valid_chest"].strftime("%Y-%m-%d %H:%M:%S") == "2025-03-08 15:55:00"
        ), 'mismatch datetime_latest_valid_chest'
        assert (
            response["datetime_latest_valid_finger"].strftime("%Y-%m-%d %H:%M:%S") == "2025-03-08 15:53:00"
        ), 'mismatch datetime_latest_valid_finger'


class TestGetDeviceData(TestCase) :

    def test_compare_muliple_and_single_device_request(self):
        """check response of multiple devices get api is equal to individual devices get api"""
        list_id = "0,1,2"

        list_id = list_id.split(",")
        dict_res_multiple_ids = get_devices_data_multiple(list_id)

        dict_res_single_id = {}
        for x_id in list_id:
            response_single_id = {x_id: {}}
            get_devices_data(response_single_id, x_id)
            dict_res_single_id.update(response_single_id)

        assert dict_res_multiple_ids == dict_res_single_id


class TestGetStartDateTimeInLoadFromCache(TestCase):

    """test that start dates are correct based on resolution provided in load_from_cache function"""

    def test_list_resolution_minutes(self):

        stop_date = datetime(2023, 4, 3, 7, 50, 59)
        expected_start_date_minutes = datetime(2023, 4, 2, 23, 50, 59)

        list_resolution = "minutes"

        if list_resolution == "minutes":
            list_timedelta_resolution = "MINUTES"
            start_date = stop_date - timedelta(
                minutes=list_timedelta[list_timedelta_resolution]
            )

        assert expected_start_date_minutes == start_date

    def test_list_resolution_days(self):

        stop_date = datetime(2023, 4, 3, 7, 50, 59)
        expected_start_date_days = datetime(2023, 3, 28, 7, 50, 59)
        list_resolution = "daily"

        if list_resolution == "daily":
            list_timedelta_resolution = "DAYS"
            start_date = stop_date - timedelta(
                days=list_timedelta[list_timedelta_resolution] - 1
            )

        assert expected_start_date_days == start_date

    def test_list_resolution_hours(self):

        stop_date = datetime(2023, 4, 3, 7, 50, 59)
        expected_start_date_days = datetime(2023, 4, 2, 7, 50, 59)
        list_resolution = "hourly"

        if list_resolution == "hourly":
            list_timedelta_resolution = "HOURS"
            start_date = stop_date - timedelta(
                hours=list_timedelta[list_timedelta_resolution]
            )

        assert expected_start_date_days == start_date


class TestHandleQueryDaily(TestCase):

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

        self.url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.valid_token = settings.VALID_REFERER[0]
        self.invalid_token = 'invalid' + settings.VALID_REFERER[0]

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()

    def test_valid_chest_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """
        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_14_input))

        test_data = test_data.sort_values("datetime_updated")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = MetricDailyCache.objects.create(**cleaned_row)

        # read expected output
        expected_data = pd.read_csv(StringIO(test_case_14_output))
        expected_data = expected_data.sort_values("dateTimeUpdated")

        query_params = {
            "start_datetime": "2000-01-01T00:00:00",
            "stop_datetime": "2000-01-07T00:00:00",
            "id": "-2",
            "resolution": "daily",
            "utc_offset": "+00:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["listdate"] == expected_data["dateTimeUpdated"]
        ).all(), "date and time mismatch."

        assert (
            response_data[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "HR mismatches"

        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "RR mismatches"

        assert (
            response_data[user_id]["metrics"]["SpO2"] == expected_data["SpO2"]
        ).all(), "SpO2 mismatches"

        assert (
            response_data[user_id]["metrics"]["EWS"] == expected_data["EWS"]
        ).all(), "EWS mismatches"


class TestHandleQueryHourly(TestCase):

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

        self.url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.valid_token = settings.VALID_REFERER[0]
        self.invalid_token = 'invalid' + settings.VALID_REFERER[0]

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()
        
    def test_valid_chest_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """

        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_12_input))
        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

            start_date, stop_date = hourly_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_hourly_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        # read expected output
        expected_data = pd.read_csv(StringIO(test_case_12_output))
        expected_data = expected_data.sort_values("dateTime")

        query_params = {
            "start_datetime": "2023-02-17T09:00:00",
            "stop_datetime": "2023-02-17T16:59:59",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "08:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "date and time mismatch."

        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "RR mismatches"


    def test_valid_finger_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """
        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_13_input))

        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

            start_date, stop_date = hourly_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_hourly_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        # read expected output
        expected_data = pd.read_csv(StringIO(test_case_13_output))
        expected_data = expected_data.sort_values("dateTime")

        query_params = {
            "start_datetime": "2000-01-01T00:00:00",
            "stop_datetime": "2000-01-01T06:59:59",
            "id": "-2",
            "resolution": "hourly",
            "utc_offset": "08:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "date and time mismatch."

        assert (
            response_data[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "HR mismatches"

        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "RR mismatches"

        assert (
            response_data[user_id]["metrics"]["SpO2"] == expected_data["SpO2"]
        ).all(), "SpO2 mismatches"


class TestHandleQueryMinutes(TestCase):

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

        self.url = "/api/v1/query/trends"
        self.token = self._get_auth_token()
        self.valid_token = settings.VALID_REFERER[0]
        self.invalid_token = 'invalid' + settings.VALID_REFERER[0]

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()

    def test_valid_chest_with_hr_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """
        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_9_input))
        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

        expected_data = pd.read_csv(StringIO(test_case_9_output))
        expected_data = expected_data.sort_values("dateTime")
        expected_data["HR"] = expected_data["HR"].fillna(
            val_replace_NaN
        )  # convert HR from NaN to -1

        if not BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES:
            expected_data["HR"] = val_replace_NaN  # convert HR to -1

        query_params = {
            "start_datetime": "2023-08-07T20:36:02",
            "stop_datetime": "2023-08-07T20:55:59",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "mismatched RR"
        assert (
            response_data[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "mismatched HR"
        assert (
            response_data[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"


    def test_valid_chest_without_hr_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """

        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_10_input))
        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

        expected_data = pd.read_csv(StringIO(test_case_10_output))
        expected_data = expected_data.sort_values("dateTime")
        expected_data["HR"] = expected_data["HR"].fillna(
            val_replace_NaN
        )  # convert HR from NaN to -1

        if not BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES:
            expected_data["HR"] = val_replace_NaN  # convert HR to -1

        query_params = {
            "start_datetime": "2023-08-07T20:36:02",
            "stop_datetime": "2023-08-07T20:55:59",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "mismatched RR"
        assert (
            response_data[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "mismatched HR"
        assert (
            response_data[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"


    def test_valid_chest_without_hr_and_finger_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """
        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_11_input))
        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

        expected_data = pd.read_csv(StringIO(test_case_11_output))
        expected_data = expected_data.sort_values("dateTime")
        expected_data["HR"] = expected_data["HR"].fillna(
            val_replace_NaN
        )  # convert HR from NaN to -1

        if not BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES:
            expected_data.loc[expected_data["dashboardMode"] == "RR", "HR"] = (
                val_replace_NaN  # convert HR to -1
            )
        query_params = {
            "start_datetime": "2023-07-26T14:14:50",
            "stop_datetime": "2023-07-26T14:24:07",
            "id": "-2",
            "resolution": "minutes",
            "utc_offset": "+08:00"
        }
        url = (
            f"{self.url}"
            f"?start_datetime={query_params['start_datetime']}"
            f"&stop_datetime={query_params['stop_datetime']}"
            f"&id={query_params['id']}"
            f"&resolution={query_params['resolution']}"
            f"&utc_offset={query_params['utc_offset']}"
        )
        headers = {'HTTP_AUTHORIZATION': f"Bearer {self.token}"}
        response = self.client.get(url, **headers)
        response_data = (response.json())['response']

        # verify output
        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "mismatched RR"
        assert (
            response_data[user_id]["metrics"]["HR"] == expected_data["HR"]
        ).all(), "mismatched HR"
        assert (
            response_data[user_id]["metrics"]["SpO2"] == expected_data["SpO2"]
        ).all(), "mismatched HR"
        assert (
            response_data[user_id]["metrics"]["listtime"] == expected_data["dateTime"]
        ).all(), "mismatched date and time"


class TestHandleSpotTrend(TestCase) :

    # def tearDown(self):
    #     DataProcessing.objects.all().delete()
    #     MetricMinutesCache.objects.all().delete()
    #     MetricHourlyCache.objects.all().delete()
    #     MetricDailyCache.objects.all().delete()
    #     SpotCache.objects.all().delete()
    #     StagingHourlyCache.objects.all().delete()
    #     HealthData.objects.all().delete()
        
    def test_valid_finger_data(self):
        """check minutes resolution for handle_spot_trend_query function does not return additional temperature"""

        table = DataProcessing.objects.all()
        userID = "-23"
        startDateTime = "2022-11-24 07:00:00"
        stopDateTime = "2022-11-24 09:00:00"
        desired_attr = ["HR"]
        cond_attr = ["HR"]

        response =  handle_spot_trend_query(
            table, 
            desired_attr, True, False, True, True
            )
        
        # Check if the value in `cond_attr` is equal to any key in `response["metrics"]`
        cond_attr_found = any(attr == cond_attr[0] for attr in response["metrics"])

        # Assert that the value is present as a key in the dictionary
        assert cond_attr_found, f"The value '{cond_attr[0]}' is not a key in the dictionary"

        # assert that temperature isnt part of the dict keys
        temperature_found = "temperature" in response["metrics"]
        assert not temperature_found



    def test_valid_finger_and_chest_data(self):
        table = DataProcessing.objects.all()
        userID = "-25"
        startDateTime = "2022-11-24 07:00:00"
        stopDateTime = "2022-11-24 09:00:00"
        desired_attr = ["HR", "temperature"]
        cond_attr = ["HR", "temperature"]

        response =  handle_spot_trend_query(
            table, 
            desired_attr, True, False, True, True
            )
        
        # Check if "temperature" and "HR" are keys in `response["metrics"]`
        found_temperature = "temperature" in response["metrics"]
        found_hr = "HR" in response["metrics"]

        # Assert that "temperature" and "HR" are present as keys in the dictionary
        assert found_temperature, "The key 'temperature' is not present in the dictionary"
        assert found_hr, "The key 'HR' is not present in the dictionary"


    def test_valid_data(self):
        """
        refer to github issue: https://github.com/Respiree/rpm_data_processing_backend/issues/212
        """
        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_3))
        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)

        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]
        val_nan = val_replace_NaN

        data_cols = ["user_id","date_time","datetime_server_received","battery","rr","sensor_onskin_status","signal_quality_status","body_temperature","dashboard_mode","hr","rr_dc","rr_td","skin_temperature"]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row[data_cols].dropna().to_dict()
            DataProcessing.objects.create(**cleaned_row)
            SpotCache.objects.create(**cleaned_row,source = 'sensor')


        """
        Query (24 Permutations)
        - contact Good, BAD, -1
        - RR      20, -1
        - SQS     Good, Moderate, Poor, Motion
        """

        start_datetime = "2023-02-17 00:00:00"
        end_datetime = "2023-02-17 23:59:59"

        response_spot = get_spot_data(
            DataProcessing.objects,
            user_id,
            str(start_datetime),
            str(end_datetime),
            val_replace_NaN,
        )

        df_spot = pd.DataFrame(response_spot["history"])
        df_spot = df_spot.sort_values("timestamp")

        # get response from SPOT cache
        response_spot_cache = get_spot_data_from_cache_v2(user_id,SpotCache.objects)
        df_spot_cache = pd.DataFrame(response_spot_cache["history"])
        df_spot_cache = df_spot_cache.sort_values("timestamp")

        # extract expected values
        expected_datetime = test_data["expected_datetime"]
        expected_mode = test_data["expected_mode"]
        expected_sensor_onskin_status = test_data["expected_sensor_onskin_status"]
        expected_signal_quality_status = test_data["expected_signal_quality_status"]
        expected_RR = test_data["expected_RR"]
        expected_RR_TD = test_data["expected_RR_TD"]
        expected_HR = test_data["expected_HR"]
        expected_SpO2 = test_data["expected_SpO2"]
        expected_skin_temperature = test_data["expected_skin_temperature"]
        expected_body_temperature = test_data["expected_body_temperature"]


        assert (
            df_spot_cache["timestamp"].values == expected_datetime.values
        ).all(), "timestamp mismatched"
        assert (
            df_spot_cache["mode"].values == expected_mode.values
        ).all(), "mode mismatched"
        assert (
            (df_spot_cache["skin_contact"].values).astype(str)
            == expected_sensor_onskin_status.values
        ).all(), "sensor_onskin_status mismatched"
        assert (
            (df_spot_cache["signal_quality_status"].values).astype(str)
            == expected_signal_quality_status.values
        ).all(), "signal_quality_status mismatched"
        assert (df_spot_cache["RR"].values == expected_RR.values).all(), "RR mismatched"
        assert (
            df_spot_cache["RR_TD"].values == expected_RR_TD.values
        ).all(), "RR_TD mismatched"
        assert (df_spot_cache["HR"].values == expected_HR.values).all(), "HR mismatched"
        assert (
            df_spot_cache["SpO2"].values == expected_SpO2.values
        ).all(), "SpO2 mismatched"
        assert (
            df_spot_cache["skin_temperature"].values == expected_skin_temperature.values
        ).all(), "skin_temperature mismatched"
        assert (
            df_spot_cache["body_temperature"].values == expected_body_temperature.values
        ).all(), "body_temperature mismatched"





    def test_output_when_attr_is_disabled(self):

        """
        test whether output does not contains sqa and skin status if setting is disabled for them and vice versa
        """
        user_id = "-1"

        desired_attr = ["HR", "RR"]
        cond_attr = ["HR", "RR"]
        bool_remove_bad_data = True
        bool_keep_bad_data_as_NaN = True
        replace_NaN_with_value = (False,)

        # initially disable these
        add_sqa_to_trend = False
        add_skin_status_to_trend = False

        start_datetime = "2023-06-09 03:50:26"
        end_datetime = "2023-06-09 05:50:26"

        # data for TestHandleSpotTrend::test_output_when_attr_is_disabled
        test_case_4 = {
            "user_id": "-1",
            "datetime_server_received": "2023-05-23 09:02:22",
            "body_temperature": 35.9,
            "dashboard_mode": "RR",
            "date_time": "2023-06-09 03:50:27",
            "hr": "nan",
            "rr": 10,
            "rr_dc": 55,
            "rr_td": 49.06666667,
            "sensor_contact_status": "Good",
            "sensor_onskin_status": 1,
            "skin_temperature": 33.9,
            "signal_quality_status": "Good"
        }


        input_data = test_case_4
        DataProcessing.objects.create(**input_data)
 
        response = handle_spot_trend_query(
            DataProcessing.objects.all(), desired_attr, bool_remove_bad_data, bool_keep_bad_data_as_NaN,replace_NaN_with_value, add_sqa_to_trend, add_skin_status_to_trend
        )
        # should not contain sensor_onskin_status and signal_quality_status
        assert all(
            key in response["metrics"] for key in ["HR", "RR", "listtime"]
        ) and all(
            key not in response["metrics"]
            for key in ["signal_quality_status", "sensor_onskin_status"]
        ), "Keys are missing or present incorrectly in 'metrics' dictionary."

        # reenable this
        add_sqa_to_trend = True
        add_skin_status_to_trend = True

        dataset = DataProcessing.objects.filter(user_id =user_id)

        response = handle_spot_trend_query(
            dataset, desired_attr, bool_remove_bad_data, bool_keep_bad_data_as_NaN, replace_NaN_with_value, add_sqa_to_trend,add_skin_status_to_trend
        )
        # should contain sensor_onskin_status and signal_quality_status
        assert all(
            key in response["metrics"]
            for key in [
                "signal_quality_status",
                "sensor_onskin_status",
                "HR",
                "RR",
                "listtime",
            ]
        ), "Keys are missing in 'metrics' dictionary."




    def test_skin_contact_is_not_nan_when_no_skin_contact(self):
        """
        test whether output does not contain nan values and instead is replaced with 0 for skin contact
        """
        user_id = "-1"
        desired_attr = ["HR", "RR"]
        cond_attr = ["HR", "RR"]
        bool_remove_bad_data = True
        bool_keep_bad_data_as_NaN = True
        replace_NaN_with_value = (False,)

        # initially disable these
        add_sqa_to_trend = True
        add_skin_status_to_trend = True

        start_datetime = "2023-07-25 06:00:00"
        end_datetime = "2023-07-25 06:30:00"

        # data for TestHandleSpotTrend::test_skin_contact_is_not_nan_when_no_skin_contact
        test_case_5 = {
            "user_id": "-1",
            "date_time": "2023-07-25 06:27:25",
            "datetime_server_received": "2023-07-25 06:27:35",
            "body_temperature": 26,
            "dashboard_mode": "RR",
            "hr": "nan",
            "rr": "nan",
            "rr_dc": "nan",
            "rr_td": "nan",
            "sensor_contact_status": "Poor",
            "signal_quality_status": "nan",
            "skin_temperature": 24
        }


        input_data = test_case_5
        DataProcessing.objects.create(**input_data)

        dataset = DataProcessing.objects.filter(user_id =user_id)
        response = handle_spot_trend_query(
            dataset, desired_attr, bool_remove_bad_data, bool_keep_bad_data_as_NaN, replace_NaN_with_value, add_sqa_to_trend,add_skin_status_to_trend
        )
        print(response["metrics"])
        assert response["metrics"]["sensor_onskin_status"] == [
            0
        ], "NaN skin contact is not set to zero"


class TestBatteryData(TestCase):

    '''test displaying of battery in patient list and spot api'''


    def test_case_1(self):
        '''
        test displaying of battery in patient list  when all sensors are online
        '''

        user_id = '0'

        device_data = {
            user_id: {
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:10:01",
                "sensor_status_chest": 1,
                "sensor_chest_last_connect_time": "2025-07-15 07:10:01",
                "sensor_status_finger": 1,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "last_connect_time": "2025-07-15 06:21:20",
                "sensor_status": 1,
            }
        }

        patient_list_response = {
            user_id: {
                "activity": 34.0,
                "RR": 25.0,
                "dateTime": "2025-07-15 07:43:01",
                "dateTime_latest_valid_chest": "2025-07-15 07:43:01",
                "dateTime_latest_valid_finger": "2025-07-15 03:58:29",
                "last_sync": "2025-07-15 07:43:11",
                "HR": 48.0,
                "battery": 95.0,
                "SpO2": 100.0,
                "userId": "2155",
                "bodyTemp": 35.5,
                "battery_chest": 95.0,
                "skinTemp": 33.5,
                "battery_finger": 57.0,
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:43:16",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": 1,
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": None,
                "skin_contact": "Bad",
                "skin_contact_chest": "Good",
                "skin_contact_finger": "Bad",
            }
        }

        display_battery(patient_list_response[user_id],'list' , device_data[user_id])

        assert patient_list_response[user_id]['battery'] == 95
        assert patient_list_response[user_id]['battery_finger'] == 57
        assert patient_list_response[user_id]['battery_chest'] == 95


    def test_case_2(self):

        '''
        test displaying of battery in patient list when all sensors are offline
        '''
        user_id = '0'

        device_data = {
            user_id: {
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:10:01",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:10:01",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "last_connect_time": "2025-07-15 06:21:20",
                "sensor_status": 0,
            }
        }

        patient_list_response = {
            user_id: {
                "activity": 34.0,
                "RR": 25.0,
                "dateTime": "2025-07-15 07:43:01",
                "dateTime_latest_valid_chest": "2025-07-15 07:43:01",
                "dateTime_latest_valid_finger": "2025-07-15 03:58:29",
                "last_sync": "2025-07-15 07:43:11",
                "HR": 48.0,
                "battery": 95.0,
                "SpO2": 100.0,
                "userId": "2155",
                "bodyTemp": 35.5,
                "battery_chest": 95.0,
                "skinTemp": 33.5,
                "battery_finger": 57.0,
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:43:16",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": None,
                "skin_contact": "Bad",
                "skin_contact_chest": "Good",
                "skin_contact_finger": "Bad",
            }
        }

        display_battery(patient_list_response[user_id],'list' , device_data[user_id])

        assert patient_list_response[user_id]['battery'] == -1
        assert patient_list_response[user_id]['battery_finger'] == -1
        assert patient_list_response[user_id]['battery_chest'] == -1


    def test_case_3(self):

        '''
        test displaying of battery in patient list when all generic sensors is  offline and finger and chest sensors are online
        '''
        user_id = '0'

        device_data = {
            user_id: {
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:10:01",
                "sensor_status_chest": 1,
                "sensor_chest_last_connect_time": "2025-07-15 07:10:01",
                "sensor_status_finger": 1,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "last_connect_time": "2025-07-15 06:21:20",
                "sensor_status": 0,
            }
        }

        patient_list_response = {
            user_id: {
                "activity": 34.0,
                "RR": 25.0,
                "dateTime": "2025-07-15 07:43:01",
                "dateTime_latest_valid_chest": "2025-07-15 07:43:01",
                "dateTime_latest_valid_finger": "2025-07-15 03:58:29",
                "last_sync": "2025-07-15 07:43:11",
                "HR": 48.0,
                "battery": 95.0,
                "SpO2": 100.0,
                "userId": "2155",
                "bodyTemp": 35.5,
                "battery_chest": 95.0,
                "skinTemp": 33.5,
                "battery_finger": 57.0,
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:43:16",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": None,
                "skin_contact": "Bad",
                "skin_contact_chest": "Good",
                "skin_contact_finger": "Bad",
            }
        }

        display_battery(patient_list_response[user_id],'list' , device_data[user_id])

        assert patient_list_response[user_id]['battery'] == -1
        assert patient_list_response[user_id]['battery_finger'] == 57
        assert patient_list_response[user_id]['battery_chest'] == 95


    def test_case_4(self):

        '''
        test displaying of battery in patient list when all chest sensors is  offline and finger and generic sensors are online
        '''
        user_id = '0'

        device_data = {
            user_id: {
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:10:01",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:10:01",
                "sensor_status_finger": 1,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "last_connect_time": "2025-07-15 06:21:20",
                "sensor_status": 1,
            }
        }

        patient_list_response = {
            user_id: {
                "activity": 34.0,
                "RR": 25.0,
                "dateTime": "2025-07-15 07:43:01",
                "dateTime_latest_valid_chest": "2025-07-15 07:43:01",
                "dateTime_latest_valid_finger": "2025-07-15 03:58:29",
                "last_sync": "2025-07-15 07:43:11",
                "HR": 48.0,
                "battery": 95.0,
                "SpO2": 100.0,
                "userId": "2155",
                "bodyTemp": 35.5,
                "battery_chest": 95.0,
                "skinTemp": 33.5,
                "battery_finger": 57.0,
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:43:16",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": None,
                "skin_contact": "Bad",
                "skin_contact_chest": "Good",
                "skin_contact_finger": "Bad",
            }
        }

        display_battery(patient_list_response[user_id],'list' , device_data[user_id])

        assert patient_list_response[user_id]['battery'] == 95
        assert patient_list_response[user_id]['battery_finger'] == 57
        assert patient_list_response[user_id]['battery_chest'] == -1


    def test_case_5(self):

        '''
        test displaying of battery in patient list when all finger sensors is  offline and chest and generic sensors are online
        '''
        user_id = '0'

        device_data = {
            user_id: {
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:10:01",
                "sensor_status_chest": 1,
                "sensor_chest_last_connect_time": "2025-07-15 07:10:01",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "last_connect_time": "2025-07-15 06:21:20",
                "sensor_status": 1,
            }
        }

        patient_list_response = {
            user_id: {
                "activity": 34.0,
                "RR": 25.0,
                "dateTime": "2025-07-15 07:43:01",
                "dateTime_latest_valid_chest": "2025-07-15 07:43:01",
                "dateTime_latest_valid_finger": "2025-07-15 03:58:29",
                "last_sync": "2025-07-15 07:43:11",
                "HR": 48.0,
                "battery": 95.0,
                "SpO2": 100.0,
                "userId": "2155",
                "bodyTemp": 35.5,
                "battery_chest": 95.0,
                "skinTemp": 33.5,
                "battery_finger": 57.0,
                "gateway_status": 1,
                "last_gateway_connect": "2025-07-15 07:43:16",
                "sensor_status_finger": 0,
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": 0,
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": None,
                "skin_contact": "Bad",
                "skin_contact_chest": "Good",
                "skin_contact_finger": "Bad",
            }
        }

        display_battery(patient_list_response[user_id],'list' , device_data[user_id])

        assert patient_list_response[user_id]['battery'] == 95
        assert patient_list_response[user_id]['battery_finger'] == -1
        assert patient_list_response[user_id]['battery_chest'] == 95



        '''
        test displaying of battery in spot when finger sensor  is offline, chest and generic sensors are online
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Offline",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Online",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": 'Online',
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == 95
        assert spot_response['latest']['battery_finger'] == -1
        assert spot_response['latest']['battery_chest'] == 95

    def test_casse_6(self):
        '''
        test displaying of battery in spot when all sensors are online
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Online",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Online",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": "Online",
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == 95
        assert spot_response['latest']['battery_finger'] == 57
        assert spot_response['latest']['battery_chest'] == 95


    def test_case_7(self):
        '''
        test displaying of battery in spot when all sensors are offline
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Offline",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Offline",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": -1,
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == -1
        assert spot_response['latest']['battery_finger'] == -1
        assert spot_response['latest']['battery_chest'] == -1


    def test_case_8(self):
        '''
        test displaying of battery in spot when generic sensor  is offline, finger and chest sensors are online
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Online",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Online",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": -1,
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == -1
        assert spot_response['latest']['battery_finger'] == 57
        assert spot_response['latest']['battery_chest'] == 95


    def test_case_9(self):
        '''
        test displaying of battery in spot when chest sensor  is offline, finger and generic sensors are online
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Online",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Offline",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": 'Online',
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == 95
        assert spot_response['latest']['battery_finger'] == 57
        assert spot_response['latest']['battery_chest'] == -1


    def test_case_10(self):
        '''
        test displaying of battery in spot when finger sensor  is offline, chest and generic sensors are online
        '''
        spot_response = {
            "history": {
                "HR": [
                    -1,
                ],
                "RR": [
                    25.0,
                ],
                "SpO2": [
                    -1,
                ],
                "body_temperature": [
                    35.1,
                ],
                "skin_temperature": [
                    33.5,
                    .1,
                ],
                "mode": [
                    "RR",
                ],
                "battery": [
                    95,
                ],
                "signal_quality_status": [
                    "Moderate",
                ],
                "RR_sd": [
                    0.0,
                ],
                "HR_sd": [
                    -1,
                ],
                "SpO2_sd": [
                    -1,
                ],
                "skin_contact": [
                    "Chest",
                ],
                "timestamp": [
                    "2025-07-15 07:43:01",
                ],
            },
            "latest": {
                "HR": 48.0,
                "RR": 25.0,
                "RR_TD": -1,
                "SpO2": 100.0,
                "body_temperature": 35.5,
                "skin_temperature": 33.5,
                "mode": -1,
                "battery": 95,
                "signal_quality_status": -1,
                "RR_sd": -1,
                "HR_sd": -1,
                "SpO2_sd": -1,
                "skin_contact": "Chest",
                "timestamp": -1,
                "last_connection_chest": "2025-07-15 07:43:01",
                "last_connection_finger": "2025-07-15 03:58:29",
                "skin_contact_chest": "Chest",
                "skin_contact_finger": "Bad",
                "battery_chest": 95,
                "battery_finger": 57,
                "gateway_status": "Online",
                "last_gateway_connect": "2025-07-15 08:15:55",
                "sensor_status_finger": "Offline",
                "sensor_finger_last_connect_time": "2025-07-15 06:21:20",
                "sensor_status_chest": "Online",
                "sensor_chest_last_connect_time": "2025-07-15 07:43:16",
                "last_connect_time": -1,
                "sensor_status": 'Online',
            },
        }

        display_battery(spot_response, 'spot',None)

        assert spot_response['latest']['battery'] == 95
        assert spot_response['latest']['battery_finger'] == -1
        assert spot_response['latest']['battery_chest'] == 95





class TestOtherSpotData(TestCase):
    '''test functionality of get_other_spot_data'''

    def setUp(self):

        user_id = "-1010"

        sensor_data = [
            {'user_id':user_id,'accepted_frame_spo2_ratio': 0, 'accepted_frame_spo2': 0, 'date_time': '2025-04-09 09:50:54', 'display_label': 0,  'datetime_sensor': '2025-04-09 09:50:54', 'val_sd_signal_w_sqa': 0, 'sensor_onskin_status': 0, 'debug_data_length_too_short': {'threshold': {'RR': 1000, 'HR': 654, 'finger_on_skin_algo': 754, 'SpO2': 505}, 'is_shorter_than_threshold': 0},  'dashboard_mode': 'HR', 'battery': 54},
            {'user_id':user_id,'skin_temperature': 25.2, 'date_time': '2025-04-09 09:22:37', 'datetime_sensor': '2025-04-09 09:22:37', 'val_sd_signal_w_sqa': 0,  'sensor_onskin_status': -1, 'debug_data_length_too_short': {'threshold': {'RR': 1000, 'HR': 654, 'finger_on_skin_algo': 754, 'SpO2':505}, 'is_shorter_than_threshold': -1, 'data_length': 281}, 'dashboard_mode': 'RR', 'battery': 94},
            {'user_id':user_id,'accepted_frame_spo2_ratio': 0, 'accepted_frame_spo2': 0, 'date_time': '2025-04-09 09:59:48', 'display_label': 0,  'datetime_sensor': '2025-04-09 09:59:48', 'val_sd_signal_w_sqa': 0, 'sensor_onskin_status': 0, 'debug_data_length_too_short': {'threshold': {'RR': 1000, 'HR': 654, 'finger_on_skin_algo': 754, 'SpO2': 505}, 'is_shorter_than_threshold': 0}, 'dashboard_mode': 'HR', 'battery': 52}
        ]

        # Inject dummy data to DB
        for item in sensor_data:
            DataProcessing.objects.create(**item)


    def test_hourly(self):


        user_id = "-1010"






        list_resolution = "hourly"
        stop_date = "2025-04-09T11:37:53"
        response = {user_id:{}}
        dateTime = datetime.strptime(stop_date, '%Y-%m-%dT%H:%M:%S')

        get_other_spot_data(response, user_id, list_resolution, dateTime, DataProcessing.objects.all())
        
        assert response[user_id]['battery'] == 52
        assert response[user_id]['battery_chest'] == 94
        assert response[user_id]['battery_finger'] == 54
        assert response[user_id]['skin_contact'] == 'Bad'
        assert response[user_id]['skin_contact_chest'] == -1
        assert response[user_id]['skin_contact_finger'] == 'Bad'


    def test_daily(self):

        user_id = "-1010"

        list_resolution = "daily"
        stop_date = "2025-04-09T11:37:53"
        response = {user_id:{}}
        dateTime = datetime.strptime(stop_date, '%Y-%m-%dT%H:%M:%S')

        get_other_spot_data(response, user_id, list_resolution, dateTime, DataProcessing.objects.all())

        assert response[user_id]['battery'] == 52
        assert response[user_id]['battery_chest'] == 94
        assert response[user_id]['battery_finger'] == 54
        assert response[user_id]['skin_contact'] == 'Bad'
        assert response[user_id]['skin_contact_chest'] == -1
        assert response[user_id]['skin_contact_finger'] == 'Bad'

