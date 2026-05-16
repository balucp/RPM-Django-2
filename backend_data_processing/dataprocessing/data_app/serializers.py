import requests
from urllib.parse import urljoin
from rest_framework import serializers
from .models import *
import rest_framework.exceptions as rest_exception
from .helpers import (
    convert_str_to_datetime,
    update_sensor_last_connect,
    create_directory,
    write_array_to_file,
    load_rawdata,
    convert_to_datetime_to_utc,
    get_object_attribute,
    get_patient_timezone,
)
import numpy as np
import datetime as dt
from datetime import timezone
import os
import pytz
import logging
from .metric_calculation import calculate_metric
from .helpers import check_if_utc_format
import threading
from dataprocessing import lib_settings as settings
# from data_app import lib_update_cache_incremental as cache
from . import lib_common as common
# from data_app import lib_update_compliance as compliance
import sys
import traceback

class DynamicFieldsSerializerMixin(object):
    """
    can take fields as input and show only those fields
    """

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop("fields", None)

        # Instantiate the superclass normally
        super(DynamicFieldsSerializerMixin, self).__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class RelatedFieldAlternative(serializers.PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        self.serializer = kwargs.pop("serializer", None)
        self.fields = kwargs.pop("fields", None)
        if self.serializer is not None and not issubclass(
            self.serializer, serializers.Serializer
        ):
            raise TypeError('"serializer" is not a valid serializer class')

        super().__init__(**kwargs)

    def use_pk_only_optimization(self):
        return False if self.serializer else True

    def to_representation(self, instance):
        if issubclass(self.serializer, DynamicFieldsSerializerMixin):
            if self.fields:
                return self.serializer(
                    instance, context=self.context, fields=self.fields
                ).data
        if self.serializer:
            return self.serializer(instance, context=self.context).data
        return super().to_representation(instance)


class UploadSerializer(DynamicFieldsSerializerMixin, serializers.ModelSerializer):
    userID = serializers.IntegerField(source="user_id")
    datetime = serializers.DateTimeField(source="date_time")
    sensorID = serializers.CharField(source="sensor_id")
    sensorMode = serializers.CharField(source="dashboard_mode")
    packetNumber = serializers.CharField(source="packet_number")
    totalPacket = serializers.IntegerField(source="total_packet")
    data = serializers.JSONField()
    dataColName = serializers.CharField(source="data_col_name")
    mode = serializers.CharField(source="hardware_mode")
    recordCollectedBySensor = serializers.IntegerField(
        source="record_collected_by_sensor", required=False)
    recordReceivedByGateway = serializers.IntegerField(
        source="record_received_by_gateway", required=False)
    recordServerReceived = serializers.IntegerField(
        source="record_server_received", required=False)

    class Meta:
        model = DataProcessing
        # fields = (
        #     "id", "userID", "datetime", "accepted_frame", "accepted_frame_ratio", "accepted_frame_spo2", "accepted_frame_spo2_ratio",
        #     "accepted_frame_tdomain", "accepted_frame_tdomain_ratio", "activity_calories", "activity_percentage", "activity_step", "aws_request_id_data_sent",
        #     "aws_request_id_metric", "aws_request_id_upload", "battery", "body_temperature", "bucket", "data_is_sent_to_client", "dataColName", "datetime_gateway_sent", "datetime_sensor",
        #     "datetime_server_received", "debug_data_length_too_short", "debug_list_bpm_round", "debug_list_status", "error_sensor_onskin_status",
        #     "filename", "filepath", "hr", "hr_fdomain", "hr_fdomain_w_good_sqa", "hr_tdomain", "is_genmode_from_dashboard",
        #     "list_onskin_status_stdev_ratio", "list_output_kurtosis", "list_output_peakratio", "list_output_skewness", "list_output_stdev",
        #     "list_phase_diff", "list_sd_signal_w_sqa", "list_sensor_onskin_status_ratio", "median_list_output_kurtosis", "median_list_output_peakratio",
        #     "median_list_output_skewness", "median_list_output_stdev", "num_record_error", "num_temperature_out_of_range",
        #     "onskin_2lightsources_median_diff_cv", "onskin_2lightsources_median_diff_mean", "onskin_2lightsources_median_diff_median",
        #     "onskin_2lightsources_median_diff_sd", "packetNumber", "point_awake", "point_sleep", "recordCollectedBySensor", "recordReceivedByGateway",
        #     "recordServerReceived", "rr", "rr_dc", "rr_fdomain", "rr_fdomain_w_good_sqa", "rr_hybrid", "rr_ibi", "rr_sd", "rr_sqaml",
        #     "rr_sqaml_sd", "rr_td", "rr_tdomain", "sensor_contact_status", "sensorID", "sensor_onskin_status", "sensor_onskin_status_stdev",
        #     "signal_quality_status", "skin_temperature", "sleep_duration_seconds", "spo2", "sqa", "sqa_index", "total_frame",
        #     "total_frame_spo2", "total_frame_tdomain", "totalPacket", "val_sd_signal_w_sqa", "val_sd_signal_wo_sqa", "wavelets_transform",
        #     "wellness_calmness", "wellness_stress", "sensorMode", "data", "mode", "is_calculated", "bool_force_onskin_chest", "bool_force_onskin_finger",
        #     "bool_impute_rr", "bool_impute_hr", "bool_impute_spo2", "error_pipeline_calculation", "hr_fdomain_w_good_sqa_sd", "hr_sd", "spo2_sd",
        # )

        fields = (
            "id", "userID", "datetime", "sensorID", "sensorMode", "packetNumber", "totalPacket",
            "data", "dataColName", "mode", "recordCollectedBySensor", "recordReceivedByGateway",
            "recordServerReceived"
        )

        # extra_kwargs = {
        #     "userID": {"required": True, "allow_null": False}, "packetNumber": {"required": True, "allow_null": False},
        #     "totalPacket": {"required": True, "allow_null": False}, "datetime": {"required": True, "allow_null": False},
        #     "dataColName": {"required": True, "allow_null": False}, "sensorMode": {"required": True, "allow_null": False},
        #     "mode": {"required": True, "allow_null": False}, "data": {"required": True, "allow_null": False, "write_only": True},
        #     "is_calculated": {"read_only": True}
        # }

    def extract_data_format(self, data_col_name):
        data_col_name_mapping = {
            "{datetime|sensor1|sensor2}": "2",
            "{DDDDDDDDRRRSSSXXXYYYZZZTTTM}": "3",
            "{DDDDDDDDRRRRSSSSXXXYYYZZZTTTM}": "4",
            "{ADDDDDDDDRRRRSSSSXXXYYYZZZTTTMBB,RRRRSSSSXXXYYYZZZ}": "5"
        }
        return data_col_name_mapping.get(data_col_name, "1")

    def process_data_format_2(self, element):
        temp_data_input = element.split("|")

        temp_epoch_time = int(temp_data_input[0], 16)
        temp_s1 = int(temp_data_input[1], 16)
        temp_s2 = int(temp_data_input[2], 16)

        temp_data = np.array([temp_epoch_time, temp_s1, temp_s2])
        return temp_data

    def process_data_format_3(self, element, hardware_mode):
        temp_data_input = element

        temp_epoch_time = int(temp_data_input[0:8], 16)
        temp_s1 = int(temp_data_input[8:11], 16)
        temp_s2 = int(temp_data_input[11:14], 16)
        temp_accl_x = int(temp_data_input[14:17], 16)
        temp_accl_y = int(temp_data_input[17:20], 16)
        temp_accl_z = int(temp_data_input[20:23], 16)
        temp_temperature = int(temp_data_input[23:26], 16)
        temp_mode = int(temp_data_input[26], 16)

        temp_motion = np.sqrt(
            np.square(temp_accl_x)
            + np.square(temp_accl_y)
            + np.square(temp_accl_z)
        )

        if hardware_mode == "respiratory-rate":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_motion, temp_accl_x,
                    temp_accl_y, temp_accl_z, temp_temperature, temp_mode]
            )
        elif hardware_mode == "pulse-oximetry":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_s2, temp_accl_x,
                    temp_accl_y, temp_accl_z, temp_temperature, temp_mode]
            )
        return temp_data

    def process_data_format_4(self, element, hardware_mode):
        temp_data_input = element
        temp_epoch_time = int(temp_data_input[0:8], 16)
        temp_s1 = int(temp_data_input[8:12], 16)
        temp_s2 = int(temp_data_input[12:16], 16)
        temp_accl_x = int(temp_data_input[16:19], 16)
        temp_accl_y = int(temp_data_input[19:22], 16)
        temp_accl_z = int(temp_data_input[22:25], 16)
        temp_temperature = int(temp_data_input[25:28], 16)
        temp_mode = int(temp_data_input[28], 16)

        temp_motion = np.sqrt(
            np.square(temp_accl_x)
            + np.square(temp_accl_y)
            + np.square(temp_accl_z)
        )

        if hardware_mode == "respiratory-rate":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_motion, temp_accl_x,
                    temp_accl_y, temp_accl_z, temp_temperature, temp_mode]
            )
        elif hardware_mode == "pulse-oximetry":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_s2, temp_accl_x, temp_accl_y, temp_accl_z, temp_temperature, temp_mode,
                 ]
            )
        return temp_data

    def process_data_format_5(self, element, hardware_mode, temp_epoch_time, temp_temperature, temp_mode, temp_battery):
        temp_data_input = str(element)

        if len(temp_data_input) == 32:
            temp_epoch_time = int(temp_data_input[1:9], 16)
            temp_s1 = int(temp_data_input[9:13], 16)
            temp_s2 = int(temp_data_input[13:17], 16)
            temp_accl_x = int(temp_data_input[17:20], 16)
            temp_accl_y = int(temp_data_input[20:23], 16)
            temp_accl_z = int(temp_data_input[23:26], 16)
            temp_temperature = int(temp_data_input[26:29], 16)
            temp_mode = int(temp_data_input[29], 16)
            temp_battery = int(temp_data_input[30:32], 16)
        elif len(temp_data_input) == 17:
            temp_s1 = int(temp_data_input[0:4], 16)
            temp_s2 = int(temp_data_input[4:8], 16)
            temp_accl_x = int(temp_data_input[8:11], 16)
            temp_accl_y = int(temp_data_input[11:14], 16)
            temp_accl_z = int(temp_data_input[14:17], 16)

        temp_motion = np.sqrt(
            np.square(temp_accl_x)
            + np.square(temp_accl_y)
            + np.square(temp_accl_z)
        )
        if hardware_mode == "respiratory-rate":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_motion, temp_accl_x, temp_accl_y,
                    temp_accl_z, temp_temperature, temp_mode, temp_battery]
            )
        elif hardware_mode == "pulse-oximetry":
            temp_data = np.array(
                [temp_epoch_time, temp_s1, temp_s2, temp_accl_x, temp_accl_y,
                    temp_accl_z, temp_temperature, temp_mode, temp_battery]
            )
        return temp_data, temp_epoch_time, temp_temperature, temp_mode, temp_battery

    def calculate_data(self, data_input, data_format, hardware_mode, user_id, datetime_str):
        num_record_error = 0
        data = []

        temp_epoch_time, temp_temperature, temp_mode, temp_battery = None, None, None, None
        for element in data_input:
            try:
                if data_format == "1":
                    data = np.append(
                        data, element).reshape(-1, len(element))

                elif data_format == "2":
                    temp_data = self.process_data_format_2(element)
                    data = np.append(
                        data, temp_data).reshape(-1, len(temp_data))

                elif data_format == "3":
                    temp_data = self.process_data_format_3(
                        element, hardware_mode)
                    data = np.append(
                        data, temp_data).reshape(-1, len(temp_data))

                elif data_format == "4":
                    temp_data = self.process_data_format_4(
                        element, hardware_mode)
                    data = np.append(
                        data, temp_data).reshape(-1, len(temp_data))

                elif data_format == "5":
                    temp_data, temp_epoch_time, temp_temperature, temp_mode, temp_battery = self.process_data_format_5(
                        element, hardware_mode, temp_epoch_time, temp_temperature, temp_mode, temp_battery)
                    data = np.append(
                        data, temp_data).reshape(-1, len(temp_data))

            except Exception as e:
                logging.error(
                    f"[ERROR] in data format / user {user_id}, date_timeGateway {datetime_str} >>> {e} >>> received {element}")
                num_record_error += 1
        return data, num_record_error

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        sensor_id = attrs.get("sensor_id")
        dashboard_mode = attrs.get("dashboard_mode").upper()
        data_input = attrs.pop("data")
        record_received_by_gateway = attrs.get("record_received_by_gateway")
        data_col_name = attrs.get("data_col_name")
        hardware_mode = (attrs.get("hardware_mode").lower()).replace(" ", "-")

        date_time, datetime_str = convert_to_datetime_to_utc(
            attrs.get("date_time"),
            settings.make_timezone_aware,
            settings.datetime_format,
        )

        if not data_input:
            raise rest_exception.ValidationError({'message': 'data is empty'})

        datetime_server_received = dt.datetime.now().replace(microsecond=0)
        if settings.make_timezone_aware:
            datetime_server_received = datetime_server_received.replace(
                tzinfo=timezone.utc)
        
        if (datetime_server_received-date_time).total_seconds()>60*60*24*30*12: # more than one year
            date_time = datetime_server_received
            datetime_str = datetime_server_received.strftime("%Y-%m-%d %H:%M:%S")

        split_datetime = datetime_str.split(" ")
        date = split_datetime[0]
        time = split_datetime[1].replace(":", "-")

        path_raw_data = os.path.join(settings.path_raw_data, str(user_id))
        filename = f"{user_id}_{dashboard_mode}_{date}_{time}.txt"
        filepath_rawdata = os.path.join(path_raw_data, filename)

        # Update backend with sensor last connection time

        update_sensor_last_connect(sensor_id, settings.backend_url)

        is_genmode_from_dashboard = dashboard_mode == "GEN"

        if is_genmode_from_dashboard:
            if hardware_mode == "respiratory-rate":
                dashboard_mode = "RR"
            elif hardware_mode == "pulse-oximetry":
                dashboard_mode = "HR"

        data_format = self.extract_data_format(data_col_name)
        data, num_record_error = self.calculate_data(
            data_input, data_format, hardware_mode, user_id, datetime_str)

        # remove [0,0,0] at the end
        if sum(data[-1]) == 0:
            data = data[0:-1, :]

        if data_format == "1":
            datetime_sensor = date_time
        else:
            for j in range(len(data)-1, -1, -1):
                record_time_stamp = data[j, 0]
                if record_time_stamp != 4294967295:
                    break

            datetime_sensor_str = dt.datetime.fromtimestamp(
                record_time_stamp).strftime(settings.datetime_format)

            split_datetime = datetime_sensor_str.split(" ")

            datetime_sensor, _ = convert_str_to_datetime(
                datetime_sensor_str, settings.make_timezone_aware, settings.datetime_format)

        attrs.update(
            {
                "datetime_gateway_sent": date_time,
                "date_time": date_time,
                "datetime_sensor": datetime_sensor,
                "filename": filename,
                "filepath": filepath_rawdata,
                "is_genmode_from_dashboard": is_genmode_from_dashboard,
                "dashboard_mode": dashboard_mode,
                "datetime_server_received": datetime_server_received,
                "hardware_mode": hardware_mode,
                "num_record_error": num_record_error,
                "data": data,
            }
        )

        create_directory(path_raw_data)  # create a folder on user id

        return attrs

    def concat_previous_new_obj(self, obj, validated_data):
        previous_data = load_rawdata(validated_data.get("filepath"))
        np.vstack([previous_data, validated_data.get("data")])

        obj.packet_number = f'{obj.packet_number},{validated_data.get("packet_number")}'
        obj.datetime_sensor = validated_data.get("datetime_sensor")
        obj.datetime_server_received = validated_data.get(
            "datetime_server_received")
        obj.num_record_error = validated_data.get(
            "num_record_error")+get_object_attribute(obj, 'num_record_error', 0)
        obj.save()
        return obj

    def get_utc_offset(self, validated_data):
        try:
            patient_data = validated_data.get("user_id")
            org_timezone = get_patient_timezone(patient_data)
            org_tz = pytz.timezone(org_timezone)
            org_time = dt.datetime.now(org_tz)
            raw_offset = org_time.strftime("%z")
            offset_str = f"{raw_offset[0]}{raw_offset[1:3]}:{raw_offset[3:]}"
            return offset_str
        except Exception as e:
            logging.error(f"Failed to compute utc_offset: {e}")
            return "+00:00"

    def create(self, validated_data):
        write_array_to_file(validated_data.get('data'),
                            validated_data.get("filepath"))
        obj = DataProcessing.objects.filter(user_id=validated_data.get(
            "user_id"), date_time=validated_data.get("date_time")).first()


        # get sensor version
        try:
            url_sensor = urljoin(
                settings.UI_URL_REST_API_BASE, f"{settings.UI_URL_REST_API_SENSOR}/{validated_data.get('sensorID')}"
            )
            HEADERS = {
                "accept": "*/*",
                "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
                "Content-Type": "application/json",
            }

            response_sensor = requests.get(url_sensor, headers=HEADERS).json()
            sensor_version = response_sensor.get("fwVersion", None)

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err = "\n".join(traceback.format_exception(*sys.exc_info()))
            logging.error(f"error when getting sensor details. error message is {err}")
            sensor_version = None


        if obj:
            obj = self.concat_previous_new_obj(obj, validated_data)
        else:
            del validated_data["data"]
            validated_data["utc_offset"] = self.get_utc_offset(validated_data)
            obj = DataProcessing.objects.create(**validated_data)
        obj.sensor_version = sensor_version


        try:
            org_timezone = common.get_patient_timezone(str(validated_data.get('user_id')))
            org_tz = pytz.timezone(org_timezone)
            org_time = dt.datetime.now(org_tz)
            offset_str = f'{org_time.strftime("%z")[0:3]}:{org_time.strftime("%z")[3:]}'
        except Exception as e:
            logging.error(f"Fail to get patient timezone. error message is {e}.")
            offset_str = "+00:00"
        obj.utc_offset = offset_str
        obj.save()

        current_packet_size = len(obj.packet_number.split(','))
        if current_packet_size >= validated_data.get('total_packet'):
            timeout = 0
        else:
            timeout = settings.wait_for_next_packet

        func_kwargs = {
            'user_id': obj.user_id,
            'date_time': obj.date_time,
            'previous_packet_size': current_packet_size,
            'packet_number': obj.packet_number,
            'total_packet': obj.total_packet,
            'datetime_server_received': obj.datetime_server_received,
            'dashboard_mode': obj.dashboard_mode,
            'hardware_mode': obj.hardware_mode
        }
        # calculate_metric.apply_async(kwargs=func_kwargs, countdown=timeout)
        calculate_metric(**func_kwargs)

        return obj

