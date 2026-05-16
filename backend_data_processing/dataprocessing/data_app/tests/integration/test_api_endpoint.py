import os
import pytest
import environ
import requests
import json
import django


# Initialize environ to access environment variables
env = environ.Env()

# Set the Django settings module environment variable
os.environ['DJANGO_SETTINGS_MODULE'] = 'dataprocessing.settings'

# Initialize Django once before any tests
django.setup()

from dataprocessing import lib_settings as settings
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app.models import *


def get_auth_token():
    payload = json.dumps(auth_login)
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"{backend_url}/api/auth/login", data=payload, headers=headers
    )
    if response.status_code in (200, 201):
        return response.json().get("access_token")
    else:
        print(
            f"Failed to retrieve token: {response.status_code} - {response.text}"
        )



class TestGetProcessInProgressUsers:
    """test get api to return user ids of users whose data are in progress"""

    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/processing"


    def test_get_process_in_progress_users_hourly(self):
        """test api returns user is when data process is in progress  using hourly resolution"""

        user_id = 0
        data = {
            "user_id": user_id,
            "datetime": "2025-05-21 11:30:00",
            "timestamp_server_received": "2025-05-21 11:30:00",
            "timestamp_daily": "2025-05-21 00:00:00",
            "utc_offset": "+00:00",
            "timestamp_hourly": "2025-05-21 11:00:00",
            "data_source": "sensor",
        }
        
        ProcessInProgress.objects.create(**data)

        payload = {
            "user_ids": "0,-1,-2",
            "query_time_start": "2025-05-21T11:00:00",
            "query_time_end": "2025-05-21T11:59:59",
            "resolution": "hourly",
        }
        response = requests.get(self.api_url, payload, headers=self.headers)

        ProcessInProgress.objects.filter(user_id= user_id).delete()

        assert response.status_code == requests.codes.ok
        response = response.json()["response"]
        assert (
            "user_in_progress" in response
        ), f"Key '{'user_in_progress'}' not found in response"
        assert response["user_in_progress"] == [user_id], "Mismatch in users in progress"


    def test_get_no_process_in_progress_users_hourly(self):
        """test api return [] when no  data process is in progress  using hourly resolution"""

        payload = {
            "user_ids": "-1,-2",
            "query_time_start": "2025-05-21T12:00:00",
            "query_time_end": "2025-05-21T12:59:59",
            "resolution": "hourly",
        }

        response = requests.get(self.api_url, payload, headers=self.headers)
        assert response.status_code == requests.codes.ok
        response = response.json()["response"]
        assert (
            "user_in_progress" in response
        ), f"Key '{'user_in_progress'}' not found in response"
        assert response["user_in_progress"] == [], "Mismatch in users in progress"


    def test_get_process_in_progress_users_daily(self):
        """test api returns user is when data process is in progress  using daily resolution"""

        user_id = 0
        data = {
            "user_id": user_id,
            "datetime": "2025-05-21 11:30:00",
            "timestamp_server_received": "2025-05-21 11:30:00",
            "timestamp_daily": "2025-05-21 00:00:00",
            "utc_offset": "+00:00",
            "timestamp_hourly": "2025-05-21 11:00:00",
            "data_source": "sensor",
        }
        ProcessInProgress.objects.create(**data)

        payload = {
            "user_ids": "0,-1,-2",
            "query_time_start": "2025-05-21T00:00:00",
            "query_time_end": "2025-05-21T23:59:59",
            "resolution": "daily",
        }
        response = requests.get(self.api_url, payload, headers=self.headers)

        ProcessInProgress.objects.filter(user_id= user_id).delete()

        assert response.status_code == requests.codes.ok
        response = response.json()["response"]
        assert (
            "user_in_progress" in response
        ), f"Key '{'user_in_progress'}' not found in response"
        assert response["user_in_progress"] == [user_id], "Mismatch in users in progress"

 
    def test_get_no_process_in_progress_users_daily(self):
        """test api return [] when no  data process is in progress using daily resolution"""


        payload = {
            "user_ids": "-1,-2",
            "query_time_start": "2025-05-22T00:00:00",
            "query_time_end": "2025-05-22T23:59:59",
            "resolution": "daily",
        }
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok
        response = response.json()["response"]
        assert (
            "user_in_progress" in response
        ), f"Key '{'user_in_progress'}' not found in response"
        assert response["user_in_progress"] == [], "Mismatch in users in progress"


