import math
import json
import os
import datetime
import pandas as pd
import numpy as np
import requests
import urllib.parse
from decimal import Decimal
from django.test import TestCase
from django.db.models import Q

from dataprocessing import lib_settings as settings
from dataprocessing import settings as original_settings
from data_app.models import DataProcessing, SpotCache, HealthData,MetricDailyCache,MetricHourlyCache
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app import lib_query_data_syncing
from dataprocessing import settings as original_settings


class DataSyncTestCase(TestCase):

    def test_case_1(self):

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_data_syncing",
            "test_case_1",
            "test_data_1.csv",
        )


        df = pd.read_csv(filepath_input)

        # actual calculate_sensor_duration params

        queryItemsSensorDuration = df.to_dict(orient="records")
        key_dataSync = "datetime_sensor"
        key_recordReceivedByGateway = "record_received_by_gateway"
        key_dashboardMode = "dashboard_mode"
        key_dateTimeServerReceived = "datetime_server_received"

        df_selected = {
            "gateway_mac": ["leonpatient-app", "leonpatient-app", "leonpatient-app"],
            "source": [
                "Perfomatix_StompService",
                "Perfomatix_StompService",
                "Perfomatix_StompService",
            ],
            "user_id": [228, 228, 228],
            "ping_timestamp": [
                "2023-03-23T10:15:31.035Z",
                "2023-03-23T10:24:48.332Z",
                "2023-03-23T10:30:48.334Z",
            ],
        }
        df_selected = pd.DataFrame(df_selected)
        data_length = 1
        startDateTime = datetime.datetime.strptime(
            "2023-03-23 10:00:59", "%Y-%m-%d %H:%M:%S"
        )
        stopDateTime = datetime.datetime.strptime(
            "2023-03-23 10:30:59", "%Y-%m-%d %H:%M:%S"
        )
        resolution = "daily"
        utc_offset = [8, 0]

        actual_sensor_duration_mins = lib_query_data_syncing.calculate_sensor_duration(
            queryItemsSensorDuration,
            key_dataSync,
            key_recordReceivedByGateway,
            key_dashboardMode,
            df_selected,
            key_dateTimeServerReceived,
            data_length,
            startDateTime,
            stopDateTime,
            resolution,
            utc_offset,
        )

        # expected sensor duration calculation

        df["datetime_server_received"] = pd.to_datetime(df["datetime_server_received"])

        # include +5 minutes for the last data point assuming online at that last data point for additional 5 minutes

        expected_sensor_duration = (
            df["datetime_server_received"].iloc[-1]
            - df["datetime_server_received"].iloc[0]
            + datetime.timedelta(minutes=5)
        )

        expected_sensor_duration_mins = expected_sensor_duration.total_seconds() // 60
        tolerance = 0.01
        assert math.isclose(
            expected_sensor_duration_mins,
            actual_sensor_duration_mins,
            rel_tol=tolerance,
        )


