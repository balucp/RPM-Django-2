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



class PatientListMinuteTesTestQueryDataSyncingtCase(TestCase):

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



    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()







    def test_daily_single_id_valid(self):

        user_id = "1896"

        params =  {
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
        response = response.json()["response"]

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