class TestOtherDeviceReadingSubmission:

    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/data/other/bp-device"


    def test_bp_device_submission(self):
        '''
        test submmission of reading from BP device
        '''

        user_id = "0"

        data = {
            "userId": 0,
            "bloodPressureSystolic": 120,
            "bloodPressureDiastolic": 80,
            "deviceId": "b8b77d137f35"
        }

        response = self.client.post(
            self.api_url,
            data=payload,
            content_type="application/json",
            HTTP_REFERER=settings.VALID_REFERER[0]

        )


        assert response.status_code == requests.codes.created

        # clear  test data
        OtherDeviceReading.objects.filter(user_id = user_id).delete()
        ProcessInProgress.objects.filter(user_id = user_id).delete()
        MetricMinutesCache.objects.filter(user_id = user_id).delete()


class TestGetBPDeviceData:
    """test get api to return bp device data"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/query/spot/bp-device"


    def test_get_bp_device_data(self):
        """test get api to return bp device data"""
 
        payload = {
            "user_id": "0",
            "stop_datetime": "2023-02-08T22:13:00",
            "date_time": "2023-02-08T22:13:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestPatientListAPI:
    """test get api to return bp device data"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/query/list"


    def test_query_list_minutes(self):
        """test patient list api of multiple users in minute resoluion"""
 
        payload = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-03-09T03:05:59",
            "resolution": "minutes",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_list_daily(self):
        """test patient list api of multiple users in daily resoluion"""
 
        payload = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-03-09T03:05:59",
            "resolution": "daily",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_list_hourly(self):
        """test patient list api of multiple users in hourly resoluion"""
 
        payload = {
            "list_of_id": "0,1,2,3",
            "date_time": "2023-03-09T03:05:59",
            "resolution": "hourly",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestTrendsAPI:
    """test trends API"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/query/trends"


    def test_query_list_minutes(self):
        """test trends api of a single user in minute resoluion"""
 
        payload = {
            "id": "0",
            "start_datetime": "2023-02-08T12:00:00",
            "stop_datetime": "2023-02-08T22:13:00",
            "resolution": "minutes",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_list_daily(self):
        """test trends api of a single user in daily resoluion"""
 
        payload = {
            "id": "0",
            "start_datetime": "2022-09-25T16:00:00",
            "stop_datetime": "2022-10-04T15:59:59",
            "resolution": "daily",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_list_hourly(self):
        """test trends api of a single user in hourly resoluion"""
 
        payload = {
            "id": "0",
            "start_datetime": "2022-07-28T03:40:40",
            "stop_datetime": "2022-08-02T01:25:43",
            "resolution": "hourly",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_trend_minutes_multiple_ids(self):
        """test trends api of multiple users in minutes resoluion"""
 
        payload = {
            "id": "0,1,2,3,4,5",
            "start_datetime": "2023-02-08T12:00:00",
            "stop_datetime": "2023-02-08T22:13:00",
            "resolution": "minutes",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_trend_hourly_multiple_ids(self):
        """test trends api of multiple users in hourly resoluion"""
 
        payload = {
            "id": "0,1,2,3,4,5",
            "start_datetime": "2022-07-28T03:40:40",
            "stop_datetime": "2022-08-02T01:25:43",
            "resolution": "hourly",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_trend_daily_multiple_ids(self):
        """test trends api of multiple users in daily resoluion"""
 
        payload = {
            "id": "0,1,2,3,4,5",
            "start_datetime": "2022-09-25T16:00:00",
            "stop_datetime": "2022-10-04T15:59:59",
            "resolution": "daily",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_query_data_syncing(self):
 
        payload = {
            "id": "0",
            "start_datetime": "2022-07-19T03:59:59",
            "stop_datetime": "2022-08-17T03:59:59",
            "data_type": "dateTimeSensor",
            "resolution": "daily",
            "utc_offset": "+08:00",
        }

 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestSpotAPI:
    """test spot api"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/query/spot"


    def test_query_spot(self):
 
        payload = {
            "id": "0",
            "date_time": "2023-03-09T03:05:59",
            "utc_offset": "+08:00",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestGatewayPing:
    """test gateway ping api"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/gateway_ping/last-connection"


    def test_main_physical_gateway_ping(self):

        payload = {
            "gateway_mac": "abc123",
            "source": "dummy_source",
        }

        response = requests.post(self.api_url, json=payload, headers=self.headers)

        pings  = GatewayPings.objects.filter(gateway_mac = payload['gateway_mac'])
        pings.delete()

        assert response.status_code == requests.codes.ok


    def test_main_application_gateway_ping(self):

        payload = {
            "gateway_mac": "cde123-app",
            "source": "dummy_source",
            "fwVersion": "null",
            "patientId": 0,
        }

        response = requests.post(self.api_url, json=payload, headers=self.headers)

        pings  = GatewayPings.objects.filter(gateway_mac = payload['gateway_mac'])
        pings.delete()

        assert response.status_code == requests.codes.ok


class TestExportAPI:
    """test export api"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/export/processed"


    def test_main_export_1(self):
 
        payload = {
            "users": '[{"username":"dummy","id":-1,"utc_offset":"+08:00"}]',
            "data": "RR,HR",
            "startTime": "2023-07-25T06:00:00",
            "endTime": "2023-07-25T08:30:00",
            "resolution": "minutes",
        }
     
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_main_export_2(self):
 
        payload = {
            "users": '[{"username":"dummy","id":-1,"utc_offset":"+08:00"}]',
            "data": "RR,HR",
            "startTime": "2023-07-25T06:00:00",
            "endTime": "2023-07-25T08:30:00",
            "resolution": "minute",
        }

     
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_main_export_3(self):
 
        payload = {
            "users": '[{"username":"dummy","id":-1,"utc_offset":"+08:00"}]',
            "data": "RR,HR",
            "startTime": "2023-07-25T06:00:00",
            "endTime": "2023-07-25T08:30:00",
            "resolution": "random",
        }

     
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestThirdPartyIntegrationAPI:
    """test third party integration"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/vitals/readings"


    def test_third_party_integration(self):

        payload = {
            "userid": '2157',
            "start": "2025-03-05T05:45:28",
            "end": "2025-03-05T08:45:28",
            "page": 1,
            "limit": 1,
        }
 
        response = requests.get(self.api_url, params=payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


class TestUploadAPI:
    """test sensor data upload API"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Referer": settings.VALID_REFERER[0]
        }
        self.api_url = f"{base_url}/api/v1/upload"


    def test_upload_with_valid_token(self):

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
 
        response = requests.post(self.api_url, json=payload, headers=self.headers)

        assert response.status_code == requests.codes.ok


    def test_upload_with_invalid_token(self):

        invalid_headers = {"Referer": "InVaLiDtOkEn"}

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
 
        response = requests.post(self.api_url, json=payload, headers=invalid_headers)

        assert response.status_code == requests.codes.forbidden


class TestDataSyncAPI:
    """test data sync API"""
 
    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/query/data_syncing/trends"

    def test_main_query_data_sync_trends_hourly_single_id(self):
        """test data sync api of a single user in hourly resoluion"""
 
        payload = {
            "start_datetime": "2023-04-03T16:00:00",
            "stop_datetime": "2023-04-04T15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "id": "0",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok

    def test_main_query_data_sync_trends_hourly_multiple_ids(self):
        """test data sync api of multiple user in hourly resoluion"""
 
        payload = {
            "start_datetime": "2023-04-03T16:00:00",
            "stop_datetime": "2023-04-04T15:59:59",
            "resolution": "hourly",
            "data_type": "dateTimeSensor",
            "list_of_ids": "0,1,2,3",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok

    def test_main_query_data_sync_trends_daily_single_id(self):
        """test data sync api of a single user in daily resoluion"""
 
        payload = {
            "start_datetime": "2023-04-03T16:00:00",
            "stop_datetime": "2023-04-04T15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "id": "0",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok

    def test_main_query_data_sync_trends_daily_multiple_ids(self):
        """test data sync api of multiple user in daily resoluion"""
 
        payload = {
            "start_datetime": "2023-04-03T16:00:00",
            "stop_datetime": "2023-04-04T15:59:59",
            "resolution": "daily",
            "data_type": "dateTimeSensor",
            "utc_offset": "+08:00",
            "list_of_ids": "0,1,2,3",
        }
 
        response = requests.get(self.api_url, payload, headers=self.headers)

        assert response.status_code == requests.codes.ok



class TestSubmitHealthInput:
    """test API of health inout data submission"""
 

    @pytest.fixture(autouse=True)
    def setup(self):

        base_url = settings.DATA_PROCESSING_URL
        token = get_auth_token()

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.api_url = f"{base_url}/api/v1/submit-health-input"

    def test_submit_health_input_valid_data(self):

        user_id = -10
        payload = {
            "user_id": user_id,
            "datetime_data_collected": "2000-03-12T03:12:24",
            "data": {
                "bp_sys": 200,
                "bp_dia": 90,
                "weight": 85,
                "blood_sugar": 5.5,
                "rr": 30,
                "hr": 115,
                "spo2": 98,
                "body_temperature": 35.6,
            },
        }
 
        response = requests.post(self.api_url, json=payload, headers=self.headers)

        OtherDeviceReading.objects.filter(user_id = user_id).delete()
        ProcessInProgress.objects.filter(user_id = user_id).delete()
        MetricMinutesCache.objects.filter(user_id = user_id).delete()
        HealthData.objects.filter(user_id = user_id).delete()

        assert response.status_code == requests.codes.ok


    def test_submit_health_input_invalid_data(self):

        payload = {
            "user_id": "-1",
            "datetime_data_collected": "2000-03",
            "data": {"bp_sys": 200, "bp_dia": 90},
        }

        response = requests.post(self.api_url, json=payload, headers=self.headers)

        assert response.status_code == requests.codes.bad
