import json
import re
import datetime
import requests
import urllib.parse
from urllib.parse import quote, unquote
from datetime import timezone, timedelta

from django.test import TestCase
from dataprocessing import lib_settings as settings
from data_app.models import DataProcessing, HealthData
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url


class ExportTestCase(TestCase):

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

    def _upload_health_data(self, dataset_type="manual_data_1"):

        manual_data_1 = [
            {
                "user_id": -3,
                "datetime": datetime.datetime(2001, 7, 8, 13, 1, 42, tzinfo=datetime.timezone.utc),
                "bp_sys": 90,
                "hr": 78,
            },
            {
                "user_id": -3,
                "datetime": datetime.datetime(2001, 7, 8, 13, 1, 39, tzinfo=datetime.timezone.utc),
                "bp_sys": 95,
                "rr": 31,
            },
        ]

        manual_data_2 = [
            {
                "user_id": -3,
                "datetime": datetime.datetime(2001, 7, 8, 13, 0, 0, tzinfo=datetime.timezone.utc),
                "bp_sys": 101,
                "bp_dia": 61,
                "weight": 67,
                "blood_sugar": 5.6,
                "rr": 33,
                "hr": 56,
                "spo2": 97,
                "body_temp": 37.3
            }
        ]

        manual_data_3 = [
            {
                "user_id": -3,
                "datetime": datetime.datetime(2001, 7, 8, 0, 0, 0, tzinfo=datetime.timezone.utc),
                "bp_sys": 101,
                "bp_dia": 61,
                "weight": 67,
                "blood_sugar": 5.6,
                "rr": 33,
                "hr": 56,
                "spo2": 97,
                "body_temp": 37.3       
            }
        ]

        dataset_map = {
            "manual_data_1": manual_data_1,
            "manual_data_2": manual_data_2,
            "manual_data_3": manual_data_3,
        }

        manual_data = dataset_map.get(dataset_type)
        for item in manual_data:
            HealthData.objects.create(**item)

    def get_expected_filename_from_params(self, params):
        """
        Generate the expected Excel filename pattern based on export parameters.
        Matches the backend filename logic for test validation.
        """
        start_dt = params["startTime"]
        end_dt = params["endTime"]
        org_name = params.get("organisationName", "").strip()

        # Parse user UTC offset
        users = json.loads(unquote(params["users"]))
        utc_offset_str = users[0]["utc_offset"]  # e.g. "+08:00"

        # Convert UTC offset string to hours/minutes
        sign = 1 if utc_offset_str[0] == "+" else -1
        hours, minutes = map(int, utc_offset_str[1:].split(":"))
        offset = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))

        # Convert input ISO times to UTC → then to local timezone
        utc_start = datetime.datetime.fromisoformat(start_dt).replace(tzinfo=timezone.utc)
        utc_end = datetime.datetime.fromisoformat(end_dt).replace(tzinfo=timezone.utc)

        local_start = utc_start.astimezone(offset)
        local_end = utc_end.astimezone(offset)

        # Format time range
        date_range = (
            f"{local_start.strftime('%d%m%Y %H_%M_%S')} to "
            f"{local_end.strftime('%d%m%Y %H_%M_%S')}"
        )

        # Build expected pattern (matches backend logic)
        if org_name:
            expected = f"Respiree_PatientVitals_{org_name}_{date_range}.xlsx"
        else:
            expected = f"Respiree_PatientVitals_{date_range}.xlsx"

        return expected

    def setUp(self):

        self.url = "/api/v1/export/processed"
        self.token = self._get_auth_token()

        data_processing_data = [
            {
                "user_id": -1,
                "date_time": datetime.datetime(
                    1999, 1, 2, 0, 0, 1, tzinfo=datetime.timezone.utc
                ),
                "dashboard_mode": "RR",
                "hr": 10,
                "rr": 50,
                "spo2": 100,
            }
        ]

        for item in data_processing_data:
            DataProcessing.objects.create(**item)

    def test_minutes_export(self):

        params = {
            "resolution": "minutes",
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T00:00:02",
            "data": "RR,HR",
            "organisationName": "test org",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))

    def test_hourly_export(self):

        params = {
            "resolution": "hourly",
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T02:00:00",
            "data": "RR,HR",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))

    def test_daily_export(self):

        params = {
            "resolution": "daily",
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-01T16:00:00",
            "endTime": "1999-01-03T16:00:00",
            "data": "RR,HR",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))

    def test_minutes_invalid_parametert(self):

        params = {
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T00:00:02",
            "data": "RR,HR",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)

    def test_hourly_export_invalid_parameter(self):

        params = {
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T02:00:00",
            "data": "RR,HR",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)

    def test_daily_export_invalid_parameter(self):

        params = {
            "resolution": "daily",
            "users": json.dumps(
                [{"username": "dummy", "id": -1, "utc_offset": "+08:00"}]
            ),
            "startTime": "1999-01-01T16:00:00",
            "endTime": "1999-01-03T16:00:00",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"

        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        self.assertEqual(response.status_code, 400)

    def test_export_processed_with_org_name(self):

        params = {
            "resolution": "minutes",
            "users": json.dumps(
                [{"username":"dummy","id":-1,"utc_offset":"+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T00:00:02",
            "data": "RR,HR",
            "organisationName": "Test Organisation",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        content_disposition = response.get("Content-Disposition", "")
        match = re.search(r'filename="([^"]+)"', content_disposition)
        self.assertIsNotNone(match, "No filename found in Content-Disposition header")

        filename = match.group(1)
        org_name = params["organisationName"].lower().replace(" ", "")
        filename_normalized = filename.lower().replace("_", "").replace(" ", "")
        self.assertIn(org_name, filename_normalized, f'Expected organisation name "{org_name}" to appear in filename "{filename}"',)

    def test_filename(self):

        params = {
            "resolution": "minutes",
            "users": json.dumps(
                [{"username":"dummy","id":-1,"utc_offset":"+08:00"}]
            ),
            "startTime": "1999-01-02T00:00:00",
            "endTime": "1999-01-02T00:00:02",
            "data": "RR,HR",
            "organisationName": "Test Organisation",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        content_disposition = response.get("Content-Disposition", "")
        match = re.search(r'filename="([^"]+)"', content_disposition)
        self.assertIsNotNone(match, "No filename found in Content-Disposition header")

        filename = match.group(1)
        expected_filename = self.get_expected_filename_from_params(params)
        self.assertEqual(filename, expected_filename, f"Expected filename '{expected_filename}', got '{filename}'",)

    def test_manual_health_input_minute_export(self):

        self._upload_health_data("manual_data_1")
        params = {
            "resolution": "minutes",
            "users": quote(r'[{"username":"xxx","id":"-3","utc_offset":"+05:30"},{"username":"yyy","id":"-30","utc_offset":"+05:30"}]'),
            "startTime": "2001-07-08T12:50:42",
            "endTime": "2001-07-08T13:10:42",
            "data": "HR_manual,RR_manual,Spo2_manual,body_temperature_manual,blood_sugar,BP_diastolic,BP_systolic,weight",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))

    def test_manual_health_input_hourly_export(self):

        self._upload_health_data("manual_data_2")
        params = {
            "resolution": "hourly",
            "users": quote(r'[{"username":"xxx","id":"-3","utc_offset":"+00:00"},{"username":"yyy","id":"-4","utc_offset":"+05:30"},{"username":"zzz","id":"-5","utc_offset":"+08:00"}]'),
            "startTime": "2001-07-08T10:00:00",
            "endTime": "2001-07-08T15:00:00",
            "data": "HR_manual,RR_manual,Spo2_manual,body_temperature_manual,blood_sugar,BP_diastolic,BP_systolic,weight",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))

    def test_manual_health_input_daily_export(self):

        self._upload_health_data("manual_data_3")
        params = {
            "resolution": "daily",
            "users": quote(r'[{"username":"xxx","id":"-3","utc_offset":"+00:00"},{"username":"yyy","id":"-30","utc_offset":"+05:30"},{"username":"zzz","id":"-40","utc_offset":"+08:00"}]'),
            "startTime": "2001-07-02T09:00:00",
            "endTime": "2001-07-10T19:00:00",
            "data": "HR_manual,RR_manual,Spo2_manual,body_temperature_manual,blood_sugar,BP_diastolic,BP_systolic,weight",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

        # Check that the response status code is 200 (OK)

        self.assertEqual(response.status_code, 200)

        # Check the Content-Type header for Excel file format

        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Check the Content-Disposition header for an attachment and filename

        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].endswith('.xlsx"'))