class UpdateCacheSerializer(serializers.Serializer):
    date_time = serializers.DateTimeField(required=True)
    ids = serializers.ListField(required=True)
    utc_offset = serializers.CharField(required=True)

    def validate_utc_offset(self, attr):
        if not check_if_utc_format(attr):
            raise rest_exception.ValidationError('Invalid value provided.')
        return attr


class MetricCacheSerializer(serializers.ModelSerializer):

    class Meta:
        model = MetricDailyCache
        fields = '__all__'

class HealthDataSerializer(serializers.ModelSerializer):

    class Meta:
        model = HealthData
        fields = '__all__'


class BPDeviceDataSerializer(serializers.Serializer):
    userId = serializers.FloatField(required=True)
    bloodPressureSystolic = serializers.FloatField(required=True)
    bloodPressureDiastolic = serializers.FloatField(required=True)
    source = serializers.CharField(required=True)
    deviceId = serializers.CharField(required=True)
    datetime = serializers.DateTimeField(required=True)

    def create(self, validated_data):
        return OtherDeviceReading.objects.create(user_id = validated_data['userId'],
            bp_sys = validated_data['bloodPressureSystolic'],
            bp_dia = validated_data['bloodPressureDiastolic'],
            datetime = validated_data['datetime'],
            source = validated_data['source']
            )


class OtherDeviceReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model = OtherDeviceReading
        fields = '__all__'


class PatientListCacheQueryParamSerializer(serializers.Serializer):
    organizationId = serializers.CharField(required=True, max_length=255)
    userId = serializers.CharField(required=True)
    resolution = serializers.CharField(required=True)
    timestamp = serializers.CharField(required=True)

    def validate_timestamp(self, value):
        try:
            # Try to parse the timestamp to check if it is in the correct format

            value = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            raise serializers.ValidationError(
                "Timestamp must be in the format yyyy-mm-ddThh:mm:ss"
            )
        return value

    def validate_userId(self, value):
        # Validate that userIds are comma-separated

        try:
            user_id_list = [int(user_id) for user_id in value.split(",")]
        except ValueError:
            raise serializers.ValidationError("userId is invalid")
        return user_id_list

    def validate_resolution(self, value):
        # Validate that resolution is comma-separated

        resolutions = value.split(",")
        possible_resolutions = ["minutes", "hourly", "daily"]
        for resolution in resolutions:
            if resolution not in possible_resolutions:
                raise serializers.ValidationError("Invalid resolution")
        return resolutions

    def validate_organizationId(self, value):
        if not value.strip():
            raise serializers.ValidationError("Organization ID must not be empty")
        return value



