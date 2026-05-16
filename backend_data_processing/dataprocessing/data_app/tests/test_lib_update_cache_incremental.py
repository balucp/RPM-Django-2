import math
import json
import os
import datetime
import pandas as pd
import numpy as np
import requests
import urllib.parse
import pandas as pd
import csv
from io import StringIO

from django.test import TestCase

from dataprocessing import settings as original_settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from dataprocessing import lib_settings as settings
from data_app.models import *
from data_app.lib_update_cache_incremental import(
    hourly_start_stop_timeframe,
    handle_update_hourly_cache,
    daily_start_stop_timeframe,
    handle_update_daily_cache
)
from data_app.tests.data.data_lib_update_cache_incremental import *

class TestUpdateCacheHourly(TestCase):
    """test hourly cache incremental"""

    def setUp(self):

        self.sensor_data = [
            {
                "user_id": "-2",
                "date_time": "2000-01-01 00:00:01",
                "rr": 9.0,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 10,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-01 00:00:00",
                "hr": 76.0,
                "spo2": 93.0,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,

            },
            {
                "user_id": "-2",
                "date_time": "2000-01-02 01:00:01",
                "body_temperature": 40.2,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 20,
                "rr": 9.0,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-02 01:00:00",
                "hr": 23.0,
                "spo2": 100.0,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-03 02:00:01",
                "rr": 10.0,
                "body_temperature": 33.2,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 30,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-03 02:00:00",
                "spo2": 98.0,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
                "hr": 23.0,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-04 03:00:01",
                "rr": 8.0,
                "body_temperature": 38.1,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 40,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-04 03:00:00",
                "hr": 88.0,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
                "spo2": 98.0,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-05 04:00:01",
                "rr": 23.0,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 50,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-05 04:00:00",
                "hr": 142.0,
                "spo2": 85.0,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-06 05:00:01",
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 60,
                "rr": 9,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-06 05:00:00",
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-07 00:00:00",
                "rr": 9.0,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 10,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-07 00:00:01",
                "rr": 9.0,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 10,
            },
        ]

        self.manual_data = [
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:45",
                "datetime_received": "2001-07-08 13:01:46",
                "weight": 67,
                "blood_sugar": 5.6,
            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:44",
                "datetime_received": "2001-07-08 13:01:45",
                "bp_sys": 100,
            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:43",
                "datetime_received": "2001-07-08 13:01:44",
                "bp_dia": 60,
            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:42",
                "datetime_received": "2001-07-08 13:01:43",
                "bp_sys": 90,
                "hr": 78,
            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:41",
                "datetime_received": "2001-07-08 13:01:42",
                "spo2": 89,

            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:40",
                "datetime_received": "2001-07-08 13:01:41",
                "rr": 32,
                "spo2": 91,
            },
            {
                "user_id": -3,
                "datetime": "2001-07-08 13:01:39",
                "datetime_received": "2001-07-08 13:01:40",
                "rr": 31,
                "body_temp": 36.3,
            },
        ]

        self.bp_data = [

            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:44",
                "bp_sys": "100",
                "source": "other"
            },
            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:43",
                "bp_dia": "60",
                "source": "other"
            },
            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:42",
                "bp_sys": "90",
                "source": "other"
            },
        ]

        self.emr_data = [

            {
                "datetime": "2002-07-08 13:01:44",
                'bp_sys': 131,
                'bp_dia': 60,
                'rr': 17,
                'hr': 63,
                'spo2': 97,
                'body_temperature': 36.6,
                'weight': 81,
                'blood_sugar': 105,
                "user_id": -5,
            },
            {
                "datetime": "2002-07-08 13:01:43",
                'bp_sys': 113,
                'bp_dia': 64,
                'rr': 16,
                'hr': 99,
                'spo2': 96,
                'body_temperature': 36.6,
                'weight': 92,
                'blood_sugar': 103,
                "user_id": -5,
            },
            {
                "datetime": "2002-07-08 13:01:42",
                'bp_sys': 134,
                'bp_dia': 87,
                'rr': 12,
                'hr': 67,
                'spo2': 96,
                'body_temperature': 36.8,
                'weight': 58,
                'blood_sugar': 126,
                "user_id": -5,
            },
        ]


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()


    def test_update_cache_using_sensor_data_only(self):

        for data in self.sensor_data:

            dataprocessing_obj = DataProcessing.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = hourly_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)
            response = handle_update_hourly_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


        expected_data = [
            {
                "user_id": -2,
                "datetime_updated": "2000-01-01 00:00:00",
                "rr": 9,
                "hr": 76,
                "spo2": 93,
                "activity": 10,
            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-02 01:00:00",
                "hr": 23,
                "spo2": 100,
                "activity": 20,
                "rr": 9,
            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-03 02:00:00",
                "rr": 10,
                "spo2": 98,
                "activity": 30,
                "hr": 23,

            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-04 03:00:00",
                "rr": 8,
                "hr": 88,
                "activity": 40,
                "spo2": 98,

            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-05 04:00:00",
                "rr": 23,
                "hr": 142,
                "spo2": 85,
                "activity": 50,
            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-06 05:00:00",
                "activity": 60,
                "rr": 9,

            },
            {
                "user_id": -2,
                "datetime_updated": "2000-01-07 00:00:00",
                "skin_temperature": 33.3,
                "activity": 10,
                "rr": 9,
                "activity_SD": 0,
            }
        ]

        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricHourlyCache.objects.filter(user_id=-2 , datetime_updated__range = ('2000-01-01 00:00:00','2000-01-07 05:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['rr'].astype(float) == querya_df['rr']).all(), "Mismatch in RR"
        assert (expected_data_df['hr'].astype(str) == querya_df['hr'].astype(str)).all(), "Mismatch in HR"
        assert (expected_data_df['spo2'].astype(str) == querya_df['spo2'].astype(str)).all(), "Mismatch in SpO2"
        assert (expected_data_df['activity'].astype(float) == querya_df['activity'].astype(float)).all(), "Mismatch in activity"
        assert (expected_data_df['activity_SD'].astype(str) == querya_df['activity_SD'].astype(str)).all(), "Mismatch in activity_SD"
        

    def test_update_cache_using_health_input_data_only(self):

        for data in self.manual_data:

            mhi_obj = HealthData.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = hourly_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)
            response = handle_update_hourly_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                'user_id': -3,
                'datetime_updated': '2001-07-08 13:00:00',
                'rr': 32,
                'hr': 78,
                'spo2': 90,
                'body_temperature': 36.3,
                'bp_dia': 60,
                'bp_sys': 95,
                'weight': 67,
                'blood_sugar': 5.6
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricHourlyCache.objects.filter(user_id=-3 , datetime_updated__range = ('2001-07-08 13:00:00','2001-07-08 13:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['rr'] == querya_df['rr']).all(), "Mismatch in RR"
        assert (expected_data_df['hr'] == querya_df['hr']).all(), "Mismatch in HR"
        assert (expected_data_df['spo2'] == querya_df['spo2']).all(), "Mismatch in SpO2"
        assert (expected_data_df['body_temperature'] == querya_df['body_temperature']).all(), "Mismatch in body_temperature"
        assert (expected_data_df['bp_dia'] == querya_df['bp_dia']).all(), "Mismatch in BP_Dia"
        assert (expected_data_df['bp_sys'] == querya_df['bp_sys']).all(), "Mismatch in BP_Sys"
        assert (expected_data_df['weight'] == querya_df['weight']).all(), "Mismatch in weight"
        assert (expected_data_df['blood_sugar'] == querya_df['blood_sugar']).all(), "Mismatch in blood_sugar"


    def test_update_cache_using_db_device_input(self):

        for data in self.bp_data:

            bp_obj = OtherDeviceReading.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = hourly_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)
            response = handle_update_hourly_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                'user_id': -4,
                'datetime_updated': '2001-07-08 13:00:00',
                'bp_dia': 60,
                'bp_sys': 95,
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricHourlyCache.objects.filter(user_id=-4 , datetime_updated__range = ('2001-07-08 13:00:00','2001-07-08 13:00:00')).values()
        querya_df = pd.DataFrame(queryset)


        assert (expected_data_df['bp_dia'] == querya_df['bp_dia']).all(), "Mismatch in BP_Dia"
        assert (expected_data_df['bp_sys'] == querya_df['bp_sys']).all(), "Mismatch in BP_Sys"


    def test_update_cache_using_emr_input(self):

        for data in self.emr_data:

            emr_obj = OtherDeviceReading.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = hourly_start_stop_timeframe(emr_obj.user_id, emr_obj.datetime)
            response = handle_update_hourly_cache(
                user_id=emr_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )


        expected_data = [
            {
                'user_id': '-5',
                'datetime': '2002-07-08 13:00:00',
                'bp_dia': '64.0',
                'bp_sys': '131.0',
                'rr': '16.0',
                'hr': '67.0',
                'spo2': '96.0',
                'body_temperature': '36.6',
                'weight': '81.0',
                'blood_sugar': '105.0'
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricHourlyCache.objects.filter(user_id=-5 , datetime_updated__range = ('2002-07-08 13:00:00','2002-07-08 13:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['bp_dia'].astype(str) == querya_df['bp_dia'].astype(str)).all(), "Mismatch in bp_dia"
        assert (expected_data_df['bp_sys'].astype(str) == querya_df['bp_sys'].astype(str)).all(), "Mismatch in bp_sys"
        assert (expected_data_df['hr'].astype(str) == querya_df['hr'].astype(str)).all(), "Mismatch in hr"
        assert (expected_data_df['rr'].astype(str) == querya_df['rr'].astype(str)).all(), "Mismatch in rr"
        assert (expected_data_df['spo2'].astype(str) == querya_df['spo2'].astype(str)).all(), "Mismatch in spo2"
        assert (expected_data_df['body_temperature'].astype(str) == querya_df['body_temperature'].astype(str)).all(), "Mismatch in body_temperature"
        assert (expected_data_df['weight'].astype(str) == querya_df['weight'].astype(str)).all(), "Mismatch in weight"
        assert (expected_data_df['blood_sugar'].astype(str) == querya_df['blood_sugar'].astype(str)).all(), "Mismatch in blood_sugar"


class TestUpdateCacheDaily(TestCase):
    """test Daily cache incremental"""

    def setUp(self):

        self.sensor_data = [
            {
                "user_id": "-2",
                "date_time": "2000-01-01 00:00:01",
                "rr": 9,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":10,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-01 00:00:00",
                "hr": 76,
                "spo2": 93,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-02 01:00:01",
                "body_temperature": 40.2,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":20,
                "rr":20,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-02 01:00:00",
                "hr": 23,
                "spo2": 100,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-03 02:00:01",
                "rr": 10,
                "body_temperature": 33.2,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":30,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-03 02:00:00",
                "spo2": 98,
                "hr": 78,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-04 03:00:01",
                "rr": 8,
                "body_temperature": 38.1,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":40,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-04 03:00:00",
                "hr": 88,
                "spo2": 98,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-05 04:00:01",
                "rr": 23,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":50,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-05 04:00:00",
                "hr": 142,
                "spo2": 85,
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-06 05:00:01",
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity":60,
                "rr": 9,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-06 05:00:00",
                "sensor_onskin_status": 1,
                "dashboard_mode": "HR",
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-07 00:00:00",
                "rr": 9,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 10,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
            {
                "user_id": "-2",
                "date_time": "2000-01-07 00:00:01",
                "rr": 9,
                "body_temperature": 35.3,
                "signal_quality_status": "Good",
                "sensor_contact_status": "Good",
                "sensor_onskin_status": 1,
                "dashboard_mode": "RR",
                "skin_temperature": 33.3,
                "activity": 10,
                "accepted_frame_spo2": 9,
                "val_sd_signal_w_sqa": 0.5,
            },
        ]

        self.manual_data = [
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:45",
                "datetime_received": "2001-07-08 13:01:46",
                "weight": 67,
                "blood_sugar": 5.6,
            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:44",
                "datetime_received": "2001-07-08 13:01:45",
                "bp_sys": 100,
            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:43",
                "datetime_received": "2001-07-08 13:01:44",
                "bp_dia": 60,
            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:42",
                "datetime_received": "2001-07-08 13:01:43",
                "bp_sys": 90,
                "hr": 78,
            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:41",
                "datetime_received": "2001-07-08 13:01:42",
                "spo2": 89,

            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:40",
                "datetime_received": "2001-07-08 13:01:41",
                "rr": "32",
                "spo2": 91,
            },
            {
                "user_id": "-3",
                "datetime": "2001-07-08 13:01:39",
                "datetime_received": "2001-07-08 13:01:40",
                "rr": 31,
                "body_temp": 36.3,
            },
        ]

        self.bp_data = [

            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:44",
                "bp_sys": "100",
                "source": "other"
            },
            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:43",
                "bp_dia": "60",
                "source": "other"
            },
            {
                "user_id": -4,
                "datetime": "2001-07-08 13:01:42",
                "bp_sys": "90",
                "source": "other"
            },
        ]

        self.emr_data = [

            {
                "datetime": "2002-07-08 13:01:44",
                'bp_sys': 131,
                'bp_dia': 60,
                'rr': 17,
                'hr': 63,
                'spo2': 97,
                'body_temperature': 36.6,
                'weight': 81,
                'blood_sugar': 105,
                "user_id": -5,
                "source": "emr"

            },
            {
                "datetime": "2002-07-08 13:01:43",
                'bp_sys': 113,
                'bp_dia': 64,
                'rr': 16,
                'hr': 99,
                'spo2': 96,
                'body_temperature': 36.6,
                'weight': 92,
                'blood_sugar': 103,
                "user_id": -5,
                "source": "emr"

            },
            {
                "datetime": "2002-07-08 13:01:42",
                'bp_sys': 134,
                'bp_dia': 87,
                'rr': 12,
                'hr': 67,
                'spo2': 96,
                'body_temperature': 36.8,
                'weight': 58,
                'blood_sugar': 126,
                "user_id": -5,
                "source": "emr"

            },
        ]

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()

    def test_update_cache_using_health_input_data_only(self):

        for data in self.manual_data:

            mhi_obj = HealthData.objects.create(**data)

            #trigger daily cache
            start_date, stop_date = daily_start_stop_timeframe(mhi_obj.user_id, mhi_obj.datetime)
            response = handle_update_daily_cache(
                user_id=mhi_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                'user_id': -3,
                'datetime_updated': '2001-07-08 00:00:00',
                'rr': 32,
                'hr': 78,
                'spo2': 90,
                'body_temperature': 36.3,
                'bp_dia': 60,
                'bp_sys': 95,
                'weight': 67,
                'blood_sugar': 5.6
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricDailyCache.objects.filter(user_id=-3 , datetime_updated = '2001-07-08 00:00:00').values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['rr'] == querya_df['rr']).all(), "Mismatch in RR"
        assert (expected_data_df['hr'] == querya_df['hr']).all(), "Mismatch in HR"
        assert (expected_data_df['spo2'] == querya_df['spo2']).all(), "Mismatch in SpO2"
        assert (expected_data_df['body_temperature'] == querya_df['body_temperature']).all(), "Mismatch in body_temperature"
        assert (expected_data_df['bp_dia'] == querya_df['bp_dia']).all(), "Mismatch in BP_Dia"
        assert (expected_data_df['bp_sys'] == querya_df['bp_sys']).all(), "Mismatch in BP_Sys"
        assert (expected_data_df['weight'] == querya_df['weight']).all(), "Mismatch in weight"
        assert (expected_data_df['blood_sugar'] == querya_df['blood_sugar']).all(), "Mismatch in blood_sugar"


    def test_update_cache_using_sensor_data_only(self):

        for data in self.sensor_data:

            dataprocessing_obj = DataProcessing.objects.create(**data)

            #trigger daily cache
            start_date, stop_date = daily_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)
            response = handle_update_daily_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-01 00:00:00",
                "rr": 9,
                "hr": 76,
                "spo2": 93,
                "activity":10,
                "news":3,
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-02 00:00:00",
                "hr": 23,
                "rr": 20,
                "spo2": 100,
                "activity":20,
                "news":3,
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-03 00:00:00",
                "rr": 10,
                "hr": 78,
                "spo2": 98,
                "activity":30,
                "news":1,
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-04 00:00:00",
                "rr": 8,
                "hr": 88,
                "activity":40,
                "spo2": 98,
                "news":3,
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-05 00:00:00",
                "rr": 23,
                "hr": 142,
                "spo2": 85,
                "activity":50,
                "news":8
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-06 00:00:00",
                "activity":60,
                "news":0,
                "rr": 9,
            },
            {
                "user_id": "-2",
                "datetime_updated": "2000-01-07 00:00:00",
                "skin_temperature": 33.3,
                "activity": 10,
                "rr": 9,
                "activity_SD": 0,
                "news": 1,
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricDailyCache.objects.filter(user_id=-2 , datetime_updated__range = ('2000-01-01 00:00:00','2000-01-07 00:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['rr'].astype(float) == querya_df['rr']).all(), "Mismatch in RR"
        assert (expected_data_df['hr'].astype(str) == querya_df['hr'].astype(str)).all(), "Mismatch in HR"
        assert (expected_data_df['spo2'].astype(str) == querya_df['spo2'].astype(str)).all(), "Mismatch in SpO2"
        assert (expected_data_df['activity'].astype(float) == querya_df['activity'].astype(float)).all(), "Mismatch in activity"
        assert (expected_data_df['activity_SD'].astype(str) == querya_df['activity_SD'].astype(str)).all(), "Mismatch in activity_SD"
        

    def test_update_cache_using_db_device_input(self):

        for data in self.bp_data:

            bp_obj = OtherDeviceReading.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(bp_obj.user_id, bp_obj.datetime)
            response = handle_update_daily_cache(
                user_id=bp_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                'user_id': -4,
                'datetime_updated': '2001-07-08 00:00:00',
                'bp_dia': 60,
                'bp_sys': 95,
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricDailyCache.objects.filter(user_id=-4 , datetime_updated__range = ('2001-07-08 00:00:00','2001-07-08 00:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['bp_dia'] == querya_df['bp_dia']).all(), "Mismatch in BP_Dia"
        assert (expected_data_df['bp_sys'] == querya_df['bp_sys']).all(), "Mismatch in BP_Sys"


    def test_update_cache_using_emr_input(self):

        for data in self.emr_data:

            emr_obj = OtherDeviceReading.objects.create(**data)

            #trigger hourly cache
            start_date, stop_date = daily_start_stop_timeframe(emr_obj.user_id, emr_obj.datetime)
            response = handle_update_daily_cache(
                user_id=emr_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        expected_data = [
            {
                'user_id': '-5',
                'datetime': '2002-07-08 00:00:00',
                'bp_dia': '64.0',
                'bp_sys': '131.0',
                'rr': '16.0',
                'hr': '67.0',
                'spo2': '96.0',
                'body_temperature': '36.6',
                'weight': '81.0',
                'blood_sugar': '105.0'
            }
        ]
        expected_data_df = pd.DataFrame(expected_data)

        queryset = MetricDailyCache.objects.filter(user_id=-5 , datetime_updated__range = ('2002-07-08 00:00:00','2002-07-08 00:00:00')).values()
        querya_df = pd.DataFrame(queryset)

        assert (expected_data_df['bp_dia'].astype(str) == querya_df['bp_dia'].astype(str)).all(), "Mismatch in bp_dia"
        assert (expected_data_df['bp_sys'].astype(str) == querya_df['bp_sys'].astype(str)).all(), "Mismatch in bp_sys"
        assert (expected_data_df['hr'].astype(str) == querya_df['hr'].astype(str)).all(), "Mismatch in hr"
        assert (expected_data_df['rr'].astype(str) == querya_df['rr'].astype(str)).all(), "Mismatch in rr"
        assert (expected_data_df['spo2'].astype(str) == querya_df['spo2'].astype(str)).all(), "Mismatch in spo2"
        assert (expected_data_df['body_temperature'].astype(str) == querya_df['body_temperature'].astype(str)).all(), "Mismatch in body_temperature"
        assert (expected_data_df['weight'].astype(str) == querya_df['weight'].astype(str)).all(), "Mismatch in weight"
        assert (expected_data_df['blood_sugar'].astype(str) == querya_df['blood_sugar'].astype(str)).all(), "Mismatch in blood_sugar"


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

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()


    def test_valid_chest_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """

        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_5_input))


        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]


        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

            #trigger daily cache
            start_date, stop_date = daily_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_daily_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        # read expected output
        expected_data = pd.read_csv(StringIO(test_case_5_output))
        expected_data = expected_data.sort_values("date_time")

        query_params = {
            "start_datetime": "2023-02-17T00:00:00",
            "stop_datetime": "2023-02-24T00:00:00",
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
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"]
        ).all(), "mismatched RR"
        assert (
            response_data[user_id]["metrics"]["listdate"] == expected_data["date_time"]
        ).all(), "mismatched date_time"


    def test_valid_finger_data(self):
        """
        Test daily trends for this Pull Request: https://github.com/Respiree/rpm_data_processing_backend/pull/236

        Expected
        - remove BAD skin contact
        - remove POOR signal quality
        """

        # read raw samples
        test_data = pd.read_csv(StringIO(test_case_6_input))

        test_data = test_data.sort_values("date_time")
        test_data["user_id"] = test_data["user_id"].astype(str)
        # assume all records use same user id
        user_id = test_data["user_id"].iloc[0]

        # Iterate over rows and remove columns with NaN values & insert to db
        for index, row in test_data.iterrows():
            cleaned_row = row.dropna().to_dict()
            dataprocessing_obj = DataProcessing.objects.create(**cleaned_row)

            #trigger daily cache
            start_date, stop_date = daily_start_stop_timeframe(dataprocessing_obj.user_id, dataprocessing_obj.date_time)

            handle_update_daily_cache(
                user_id=dataprocessing_obj.user_id,
                start_datetime=start_date,
                stop_datetime=stop_date,
            )

        # read expected output
        expected_data = pd.read_csv(StringIO(test_case_6_output))
        expected_data = expected_data.sort_values("dateTime")

        query_params = {
            "start_datetime": "2000-01-01T00:00:00",
            "stop_datetime": "2000-01-07T06:59:59",
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

        user_id = str(user_id)

        assert (
            response_data[user_id]["metrics"]["listdate"] == expected_data["dateTime"]
        ).all(), "date and time mismatch."

        assert ( response_data[user_id]["metrics"]["HR"] == expected_data["HR"].astype(float)).all(), "HR mismatches"

        assert (
            response_data[user_id]["metrics"]["RR"] == expected_data["RR"].astype(float)
        ).all(), "RR mismatches"

        assert (
            response_data[user_id]["metrics"]["SpO2"] == expected_data["SpO2"].astype(float)
        ).all(), "SpO2 mismatches"

        assert (
            response_data[user_id]["metrics"]["EWS"] == expected_data["EWS"]
        ).all(), "EWS mismatches"

