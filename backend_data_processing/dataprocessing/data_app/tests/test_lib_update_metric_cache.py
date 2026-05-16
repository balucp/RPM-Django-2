import math
import json
import os
import datetime
import pandas as pd
import numpy as np
import requests
import urllib.parse
from django.test import TestCase
from decimal import Decimal

from dataprocessing import lib_settings as settings
from dataprocessing import settings as original_settings
from data_app.models import DataProcessing, SpotCache, HealthData, MetricMinutesCache
from dataprocessing.secrets import auth_login
from dataprocessing.lib_settings import backend_url
from data_app import lib_common as common
from data_app import lib_update_metric_cache
from django.db.models import Q


def read_csv_data(filename):
    return pd.read_csv(filename)


def query_table(user_id, date_time=None):
    if date_time == None:
        queryResponse = MetricMinutesCache.objects.filter(user_id=user_id)
    else:
        queryResponse = MetricMinutesCache.objects.filter(
            user_id=user_id, date_time=date_time
        )
    item = queryResponse[0]
    return item


def function_read_and_upload_data_metric_minutes_cache(sample_number, filename):
    # extract sample data

    test_data = read_csv_data(filename)

    data = test_data.loc[test_data["sample_number"] == sample_number]

    # convert df to dict

    dict_data = data.to_dict("records")[0]

    date_time_keys = ['date_time', 'datetime_gateway_sent', 'datetime_sensor', 'datetime_server_received']

    for key in date_time_keys:
        if key in dict_data:
            dict_data[key] = datetime.datetime.strptime(dict_data[key], "%Y-%m-%d %H:%M:%S")

    # add record to cache table

    res = "minutes"
    is_trigger_cache = lib_update_metric_cache.update(dict_data, res)

    # read record from table

    if is_trigger_cache:
        item = query_table(dict_data["user_id"])
        # item = query_dynamodb( dict_data['userId'])
    else:
        item = []
    return item


class UpdateTestCase(TestCase):

    def test_libUpdateMetricCache_case1(self):
        # good chest data

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_001.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(1, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-01-11 07:45:02"
        ), "incorrect dateTime"
        assert item.rr == 18, "incorrect RR"

    def test_libUpdateMetricCache_case2(self):
        # bad chest data

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_001.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(2, filename)
        print('ITEM',vars(item))
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-01-11 08:23:48"
        ), "incorrect dateTime"
        assert item.skin_contact_chest == None, "Skin_contact_chest should not be present in bad data"

    def test_libUpdateMetricCache_case3(self):
        # good finger data

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_002.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(1, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:30:15"
        ), "incorrect dateTime"

    def test_libUpdateMetricCache_case4(self):
        # good finger data

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_002.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(2, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:31:40"
        ), "incorrect dateTime"

    def test_libUpdateMetricCache_case5(self):  # bad finger data
        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_002.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(3, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:33:02"
        ), "incorrect dateTime"

    def test_libUpdateMetricCache_case6(self):
        # bad finger data

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_002.csv",
        )
        item = function_read_and_upload_data_metric_minutes_cache(4, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:34:26"
        ), "incorrect dateTime"

    def test_libUpdateMetricCache_case7(self):
        """
        https://github.com/Respiree/Respiree_data-processing-AWS-backend/issues/94

        1. upload good chest data
        2. upload bad chest data
        """

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_003.csv",
        )

        # good chest data

        item_1 = function_read_and_upload_data_metric_minutes_cache(3, filename)
        assert (
            item_1.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-22 15:44:00"
        ), "incorrect dateTime"
        assert item_1.rr == 13, "incorrect RR"

        # bad chest data

        item_2 = function_read_and_upload_data_metric_minutes_cache(2, filename)
        assert (
            item_2.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-22 15:45:00"
        ), "incorrect dateTime"
        assert item_2.rr == 31, "incorrect RR"

        # bad chest data

        item_3 = function_read_and_upload_data_metric_minutes_cache(1, filename)
        assert (
            item_3.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-22 15:47:00"
        ), "incorrect dateTime"
        assert item_3.rr == 3, "incorrect RR"

    def test_libUpdateMetricCache_case8(self):
        """
        https://github.com/Respiree/Respiree_data-processing-AWS-backend/issues/97

        1. upload good finger data
        2. upload good finger data
        3. upload bad finger data
        4. upload bad finger data
        """

        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_002.csv",
        )
        # good finger data

        item_1 = function_read_and_upload_data_metric_minutes_cache(1, filename)
        assert (
            item_1.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:30:15"
        ), "incorrect dateTime"
        assert item_1.hr == 85, "incorrect HR"
        assert item_1.spo2 == 94, "incorrect SpO2"

        # good finger data

        item_2 = function_read_and_upload_data_metric_minutes_cache(2, filename)
        assert (
            item_2.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:31:40"
        ), "incorrect dateTime"
        assert item_2.hr == 82, "incorrect HR"
        assert item_2.spo2 == 95, "incorrect SpO2"

        # bad finger data

        item_3 = function_read_and_upload_data_metric_minutes_cache(3, filename)
        assert (
            item_3.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:33:02"
        ), "incorrect dateTime"
        assert item_3.hr == 82, "incorrect HR"
        assert item_3.spo2 == 90, "incorrect SpO2"

        # bad finger data

        item_4 = function_read_and_upload_data_metric_minutes_cache(4, filename)
        assert (
            item_4.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-25 06:34:26"
        ), "incorrect dateTime"
        print('hr = ',item_4.hr)
        print('spo2 = ',item_4.spo2)
        assert item_4.hr == 82, "incorrect HR"
        assert item_4.spo2 == 92, "incorrect SpO2"

    def test_libUpdateMetricCache_case9(self):
        """
        https://github.com/Respiree/Respiree_data-processing-AWS-backend/issues/100
        """
        filename = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            # "unit",
            "test_data",
            "test_data_004.csv",
        )
        # good chest data

        item = function_read_and_upload_data_metric_minutes_cache(1, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-24 11:18:37"
        ), "incorrect dateTime"
        assert item.rr == 22, "incorrect RR"

        # good chest data

        item = function_read_and_upload_data_metric_minutes_cache(2, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-24 11:26:21"
        ), "incorrect dateTime"
        assert item.rr == 18, "incorrect RR"

        # good chest data

        item = function_read_and_upload_data_metric_minutes_cache(3, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-24 11:27:35"
        ), "incorrect dateTime"
        assert item.rr == 22, "incorrect RR"

        # good chest data

        item = function_read_and_upload_data_metric_minutes_cache(4, filename)
        assert (
            item.date_time.strftime("%Y-%m-%d %H:%M:%S") == "2023-02-24 11:28:48"
        ), "incorrect dateTime"
        assert item.rr == 21, "incorrect RR"
