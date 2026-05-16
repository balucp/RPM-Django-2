import math
import json
import os
import datetime
import pandas as pd
import numpy as np
import requests
import urllib.parse

from django.test import TestCase

from dataprocessing import settings as original_settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from dataprocessing import lib_settings as settings
from data_app.models import *
from data_app.staging_hourly import staging_hourly


class TestProcessInProgressCreate(TestCase):

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

        self.url = "/api/v1/upload"
        self.submit_health_input_url = "/api/v1/submit-health-input"
        self.token = self._get_auth_token()
        self.valid_token = settings.VALID_REFERER[0]

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        ProcessInProgress.objects.all().delete()

    def test_upload_sensor_data(self):

        data = {
            "userID": "100",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6423f9b6004900008177df6a30f8a00"],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        assert response.json()["userID"] == 100
        count = ProcessInProgress.objects.filter(user_id=100).count()
        assert count == 1

    def test_submit_health_input(self):

        user_id = '200'
        data = {
            "user_id": user_id,
            "datetime_data_collected": "2000-08-09T04:41:53",
            "data": {
                "bp_dia": 80,
                "bp_sys": 120,
                "weight": 85,
                "blood_sugar": 5.5,
                "rr": 30,
                "hr": 115,
                "spo2": 98,
                "body_temperature": 35.6,
            },
        }

        response = self.client.post(
            self.submit_health_input_url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        count = ProcessInProgress.objects.filter(user_id=200).count()
        assert count == 1



class TestGetProcessInProgressUsers(TestCase):
    """test function to process data uploaded by the gateway"""

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

        self.url = "/api/v1/processing"
        self.token = self._get_auth_token()

        data = {
            "user_id": "0",
            "datetime": "2025-05-21 11:30:00+00",
            "timestamp_server_received": "2025-05-21 11:30:00+00",
            "timestamp_daily": "2025-05-21 00:00:00+00",
            "utc_offset": "+00:00",
            "timestamp_hourly": "2025-05-21 11:00:00+00",
            "data_source": "sensor",
        }
        ProcessInProgress.objects.create(**data)


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        ProcessInProgress.objects.all().delete()

    def test_get_process_in_progress_users_hourly(self):

        user_id = "0,-1,-2"

        params = {
            "user_ids": user_id,
            "query_time_start": "2025-05-21T10:00:00",
            "query_time_end": "2025-05-21T12:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        response = response.json()
        self.assertEqual(response['response']['user_in_progress'], [0], "request is not successful")


    def test_get_no_process_in_progress_users_hourly(self):

        user_id = "-1,-2"
        params = {
            "user_ids": user_id,
            "query_time_start": "2025-05-21T10:00:00",
            "query_time_end": "2025-05-21T12:00:00",
            "resolution": "hourly",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        
        self.assertEqual(response.status_code, 200, "request is not successful")
        response = response.json()
        self.assertEqual(response['response']['user_in_progress'], [], "request is not successful")

    def test_get_process_in_progress_users_daily(self):

        user_id = "0,-1,-2"
        params = {
            "user_ids": user_id,
            "query_time_start": "2025-05-21T00:00:00",
            "query_time_end": "2025-05-21T10:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        response = response.json()
        self.assertEqual(response['response']['user_in_progress'], [0], "request is not successful")


    def test_get_no_process_in_progress_users_daily(self):

        user_id = "-1,-2"
        params = {
            "user_ids": user_id,
            "query_time_start": "2025-05-21T00:00:00",
            "query_time_end": "2025-05-21T10:00:00",
            "resolution": "daily",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 200, "request is not successful")
        response = response.json()
        self.assertEqual(response['response']['user_in_progress'], [], "request is not successful")



class TestProcessInProgressDelete(TestCase):
    """test records are deleting from process-in-progress table after processing data """


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        ProcessInProgress.objects.all().delete()


    def test_get_process_in_progress_users_hourly(self):
        self.skipTest("Relies on real user ID. See issue #582")
        user_id = '1919'
        data_source = 'sensor'

        current_datetime = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        )

        processdata = {
            "user_id": user_id,
            "datetime": current_datetime,
            "timestamp_server_received": current_datetime,
            "timestamp_daily": current_datetime,
            "utc_offset": "+00:00",
            "timestamp_hourly": current_datetime,
            "data_source": data_source,
        }
        ProcessInProgress.objects.create(**processdata)

        cache_data = {
            "datetime_local": current_datetime,
            "user_id": user_id,
            "datetime_updated": current_datetime,
            "listtime": current_datetime,
            "utc_offset": "00:00",
            "recordReceivedByGateway_to_duration_hrs_chest": float(
                "0.021233333333333333"
            ),
            "recordReceivedByGateway_to_duration_hrs": float("0.021233333333333333"),
        }

        MetricHourlyCache.objects.create(**cache_data)
        StagingHourlyCache.objects.create(**cache_data)

        staging_hourly()

        in_progress_data = ProcessInProgress.objects.filter(user_id = user_id, data_source = data_source)
        self.assertEqual(in_progress_data.count(), 0, "deletion failed")


