import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from data_app.models import *
from decimal import Decimal
from datetime import datetime
import copy


field_small_case_mapping = {
    "userId": "user_id",
    "dateTime": "date_time",
    "dateTimeUpdated": "datetime_updated",
    "dashboardMode": "dashboard_mode",
    "dataColName": "data_col_name",
    "dateTimeGatewaySent": "datetime_gateway_sent",
    "dateTimeSensor": "datetime_sensor",
    "dateTimeServerReceived": "datetime_server_received",
    "ERROR_sensor_onskin_status": "error_sensor_onskin_status",
    "hardwareMode": "hardware_mode",
    "HR": "hr",
    "HR_fdomain": "hr_fdomain",
    "HR_fdomain_w_good_sqa": "hr_fdomain_w_good_sqa",
    "HR_tdomain": "hr_tdomain",
    "isGenModeFromDashboard": "is_genmode_from_dashboard",
    "packetNumber": "packet_number",
    "recordCollectedBySensor": "record_collected_by_sensor",
    "recordReceivedByGateway": "record_received_by_gateway",
    "recordServerReceived": "record_server_received",
    "RR": "rr",
    "RR_DC": "rr_dc",
    "RR_fdomain": "rr_fdomain",
    "RR_fdomain_w_good_sqa": "rr_fdomain_w_good_sqa",
    "RR_hybrid": "rr_hybrid",
    "RR_IBI": "rr_ibi",
    "RR_sd": "rr_sd",
    "RR_SQAML": "rr_sqaml",
    "RR_SQAML_sd": "rr_sqaml_sd",
    "RR_TD": "rr_td",
    "RR_tdomain": "rr_tdomain",
    "SpO2": "spo2",
    "SQA": "sqa",
    "SQA_index": "sqa_index",
    "totalPacket": "total_packet",
    "waveletsTransform": "wavelets_transform",
    "bodyTemp": "body_temperature",
    "skinTemp": "skin_temperature",
    "dateTime_chest": "datetime_chest",
    "dateTime_finger": "datetime_finger",
    "dateTime_latest_valid_chest": "datetime_latest_valid_chest",
    "dateTime_latest_valid_finger": "datetime_latest_valid_finger",
    "BP_Dia": "bp_dia",
    "BP_Sys": "bp_sys",
    "HR_fdomain_w_good_sqa_sd": "hr_fdomain_w_good_sqa_sd",
    "HR_sd": "hr_sd",
    "SpO2_sd": "spo2_sd",
    "dateTimeDataSent": "datetime_data_sent",
}


class Command(BaseCommand):
    help = "dump the dynamo db data to postgresql"

    def update_field_name(self, item):
        item_copy = copy.deepcopy(item)
        for k, v in item.items():
            if k in field_small_case_mapping:
                item_copy[field_small_case_mapping.get(k)] = v
                del item_copy[k]
        return item_copy

    def refactor_sub_dic(self, req_json):
        for k, v in req_json.items():
            if isinstance(v, dict):
                req_json[k] = self.refactor_sub_dic(v)
            elif isinstance(v, Decimal):
                req_json[k] = float(v)
            req_json = self.update_field_name(req_json)
        return req_json

    def funnel_data(self, items, fields):
        updated_item_list = []

        datetime_fields = []
        boolean_fields = []
        float_fields = []

        for field in fields:
            if isinstance(field, models.DateTimeField):
                datetime_fields.append(field.name)
            elif isinstance(field, models.BooleanField):
                boolean_fields.append(field.name)
            elif isinstance(field, models.FloatField):
                float_fields.append(field.name)
        for item in items:
            if item.get("RR_SD"):
                del item["RR_SD"]
            if item.get("sensor_id") and item.get("sensorID"):
                del item["sensorID"]
            elif item.get("sensorID") and not item.get("sensor_id"):
                item["sensor_id"] = item.get("sensorID")
                del item["sensorID"]

            for k, v in item.items():
                if k in datetime_fields:
                    if v:
                        item[k] = datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%fZ")
                elif k in boolean_fields:
                    if v is not None:
                        item[k] = False
                        if v == "true" or v == True:
                            item[k] = True
                elif k in float_fields:
                    try:
                        item[k] = float(v)
                    except:
                        item[k] = None
                if isinstance(v, dict):
                    item[k] = self.refactor_sub_dic(v)
            item_copy = self.update_field_name(item)
            updated_item_list.append(item_copy)
        return updated_item_list

    def process_data_processing(self, dynamo_client):
        data_processing = dynamo_client.Table("respiree-data-processing-mj7rfl8r0p")
        response = data_processing.scan()
        items = response.get("Items")

        fields = DataProcessing._meta.fields
        items = self.funnel_data(items, fields)

        for item in items:
            DataProcessing.objects.get_or_create(**item)

        print("DataProcessing completed")

    def process_metric_minutes_cache(self, dynamo_client):
        data_processing = dynamo_client.Table(
            "respiree-metric-minutes-cache-mj7rfl8r0p"
        )
        response = data_processing.scan()
        items = response.get("Items")

        fields = MetricMinutesCache._meta.fields

        items = self.funnel_data(items, fields)

        for item in items:
            MetricMinutesCache.objects.get_or_create(**item)

        print("MetricMinutesCache completed")

    def process_metric_cache(self, dynamo_client):
        data_processing = dynamo_client.Table("respiree-metric-cache-mj7rfl8r0p")
        response = data_processing.scan()
        items = response.get("Items")

        fields = MetricCache._meta.fields

        items = self.funnel_data(items, fields)

        for item in items:
            MetricCache.objects.get_or_create(**item)

        print("MetricCache completed")

    def process_spot_cache(self, dynamo_client):
        data_processing = dynamo_client.Table("respiree-spot-cache-mj7rfl8r0p")
        response = data_processing.scan()
        items = response.get("Items")

        fields = SpotCache._meta.fields

        items = self.funnel_data(items, fields)

        for item in items:
            SpotCache.objects.get_or_create(**item)

        print("SpotCache completed")

    def process_api_data_sentout_table(self, dynamo_client):
        data_processing = dynamo_client.Table(
            "respiree_api_dataSentOutTable-mj7rfl8r0p"
        )
        response = data_processing.scan()
        items = response.get("Items")

        fields = ApiDataSentOut._meta.fields

        items = self.funnel_data(items, fields)

        for item in items:
            ApiDataSentOut.objects.get_or_create(**item)

        print("ApiDataSentOut completed")

    def process_gateway_pings_table(self, dynamo_client):
        data_processing = dynamo_client.Table(
            "respiree_gateway_pings"
        )
        response = data_processing.scan()
        items = response.get("Items")

        fields = GatewayPings._meta.fields

        items = self.funnel_data(items, fields)

        for item in items:
            GatewayPings.objects.get_or_create(**item)

        print("GatewayPings completed")

    def handle(self, *args, **options):
        dynamo_client = boto3.resource(
            service_name="dynamodb",
            region_name=settings.AWS_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.process_metric_minutes_cache(dynamo_client)
        self.process_metric_cache(dynamo_client)
        self.process_spot_cache(dynamo_client)
        self.process_api_data_sentout_table(dynamo_client)
        self.process_data_processing(dynamo_client)
        self.process_gateway_pings_table(dynamo_client)
