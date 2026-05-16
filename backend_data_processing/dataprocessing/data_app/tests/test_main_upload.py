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

from django.db import connection


from django.test import  override_settings

@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True
)
class TestDataUpload(TestCase):
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

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Reconnect DB if it's been closed
        connection.ensure_connection()

        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()

    def test_upload_chest_valid(self):

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": [
                "A6423f9b6004900008177df6a30f8a00",
                "004a000081a7de6a3",
                "004a00008177dd6a2",
                "004a00008177dd6a2",
                "004a000081a7de6a3",
                "004a00008187dd6a2",
                "004a00008187de6a4",
                "004a00008187dd6a2",
                "004a00008177de6a3",
                "004a00008197df6a2",
                "004a00008167de6a4",
                "004a00008187de6a5",
                "004a00008167dd6a4",
                "004a00008197de6a4",
                "004a00008177df6a3",
                "004a00008177df6a2",
                "A6423f9b7004a00008177dd6a10f8a00",
                "004a00008167de6a3",
                "004a000081a7de6a4",
                "004a00008167dd6a2",
                "004a00008177dd6a4",
                "004a00008187dd6a4",
                "004a00008167dd6a4",
                "004a00008187dd6a4",
                "004a00008197de6a5",
                "004a00008197dd6a1",
                "004a00008187dd6a5",
                "004a00008177dd6a4",
                "004a00008167dd6a1",
                "004a00008177dd6a2",
                "004a00008177dd6a4",
                "004a00008187de6a2",
                "004a00008167de6a5",
                "A6423f9b8004a00008167dd6a50f8a00",
                "004a00008187dd6a4",
                "004a00008187df6a2",
                "004a00008187de6a2",
                "004a00008187df6a3",
                "004a00008167dd6a1",
                "004a00008177de6a2",
                "004a00008187de6a4",
                "004a00008167de6a2",
                "004a00008167dd6a3",
                "004a00008197dd6a3",
                "004a00008167de6a3",
                "004a00008167de6a2",
                "004a00008187dc6a2",
                "004a00008167dd6a2",
                "004a00008177df6a2",
            ],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        assert response.json()["userID"] == 0

    def test_upload_chest_edge_data_length_is_one(self):

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6423f9b6004900008177df6a30f8a00"],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        assert response.json()["userID"] == 0

    def test_upload_chest_edge_empty_data(self):

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": [],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 400, "request is  successful")
        assert response.json()["message"][0] == "data is empty"

    def test_upload_chest_invalid(self):

        # invalid input, key data is missing

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 400, "request is  successful")

    def test_upload_chest_valid_using_invalid_token(self):

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6423f9b6004900008177df6a30f8a00"],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_referer=self.invalid_token,

        )
        self.assertEqual(response.status_code, 403, "request is not successful")

    def test_upload_finger_valid(self):

        data = {
                "userID": "0",
                "datetime": "2024-11-14 07:20:56",
                "battery": 93,
                "sensorID": "80e1279dac4e",
                "mode": "PULSE OXIMETRY",
                "sensorMode": "HR",
                "packetNumber": 0,
                "totalPacket": 1,
                "recordCollectedBySensor": 3000,
                "recordReceivedByGateway": 3000,
                "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
                "data": [
                    "A6735a44b100010008c36cc6e3110500",
                    "100010008ba6ea833",
                    "1000100094e72b94c",
                    "100010009ca6ad910",
                    "A6735a44c100010009037c78a5110500",
                    "10000c1471075070b",
                    "100010009057c9a34",
                    "100010008f97c69b0",
                    "1000100089d80d9ad",
                    "1000100088b7dd98c",
                    "1000100080480d93a",
                    "1000100081d82b95c",
                    "100010008407db94e",
                    "1000100080c814894",
                    "100010008627f7999",
                    "1000100082e77d730",
                    "100010008537ee720",
                    "100010007fc87786a",
                    "100010007e28789c8",
                    "100010007ce84b9bb",
                    "100010007e08a3990",
                    "100010008098ad986",
                    "1000100080a8f2947",
                    "10000d688258e7930",
                    "0c1d09b98139118da",
                    "08c3069878a8f48bc",
                    "073906a485296982d",
                    "071e062286b9738ad",
                    "06de062882596c880",
                    "A6735a44d06f6066a82a98c948110500",
                    "065105d58259cd830",
                    "07b9072283b928832",
                    "07d8072183592889e",
                    "07c70701808944849",
                    "079206c183796991b",
                    "0751069884890c876",
                    "073f068e83695c8fa",
                    "073a069083a93d895",
                    "073f069982199291b",
                    "0743069280695b872",
                    "0737068c812909851",
                    "07330686866a10938",
                    "0733069884b9458a4",
                    "075106b383795e87c",
                    "075d06ac83098086d",
                    "074e06a683294185c",
                    "075506b484095a80a",
                    "076206be84b92e885",
                    "077006e183a9c4894",
                    "07bb080e8499388b1",
                    "0b700b89844930947",
                    "0bf209eb86899c949",
                    "07b106608739818a5",
                    "061605a98279b3849",
                    "A6735a44e0602053482b804806110500",
                    "05d4050a94bad69e0",
                    "058504e88bc8898c9",
                    "05ca05747aaa938a3",
                    "0690064486197187b",
                    "06bf0592885950857",
                    "056904508bc978861",
                    "04a303bf8ca9d088a",
                    "047b03df830990812",
                    "049703ce8a899e8b7",
                    "044603108c396282e",
                    "035b0235894951809",
                    "0323030991995f78a",
                    "0473038d8ba9077bb",
                    "0394022b8ae92977f",
                    "02b0019f848a467e6",
                    "0280017488992775a",
                    "0275012b8ab8e4707",
                    "01b1010c8918d36ec",
                    "01ae01098a18b06e5",
                    "01a801018e17ff683",
                    "01ac011588d8176b7",
                    "0206012f7ad7d85c4",
                    "021a014283d8725c7",
                    "0273088e7d97bb69b",
                    "A6735a44f08e909648497e267d110500",
                    "0acc0a8f8567906aa",
                    "0aa00a1e7e07b466a",
                    "0b840c218878055fb",
                    "0e100f047dc817543",
                    "10000fff7c47d567f",
                    "100010007ff7e568a",
                    "100010008667ea6ca",
                    "100010007a97f9694",
                    "1000100086b7c2687",
                    "100010007e77c66a5",
                    "0fa1100086c814699",
                    "100010007cd7d2678",
                    "10001000845812780",
                    "1000100085a76d643",
                    "1000100083a7b366b",
                    "100010008877946a5",
                    "100010007ff765681",
                    "1000100083b7736b0",
                    "1000100088d7a46a5",
                    "1000100084477a697",
                    "10001000845778669",
                    "1000100081577967f",
                    "1000100080379f6e9",
                    "100010008788107d4",
                    "A6735a450100010007ba7dd6ad110500",
                    "100010008037c76d2",
                    "0fc20f3482483c651",
                    "0fab0fab89a7a569b",
                    "10000f7081582d676",
                    "0fa910008607996b8",
                    "100010007d27cf658",
                    "100010007c77cb686",
                    "100010007c4810699",
                    "100010008058096ae",
                    "1000100086881e674",
                    "100010008147a5690",
                    "10000ec37306e45fa",
                    "0f020edf7da7f8632",
                    "0fe90f198227ea680",
                    "0f930f2a7e479c70e",
                    "1000100094b76d5d3",
                    "1000100088880a6b5",
                    "100010007ff7c2654",
                    "A6735a4510c150be382b7ee682110500",
                    "0db10cb58327e5694",
                    "0fc20fff8367d768e",
                    "10000ede8407e7688",
                    "0ddc0d8b8397df68d",
                    "0e0f0dec83e7e3699",
                    "0e620e118407e668a",
                    "0ea20dd983e7e568e",
                    "0e460ddf8427e868e",
                    "0f040eed8487f068b",
                    "0fed0f4183c7e6697",
                    "0f940f2b8447e9690",
                    "0fe20f238457e768f",
                    "0f860dd08457e9690",
                    "0d3e0b328457e768e",
                    "0a4807ea8457eb690",
                    "07e106e28467e768f",
                    "07a607188447e768d",
                    "0822079a8447e968d",
                    "083407308447e868c",
                    "07cd06f38467e8690",
                    "07a806e78477e968e",
                    "07ac06f08467e768d",
                    "A6735a45207b106e88467eb68f110500",
                    "07a006d68447e968d",
                    "078f06c88457e868d",
                    "078606c28447e868f",
                    "078306be8437e868b",
                    "077d06b98457e968f",
                    "077606af8457e768c",
                    "076906998447e968d",
                    "0735061d8467e868f",
                    "068405f68547f367b",
                    "06c305ff8537f1692",
                    "06c306008517f268e",
                    "06c606028527f0691",
                    "06c806048527f1690",
                    "06c906058527f2691",
                    "06ca06068547f0690",
                    "06cb06078517f2690",
                    "06cc06078527f0690",
                    "06cb06088517f0690",
                    "06cc06088517f1690",
                    "06cc06088507f168e",
                    "06cd06098507f1690",
                    "06cd06098527f0690",
                    "06cf060d8527f0690",
                    "06d306108507f0690",
                    "A6735a45306d606148517f1692110500",
                    "06e106248517f1690",
                    "06ea06278517f0690",
                    "06ec06298517f0690",
                    "06ee062b8537f068d",
                    "06ef062d8527f268e",
                    "06f3062f8507f0691",
                    "06f506328527f1690",
                    "06f806378507f168e",
                    "06ff063d8537f0690",
                    "070406418517f0691",
                    "070506428527f068f",
                    "070606448507f168e",
                    "070806458517f0690",
                    "070806448527f068f",
                    "070806458517f2690",
                    "070906468517f1690",
                    "070906458527f2690",
                    "070806458517f1692",
                    "070906458517f0690",
                    "070906468517f0690",
                    "070a06478527f0690",
                    "070b06498507f0690",
                    "070e064e8517f168e",
                    "071206538517f068e",
                    "A6735a454071506538537ef691110500",
                    "071606528527f0690",
                    "071506538507f268f",
                    "071506528507f0690",
                    "071606538507f1690",
                    "071606538507f1690",
                    "071606528517f0690",
                    "071606538507f0690",
                    "071606528507f168f",
                    "071606538517f1691",
                    "071606538517f0691",
                    "071706548517f1690",
                    "071706548517f068f",
                    "071806548517f068f",
                    "071806558527f0690",
                    "071906568517f0690",
                    "071e06668527f0690",
                    "072b06678527ef68e",
                    "072a06688507f1690",
                    "072a06678527f168f",
                    "072a06678527f0691",
                    "072a06678517f0690",
                    "072a06678527f1690",
                    "072906678517f268f",
                    "072906678507f168e",
                    "A6735a455072906678517f0691110500",
                    "072906678527f168e",
                    "072906668517f1691",
                    "072906668507f1690",
                    "072906678517f0690",
                    "072806668517f1690",
                    "072806668507f068e",
                    "072906658527f068f",
                    "072806668527f1690",
                    "072806658517f068e",
                    "072706658507f1690",
                    "072706658517f2690",
                    "072806658517f0690",
                    "072706658507f1690",
                    "072706658517f0690",
                    "072706648517f268f",
                    "072706648517f1691",
                    "072606648517f0690",
                    "072706688527f1691",
                    "073006648517f1690",
                    "072506628507f1690",
                    "072506658517f0691",
                    "072306598537f0690",
                    "070706498507f1690",
                    "070706478527f0690",
                    "A6735a45606c7054a8517f0690110500",
                    "062b05448527f2691",
                    "0620054f8517f068e",
                    "065205878517f0690",
                    "066005818527f1690",
                    "065f05868527f0690",
                    "065e05878527f0690",
                    "065e05868507f0690",
                    "065f05868517f1690",
                    "066005878527f1690",
                    "066005878527ef690",
                    "066105888517f068f",
                    "066005878527f168e",
                    "066005868507f0690",
                    "065f05868517f168e",
                    "065f05858527f268f",
                    "065f05868517f068e",
                    "065f05858517f0690",
                    "065f05888527f1692",
                    "066805908517f1690",
                    "066b05918527f0691",
                    "066a058f8527f0690",
                    "0667058d8517f0690",
                    "0666058e8517f1690",
                    "0667058e8527f0691",
                    "A6735a4570667058f8507f1691110500",
                    "066805908517f2690",
                    "066905908507f0690",
                    "066a05918527f0692",
                    "066c059a8527f168f",
                    "0673059c8557f068f",
                    "0675059d8527f1687",
                    "0675059e8507f0691",
                    "0676059f8527f2692",
                    "0676059e8517f1691",
                    "0676059e8527f0690",
                    "0676059f84f7f168e",
                    "0677059f8517f068e",
                    "0676059f8517f1690",
                    "0677059f8517f1690",
                    "067705a08517f0690",
                    "0677059e8507f1691",
                    "067905a68507f1690",
                    "067d05a58517f0690",
                    "067c05a58507f168f",
                    "067d05a58517f0690",
                    "067d05a58527f0690",
                    "067c05a58507f0690",
                    "067c05a58517f1690",
                    "067c05a58517f0690",
                    "A6735a458067d05a58517f1691110500",
                    "067c05a58507f268f",
                    "067d05a58517f0690",
                    "067d05a68507f0690",
                    "067d05a68517f1690",
                    "067e05a68527f1691",
                    "067d05a68507f0690",
                    "067d05a68517f0692",
                    "067d05a58507f068f",
                    "067d05a68557f868f",
                    "067d05a68527f068f",
                    "068005ab8507f2690",
                    "068105ab8517f1690",
                    "068105a98527f168d",
                    "068105aa8507f168f",
                    "068105aa8527f1691",
                    "068105aa8517f1691",
                    "068005aa8527f1690",
                    "068005aa8507f1690",
                    "068005a98517f1690",
                    "068005aa8527f0690",
                    "068005aa8517f0690",
                    "068005a98507f1690",
                    "068005a98527f068f",
                    "068005a98527f2690",
                    "A6735a459068105aa8507f168f110500",
                    "068105aa8527f068e",
                    "068105aa8537f168e",
                    "068205ab8527f0690",
                    "068205aa8537f168f",
                    "068105ab8507f1691",
                    "068105aa8527f0690",
                ],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        assert response.json()["userID"] == 0

    def test_upload_finger_edge_data_length_is_one(self):

        data = {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6735a44b100010008c36cc6e3110500"],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,

        )

        self.assertEqual(response.status_code, 200, "request is not successful")
        assert response.json()["userID"] == 0

    def test_upload_finger_edge_empty_data(self):

        data = {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": [],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 400, "request is  successful")
        assert response.json()["message"][0] == "data is empty"

    def test_upload_finger_invalid(self):

        # invalid input, key data is missing

        data = {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,

        )

        self.assertEqual(response.status_code, 400, "request is  successful")

    def test_upload_finger_valid_using_invalid_token(self):

        data = {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6735a44b100010008c36cc6e3110500"],
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_referer=self.invalid_token,

        )
        self.assertEqual(response.status_code, 403, "request is not successful")


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True
)
class TestDataUploadWithBodyJson(TestCase):
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

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Reconnect DB if it's been closed
        connection.ensure_connection()
        DataProcessing.objects.all().delete()
        MetricMinutesCache.objects.all().delete()
        MetricHourlyCache.objects.all().delete()
        MetricDailyCache.objects.all().delete()
        SpotCache.objects.all().delete()
        StagingHourlyCache.objects.all().delete()
        HealthData.objects.all().delete()


    def test_upload_chest_valid(self):

        data = {
            "body-json" : {
                "userID": "0",
                "datetime": "2023-03-29 08:45:57",
                "battery": 64,
                "sensorID": "dummy",
                "mode": "RESPIRATORY RATE",
                "sensorMode": "RR",
                "packetNumber": 0,
                "totalPacket": 1,
                "recordCollectedBySensor": 3000,
                "recordReceivedByGateway": 1274,
                "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
                "data": [
                    "A6423f9b6004900008177df6a30f8a00",
                    "004a000081a7de6a3",
                    "004a00008177dd6a2",
                    "004a00008177dd6a2",
                    "004a000081a7de6a3",
                    "004a00008187dd6a2",
                    "004a00008187de6a4",
                    "004a00008187dd6a2",
                    "004a00008177de6a3",
                    "004a00008197df6a2",
                    "004a00008167de6a4",
                    "004a00008187de6a5",
                    "004a00008167dd6a4",
                    "004a00008197de6a4",
                    "004a00008177df6a3",
                    "004a00008177df6a2",
                    "A6423f9b7004a00008177dd6a10f8a00",
                    "004a00008167de6a3",
                    "004a000081a7de6a4",
                    "004a00008167dd6a2",
                    "004a00008177dd6a4",
                    "004a00008187dd6a4",
                    "004a00008167dd6a4",
                    "004a00008187dd6a4",
                    "004a00008197de6a5",
                    "004a00008197dd6a1",
                    "004a00008187dd6a5",
                    "004a00008177dd6a4",
                    "004a00008167dd6a1",
                    "004a00008177dd6a2",
                    "004a00008177dd6a4",
                    "004a00008187de6a2",
                    "004a00008167de6a5",
                    "A6423f9b8004a00008167dd6a50f8a00",
                    "004a00008187dd6a4",
                    "004a00008187df6a2",
                    "004a00008187de6a2",
                    "004a00008187df6a3",
                    "004a00008167dd6a1",
                    "004a00008177de6a2",
                    "004a00008187de6a4",
                    "004a00008167de6a2",
                    "004a00008167dd6a3",
                    "004a00008197dd6a3",
                    "004a00008167de6a3",
                    "004a00008167de6a2",
                    "004a00008187dc6a2",
                    "004a00008167dd6a2",
                    "004a00008177df6a2",
                ],
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
        assert response.json()["userID"] == 0

    def test_upload_chest_edge_data_length_is_one(self):

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6423f9b6004900008177df6a30f8a00"],
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
        assert response.json()["userID"] == 0

    def test_upload_chest_edge_empty_data(self):

        data = {
            "body-json" : {
             "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": [],
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 400, "request is  successful")
        assert response.json()["message"][0] == "data is empty"

    def test_upload_chest_invalid(self):

        # invalid input, key data is missing

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,

        )

        self.assertEqual(response.status_code, 400, "request is  successful")

    def test_upload_chest_valid_using_invalid_token(self):

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6423f9b6004900008177df6a30f8a00"],
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_referer=self.invalid_token,

        )
        self.assertEqual(response.status_code, 403, "request is not successful")

    def test_upload_finger_valid(self):

        data = {
            "body-json" : {
                "userID": "0",
                "datetime": "2024-11-14 07:20:56",
                "battery": 93,
                "sensorID": "80e1279dac4e",
                "mode": "PULSE OXIMETRY",
                "sensorMode": "HR",
                "packetNumber": 0,
                "totalPacket": 1,
                "recordCollectedBySensor": 3000,
                "recordReceivedByGateway": 3000,
                "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
                "data": [
                    "A6735a44b100010008c36cc6e3110500",
                    "100010008ba6ea833",
                    "1000100094e72b94c",
                    "100010009ca6ad910",
                    "A6735a44c100010009037c78a5110500",
                    "10000c1471075070b",
                    "100010009057c9a34",
                    "100010008f97c69b0",
                    "1000100089d80d9ad",
                    "1000100088b7dd98c",
                    "1000100080480d93a",
                    "1000100081d82b95c",
                    "100010008407db94e",
                    "1000100080c814894",
                    "100010008627f7999",
                    "1000100082e77d730",
                    "100010008537ee720",
                    "100010007fc87786a",
                    "100010007e28789c8",
                    "100010007ce84b9bb",
                    "100010007e08a3990",
                    "100010008098ad986",
                    "1000100080a8f2947",
                    "10000d688258e7930",
                    "0c1d09b98139118da",
                    "08c3069878a8f48bc",
                    "073906a485296982d",
                    "071e062286b9738ad",
                    "06de062882596c880",
                    "A6735a44d06f6066a82a98c948110500",
                    "065105d58259cd830",
                    "07b9072283b928832",
                    "07d8072183592889e",
                    "07c70701808944849",
                    "079206c183796991b",
                    "0751069884890c876",
                    "073f068e83695c8fa",
                    "073a069083a93d895",
                    "073f069982199291b",
                    "0743069280695b872",
                    "0737068c812909851",
                    "07330686866a10938",
                    "0733069884b9458a4",
                    "075106b383795e87c",
                    "075d06ac83098086d",
                    "074e06a683294185c",
                    "075506b484095a80a",
                    "076206be84b92e885",
                    "077006e183a9c4894",
                    "07bb080e8499388b1",
                    "0b700b89844930947",
                    "0bf209eb86899c949",
                    "07b106608739818a5",
                    "061605a98279b3849",
                    "A6735a44e0602053482b804806110500",
                    "05d4050a94bad69e0",
                    "058504e88bc8898c9",
                    "05ca05747aaa938a3",
                    "0690064486197187b",
                    "06bf0592885950857",
                    "056904508bc978861",
                    "04a303bf8ca9d088a",
                    "047b03df830990812",
                    "049703ce8a899e8b7",
                    "044603108c396282e",
                    "035b0235894951809",
                    "0323030991995f78a",
                    "0473038d8ba9077bb",
                    "0394022b8ae92977f",
                    "02b0019f848a467e6",
                    "0280017488992775a",
                    "0275012b8ab8e4707",
                    "01b1010c8918d36ec",
                    "01ae01098a18b06e5",
                    "01a801018e17ff683",
                    "01ac011588d8176b7",
                    "0206012f7ad7d85c4",
                    "021a014283d8725c7",
                    "0273088e7d97bb69b",
                    "A6735a44f08e909648497e267d110500",
                    "0acc0a8f8567906aa",
                    "0aa00a1e7e07b466a",
                    "0b840c218878055fb",
                    "0e100f047dc817543",
                    "10000fff7c47d567f",
                    "100010007ff7e568a",
                    "100010008667ea6ca",
                    "100010007a97f9694",
                    "1000100086b7c2687",
                    "100010007e77c66a5",
                    "0fa1100086c814699",
                    "100010007cd7d2678",
                    "10001000845812780",
                    "1000100085a76d643",
                    "1000100083a7b366b",
                    "100010008877946a5",
                    "100010007ff765681",
                    "1000100083b7736b0",
                    "1000100088d7a46a5",
                    "1000100084477a697",
                    "10001000845778669",
                    "1000100081577967f",
                    "1000100080379f6e9",
                    "100010008788107d4",
                    "A6735a450100010007ba7dd6ad110500",
                    "100010008037c76d2",
                    "0fc20f3482483c651",
                    "0fab0fab89a7a569b",
                    "10000f7081582d676",
                    "0fa910008607996b8",
                    "100010007d27cf658",
                    "100010007c77cb686",
                    "100010007c4810699",
                    "100010008058096ae",
                    "1000100086881e674",
                    "100010008147a5690",
                    "10000ec37306e45fa",
                    "0f020edf7da7f8632",
                    "0fe90f198227ea680",
                    "0f930f2a7e479c70e",
                    "1000100094b76d5d3",
                    "1000100088880a6b5",
                    "100010007ff7c2654",
                    "A6735a4510c150be382b7ee682110500",
                    "0db10cb58327e5694",
                    "0fc20fff8367d768e",
                    "10000ede8407e7688",
                    "0ddc0d8b8397df68d",
                    "0e0f0dec83e7e3699",
                    "0e620e118407e668a",
                    "0ea20dd983e7e568e",
                    "0e460ddf8427e868e",
                    "0f040eed8487f068b",
                    "0fed0f4183c7e6697",
                    "0f940f2b8447e9690",
                    "0fe20f238457e768f",
                    "0f860dd08457e9690",
                    "0d3e0b328457e768e",
                    "0a4807ea8457eb690",
                    "07e106e28467e768f",
                    "07a607188447e768d",
                    "0822079a8447e968d",
                    "083407308447e868c",
                    "07cd06f38467e8690",
                    "07a806e78477e968e",
                    "07ac06f08467e768d",
                    "A6735a45207b106e88467eb68f110500",
                    "07a006d68447e968d",
                    "078f06c88457e868d",
                    "078606c28447e868f",
                    "078306be8437e868b",
                    "077d06b98457e968f",
                    "077606af8457e768c",
                    "076906998447e968d",
                    "0735061d8467e868f",
                    "068405f68547f367b",
                    "06c305ff8537f1692",
                    "06c306008517f268e",
                    "06c606028527f0691",
                    "06c806048527f1690",
                    "06c906058527f2691",
                    "06ca06068547f0690",
                    "06cb06078517f2690",
                    "06cc06078527f0690",
                    "06cb06088517f0690",
                    "06cc06088517f1690",
                    "06cc06088507f168e",
                    "06cd06098507f1690",
                    "06cd06098527f0690",
                    "06cf060d8527f0690",
                    "06d306108507f0690",
                    "A6735a45306d606148517f1692110500",
                    "06e106248517f1690",
                    "06ea06278517f0690",
                    "06ec06298517f0690",
                    "06ee062b8537f068d",
                    "06ef062d8527f268e",
                    "06f3062f8507f0691",
                    "06f506328527f1690",
                    "06f806378507f168e",
                    "06ff063d8537f0690",
                    "070406418517f0691",
                    "070506428527f068f",
                    "070606448507f168e",
                    "070806458517f0690",
                    "070806448527f068f",
                    "070806458517f2690",
                    "070906468517f1690",
                    "070906458527f2690",
                    "070806458517f1692",
                    "070906458517f0690",
                    "070906468517f0690",
                    "070a06478527f0690",
                    "070b06498507f0690",
                    "070e064e8517f168e",
                    "071206538517f068e",
                    "A6735a454071506538537ef691110500",
                    "071606528527f0690",
                    "071506538507f268f",
                    "071506528507f0690",
                    "071606538507f1690",
                    "071606538507f1690",
                    "071606528517f0690",
                    "071606538507f0690",
                    "071606528507f168f",
                    "071606538517f1691",
                    "071606538517f0691",
                    "071706548517f1690",
                    "071706548517f068f",
                    "071806548517f068f",
                    "071806558527f0690",
                    "071906568517f0690",
                    "071e06668527f0690",
                    "072b06678527ef68e",
                    "072a06688507f1690",
                    "072a06678527f168f",
                    "072a06678527f0691",
                    "072a06678517f0690",
                    "072a06678527f1690",
                    "072906678517f268f",
                    "072906678507f168e",
                    "A6735a455072906678517f0691110500",
                    "072906678527f168e",
                    "072906668517f1691",
                    "072906668507f1690",
                    "072906678517f0690",
                    "072806668517f1690",
                    "072806668507f068e",
                    "072906658527f068f",
                    "072806668527f1690",
                    "072806658517f068e",
                    "072706658507f1690",
                    "072706658517f2690",
                    "072806658517f0690",
                    "072706658507f1690",
                    "072706658517f0690",
                    "072706648517f268f",
                    "072706648517f1691",
                    "072606648517f0690",
                    "072706688527f1691",
                    "073006648517f1690",
                    "072506628507f1690",
                    "072506658517f0691",
                    "072306598537f0690",
                    "070706498507f1690",
                    "070706478527f0690",
                    "A6735a45606c7054a8517f0690110500",
                    "062b05448527f2691",
                    "0620054f8517f068e",
                    "065205878517f0690",
                    "066005818527f1690",
                    "065f05868527f0690",
                    "065e05878527f0690",
                    "065e05868507f0690",
                    "065f05868517f1690",
                    "066005878527f1690",
                    "066005878527ef690",
                    "066105888517f068f",
                    "066005878527f168e",
                    "066005868507f0690",
                    "065f05868517f168e",
                    "065f05858527f268f",
                    "065f05868517f068e",
                    "065f05858517f0690",
                    "065f05888527f1692",
                    "066805908517f1690",
                    "066b05918527f0691",
                    "066a058f8527f0690",
                    "0667058d8517f0690",
                    "0666058e8517f1690",
                    "0667058e8527f0691",
                    "A6735a4570667058f8507f1691110500",
                    "066805908517f2690",
                    "066905908507f0690",
                    "066a05918527f0692",
                    "066c059a8527f168f",
                    "0673059c8557f068f",
                    "0675059d8527f1687",
                    "0675059e8507f0691",
                    "0676059f8527f2692",
                    "0676059e8517f1691",
                    "0676059e8527f0690",
                    "0676059f84f7f168e",
                    "0677059f8517f068e",
                    "0676059f8517f1690",
                    "0677059f8517f1690",
                    "067705a08517f0690",
                    "0677059e8507f1691",
                    "067905a68507f1690",
                    "067d05a58517f0690",
                    "067c05a58507f168f",
                    "067d05a58517f0690",
                    "067d05a58527f0690",
                    "067c05a58507f0690",
                    "067c05a58517f1690",
                    "067c05a58517f0690",
                    "A6735a458067d05a58517f1691110500",
                    "067c05a58507f268f",
                    "067d05a58517f0690",
                    "067d05a68507f0690",
                    "067d05a68517f1690",
                    "067e05a68527f1691",
                    "067d05a68507f0690",
                    "067d05a68517f0692",
                    "067d05a58507f068f",
                    "067d05a68557f868f",
                    "067d05a68527f068f",
                    "068005ab8507f2690",
                    "068105ab8517f1690",
                    "068105a98527f168d",
                    "068105aa8507f168f",
                    "068105aa8527f1691",
                    "068105aa8517f1691",
                    "068005aa8527f1690",
                    "068005aa8507f1690",
                    "068005a98517f1690",
                    "068005aa8527f0690",
                    "068005aa8517f0690",
                    "068005a98507f1690",
                    "068005a98527f068f",
                    "068005a98527f2690",
                    "A6735a459068105aa8507f168f110500",
                    "068105aa8527f068e",
                    "068105aa8537f168e",
                    "068205ab8527f0690",
                    "068205aa8537f168f",
                    "068105ab8507f1691",
                    "068105aa8527f0690",
                ],
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
        assert response.json()["userID"] == 0

    def test_upload_finger_edge_data_length_is_one(self):

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6735a44b100010008c36cc6e3110500"],
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
        assert response.json()["userID"] == 0

    def test_upload_finger_edge_empty_data(self):

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": [],
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,
        )

        self.assertEqual(response.status_code, 400, "request is  successful")
        assert response.json()["message"][0] == "data is empty"

    def test_upload_finger_invalid(self):

        # invalid input, key data is missing

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2023-03-29 08:45:57",
            "battery": 64,
            "sensorID": "dummy",
            "mode": "RESPIRATORY RATE",
            "sensorMode": "RR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 1274,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_REFERER=self.valid_token,

        )

        self.assertEqual(response.status_code, 400, "request is  successful")

    def test_upload_finger_valid_using_invalid_token(self):

        data = {
            "body-json" : {
            "userID": "0",
            "datetime": "2024-11-14 07:20:56",
            "battery": 93,
            "sensorID": "80e1279dac4e",
            "mode": "PULSE OXIMETRY",
            "sensorMode": "HR",
            "packetNumber": 0,
            "totalPacket": 1,
            "recordCollectedBySensor": 3000,
            "recordReceivedByGateway": 3000,
            "dataColName": "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}",
            "data": ["A6735a44b100010008c36cc6e3110500"],
            }
        }

        response = self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            HTTP_referer=self.invalid_token,

        )
        self.assertEqual(response.status_code, 403, "request is not successful")