class TestQueryDataSyncing(TestCase):

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

        self.url = "/api/v1/query/data_syncing/trends"
        self.token = self._get_auth_token()

    def __assert_output(self, api_response, expected_data):
        
        response_data = api_response['response']

        if isinstance(expected_data, dict):

            for key, expected_values in expected_data.items():
                assert key in response_data, f"Missing key in response: {key}"
                actual_values = response_data[key]
                assert actual_values == expected_values, f"Incorrect {key}"

        else:
            for i, expected_record in enumerate(expected_data):
                actual_record = next((record for record in response_data if record['id'] == expected_record['id']), None)
                assert actual_record is not None, f"No record found in response_data with id {expected_record['id']}"

                for key, expected_values in expected_record.items():
                    assert key in actual_record, f"Missing key in response: {key}"
                    actual_values = actual_record[key]
                    assert actual_values == expected_values, f"Incorrect {key}"


    def test_daily_single_id_valid(self):

        sample_data = [
            {
                "recordDateHourGateway": 1.5823152777777776,
                "utc_offset": "08:00",
                "datetime_local": "2025-04-29 00:00:00",
                "listdate": "2025-04-28 16:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 16:00:00",
            },
            {
                "activity":0,
                "rr": 16,
                "rr_dc": 52,
                "rr_td_SD": 1,
                "activity_SD": 0,
                "datetime_local": "2025-04-30 00:00:00",
                "has_manual_reading": False,
                "rr_dc_SD": 7,
                "listdate": "2025-04-29 16:00:00",
                "recordDateHourServerRR": 0.89,
                "recordReceivedByGateway_to_duration_hrs_chest": 0.28490000000000004,
                "recordReceivedByGateway_to_duration_hrs": 0.28490000000000004,
                "rr_SD": 3,
                "skin_temperature": 26.5,
                "rr_td": 3,
                "recordDateHourGateway": 0.9806466666666666,
                "recordDateHourServer": 0.89,
                "user_id": "-5",
                "datetime_updated": "2025-04-29 16:00:00",
                "utc_offset": "08:00",
                "skin_temperature_SD": 0,
            },
        ]

        for data in sample_data:
            MetricDailyCache.objects.create(**data)

        user_id = "-5"

        params = {
            "start_datetime": "2025-04-28T16:00:00",
            "stop_datetime": "2025-04-30T15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "id": user_id,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "statusCode is not successful")

        expected_data =  {
            'listdate': ['2025-04-29', '2025-04-30'], 
            'recordDateHourGateway': [1.5823152777777776, 0.9806466666666666], 
            'recordDateHourServer': [0.0, 0.89], 
            'recordDateHourServerRR': [0.0, 0.89], 
            'recordReceivedByGateway_to_duration_hrs_chest': [0.0, 0.28490000000000004], 
            'recordReceivedByGateway_to_duration_hrs': [0.0, 0.28490000000000004], 
            'recordDateHourServerHR': [0, 0], 
            'recordReceivedByGateway_to_duration_hrs_finger': [0, 0]
            }
        self.__assert_output(response.json(), expected_data)

    def test_daily_single_id_invalid_datetime_format(self):

        user_id = "0"

        params = {
            "start_datetime": "2023-04-03 16:00:00",
            "stop_datetime": "2023-04-04 15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "id": user_id,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            "start_datetime" in response.json() or "stop_datetime" in response.json(),
        )

    def test_daily_multiple_id_valid(self):


        sample_data =   [
                {
                    "recordDateHourGateway": 1.5823152777777776,
                    "utc_offset": "08:00",
                    "datetime_local": "2025-04-29 00:00:00",
                    "listdate": "2025-04-28 16:00:00",
                    "user_id": "-5",
                    "datetime_updated": "2025-04-28 16:00:00",
                },
                {
                    "recordDateHourGateway": 23.878208333333337,
                    "utc_offset": "08:00",
                    "datetime_local": "2025-04-29 00:00:00",
                    "listdate": "2025-04-28 16:00:00",
                    "user_id": "-4",
                    "datetime_updated": "2025-04-28 16:00:00",
                }            
            ]
        for data in sample_data:
            MetricDailyCache.objects.create(**data)

        list_user_id = "-5,-4"

        params = {
            "start_datetime": "2025-04-28T16:00:00",
            "stop_datetime": "2025-04-29T15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "list_of_ids": list_user_id,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )


        expected_data = [{
            'listdate': ['2025-04-29'], 
            'recordDateHourGateway': [1.5823152777777776], 
            'recordDateHourServer': [0], 
            'recordDateHourServerRR': [0], 
            'recordDateHourServerHR': [0], 
            'recordReceivedByGateway_to_duration_hrs': [0], 
            'recordReceivedByGateway_to_duration_hrs_finger': [0], 
            'recordReceivedByGateway_to_duration_hrs_chest': [0], 
            'id': '-5'
        }, {
            'listdate': ['2025-04-29'], 
            'recordDateHourGateway': [23.878208333333337], 
            'recordDateHourServer': [0], 
            'recordDateHourServerRR': [0], 
            'recordDateHourServerHR': [0], 
            'recordReceivedByGateway_to_duration_hrs': [0], 
            'recordReceivedByGateway_to_duration_hrs_finger': [0], 
            'recordReceivedByGateway_to_duration_hrs_chest': [0], 
            'id': '-4'
        }]


        self.__assert_output(response.json(), expected_data)

    def test_daily_multiple_id_invalid_datetime_format(self):
        list_user_id = "0,1,2,3"

        params = {
            "start_datetime": "2023-04-03 16:00:00",
            "stop_datetime": "2023-04-04 15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "list_of_ids": list_user_id,
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            "start_datetime" in response.json() or "stop_datetime" in response.json(),
        )

    def test_hourly_single_id_valid(self):


        sample_data = [
            {
                "recordDateHourGateway": 0.4001502777777778,
                "datetime_local": "2025-04-29 09:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 01:00:00",
                "listtime": "2025-04-29 01:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 01:00:00",
            },
            {
                "recordDateHourGateway": 0.45239999999999997,
                "datetime_local": "2025-04-29 10:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 02:00:00",
                "listtime": "2025-04-29 02:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 02:00:00",
            },
            {
                "recordDateHourGateway": 0.5761494444444445,
                "datetime_local": "2025-04-29 11:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 03:00:00",
                "listtime": "2025-04-29 03:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 03:00:00",
            },
            {
                "recordDateHourGateway": 0.14056444444444444,
                "datetime_local": "2025-04-29 15:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 07:00:00",
                "listtime": "2025-04-29 07:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 07:00:00",
            },
            {
                "activity": 0,
                "rr": 16,
                "rr_dc": 52,
                "rr_td_SD": 1,
                "activity_SD": 0,
                "datetime_local": "2025-04-30 15:00:00",
                "listtime": "2025-04-30 07:00:00",
                "has_manual_reading": False,
                "rr_dc_SD": 7,
                "recordDateHourServerRR": 0.89,
                "listtimehr": "2025-04-30 07:00:00",
                "recordReceivedByGateway_to_duration_hrs_chest": 0.28490000000000004,
                "recordReceivedByGateway_to_duration_hrs": 0.28490000000000004,
                "rr_SD": 3,
                "skin_temperature": 26.5,
                "rr_td": 3,
                "recordDateHourGateway": 0.7870455555555556,
                "recordDateHourServer": 0.89,
                "user_id": "-5",
                "datetime_updated": "2025-04-30 07:00:00",
                "utc_offset": "08:00",
                "skin_temperature_SD": 0,
            },
            {
                "recordDateHourGateway": 0.17579444444444445,
                "datetime_local": "2025-04-30 16:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-30 08:00:00",
                "listtime": "2025-04-30 08:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-30 08:00:00",
            },
        ]

        for data in sample_data:
            MetricHourlyCache.objects.create(**data)


        user_id = "-5"


        params = {
            "start_datetime": "2025-04-28T16:00:00",
            "stop_datetime": "2025-04-30T15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "id": user_id,
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "statusCode is not successful")

        expected_data = {
            'recordDateHourGateway': [0.4001502777777778, 0.45239999999999997, 0.5761494444444445, 0.14056444444444444, 0.7870455555555556, 0.17579444444444445], 
            'listtimehr': ['2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 07:00:00', '2025-04-30 07:00:00', '2025-04-30 08:00:00'], 
            'listtime': ['2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 07:00:00', '2025-04-30 07:00:00', '2025-04-30 08:00:00'], 
            'recordDateHourServer': [0.0, 0.0, 0.0, 0.0, 0.89, 0.0], 
            'recordDateHourServerRR': [0.0, 0.0, 0.0, 0.0, 0.89, 0.0], 
            'recordReceivedByGateway_to_duration_hrs_chest': [0.0, 0.0, 0.0, 0.0, 0.28490000000000004, 0.0], 
            'recordReceivedByGateway_to_duration_hrs': [0.0, 0.0, 0.0, 0.0, 0.28490000000000004, 0.0], 
            'recordDateHourServerHR': [0, 0, 0, 0, 0, 0], 
            'recordReceivedByGateway_to_duration_hrs_finger': [0, 0, 0, 0, 0, 0]
        }
        self.__assert_output(response.json(), expected_data)

    def test_hourly_single_id_invalid_datetime_format(self):

        user_id = "0"

        params = {
            "start_datetime": "2023-04-03 16:00:00",
            "stop_datetime": "2023-04-04 15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "id": user_id,
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            "start_datetime" in response.json() or "stop_datetime" in response.json(),
        )

    def test_hourly_multiple_id_valid(self):


        sample_data = [
            {
                "recordDateHourGateway": 0.4001502777777778,
                "datetime_local": "2025-04-29 09:00:00",
                "user_id": "-4",
                "datetime_updated": "2025-04-29 01:00:00",
                "listtime": "2025-04-29 01:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 01:00:00",
            },
            {
                "recordDateHourGateway": 0.45239999999999997,
                "datetime_local": "2025-04-29 10:00:00",
                "user_id": "-4",
                "datetime_updated": "2025-04-29 02:00:00",
                "listtime": "2025-04-29 02:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 02:00:00",
            },
            {
                "recordDateHourGateway": 0.5761494444444445,
                "datetime_local": "2025-04-29 11:00:00",
                "user_id": "-4",
                "datetime_updated": "2025-04-29 03:00:00",
                "listtime": "2025-04-29 03:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 03:00:00",
            },
            {
                "recordDateHourGateway": 0.14056444444444444,
                "datetime_local": "2025-04-29 15:00:00",
                "user_id": "-4",
                "datetime_updated": "2025-04-29 07:00:00",
                "listtime": "2025-04-29 07:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 07:00:00",
            },

            {
                "recordDateHourGateway": 0.9812966666666665,
                "datetime_local": "2025-04-29 00:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 16:00:00",
                "listtime": "2025-04-28 16:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 16:00:00",
            },
            {
                "recordDateHourGateway": 1.0511408333333332,
                "datetime_local": "2025-04-29 01:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 17:00:00",
                "listtime": "2025-04-28 17:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 17:00:00",
            },
            {
                "recordDateHourGateway": 0.9277922222222224,
                "datetime_local": "2025-04-29 02:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 18:00:00",
                "listtime": "2025-04-28 18:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 18:00:00",
            },
            {
                "recordDateHourGateway": 1.0160627777777778,
                "datetime_local": "2025-04-29 03:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 19:00:00",
                "listtime": "2025-04-28 19:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 19:00:00",
            },
            {
                "recordDateHourGateway": 0.8354936111111112,
                "datetime_local": "2025-04-29 04:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 20:00:00",
                "listtime": "2025-04-28 20:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 20:00:00",
            },
            {
                "recordDateHourGateway": 0.9809330555555554,
                "datetime_local": "2025-04-29 05:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 21:00:00",
                "listtime": "2025-04-28 21:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 21:00:00",
            },
            {
                "recordDateHourGateway": 0.981095,
                "datetime_local": "2025-04-29 06:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 22:00:00",
                "listtime": "2025-04-28 22:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 22:00:00",
            },
            {
                "recordDateHourGateway": 0.981481388888889,
                "datetime_local": "2025-04-29 07:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-28 23:00:00",
                "listtime": "2025-04-28 23:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-28 23:00:00",
            },
            {
                "recordDateHourGateway": 0.9813552777777778,
                "datetime_local": "2025-04-29 08:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 00:00:00",
                "listtime": "2025-04-29 00:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 00:00:00",
            },
            {
                "recordDateHourGateway": 0.9990436111111111,
                "datetime_local": "2025-04-29 09:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 01:00:00",
                "listtime": "2025-04-29 01:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 01:00:00",
            },
            {
                "recordDateHourGateway": 0.980935,
                "datetime_local": "2025-04-29 10:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 02:00:00",
                "listtime": "2025-04-29 02:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 02:00:00",
            },
            {
                "recordDateHourGateway": 0.9985572222222222,
                "datetime_local": "2025-04-29 11:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 03:00:00",
                "listtime": "2025-04-29 03:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 03:00:00",
            },
            {
                "recordDateHourGateway": 0.9814408333333333,
                "datetime_local": "2025-04-29 12:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 04:00:00",
                "listtime": "2025-04-29 04:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 04:00:00",
            },
            {
                "recordDateHourGateway": 0.9809575,
                "datetime_local": "2025-04-29 13:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 05:00:00",
                "listtime": "2025-04-29 05:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 05:00:00",
            },
            {
                "recordDateHourGateway": 0.9809280555555556,
                "datetime_local": "2025-04-29 14:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 06:00:00",
                "listtime": "2025-04-29 06:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 06:00:00",
            },
            {
                "recordDateHourGateway": 0.9809341666666668,
                "datetime_local": "2025-04-29 15:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 07:00:00",
                "listtime": "2025-04-29 07:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 07:00:00",
            },
            {
                "recordDateHourGateway": 0.9811052777777778,
                "datetime_local": "2025-04-29 16:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 08:00:00",
                "listtime": "2025-04-29 08:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 08:00:00",
            },
            {
                "recordDateHourGateway": 1.0160197222222223,
                "datetime_local": "2025-04-29 17:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 09:00:00",
                "listtime": "2025-04-29 09:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 09:00:00",
            },
            {
                "recordDateHourGateway": 0.9805688888888889,
                "datetime_local": "2025-04-29 18:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 10:00:00",
                "listtime": "2025-04-29 10:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 10:00:00",
            },
            {
                "recordDateHourGateway": 0.9809658333333334,
                "datetime_local": "2025-04-29 19:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 11:00:00",
                "listtime": "2025-04-29 11:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 11:00:00",
            },
            {
                "recordDateHourGateway": 0.9809638888888889,
                "datetime_local": "2025-04-29 20:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 12:00:00",
                "listtime": "2025-04-29 12:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 12:00:00",
            },
            {
                "recordDateHourGateway": 0.9810719444444446,
                "datetime_local": "2025-04-29 21:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 13:00:00",
                "listtime": "2025-04-29 13:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 13:00:00",
            },
            {
                "recordDateHourGateway": 0.9814302777777776,
                "datetime_local": "2025-04-29 22:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 14:00:00",
                "listtime": "2025-04-29 14:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 14:00:00",
            },
            {
                "recordDateHourGateway": 0.9830122222222223,
                "datetime_local": "2025-04-29 23:00:00",
                "user_id": "-5",
                "datetime_updated": "2025-04-29 15:00:00",
                "listtime": "2025-04-29 15:00:00",
                "utc_offset": "08:00",
                "listtimehr": "2025-04-29 15:00:00",
            },
        ]

        for data in sample_data:
            MetricHourlyCache.objects.create(**data)

        list_user_id = "-4,-5"

        params = {
            "start_datetime": "2025-04-28T16:00:00",
            "stop_datetime": "2025-04-29T15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "list_of_ids": list_user_id,
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )


        expected_data = [{
            'recordDateHourGateway': [0.4001502777777778, 0.45239999999999997, 0.5761494444444445, 0.14056444444444444], 
            'listtimehr': ['2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 07:00:00'],
             'listtime': ['2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 07:00:00'], 
            'recordDateHourServer': [0, 0, 0, 0], 
            'recordDateHourServerRR': [0, 0, 0, 0], 
            'recordDateHourServerHR': [0, 0, 0, 0], 
            'recordReceivedByGateway_to_duration_hrs': [0, 0, 0, 0], 
            'recordReceivedByGateway_to_duration_hrs_finger': [0, 0, 0, 0], 
            'recordReceivedByGateway_to_duration_hrs_chest': [0, 0, 0, 0], 
            'id': '-4'
            },
            {'recordDateHourGateway': [0.9812966666666665, 1.0511408333333332, 0.9277922222222224, 1.0160627777777778, 0.8354936111111112, 0.9809330555555554, 0.981095, 0.981481388888889, 0.9813552777777778, 0.9990436111111111, 0.980935, 0.9985572222222222, 0.9814408333333333, 0.9809575, 0.9809280555555556, 0.9809341666666668, 0.9811052777777778, 1.0160197222222223, 0.9805688888888889, 0.9809658333333334, 0.9809638888888889, 0.9810719444444446, 0.9814302777777776, 0.9830122222222223], 
             'listtimehr': ['2025-04-28 16:00:00', '2025-04-28 17:00:00', '2025-04-28 18:00:00', '2025-04-28 19:00:00', '2025-04-28 20:00:00', '2025-04-28 21:00:00', '2025-04-28 22:00:00', '2025-04-28 23:00:00', '2025-04-29 00:00:00', '2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 04:00:00', '2025-04-29 05:00:00', '2025-04-29 06:00:00', '2025-04-29 07:00:00', '2025-04-29 08:00:00', '2025-04-29 09:00:00', '2025-04-29 10:00:00', '2025-04-29 11:00:00', '2025-04-29 12:00:00', '2025-04-29 13:00:00', '2025-04-29 14:00:00', '2025-04-29 15:00:00'], 'listtime': ['2025-04-28 16:00:00', '2025-04-28 17:00:00', '2025-04-28 18:00:00', '2025-04-28 19:00:00', '2025-04-28 20:00:00', '2025-04-28 21:00:00', '2025-04-28 22:00:00', '2025-04-28 23:00:00', '2025-04-29 00:00:00', '2025-04-29 01:00:00', '2025-04-29 02:00:00', '2025-04-29 03:00:00', '2025-04-29 04:00:00', '2025-04-29 05:00:00', '2025-04-29 06:00:00', '2025-04-29 07:00:00', '2025-04-29 08:00:00', '2025-04-29 09:00:00', '2025-04-29 10:00:00', '2025-04-29 11:00:00', '2025-04-29 12:00:00', '2025-04-29 13:00:00', '2025-04-29 14:00:00', '2025-04-29 15:00:00'], 
             'recordDateHourServer': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'recordDateHourServerRR': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'recordDateHourServerHR': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'recordReceivedByGateway_to_duration_hrs': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'recordReceivedByGateway_to_duration_hrs_finger': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'recordReceivedByGateway_to_duration_hrs_chest': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
             'id': '-5'
            }
            ]

        self.assertEqual(response.status_code, 200, "statusCode is not successful")

        self.__assert_output(response.json(), expected_data)

    def test_hourly_multiple_id_invalid_datetime_format(self):

        list_user_id = "0,1,2,3"

        params = {
            "start_datetime": "2023-04-03 16:00:00",
            "stop_datetime": "2023-04-04 15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "list_of_ids": list_user_id,
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            "start_datetime" in response.json() or "stop_datetime" in response.json(),
        )

    def test_filter_records_within_dynamic_date_range_single_id(self):

        user_id = "-1"
        sample_data = [
            {
                "user_id": user_id,
                "datetime_updated": "2025-03-10 18:30:00",
                "datetime_local": "2025-03-11 00:00:00",
                "listdate": "2025-03-10 18:30:00",
                "recordReceivedByGateway_to_duration_hrs": "0.97",
                "recordReceivedByGateway_to_duration_hrs_chest": "0.97",
            },
            {
                "user_id": user_id,
                "datetime_updated": "2025-03-11 18:30:00",
                "datetime_local": "2025-03-12 00:00:00",
                "listdate": "2025-03-11 18:30:00",
                "recordReceivedByGateway_to_duration_hrs": "1.81",
                "recordReceivedByGateway_to_duration_hrs_finger": "0.23",
                "recordDateHourServerRR": "2.5",
                "recordReceivedByGateway_to_duration_hrs_chest": "1.57",
            },
            {
                "user_id": user_id,
                "datetime_updated": "2025-03-12 00:00:00",
                "datetime_local": "2025-03-12 00:00:00",
                "listdate": "2025-03-12 00:00:00",
                "recordReceivedByGateway_to_duration_hrs": "0.83",
                "recordDateHourServerRR": "0.83",
                "recordReceivedByGateway_to_duration_hrs_chest": "0.28",
            },
        ]

        for data in sample_data:
            MetricDailyCache.objects.create(**data)


        params = {
            "start_datetime": "2025-03-10T18:30:00",
            "stop_datetime": "2025-03-13T09:04:57",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+05:30",
            "id": user_id,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "statusCode is not successful")

        data = response.json()["response"]
        expected_listdate = ["2025-03-11", "2025-03-12"]

        assert len(data["listdate"]) == len(
            set(data["listdate"])
        ), f"Duplicate 'listdate' found."
        assert set(data["listdate"]) == set(
            expected_listdate
        ), f"'listdate' values do not match expected values."

    def test_filter_records_within_dynamic_date_range_multiple_id(self):

        list_user_id = [0, 1, 2]
        list_user_id_str = ",".join(map(str, list_user_id))
        for user_id in list_user_id:
            sample_data = [
                {
                    "user_id": str(user_id),
                    "datetime_updated": "2025-03-10 18:30:00",
                    "datetime_local": "2025-03-11 00:00:00",
                    "listdate": "2025-03-10 18:30:00",
                    "recordReceivedByGateway_to_duration_hrs": "0.97",
                    "recordReceivedByGateway_to_duration_hrs_chest": "0.97",
                },
                {
                    "user_id": str(user_id),
                    "datetime_updated": "2025-03-11 18:30:00",
                    "datetime_local": "2025-03-12 00:00:00",
                    "listdate": "2025-03-11 18:30:00",
                    "recordReceivedByGateway_to_duration_hrs": "1.81",
                    "recordReceivedByGateway_to_duration_hrs_finger": "0.23",
                    "recordDateHourServerRR": "2.5",
                    "recordReceivedByGateway_to_duration_hrs_chest": "1.57",
                },
                {
                    "user_id": str(user_id),
                    "datetime_updated": "2025-03-12 00:00:00",
                    "datetime_local": "2025-03-12 00:00:00",
                    "listdate": "2025-03-12 00:00:00",
                    "recordReceivedByGateway_to_duration_hrs": "0.83",
                    "recordDateHourServerRR": "0.83",
                    "recordReceivedByGateway_to_duration_hrs_chest": "0.28",
                },
            ]

            for data in sample_data:
                MetricDailyCache.objects.create(**data)

        params = {
            "start_datetime": "2025-03-10T18:30:00",
            "stop_datetime": "2025-03-13T09:04:57",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+05:30",
            "list_of_ids": list_user_id_str,
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 200, "statusCode is not successful")

        data = response.json()["response"]
        expected_listdate = ["2025-03-11", "2025-03-12"]

        ids = [int(entry["id"]) for entry in data]
        assert set(list_user_id) == set(
            ids
        ), "Mismatch list_user_id and ids are not the same"
        for entry in data:
            assert len(entry["listdate"]) == len(
                set(entry["listdate"])
            ), f"Duplicate 'listdate' found."
            assert set(entry["listdate"]) == set(
                expected_listdate
            ), f"'listdate' values do not match expected values."
