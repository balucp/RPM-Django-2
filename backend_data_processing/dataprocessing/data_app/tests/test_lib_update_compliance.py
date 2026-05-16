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
from gateway.handle_views import store_gateway_ping
from data_app.models import *
from gateway.models import *


class TestQuerySyncComplianceSensor(TestCase):
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

        self.url = "/api/v1/upload"
        self.token = self._get_auth_token()
        self.valid_token = settings.VALID_REFERER[0]
        self.invalid_token = 'invalid' + settings.VALID_REFERER[0]
        self.user_id = 0

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()

    def test_update_compliance_sensor_data(self):


        data = {
            "body-json": {
            "battery": "25",
            "data": [
                "6423fa670085059c6e08eb7de12e5",
                "6423faaa003c02206bd8c886212f5"
            ],
            "dataColName": "{DDDDDDDDRRRRSSSSXXXYYYZZZTTTM}",
            "datetime": "2025-02-10 08:45:39",
            "mode": "PULSE OXIMETRY",
            "packetNumber": 1,
            "recordCollectedBySensor": 1661,
            "recordReceivedByGateway": 1654,
            "sensorID": "dummy",
            "sensorMode": "HR",
            "totalPacket": 1,
            "userID": self.user_id
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")


class TestQuerySyncComplianceGateway(TestCase):
    """Test that a valid ping is successfully stored in DynamoDB"""

    def setUp(self):

        self.dummy_data = {
            "gateway_mac": "dummy_mac",
            "ping_timestamp": datetime.datetime(2025,5,4,7,23,1,tzinfo=datetime.timezone.utc),
            "source": "dummy_source",
            "user_id": 0,
        }


    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()


    def test_update_hourly_compliance_gateway_ping(self):

        response = store_gateway_ping(**self.dummy_data)

        self.assertEqual(response.status_code, 200, "request is not successful")

        gateway_ping = GatewayPings.objects.get(user_id = self.dummy_data["user_id"],
                                                gateway_mac = self.dummy_data["gateway_mac"])
        
        datetime_updated = gateway_ping.ping_timestamp.replace(minute=0, second=0)

        self.assertTrue(
            MetricHourlyCache.objects.filter(
                user_id=self.dummy_data["user_id"],
                datetime_updated=datetime_updated
            ).exists(),
            "MetricHourlyCache does not  exists!"
        )


    def test_update_daily_compliance_gateway_ping(self):

        response = store_gateway_ping(**self.dummy_data)

        self.assertEqual(response.status_code, 200, "request is not successful")

        gateway_ping = GatewayPings.objects.get(user_id = self.dummy_data["user_id"],
                                                gateway_mac = self.dummy_data["gateway_mac"])
        datetime_updated = gateway_ping.ping_timestamp.replace(hour = 0,minute=0, second=0)

        self.assertTrue(
            MetricDailyCache.objects.filter(
                user_id=self.dummy_data["user_id"],
                datetime_updated=datetime_updated
            ).exists(),
            "MetricDailyCache does not  exists!"
        )