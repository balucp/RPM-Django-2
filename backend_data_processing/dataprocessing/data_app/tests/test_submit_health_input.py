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


class TestHealthInputSubmission(TestCase):
    """test API  to submit-health-input"""

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

        self.url = "/api/v1/submit-health-input"
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

    def test_health_input_valid_with_authentication(self):

        data = {
            "user_id": "0",
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
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200, "request is not successful")

    def test_health_input_valid_partial_update(self):

        data = {
            "user_id": "0",
            "datetime_data_collected": "2000-08-09T04:55:00",
            "data": {
                "bp_sys": 135,
                "bp_dia": 115,
                "weight": None,
                "blood_sugar": 6,
                "rr": None,
                "hr": None,
                "spo2": None,
                "body_temperature": 37,
            },

        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")

    def test_health_input_valid_without_authentication(self):

        data = {
            "user_id": "0",
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
            self.url,
            data=data,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403, "status code is not 403")

    def test_health_input_missing_input_with_authentication(self):

        data = {
            "user_id": "0",
            "datetime_data_collected": "2000-08-09T04:41:53",
            "data": {
                "bp_dia": 80,
                "bp_sys": 120,
            },
        }
        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200, "status code is not 400")

    def test_health_input_valid_none_input_with_authentication(self):

        data = {
            "user_id": "0",
            "datetime_data_collected": "2000-08-09T04:41:53",
            "data": {
                "bp_dia": None,
                "bp_sys": None,
                "weight": None,
                "blood_sugar": None,
                "rr": None,
                "hr": None,
                "spo2": None,
                "body_temperature": None,
            },
        }
        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
