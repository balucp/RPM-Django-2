import math
import json
import os
import datetime
import requests
import urllib.parse


from django.test import TestCase

from dataprocessing import settings as original_settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from dataprocessing import lib_settings as settings
from data_app.models import *

    

class TestUploadBPDeviceData(TestCase):
    """test API  to submit-health-input"""

    def setUp(self):

        self.url = "/api/v1/data/other/bp-device"
        self.token = settings.VALID_REFERER[0]



    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()

    def test_upload_valid_data(self):

        data = {
            "userId": 0,
            "bloodPressureSystolic": 120,
            "bloodPressureDiastolic": 80,
            "deviceId": "b8b77d137f35"
        }
        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_REFERER=f"{self.token}",

        )

        self.assertEqual(response.status_code, 201, "request is not successful")

    def test_upload_missing_data(self):
        # bp_dia is  missing
        data = {
            "userId": 0,
            "bloodPressureDiastolic": 80,
            "deviceId": "b8b77d137f35"
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_REFERER=f"{self.token}",

        )

        self.assertEqual(response.status_code, 400, "request is not successful")


class TestQueryBPDeviceData(TestCase):
    """test API  to fetch bp device readings"""


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

        self.submission_url = "/api/v1/data/other/bp-device"
        self.spot_url = "/api/v1/query/spot/bp-device"
        self.token = self._get_auth_token()


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()

    def test_query_bp_device_data(self):
        data = {
            "userId": 0,
            "bloodPressureSystolic": 120,
            "bloodPressureDiastolic": 80,
            "deviceId": "b8b77d137f35"
        }

        response = self.client.post(
            self.submission_url,
            data=data,
            content_type="application/json",
            HTTP_REFERER=settings.VALID_REFERER[0]

        )

        self.assertEqual(response.status_code, 201, "request is not successful")


        params = {
            "user_id": data['userId'],
            "date_time": "2002-07-08T13:01:46",
        }
        url = f"{self.spot_url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        response = response.json()["response"]
        expected_response = {'bp_sys': [120.0], 'bp_dia': [80.0]}

        assert response['bp_sys'] == expected_response['bp_sys'] , "Mismatch in bp_sys"
        assert response['bp_dia'] == expected_response['bp_dia'], "Mismatch in bp_dia"




class TestUploadEMReData(TestCase):
    """test API  to submit emr data"""

    def setUp(self):

        self.url = "/api/v1/data/emr"
        self.token = settings.VALID_REFERER[0]


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        OtherDeviceReading.objects.all().delete()


    def test_upload_valid_data(self):

        data =     {
                "user_id": "0",
                "datetime_data_collected": "2025-09-09T03:00:12",
                "data": { 
                    "bp_dia": 85,
                    "bp_sys": 150,
                    "weight": 59,
                    "blood_sugar": 5.7,
                    "rr": 19,
                    "hr": 69,
                    "spo2": 95,
                    "body_temperature": 36.7
                }
            }
        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_REFERER=f"{self.token}",

        )

        self.assertEqual(response.status_code, 201, "request is not successful")