class CachePatientListSerializer(serializers.Serializer):
    userId = serializers.SerializerMethodField(read_only=True)
    readings = serializers.SerializerMethodField(read_only=True)
    risk = serializers.SerializerMethodField(read_only=True)
    dataCollection = serializers.SerializerMethodField(read_only=True)
    device = serializers.SerializerMethodField(read_only=True)

    def get_userId(self, obj):
        return obj["user_id"]

    def _compute_latest_vitals(self, cache_data, resolution):
        """
        Determine the latest valid value for each vital sign based on timestamp fields.
        """

        val_nan = getattr(settings, "val_replace_NaN", None)

        latest_vital_mapping = {
            "rr": {
                "rr": {"minutes": "datetime_latest_valid_chest", "other": "datetime_rr"},
                "manual_data_rr": "datetime_manual_data_rr",
                "emr_rr": "datetime_emr_rr"
            },
            "hr": {
                "hr": {"minutes": "datetime_latest_valid_finger", "other": "datetime_hr"},
                "manual_data_hr": "datetime_manual_data_hr",
                "emr_hr": "datetime_emr_hr"
            },
            "spo2": {
                "spo2": {"minutes": "datetime_latest_valid_finger", "other": "datetime_spo2"},
                "manual_data_spo2": "datetime_manual_data_spo2",
                "emr_spo2": "datetime_emr_spo2"
            },
            "skinTemp": {
                "skin_temperature": {"minutes": "datetime_latest_valid_chest", "other": "datetime_skin_temperature"},
            },
            "bodyTemp": {
                "body_temperature": {"minutes": None, "other": "datetime_body_temperature"},
                "manual_data_body_temp": "datetime_manual_data_body_temp",
                "emr_body_temperature": "datetime_emr_body_temperature"
            },
            "activity": {
                "activity": {"minutes": "datetime_latest_valid_chest", "other": "datetime_activity"},
            },
            "bpDia": {
                "bp_dia": {"minutes": None, "other": "datetime_bp_dia"},
                "manual_data_bp_dia": "datetime_manual_data_bp_dia",
                "emr_bp_dia": "datetime_emr_bp_dia",
                "other_bp_dia": "datetime_other_bp_dia"
            },
            "bpSys": {
                "bp_sys": {"minutes": None, "other": "datetime_bp_sys"},
                "manual_data_bp_sys": "datetime_manual_data_bp_sys",
                "emr_bp_sys": "datetime_emr_bp_sys",
                "other_bp_sys": "datetime_other_bp_sys"
            }
        }

        latest_vital = {}

        for vital_name, mappings in latest_vital_mapping.items():
            valid_entries = []
            for value_key, datetime_key in mappings.items():
                if isinstance(datetime_key, dict):
                    datetime_key = datetime_key.get(resolution, None)
                    if not datetime_key:
                        continue
                value = cache_data.get(value_key)
                timestamp_str = cache_data.get(datetime_key)

                if value in [None, val_nan, "NaN", "nan", ""] or not timestamp_str:
                    continue

                try:
                    dt_obj = dt.datetime.strptime(str(timestamp_str), "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue

                valid_entries.append((dt_obj, value))

            latest_vital[vital_name] = (
                max(valid_entries, key=lambda x: x[0])[1] if valid_entries else val_nan
            )

        logging.debug(f"[CachePatientListSerializer] LatestVitals computed for user {cache_data.get('user_id')}: {latest_vital}")
        return latest_vital

    def get_readings(self, obj):
        context_dict = self.context["context_dict"]
        resolution = context_dict.get("organization_resolution", "")  # default to minute
        data = {"sensor": {}}

        # Sensor vitals
        sensor_vitals = {
            "hr": {
                "vital_key": "hr",
                "timestamp_key": "datetime_hr",
                "datetime_latest_valid_key": "datetime_latest_valid_finger",
            },
            "rr": {
                "vital_key": "rr",
                "timestamp_key": "datetime_rr",
                "datetime_latest_valid_key": "datetime_latest_valid_chest",
            },
            "spo2": {
                "vital_key": "spo2",
                "timestamp_key": "datetime_spo2",
                "datetime_latest_valid_key": "datetime_latest_valid_finger",
            },
            "skinTemp": {
                "vital_key": "skin_temperature",
                "timestamp_key": "datetime_skin_temperature",
                "datetime_latest_valid_key": "datetime_latest_valid_chest",
            },
            "bodyTemp": {"vital_key": None, "timestamp_key": None},
            "activity": {
                "vital_key": "activity",
                "timestamp_key": "datetime_activity",
                "datetime_latest_valid_key": "datetime_latest_valid_chest",
            },
        }

        manual_vitals = {
            "rr": {"vital_key": "manual_data_rr", "timestamp_key": "datetime_manual_data_rr"},
            "hr": {"vital_key": "manual_data_hr", "timestamp_key": "datetime_manual_data_hr"},
            "SpO2": {"vital_key": "manual_data_spo2", "timestamp_key": "datetime_manual_data_spo2"},
            "bodyTemp": {"vital_key": "manual_data_body_temp", "timestamp_key": "datetime_manual_data_body_temp"},
            "bpSys": {"vital_key": "manual_data_bp_sys", "timestamp_key": "datetime_manual_data_bp_sys"},
            "bpDia": {"vital_key": "manual_data_bp_dia", "timestamp_key": "datetime_manual_data_bp_dia"},
        }

        emr_vitals = {
            "rr": {"vital_key": "emr_rr", "timestamp_key": "datetime_emr_rr"},
            "hr": {"vital_key": "emr_hr", "timestamp_key": "datetime_emr_hr"},
            "spo2": {"vital_key": "emr_spo2", "timestamp_key": "datetime_emr_spo2"},
            "bodyTemp": {"vital_key": "emr_body_temperature", "timestamp_key": "datetime_emr_body_temperature"},
            "bpSys": {"vital_key": "emr_bp_dia", "timestamp_key": "datetime_emr_bp_sys"},
            "bpDia": {"vital_key": "emr_bp_sys", "timestamp_key": "datetime_emr_bp_dia"},
        }

        other_vitals = {
            "bpSys": {"vital_key": "other_bp_sys", "timestamp_key": "datetime_other_bp_sys"},
            "bpDia": {"vital_key": "other_bp_dia", "timestamp_key": "datetime_other_bp_dia"},
        }

        # --- SENSOR SECTION (applies to all resolutions) ---
        for key, val in sensor_vitals.items():
            if val["vital_key"] is None:
                data["sensor"][key] = settings.val_replace_NaN
                continue

            vital_value = obj.get(val["vital_key"])
            timestamp = obj.get(val["timestamp_key"])

            # Latest valid datetime check (for certain vitals)
            if resolution == "minutes":
                if val["vital_key"] in ["hr", "spo2", "rr", "activity", "skin_temperature"]:
                    latest_valid = obj.get(val["datetime_latest_valid_key"])
                    if not latest_valid:
                        data["sensor"][key] = settings.val_replace_NaN
                        continue
            else:            
                if not timestamp or not (context_dict["threshold_date"] <= timestamp <= context_dict["timestamp"]):
                    data["sensor"][key] = settings.val_replace_NaN
                    continue

                time_diff = (context_dict["timestamp"] - latest_valid).total_seconds() / context_dict["denominator"]
                if time_diff > context_dict["timedelta"]:
                    data["sensor"][key] = settings.val_replace_NaN
                    continue

            data["sensor"][key] = vital_value

        # --- ONLY for minute resolution, add manual/emr/other ---
        if resolution == "minutes":
            data["manual"] = {}
            data["emr"] = {}
            data["other"] = {}

            for vital_type, vitals in [
                ("manual", manual_vitals),
                ("emr", emr_vitals),
                ("other", other_vitals),
            ]:
                for key, val in vitals.items():
                    if val["vital_key"] is None:
                        data[vital_type][key] = settings.val_replace_NaN
                        continue

                    vital_value = obj.get(val["vital_key"])
                    timestamp = obj.get(val["timestamp_key"])

                    if not timestamp or not (context_dict["threshold_date"] <= timestamp <= context_dict["timestamp"]):
                        data[vital_type][key] = settings.val_replace_NaN
                    else:
                        data[vital_type][key] = vital_value

        data["latestVitals"] = self._compute_latest_vitals(obj, resolution)
        return data


    def get_risk(self, obj):
        return {"ews": obj.get("news", settings.val_replace_NaN)}

    def get_dataCollection(self, obj):
        data = {
            "daily": {
                "timestamp": [],
                "amountDataInHrsChest": [],
                "amountDataInHrsFinger": [],
            }
        }
        if obj["data_sync"] not in [None]:
            for item in obj["data_sync"]:
                data["daily"]["timestamp"].append(item.get("timestamp"))
                data["daily"]["amountDataInHrsChest"].append(
                    item.get("amount_data_in_hrs_chest")
                )
                data["daily"]["amountDataInHrsFinger"].append(
                    item.get("amount_data_in_hrs_finger")
                )
        return data

    def get_device(self, obj):

        data = {"sensor": {}, "gateway": {}}
        device_data = self.context["context_dict"]["device_data"][obj["user_id"]]

        device_gateway_mapping = {
            "gatewayStatus": "gateway_status",
            "lastConnection": "last_gateway_connect",
        }

        for key, val in device_gateway_mapping.items():
            data["gateway"][key] = device_data[val]
        data["sensor"]["battery"] = obj["battery"]
        data["sensor"]["batteryChest"] = obj["battery_chest"]
        data["sensor"]["batteryFinger"] = obj["battery_finger"]

        data["sensor"]["sensorStatusGen"] = device_data["sensor_status"]
        data["sensor"]["sensorLastConnectionChest"] = device_data[
            "sensor_chest_last_connect_time"
        ]
        data["sensor"]["sensorStatusChest"] = device_data["sensor_status_chest"]
        data["sensor"]["sensorLastConnectionFinger"] = device_data[
            "sensor_finger_last_connect_time"
        ]
        data["sensor"]["sensorStatusFinger"] = device_data["sensor_status_finger"]

        skin_contact_data = obj["skin_contact_data"]
        try:
            if skin_contact_data:
                skin_contact_data.sort(key=lambda x: dt.datetime.strptime(x['dateTime'], "%Y-%m-%d %H:%M:%S"), reverse=True)
                latest_entries = skin_contact_data[:4]
                on_skin = common.check_skin_status_sequence(latest_entries, 4)

                data["sensor"]["skinContactGen"] = (
                    "Bad" if on_skin == 0 or on_skin == None else "Good"
                )

                hr_list = [
                    d for d in skin_contact_data if d.get("dashboard_mode") == "HR"
                ]
                rr_list = [
                    d for d in skin_contact_data if d.get("dashboard_mode") == "RR"
                ]

                if rr_list:
                    on_skin_rr = common.check_skin_status_sequence(
                        rr_list, len(rr_list), 'display_label'
                    )
                    data["sensor"]["skinContactChest"] = (
                        None
                        if on_skin_rr == settings.val_replace_NaN
                        else "Bad" if on_skin_rr == 0 else "Good"
                    )
                else:
                    data["sensor"]["skinContactChest"] = None
                if hr_list:
                    on_skin_hr = common.check_skin_status_sequence(
                        hr_list, len(hr_list), 'sensor_onskin_status'
                    )
                    data["sensor"]["skinContactFinger"] = (
                        None
                        if on_skin_hr == settings.val_replace_NaN
                        else "Bad" if on_skin_hr == 0 else "Good"
                    )
                else:
                    data["sensor"]["skinContactFinger"] = None
            else:
                data["sensor"]["skinContactGen"] = None
                data["sensor"]["skinContactChest"] = None
                data["sensor"]["skinContactFinger"] = None
        except Exception as e:
            logging.error(
                f"Error while processing skin_contact_data for entry, Error {e}"
            )
            data["sensor"]["skinContactGen"] = None
            data["sensor"]["skinContactChest"] = None
            data["sensor"]["skinContactFinger"] = None
        return data
