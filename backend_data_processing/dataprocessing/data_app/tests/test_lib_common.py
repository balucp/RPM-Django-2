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
from data_app import lib_common as common


class LibCommonTestCase(TestCase):


    def test_case_4(self):
        """
        tests for different scenarios of skin contact with 0 as off-skin, 1 as on-skin, -1 as invalid
        """

        filepath = os.path.join(
            original_settings.BASE_DIR,
            "data_app",
            "tests",
            "test_data",
            "test_data_lib_common",
            "test_case_5.json",
        )

        with open(filepath, "r") as f:
            data = json.load(f)
        # TEST CASE FOR ALL INVALID SKIN_CONTACT

        on_skin = common.check_skin_status_sequence(data["ALL_INV"], 4)
        assert on_skin == -1

        # TEST CASE FOR ALL OFF SKIN_CONTACT

        on_skin = common.check_skin_status_sequence(data["ALL_OFF"], 4)
        assert on_skin == 0

        # TEST CASE FOR ALL OFF SKIN_CONTACT

        on_skin = common.check_skin_status_sequence(data["ALL_ON"], 4)
        assert on_skin == 1

        # TEST CASE FOR EARLIEST THREE SKIN CONTACT AS OFF AND LAST IS ON

        on_skin = common.check_skin_status_sequence(data["FIRST_THREE_OFF_LAST_ON"], 4)
        assert on_skin == 0

        # TEST CASE FOR EARLIEST THREE SKIN CONTACT AS ON AND LAST IS OFF

        on_skin = common.check_skin_status_sequence(data["FIRST_THREE_ON_LAST_OFF"], 4)
        assert on_skin == 1

        # TEST CASE FOR SKIN CONTACT DATA POINTS CONSISTING OF INVALID AND OFF

        on_skin = common.check_skin_status_sequence(data["MIXED_INVALID_AND_OFF"], 4)
        assert on_skin == 0

        # TEST CASE FOR SKIN CONTACT DATA POINTS CONSISTING OF MIXED INVALID AND ON

        on_skin = common.check_skin_status_sequence(data["MIXED_INVALID_AND_ON"], 4)
        assert on_skin == 1

        # TEST CASE FOR SKIN CONTACT DATA POINTS CONSISTING OF MIXED INVALID, ON AND OFF

        on_skin = common.check_skin_status_sequence(
            data["MIXED_INVALID_AND_ON_AND_OFF"], 4
        )
        assert on_skin == 1
