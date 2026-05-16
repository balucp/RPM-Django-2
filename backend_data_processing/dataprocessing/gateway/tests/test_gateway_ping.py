import json
from datetime import datetime, timezone
from unittest import mock
import requests

from django.test import TestCase
from django.db import IntegrityError, transaction, connection

from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from dataprocessing import lib_settings as settings
from gateway.handle_views import store_gateway_ping
from data_app.models import *
from gateway.models import *


class TestMainGatewayPing(TestCase):

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

        self.url = "/api/v1/gateway_ping"
        self.token = self._get_auth_token()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # test_store_valid_input_all_data
        self.data_1 = {
            "gateway_mac": "dummy_mac",
            "ping_timestamp": "2025-02-04T07:23:01.967Z",
            "source": "dummy_source",
            "user_id": 1,
        }

        # test_store_valid_input_with_none_userid
        self.data_2 = {
            "gateway_mac": "dummy_mac",
            "ping_timestamp": "2025-02-05T07:23:01.967Z",
            "source": "dummy_source",
            "user_id": None,
        }

    def tearDown(self):

        if connection.in_atomic_block or connection.needs_rollback:
            try:
                connection.rollback()
            except Exception:
                pass

        cache_models = [
            DataProcessing, MetricMinutesCache, MetricHourlyCache,
            MetricDailyCache, SpotCache, StagingHourlyCache, HealthData,
        ]

        for model in cache_models:
            try:
                model.objects.all().delete()
            except Exception:
                pass

    def test_store_valid_input_all_data(self):
        """Test that a valid ping is successfully stored in DB"""

        data = self.data_1.copy()
        timestamp_str = data.get("ping_timestamp")
        timestamp_obj = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)

        store_gateway_ping(
            gateway_mac=data.get("gateway_mac"),
            ping_timestamp=timestamp_obj,
            source=data.get("source"),
            user_id=data.get("user_id"),
        )

        stored_item = GatewayPings.objects.get(
            user_id=data.get("user_id"),
            gateway_mac=data.get("gateway_mac")
        )

        assert stored_item.gateway_mac == data.get("gateway_mac"), "Mismatch in gateway_mac"
        assert stored_item.source in ["dummy_source"], "Source should be None or default"

    @mock.patch("logging.error")
    @mock.patch("logging.info")
    def test_store_valid_input_with_none_userid(self, mock_info, mock_error):
        """Test that a valid ping is successfully stored in DB"""

        data = self.data_2.copy()
        timestamp_str = data.get("ping_timestamp")
        timestamp_obj = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)

        try:
            store_gateway_ping(
                gateway_mac=data["gateway_mac"],
                ping_timestamp=timestamp_obj,
                source=data["source"],
                user_id=data["user_id"],  # None
            )
        except (IntegrityError, transaction.TransactionManagementError):
            transaction.set_rollback(True)
            pass
        except Exception as e:
            self.fail(f"store_gateway_ping raised an exception unexpectedly: {e}")

        error_calls = [str(call.args[0]) for call in mock_error.call_args_list]
        info_calls = [str(call.args[0]) for call in mock_info.call_args_list]
        
        self.assertTrue(
            any("NOT NULL constraint failed: data_app_metrichourlycache.user_id" in msg for msg in error_calls),
            "Expected IntegrityError log for missing user_id was not found in logs."
        )

        self.assertTrue(
            any("[GatewayPing] Creating ping record" in msg for msg in info_calls),
            "Expected GatewayPing creation log not found."
        )
 
    def test_upload_with_valid_token(self):

        upload_url = f"{settings.query_url}/upload"

        payload = {
            "userID": "0",
            "datetime": "2021-07-30 14:58:41",
            "battery": 20,
            "sensorID": "rs173246372",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "GEN",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 5376,
            "recordReceivedByGateway": 1034,
            "dataColName": "{DDDDDDDDRRRRSSSSXXXYYYZZZTTTM}",
            "data": [
                "6104137a004400007d47f1685142a",
                "6104137a004400007d37ef685142a",
                "6104137a004400007d27f1683142a",
            ],
        }

        valid_headers = {"Referer": settings.VALID_REFERER[0]}

        response = requests.post(upload_url, json=payload, headers=valid_headers)
        assert response.status_code == requests.codes.ok

    def test_upload_referer_param(self):

        upload_url = f"{settings.query_url}/upload"

        payload = {
            "userID": "0",
            "datetime": "2021-07-30 14:58:41",
            "battery": 20,
            "sensorID": "rs173246372",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "GEN",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 5376,
            "recordReceivedByGateway": 1034,
            "dataColName": "{DDDDDDDDRRRRSSSSXXXYYYZZZTTTM}",
            "data": [
                "6104137a004400007d47f1685142a",
                "6104137a004400007d37ef685142a",
                "6104137a004400007d27f1683142a",
            ],
        }

        valid_headers = {"referer": settings.VALID_REFERER[0]}

        response = requests.post(upload_url, json=payload, headers=valid_headers)
        assert response.status_code == requests.codes.ok

    def test_upload_with_invalid_token(self):

        upload_url = f"{settings.query_url}/upload"

        payload = {
            "userID": "0",
            "datetime": "2021-07-30 14:58:41",
            "battery": 20,
            "sensorID": "rs173246372",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "GEN",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 5376,
            "recordReceivedByGateway": 1034,
            "dataColName": "{DDDDDDDDRRRRSSSSXXXYYYZZZTTTM}",
            "data": [
                "6104137a004400007d47f1685142a",
                "6104137a004400007d37ef685142a",
                "6104137a004400007d27f1683142a",
            ],
        }

        invalid_headers = {"Referer": "InVaLiDtOkEn"}

        response = requests.post(upload_url, json=payload, headers=invalid_headers)
        assert response.status_code == requests.codes.unauthorized
