import math
import json
import os
import datetime
from urllib import response
import pandas as pd
import numpy as np
import requests
import urllib.parse
from django.test import TestCase
from decimal import Decimal

from dataprocessing import lib_settings as settings
from dataprocessing import settings as original_settings
from data_app.models import *
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url


def correct_spot_data_type(data):

    date_columns = [
        "datetime_server_received",
        "date_time",
        "datetime_gateway_sent",
        "datetime_sensor",
    ]
    boolean_columns = [
        "is_genmode_from_dashboard",
        "data_is_sent_to_client",
        "is_calculated",
        "bool_force_onskin_chest",
        "bool_force_onskin_finger",
        "bool_impute_rr",
        "bool_impute_hr",
        "bool_impute_spo2",
    ]

    for key in data.keys():
        if isinstance(data[key], float) and math.isnan(data[key]):
            data[key] = None
        if data[key] in ["nan", np.nan, float("nan"), '"nan"']:
            data[key] = None
        if key in date_columns:
            data[key] = (
                datetime.datetime.strptime(data[key], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=datetime.timezone.utc
                )
                if data[key] != None
                else None
            )
        if key in boolean_columns:
            if data[key] != None:
                if data[key] == "true":
                    data[key] = True
                if data[key] == "false":
                    data[key] = False
    return data


def correct_health_input_data_type(data):

    date_columns = ["datetime", "datetime_received"]

    for key in data.keys():

        if isinstance(data[key], float) and math.isnan(data[key]):
            data[key] = None
        if data[key] in ["nan", np.nan, float("nan"), '"nan"']:
            data[key] = None
        if key in date_columns:
            data[key] = (
                datetime.datetime.strptime(data[key], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=datetime.timezone.utc
                )
                if data[key] != None
                else None
            )
    return data


spot_cache_fields = [
    "user_id",
    "datetime_server_received",
    "accepted_frame",
    "accepted_frame_ratio",
    "accepted_frame_tdomain",
    "activity_calories",
    "activity_percentage",
    "activity_step",
    "battery",
    "body_temperature",
    "bucket",
    "dashboard_mode",
    "data_col_name",
    "date_time",
    "datetime_gateway_sent",
    "datetime_sensor",
    "filename",
    "filepath",
    "hardware_mode",
    "hr",
    "is_genmode_from_dashboard",
    # "latest_aws_request_id_upload",
    "list_onskin_status_stdev_ratio",
    "list_output_kurtosis",
    "list_output_peakratio",
    "list_output_skewness",
    "list_output_stdev",
    "list_phase_diff",
    "list_sd_signal_w_sqa",
    "list_sensor_onskin_status_ratio",
    "median_list_output_kurtosis",
    "median_list_output_peakratio",
    "median_list_output_skewness",
    "median_list_output_stdev",
    "num_record_error",
    "num_temperature_out_of_range",
    "packet_number",
    "point_awake",
    "point_sleep",
    "record_collected_by_sensor",
    "record_received_by_gateway",
    "record_server_received",
    "rr",
    "rr_dc",
    "rr_fdomain",
    "rr_fdomain_w_good_sqa",
    "rr_hybrid",
    "rr_ibi",
    "rr_sqaml",
    "rr_td",
    "rr_tdomain",
    "sensor_id",
    "sensor_contact_status",
    "sensor_onskin_status",
    "sensor_onskin_status_stdev",
    "skin_temperature",
    "sleep_duration_seconds",
    "sqa",
    "sqa_index",
    "total_packet",
    "total_frame",
    "total_frame_tdomain",
    "val_sd_signal_wo_sqa",
    "val_sd_signal_w_sqa",
    "wavelets_transform",
    "wellness_calmness",
    "wellness_stress",
    "sensor_id",
    "spo2",
    "accepted_frame_spo2",
    "accepted_frame_spo2_ratio",
    "rr_sd",
    "hr_sd",
    "spo2_sd",
    "signal_quality_status",
    "display_label"
]


health_data_fields = [
    "user_id",
    "datetime",
    "datetime_received",
    "blood_sugar",
    "body_temp",
    "bp_dia",
    "bp_sys",
    "hr",
    "rr",
    "spo2",
    "weight",
]


def read_csv_data(filename):
    """read csv file from the test dataset path

    Args:
        filename (str): filename (.csv)

    Returns:
        DataFrame: dataframe of the csv data
    """
    try:
        return pd.read_csv(os.path.join(".", "tests", "unit", "test_data", filename))
    except:
        return pd.read_csv(os.path.join(".", "test_data", filename))


