import json
import os
import datetime
import requests
import pytz
import urllib.parse
from django.test import TestCase

from dataprocessing import lib_settings as settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app.models import *


class ThirdPartyIntegrationTestCase(TestCase):

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

        self.url = "/api/v1/vitals/readings"
        self.token = self._get_auth_token()

        user_id = "0"


        data_available = [
        {
            "user_id": 0,
            "timestamp": '2025-02-15 03:05:25',
            "patient_id": "abcd",
            "rr": 1,
            "hr": 2,
            "spo2": 3,
            "rr_td": 4,
            "rr_dc": 5,
            "skin_temperature": 6,
            "activity": 7,
            "chest_signal_quality": "Good",
            "finger_signal_quality": "Good",
            "finger_skin_contact": 0,
            "chest_skin_contact": 0,
            # "risk_probability": -1,
            "sensor_name": "AAA",
            "gateway_name": "bbbb",
            "sensor_battery": 33
        }
        ]

        for data in data_available:
            data['timestamp'] = pytz.UTC.localize(datetime.datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S'))
            Staging.objects.create(**data)

    def tearDown(self):
        Staging.objects.all().delete()

    def test_third_party_integration_api(self):
        user_id = "0"

        params = {
            "userid": user_id,
            "start": "2025-02-15T01:05:25",
            "end": "2025-02-15T04:05:25",
            "page": 1,
            "limit": 10,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "request is not successful")


    def test_third_party_integration_api_with_missing_params(self):
        user_id = "0"
        params = {
            "userid": user_id,
            "start": "2002-06-08T13:01:46",
            "page": 1,
            "start": 10,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400, "Incorrect response")