class QuerySpotTestCase(TestCase):

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

    def tearDown(self):
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()
        
    def read_dummy_valid_input_data(self):

        path = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
        )
        if not os.path.exists(path):
            path = os.path.join(
                original_settings.BASE_DIR,
                "data_app",
                "test_data",
                "test_data_main_query_spot",
            )
        df_sensor_data = pd.read_csv(
            os.path.join(path, "TestQuerySpot_valid_input_sensor_data.csv")
        )

        df_expected_historical_spot_data = pd.read_csv(
            os.path.join(
                path, "TestQuerySpot_valid_input_expected_historical_spot_data.csv"
            )
        )
        df_expected_latest_data = pd.read_csv(
            os.path.join(path, "TestQuerySpot_valid_input_expected_latest_data.csv")
        )

        for index, row in df_sensor_data.iterrows():
            data_dict = {}

            for key in row.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] =  'sensor'
            SpotCache.objects.create(**formatted_data)

        return (
            df_sensor_data,
            df_expected_historical_spot_data,
            df_expected_latest_data,
        )

    def read_dummy_input_data_for_latest_data_from_sensor_case(self):

        path = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
        )
        if not os.path.exists(path):
            path = os.path.join(
                original_settings.BASE_DIR,
                "data_app",
                "test_data",
                "test_data_main_query_spot",
            )
        df_sensor_data = pd.read_csv(
            os.path.join(
                path, "TestQuerySpot_valid_latest_data_from_sensor_sensor_data.csv"
            )
        )
        df_health_input_data = pd.read_csv(
            os.path.join(
                path,
                "TestQuerySpot_valid_latest_data_from_sensor_health_input_data.csv",
            )
        )
        df_expected_latest_data = pd.read_csv(
            os.path.join(
                path,
                "TestQuerySpot_valid_latest_data_from_sensor_expected_latest_data.csv",
            )
        )

        return (
            df_sensor_data,
            df_health_input_data,
            df_expected_latest_data,
        )

    def read_dummy_input_data_for_latest_data_from_health_input_case(self):

        path = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
        )
        if not os.path.exists(path):
            path = os.path.join(
                original_settings.BASE_DIR,
                "data_app",
                "test_data",
                "test_data_main_query_spot",
            )
        df_sensor_data = pd.read_csv(
            os.path.join(
                path,
                "TestQuerySpot_valid_latest_data_from_health_input_sensor_data.csv",
            )
        )
        df_health_input_data = pd.read_csv(
            os.path.join(
                path,
                "TestQuerySpot_valid_latest_data_from_health_input_health_input_data.csv",
            )
        )
        df_expected_latest_data = pd.read_csv(
            os.path.join(
                path,
                "TestQuerySpot_valid_latest_data_from_health_input_expected_latest_data.csv",
            )
        )

        return (
            df_sensor_data,
            df_health_input_data,
            df_expected_latest_data,
        )

    def __assert_output_historical(self, spot, expected):

        assert (spot["RR"] == expected["RR"]).all(), "wrong RR"
        assert (spot["HR"] == expected["HR"]).all(), "wrong HR"
        assert (spot["SpO2"] == expected["SpO2"]).all(), "wrong SpO2"
        assert (spot["RR_TD"] == expected["RR_TD"]).all(), "wrong RR_TD"
        assert (
            spot["body_temperature"] == expected["body_temperature"]
        ).all(), "wrong body_temperature"
        assert (
            spot["skin_temperature"] == expected["skin_temperature"]
        ).all(), "wrong skin_temperature"
        assert (spot["mode"] == expected["mode"]).all(), "wrong mode"
        assert (spot["battery"] == expected["battery"]).all(), "wrong battery"
        assert (
            spot["skin_contact"] == expected["skin_contact"]
        ).all(), "wrong skin_contact"
        assert (
            spot["signal_quality_status"] == expected["signal_quality_status"]
        ).all(), "wrong signal_quality_status"
        assert (spot["timestamp"] == expected["timestamp"]).all(), "wrong timestamp"

    def __assert_output_latest(self, latest, expected):

        assert (latest["HR"] == expected["HR"]).all(), "wrong latest HR"
        assert (latest["RR"] == expected["RR"]).all(), "wrong latest RR"
        assert (latest["SpO2"] == expected["SpO2"]).all(), "wrong latest SpO2"
        assert (
            latest["body_temperature"] == expected["body_temperature"]
        ).all(), "wrong latest body_temperature"
        assert (
            latest["last_connection_chest"] == expected["last_connection_chest"]
        ).all(), "wrong latest last_connection_chest"
        assert (
            latest["last_connection_finger"] == expected["last_connection_finger"]
        ).all(), "wrong latest last_connection_finger"
        assert (
            latest["is_manual_submission_rr"] == expected["is_manual_submission_rr"]
        ).all(), "wrong latest is_manual_submission_rr"
        assert (
            latest["is_manual_submission_hr"] == expected["is_manual_submission_hr"]
        ).all(), "wrong latest is_manual_submission_hr"
        assert (
            latest["is_manual_submission_spo2"] == expected["is_manual_submission_spo2"]
        ).all(), "wrong latest is_manual_submission_spo2"
        assert (
            latest["is_manual_submission_body_temp"]
            == expected["is_manual_submission_body_temp"]
        ).all(), "wrong latest is_manual_submission_body_temp"

        assert (
            latest["timestamp_rr"] == expected["timestamp_rr"]
        ).all(), "wrong latest timestamp_rr"
        assert (
            latest["timestamp_hr"] == expected["timestamp_hr"]
        ).all(), "wrong latest timestamp_hr"
        assert (
            latest["timestamp_spo2"] == expected["timestamp_spo2"]
        ).all(), "wrong latest timestamp_spo2"
        assert (
            latest["timestamp_body_temperature"]
            == expected["timestamp_body_temperature"]
        ).all(), "wrong latest timestamp_body_temperature"
        assert (
            latest["timestamp_bp_sys"] == expected["timestamp_bp_sys"]
        ).all(), "wrong latest timestamp_bp_sys"
        assert (
            latest["timestamp_bp_dia"] == expected["timestamp_bp_dia"]
        ).all(), "wrong latest timestamp_bp_dia"

        # check that there is no np.int8, np.int16, np.int32, np.int64

        for key in latest.keys():
            assert not isinstance(
                latest[key], (np.int8, np.int16, np.int32, np.int64)
            ), f"latest spot {key} is not int"

    def setUp(self):

        self.url = "/api/v1/query/spot"
        self.token = self._get_auth_token()

    def test_case_1(self):
        """test output for signal_quality is -1 if input contains null signal_quality_status"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_invalid.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)
            formatted_data = correct_spot_data_type(input_data)
            formatted_data['source'] = "sensor"
            print('formatted_data',formatted_data)
            a = SpotCache.objects.create(**formatted_data)
            print("created spot = ",a)

            params = {
                "id": "-1",
                "date_time": "2023-05-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            ).json()

            data = response["response"]
            assert data["history"]["signal_quality_status"][0] == -1

    def test_case_2(self):
        """test case for valid signal quality input which should give corresponding output"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_valid.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)
            data_dict = {}
            for key in input_data.keys():
                if key in spot_cache_fields:
                    data_dict[key] = input_data[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)

            params = {
                "id": "-1",
                "date_time": "2023-06-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            ).json()

            data = response["response"]
            assert data["history"]["signal_quality_status"][0] == "Good"

    def test_case_3(self):
        """test case for recordServerReceived for less than 1000 input which should give corresponding output of -1"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_1000_records.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)


            data_dict = {}
            for key in input_data.keys():
                if key in spot_cache_fields:
                    data_dict[key] = input_data[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)

            params = {
                "id": "-1",
                "date_time": "2023-06-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            ).json()

            data = response["response"]
            assert data["history"]["skin_contact"][0] == -1

    def test_case_4(self):
        """
        chest sensor_onskin_status == -1
        chest sensor_onskin_status == 0
        chest sensor_onskin_status == 1
        finger sensor_onskin_status == -1
        finger sensor_onskin_status == 0
        finger sensor_onskin_status == 1
        """

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_004.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            # convert df to dict

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            x = SpotCache.objects.create(**formatted_data)
            print(x.date_time,x.hr,x.spo2)
        params = {
            "id": "-1",
            "date_time": "2023-05-09T13:01:34",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()
        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_sensor_onskin_status"
            ]
            expected_spot_signal_quality_status = str(
                current_row["expected_signal_quality_status"]
            )
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_rr = current_row["expected_rr"]
            expected_hr = current_row["expected_hr"]
            expected_spo2 = current_row["expected_spo2"]
            expected_rrtd = current_row["expected_rrtd"]

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_rr = json_response["RR"][index_response]
            current_hr = json_response["HR"][index_response]
            current_spo2 = json_response["SpO2"][index_response]
            current_rrtd = json_response["RR_TD"][index_response]

            # assert

            assert current_signal_quality_status == expected_spot_signal_quality_status
            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_datetime == expected_spot_datetime
            assert current_rr == expected_rr
            assert current_hr == expected_hr
            assert current_spo2 == expected_spo2
            assert current_rrtd == expected_rrtd

    def test_case_5(self):
        """
        issue: https://github.com/Respiree/rpm_data_processing_backend/issues/257
        verify that there are RR_sd, HR_sd, and SpO2_sd
        """

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_005.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-1",
            "date_time": "2023-05-09T13:01:34",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_sensor_onskin_status"
            ]
            expected_spot_signal_quality_status = str(
                current_row["expected_signal_quality_status"]
            )
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_spot_RR = current_row["expected_RR"]
            expected_spot_RR_sd = current_row["expected_RR_sd"]
            expected_spot_HR = current_row["expected_HR"]
            expected_spot_HR_sd = current_row["expected_HR_sd"]
            expected_spot_SpO2 = current_row["expected_SpO2"]
            expected_spot_SpO2_sd = current_row["expected_SpO2_sd"]

            # extarct computed metrics

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_RR = json_response["RR"][index_response]
            current_RR_sd = json_response["RR_sd"][index_response]
            current_HR = json_response["HR"][index_response]
            current_HR_sd = json_response["HR_sd"][index_response]
            current_SpO2 = json_response["SpO2"][index_response]
            current_SpO2_sd = json_response["SpO2_sd"][index_response]

            # assert

            assert current_signal_quality_status == expected_spot_signal_quality_status
            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_datetime == expected_spot_datetime
            assert current_RR == expected_spot_RR
            assert current_RR_sd == expected_spot_RR_sd
            assert current_HR == expected_spot_HR
            assert current_HR_sd == expected_spot_HR_sd
            assert current_SpO2 == expected_spot_SpO2
            assert current_SpO2_sd == expected_spot_SpO2_sd

    def test_case_6(self):
        """
        reference: https://github.com/Respiree/rpm_data_processing_backend/issues/190

        Summary
        - when sensor staus is not 'Good', spot table will not display any data (except RR_TD)
        """

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_006.csv",
        )

        filepath = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_006",
        )

        # read reference

        df = read_csv_data(csv_fname)

        for fname in df.filename:
            # load data

            temp_file = os.path.join(filepath, fname)
            with open(temp_file, "r") as f:
                data = json.load(f)

                data_dict = {}
                for key in data.keys():
                    if key in spot_cache_fields:
                        data_dict[key] = data[key]
                formatted_data = correct_spot_data_type(data_dict)
                formatted_data['source'] = "sensor"
                SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-1",
            "date_time": "2023-06-09T03:50:27",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df.iloc[i]

            current_filename = current_row["filename"]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_spot_skin_contact_status"
            ]
            expected_spot_signal_quality_status = current_row[
                "expected_spot_signal_quality_status"
            ]
            expected_spot_rr = current_row["expected_spot_rr"]

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_rr = json_response["RR"][index_response]

            # assert

            assert current_signal_quality_status == expected_spot_signal_quality_status
            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_rr == expected_spot_rr

    def test_case_7(self):
        """
        reference: https://github.com/Respiree/rpm_data_processing_backend/issues/284
        chest data length is less than 1000, sensor_onskin_status must be -1
        """
        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_007.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case["rr"].fillna(str("nan"), inplace=True)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            # convert df to dict

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-1",
            "date_time": "2023-09-11T10:07:35",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = str(
                current_row["expected_sensor_onskin_status"]
            )
            expected_spot_signal_quality_status = str(
                current_row["expected_signal_quality_status"]
            )
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_spot_RR = current_row["expected_RR"]
            expected_spot_RR_sd = current_row["expected_RR_sd"]
            expected_spot_HR = current_row["expected_HR"]
            expected_spot_HR_sd = current_row["expected_HR_sd"]
            expected_spot_SpO2 = current_row["expected_SpO2"]
            expected_spot_SpO2_sd = current_row["expected_SpO2_sd"]

            # extarct computed metrics

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_RR = json_response["RR"][index_response]
            current_RR_sd = json_response["RR_sd"][index_response]
            current_HR = json_response["HR"][index_response]
            current_HR_sd = json_response["HR_sd"][index_response]
            current_SpO2 = json_response["SpO2"][index_response]
            current_SpO2_sd = json_response["SpO2_sd"][index_response]

            # assert

            assert current_signal_quality_status == expected_spot_signal_quality_status
            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_datetime == expected_spot_datetime
            assert current_RR == expected_spot_RR
            assert current_RR_sd == expected_spot_RR_sd
            assert current_HR == expected_spot_HR
            assert current_HR_sd == expected_spot_HR_sd
            assert current_SpO2 == expected_spot_SpO2
            assert current_SpO2_sd == expected_spot_SpO2_sd

    def test_case_8(self):

        # github issue #325 when finger data display_label is available (1,0)

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_008.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            # convert df to dict

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-1",
            "date_time": "2023-09-11T10:07:35",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_sensor_onskin_status"
            ]
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_hr = current_row["expected_hr"]
            expected_spo2 = current_row["expected_spo2"]

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_rr = json_response["RR"][index_response]
            current_hr = json_response["HR"][index_response]
            current_spo2 = json_response["SpO2"][index_response]

            # assert

            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_datetime == expected_spot_datetime
            assert current_hr == expected_hr
            assert current_spo2 == expected_spo2

    def test_case_9(self):

        # github issue #325 when finger data display_label is not available

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_case_009.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            # convert df to dict

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-1",
            "date_time": "2023-05-09T13:01:34",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()
        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_sensor_onskin_status"
            ]
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_hr = current_row["expected_hr"]
            expected_spo2 = current_row["expected_spo2"]

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_rr = json_response["RR"][index_response]
            current_hr = json_response["HR"][index_response]
            current_spo2 = json_response["SpO2"][index_response]

            # assert

            assert current_skin_contact == expected_spot_skin_contact_status
            assert current_datetime == expected_spot_datetime
            assert current_hr == expected_hr
            assert current_spo2 == expected_spo2

    def test_case_10(self):
        # check whether last_connection_chest or last_connection_finger is available in the spot response

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_valid_chest.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)

            data_dict = {}
            for key in input_data.keys():
                if key in spot_cache_fields:
                    data_dict[key] = input_data[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)

            params = {
                "id": "-1",
                "date_time": "2024-06-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            ).json()

            data = response["response"]
            assert data["latest"]["last_connection_chest"] is not None
        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_valid_finger.json",
        )

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)

            data_dict = {}
            for key in input_data.keys():
                if key in spot_cache_fields:
                    data_dict[key] = input_data[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)

            params = {
                "id": "-1",
                "date_time": "2024-06-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            ).json()
            data = response["response"]
            assert data["latest"]["last_connection_finger"] is not None

    def test_query_spot_valid(self):

        _, df_expected_historical_spot_data, df_expected_latest_data = (
            self.read_dummy_valid_input_data()
        )

        params = {
            "id": "-1",
            "date_time": "2001-05-08T13:01:42",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        data = response["response"]
        # expect history and latest keys

        assert {"latest", "history"}.issubset(
            data.keys()
        ), "'latest' or 'history' is not in the response"

        # Sort by 'listtime' in descending order

        df_expected_historical_spot_data = df_expected_historical_spot_data.sort_values(
            by="timestamp", ascending=False
        )
        self.__assert_output_historical(
            data["history"], df_expected_historical_spot_data
        )
        self.__assert_output_latest(data["latest"], df_expected_latest_data)

    def test_query_spot_invalid_wrong_timestamp_format(self):

        params = {
            "id": "-1",
            "date_time": "2023-03-09 03:05:59",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_time", response.json(), "Error in date_time")

    def test_query_spot_invalid_missing_parameters(self):

        params = {
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_time", response.json(), "missing  date_time")
        # self.assertIn('id',response.json(), "missing id")

    def test_query_spot_chest_sqa_and_skin_contact(self):
        """
        - RR = 10, SQA = Good, SC = 1
        - RR = 11, SQA = Good, SC = 0
        - RR = 12, SQA = Good, SC = -1
        - RR = 13, SQA = Moderate, SC = 1
        - RR = 14, SQA = Moderate, SC = 0
        - RR = 15, SQA = Moderate, SC = -1
        - RR = 16, SQA = Poor, SC = 1
        - RR = 17, SQA = Poor, SC = 0
        - RR = 18, SQA = Poor, SC = -1
        - RR = 19, SQA = Motion, SC = 1
        - RR = 20, SQA = Motion, SC = 0
        - RR = 21, SQA = Motion, SC = -1
        """

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "TestQuerySpotChest.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for i in range(1, len(df_test_case) + 1):
            current_row = df_test_case.loc[df_test_case["sample_number"] == i]

            # convert df to dict

            row_dict = current_row.to_dict("records")[0]

            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-21",
            "date_time": "2000-05-08T13:01:34",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()
        json_response = response["response"]["history"]

        # assert response

        for i in range(len(json_response["skin_contact"])):

            index_response = len(json_response["skin_contact"]) - i - 1  # reverse

            current_row = df_test_case.iloc[i]

            # extract expected outcome

            expected_spot_skin_contact_status = current_row[
                "expected_sensor_onskin_status"
            ]
            expected_spot_signal_quality_status = str(
                current_row["expected_signal_quality_status"]
            )
            expected_spot_datetime = current_row["expected_dateTime"]
            expected_rr = current_row["expected_rr"]
            expected_rrtd = current_row["expected_rrtd"]

            current_signal_quality_status = str(
                json_response["signal_quality_status"][index_response]
            )
            current_skin_contact = str(json_response["skin_contact"][index_response])
            current_datetime = json_response["timestamp"][index_response]
            current_rr = json_response["RR"][index_response]
            current_rrtd = json_response["RR_TD"][index_response]

            # assert

            assert (
                current_signal_quality_status == expected_spot_signal_quality_status
            ), f"mismatched signal quality status. result is {current_signal_quality_status} but expect {expected_spot_signal_quality_status}"
            assert (
                current_skin_contact == expected_spot_skin_contact_status
            ), f"mismatched skin contact. result is {current_skin_contact} but expect {expected_spot_skin_contact_status}"
            assert (
                current_datetime == expected_spot_datetime
            ), f"mismatched datetime. result is {current_datetime} but expect {expected_spot_datetime}"
            assert (
                current_rr == expected_rr
            ), f"mismatched RR. result is {current_rr} but expect {expected_rr}"
            assert (
                current_rrtd == expected_rrtd
            ), f"mismatched RR TD. result is {current_rrtd} but expect {expected_rrtd}"

    def test_not_all_health_input_available(self):

        csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "TestQuerySpot_test_not_all_health_input_available_health_input_data.csv",
        )

        output_csv_fname = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "TestQuerySpot_test_not_all_health_input_available_expected_latest_data.csv",
        )

        df_test_case = read_csv_data(csv_fname)
        df_expected_latest_data = read_csv_data(output_csv_fname)
        df_test_case = df_test_case.where(pd.notna(df_test_case), None)

        for index, row in df_test_case.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in health_data_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_health_input_data_type(data_dict)
            HealthData.objects.create(**formatted_data)
        params = {
            "id": "-21",
            "date_time": "2000-09-17T07:50:36",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]

        # expect history and latest keys

        assert {"latest", "history"}.issubset(
            json_response.keys()
        ), "'latest' or 'history' is not in the response"
        self.__assert_output_latest(json_response["latest"], df_expected_latest_data)

    def test_query_spot_valid_with_health_input_latest_data_from_sensor(self):

        df_sensor_data, df_health_input_data, df_expected_latest_data = (
            self.read_dummy_input_data_for_latest_data_from_sensor_case()
        )

        for index, row in df_health_input_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in health_data_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_health_input_data_type(data_dict)
            HealthData.objects.create(**formatted_data)
        for index, row in df_sensor_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            DataProcessing.objects.create(**formatted_data)

        for index, row in df_sensor_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-2",
            "date_time": "2001-06-08T13:01:36",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        json_response = response["response"]

        # expect history and latest keys

        assert {"latest", "history"}.issubset(
            json_response.keys()
        ), "'latest' or 'history' is not in the response"
        self.__assert_output_latest(json_response["latest"], df_expected_latest_data)

    def test_query_spot_valid_with_health_input_latest_data_from_health_input(self):

        df_sensor_data, df_health_input_data, df_expected_latest_data = (
            self.read_dummy_input_data_for_latest_data_from_health_input_case()
        )

        for index, row in df_health_input_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in health_data_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_health_input_data_type(data_dict)
            HealthData.objects.create(**formatted_data)

        for index, row in df_sensor_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            # formatted_data['source'] = "sensor"
            DataProcessing.objects.create(**formatted_data)


        for index, row in df_sensor_data.iterrows():
            row_dict = row.to_dict()
            data_dict = {}
            for key in row_dict.keys():
                if key in spot_cache_fields:
                    data_dict[key] = row_dict[key]
            formatted_data = correct_spot_data_type(data_dict)
            formatted_data['source'] = "sensor"
            SpotCache.objects.create(**formatted_data)
        params = {
            "id": "-3",
            "date_time": "2001-07-08T13:01:35",
            "utc_offset": "+08:00",
        }

        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()
        json_response = response["response"]

        # expect history and latest keys

        assert {"latest", "history"}.issubset(
            json_response.keys()
        ), "'latest' or 'history' is not in the response"
        self.__assert_output_latest(json_response["latest"], df_expected_latest_data)


    def test_process_id_gateway_and_sensor_status(self):

        ''' test process_id_gateway_and_sensor_status '''
        from data_app.lib_query import process_id_gateway_and_sensor_status

        # response from endpoint https://devenv1.respiree.com/api/data-server/patient-devices

        input_data = {
            "sensors": [
                {
                    "id": "c5358d6e-51e8-45e0-92d9-6a65e3e006d4",
                    "name": "1117D",
                    "macId": "80e1261d4cf3",
                    "fwVersion": None,
                    "sensorType": "HR",
                    "pollingTimeInSeconds": 125,
                    "battery": None,
                    "totalCycleTime": 900,
                    "chestRecords": 2000,
                    "fingerRecords": 3000,
                    "maxDatasetStored": 0,
                    "maxDatasetFlushed": 0,
                    "isAvailable": False,
                    "isActive": True,
                    "lastConnectionTime": '2025-04-09T06:04:22.000Z',
                    "registeredTime": "2025-03-25T03:00:23.000Z",
                    "isRegistered": True,
                    "lastProcessedState": "pair",
                    "processedStateStatus": "success",
                    "sensorState": "assign",
                    "sensorStateStatus": "success",
                    "connectionMode": "gateway_mode",
                    "isPaired": True,
                    "unassignRequest": False,
                    "unassignRequestByUserId": None,
                    "patientDeviceRegistration": True,
                    "createdAt": "2025-03-25T02:42:13.049Z",
                    "createdBy": None,
                    "updatedAt": "2025-03-25T03:00:23.162Z",
                    "updatedBy": None,
                    "deletedAt": None,
                    "deletedBy": None,
                    "gatewayId": "e4ca5fd7-8ab9-4fbd-ad54-78d6b59fbde2",
                    "patientId": -1,
                    "organizationId": "d5e822dc-4844-43bc-8f45-f106953976d3",
                    "gateway": {
                        "id": "e4ca5fd7-8ab9-4fbd-ad54-78d6b59fbde2",
                        "name": "AMG500_7FBE",
                        "macId": "c049eff57fbe",
                        "fwVersion": "3.1.0rc5.2a",
                        "isAvailable": False,
                        "isActive": True,
                        "isOnline": False,
                        "lastConnectionTime": '2025-04-09T06:04:22.000Z',
                        "registeredTime": "2025-03-24T08:45:04.000Z",
                        "isRegistered": True,
                        "unassignRequest": False,
                        "unassignRequestByUserId": None,
                        "type": "gateway",
                        "status": None,
                        "location": None,
                        "createdAt": "2024-12-17T07:58:03.606Z",
                        "createdBy": None,
                        "updatedAt": "2025-03-25T04:30:07.138Z",
                        "updatedBy": None,
                        "deletedAt": None,
                        "deletedBy": None,
                        "patientId": -1,
                        "organizationId": "d5e822dc-4844-43bc-8f45-f106953976d3",
                        "serverId": None,
                        "inProcessingState": False,
                    },
                }
            ],
            "gateways": [
                {
                    "id": "e4ca5fd7-8ab9-4fbd-ad54-78d6b59fbde2",
                    "name": "AMG500_7FBE",
                    "macId": "c049eff57fbe",
                    "fwVersion": "3.1.0rc5.2a",
                    "isAvailable": False,
                    "isActive": True,
                    "isOnline": False,
                    "lastConnectionTime": "2025-03-25T04:30:07.000Z",
                    "registeredTime": "2025-03-24T08:45:04.000Z",
                    "isRegistered": True,
                    "unassignRequest": False,
                    "unassignRequestByUserId": None,
                    "type": "gateway",
                    "status": None,
                    "location": None,
                    "createdAt": "2024-12-17T07:58:03.606Z",
                    "createdBy": None,
                    "updatedAt": "2025-03-25T04:30:07.138Z",
                    "updatedBy": None,
                    "deletedAt": None,
                    "deletedBy": None,
                    "patientId": -1,
                    "organizationId": "d5e822dc-4844-43bc-8f45-f106953976d3",
                    "serverId": None,
                    "inProcessingState": False,
                    "sensors": [
                        {
                            "id": "c5358d6e-51e8-45e0-92d9-6a65e3e006d4",
                            "name": "1117D",
                            "macId": "80e1261d4cf3",
                            "fwVersion": None,
                            "sensorType": "HR",
                            "pollingTimeInSeconds": 125,
                            "battery": None,
                            "totalCycleTime": 900,
                            "chestRecords": 2000,
                            "fingerRecords": 3000,
                            "maxDatasetStored": 0,
                            "maxDatasetFlushed": 0,
                            "isAvailable": False,
                            "isActive": True,
                            "lastConnectionTime": '2025-04-09T06:04:22.000Z',
                            "registeredTime": "2025-03-25T03:00:23.000Z",
                            "isRegistered": True,
                            "lastProcessedState": "pair",
                            "processedStateStatus": "success",
                            "sensorState": "assign",
                            "sensorStateStatus": "success",
                            "connectionMode": "gateway_mode",
                            "isPaired": True,
                            "unassignRequest": False,
                            "unassignRequestByUserId": None,
                            "patientDeviceRegistration": True,
                            "createdAt": "2025-03-25T02:42:13.049Z",
                            "createdBy": None,
                            "updatedAt": "2025-03-25T03:00:23.162Z",
                            "updatedBy": None,
                            "deletedAt": None,
                            "deletedBy": None,
                            "gatewayId": "e4ca5fd7-8ab9-4fbd-ad54-78d6b59fbde2",
                            "patientId": -1,
                            "organizationId": "d5e822dc-4844-43bc-8f45-f106953976d3",
                        }
                    ],
                }
            ],
        }

        gateway_status, last_gateway_connection, sensor_status, last_sensor_connection, two_sensor_mode = process_id_gateway_and_sensor_status(input_data,
            settings.check_gateway_if_online_within,
            settings.check_sensor_if_online_within)

        assert ( gateway_status == 0), "Mismatch in gateway_status"
        assert ( last_gateway_connection == '2025-03-25T04:30:07'), "Mismatch in last_gateway_connection"
        assert ( sensor_status == {'HR': 0}), "Mismatch in sensor_status"
        assert ( two_sensor_mode == True), "Mismatch in two_sensor_mode"




class TestLatestBPReadingsInSpot(TestCase):
    """test latest bp values of spot api"""

    def setUp(self):
        self.url = "/api/v1/query/spot"
        self.token = self._get_auth_token()

    def _get_auth_token(self):
        payload = json.dumps(auth_login)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{backend_url}/api/auth/login", data=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json().get('access_token')
        else:
            self.fail(f"Failed to retrieve token: {response.status_code} - {response.text}")

    def test_latest_bp_with_bp_device_data_only(self):
        """test latest bp values of spot api  if only data from bp device is present """

        user_id = '-14'

        bp_device_data = {
         "user_id": user_id,
         "datetime": "2025-06-30 09:41:59",
         "bp_dia": 30,
         "bp_sys": 40,
         "source": 'bp-device'
        }
        bp_obj = OtherDeviceReading.objects.create(**bp_device_data)


        params = {
            "id": user_id,
            "date_time": "2001-06-08T13:01:36",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        bp_obj.delete()

        response = response['response']

        assert "latest" in response, "latest not found in response"
        assert response["latest"]['BP_Sys'] == 40, "incorrect BP_Sys"
        assert response["latest"]['BP_Dia'] == 30, "incorrect BP_Dia"
        assert response["latest"]['timestamp_bp_sys'] == '2025-06-30 09:41:59', "incorrect timestamp_bp_sys"
        assert response["latest"]['timestamp_bp_dia'] == '2025-06-30 09:41:59', "incorrect timestamp_bp_dia"
        assert response["latest"]['is_manual_submission_bp_sys'] == 0, "incorrect is_manual_submission_bp_sys"
        assert response["latest"]['is_manual_submission_bp_dia'] == 0, "incorrect is_manual_submission_bp_dia"

    def test_latest_bp_with_mhi_data_only(self):
        """test latest bp values of spot api  if only data from mhi is present """

        user_id = '-14'

        mhi_data = {
         "user_id": user_id,
         "datetime": "2025-08-07 10:07:00",
         "bp_sys": 80,
         "bp_dia": 140,
         "datetime_received": "2025-08-07 11:27:47"
        }
        mhi_obj = HealthData.objects.create(**mhi_data)

        params = {
            "id": user_id,
            "date_time": "2001-06-08T13:01:36",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        mhi_obj.delete()

        response = response['response']

        assert "latest" in response, "latest not found in response"
        assert response["latest"]['BP_Sys'] == 80, "incorrect BP_Sys"
        assert response["latest"]['BP_Dia'] == 140, "incorrect BP_Dia"
        assert response["latest"]['timestamp_bp_sys'] == '2025-08-07 10:07:00', "incorrect timestamp_bp_sys"
        assert response["latest"]['timestamp_bp_dia'] == '2025-08-07 10:07:00', "incorrect timestamp_bp_dia"
        assert response["latest"]['is_manual_submission_bp_sys'] == 1, "incorrect is_manual_submission_bp_sys"
        assert response["latest"]['is_manual_submission_bp_dia'] == 1, "incorrect is_manual_submission_bp_dia"

    def test_latest_bp_with_mhi_and_bp_device_data(self):
        """test latest bp values of spot api  if both data from mhi & bp device are present """

        user_id = '-145'

        bp_device_data = {
         "user_id": user_id,
         "datetime": "2025-06-30 09:41:59",
         "bp_dia": 30,
         "bp_sys": 40,
         "source": 'bp-device'
        }
        bp_obj = OtherDeviceReading.objects.create(**bp_device_data)

        mhi_data = {
         "user_id": user_id,
         "datetime": "2025-08-07 10:07:00",
         "bp_sys": 140,
         "bp_dia": 80,
         "datetime_received": "2025-08-07 11:27:47"
        }
        mhi_obj = HealthData.objects.create(**mhi_data)




        params = {
            "id": user_id,
            "date_time": "2001-06-08T13:01:36",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        bp_obj.delete()
        mhi_obj.delete()
        response = response['response']
        print(response["latest"])

        assert "latest" in response, "latest not found in response"
        assert response["latest"]['BP_Sys'] == 140, "incorrect BP_Sys"
        assert response["latest"]['BP_Dia'] == 80, "incorrect BP_Dia"
        assert response["latest"]['timestamp_bp_sys'] == '2025-08-07 10:07:00', "incorrect timestamp_bp_sys"
        assert response["latest"]['timestamp_bp_dia'] == '2025-08-07 10:07:00', "incorrect timestamp_bp_dia"
        assert response["latest"]['is_manual_submission_bp_sys'] == 1, "incorrect is_manual_submission_bp_sys"
        assert response["latest"]['is_manual_submission_bp_dia'] == 1, "incorrect is_manual_submission_bp_dia"

    def test_latest_bp_with_no_mhi_and_bp_device_data(self):
        """test latest bp values of spot api  if no data from mhi & bp device are present """
        user_id = '-14'
        params = {
            "id": user_id,
            "date_time": "2023-05-09T03:50:27",
        }
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        response = self.client.get(
            url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
        ).json()

        response = response['response']

        assert "latest" in response, "latest not found in response"
        assert response["latest"]['BP_Sys'] == -1, "incorrect BP_Sys"
        assert response["latest"]['BP_Dia'] == -1, "incorrect BP_Dia"
        assert response["latest"]['timestamp_bp_sys'] == -1, "incorrect timestamp_bp_sys"
        assert response["latest"]['timestamp_bp_dia'] == -1, "incorrect timestamp_bp_dia"
        assert response["latest"]['is_manual_submission_bp_sys'] == 0, "incorrect is_manual_submission_bp_sys"
        assert response["latest"]['is_manual_submission_bp_dia'] == 0, "incorrect is_manual_submission_bp_dia"

class LastConnectionTestCase(TestCase):

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

        self.url = "/api/v1/query/spot"
        self.token = self._get_auth_token()

    def test_case_1(self):
        """test last_connection"""

        filepath_input = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_main_query_spot",
            "test_data_last_connection.json",
        )

        data = {
            "user_id": "-12",
            "datetime": "2025-08-09T04:41:53",
            "datetime_received": "2025-08-09T04:41:53",
            "bp_dia": 80,
            "bp_sys": 120,
            "weight": 85,
            "blood_sugar": 5.5,
            "rr": 30,
            "hr": 115,
            "spo2": 98,
            "body_temp": 35.6,
        }

        HealthData.objects.create(**data)

        with open(filepath_input, "r") as f1:
            input_data = json.load(f1)
            formatted_data = correct_spot_data_type(input_data)
            SpotCache.objects.create(**formatted_data)

            params = {
                "id": "-1",
                "date_time": "2023-05-09T03:50:27",
                "utc_offset": "+08:00",
            }

            url = f"{self.url}?{urllib.parse.urlencode(params)}"
            response = self.client.get(
                url, params=params, HTTP_AUTHORIZATION=f"Bearer {self.token}"
            )

            self.assertEqual(response.status_code, 200)
