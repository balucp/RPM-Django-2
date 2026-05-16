from . import lib_query
import datetime
import json
import math
import pandas as pd
import pytz
import sys
import traceback
from django.http import JsonResponse
from rest_framework import status
from decimal import Decimal
from drf_yasg.utils import swagger_auto_schema
from urllib.parse import urljoin
from drf_yasg import openapi
from django.http import HttpResponse
from io import BytesIO as IO
from .authentication import DataProcessAuthentication, GatewayAuthentication
from .serializers import *
from .swagger_custom_serializers import *
from .tasks import handle_update_cache_query
from . import lib_common as common
from .helpers import get_utc_offset, check_if_utc_format, merge_dataframes_allow_empty
from .lib_query import (
    get_latest_health_input,
    display_battery,
    get_latest_input,
    query_observations_data_input
)
from .lib_query_data_syncing import (
    get_data_syncing_trends,
    get_data_syncing_trends_list,
)
from .lib_update_spot_cache import spot_cache_update
from dataprocessing import lib_settings as settings
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework import exceptions as rest_exception
from urllib.parse import unquote
from .handle_views import (
    handle_spot_query,
    handle_spot_query_via_cache,
    handle_trend_query,
    get_trends_export,
    append_list_date_export,
    get_trend_from_cache,
    get_bp_device_data,
    get_manual_health_input,
    get_bp_device_spot,
    handle_query_vital_readings,
    handle_query_monitoring_data,
    handle_query_master_cache_patient_list,
    run_manual_hourly_job
)
from django.utils.timezone import make_aware
from django.forms.models import model_to_dict
import requests

HEADERS = {
    "accept": "*/*",
    "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
    "Content-Type": "application/json",
}

class HealthCheckView(APIView):
    def get(self, request):
        return Response(
            {"status": "ok", "message": "Service is up and running."},
            status=status.HTTP_200_OK,
        )


class UploadView(APIView):
    authentication_classes = (GatewayAuthentication,)
    # authentication_classes = ()
    # permission_classes = ()
    serializer_class = UploadSerializer

    @swagger_auto_schema(
        operation_description="Upload data from the gateway to the server.",
        request_body=UploadSerializer,
        responses={200: UploadResponseSerializer},
        manual_parameters=[
            openapi.Parameter(
                "Referer",
                openapi.IN_HEADER,
                description="Referer",
                type=openapi.TYPE_STRING,
            )
        ],
    )
    def post(self, request, *args, **kwargs):

        if "body-json" in request.data:
            data = request.data["body-json"]
        else:
            data = request.data
        serializer_var = self.serializer_class(data=data)
        if serializer_var.is_valid(raise_exception=True):
            instance = serializer_var.save()

        return Response(
            {
                "userID": instance.user_id,
                "dateTimeGatewaySent": instance.datetime_gateway_sent.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "dateTimeServerReceived": instance.datetime_server_received.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )


class QuerySpotView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter(
            "date_time",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True
        ),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]


    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get("date_time"):
            raise rest_exception.ValidationError(
                {"date_time": ["this field is required."]}
            )
        if not request.GET.get("id"):
            raise rest_exception.ValidationError({"id": ["this field is required."]})
        try:
            date_time = datetime.datetime.strptime(
                request.GET.get('date_time'), '%Y-%m-%dT%H:%M:%S')
            if settings.make_timezone_aware:
                date_time = make_aware(date_time)
        except:
            raise rest_exception.ValidationError(
                {"date_time": ["format should be %Y-%m-%dT%H:%M:%S"]}
            )

        try:
            response = handle_spot_query_via_cache(request.GET.get("id"), date_time)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err = "\n".join(traceback.format_exception(*sys.exc_info()))
            logging.error(f"failed request  /api/spot. error message is {err}")

        return Response({"statusCode": 200, "response": response})


class QueryTrendView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter(
            "id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True
        ),
        openapi.Parameter(
            "resolution",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            enum=(
                "daily",
                "hourly",
                "minutes",
            ),
            required=True,
        ),
        openapi.Parameter(
            "start_datetime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "stop_datetime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "utc_offset", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )

    ]




    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get("stop_datetime"):
            raise rest_exception.ValidationError(
                {"stop_datetime": ["This field is required."]}
            )
        if not request.GET.get("id"):
            raise rest_exception.ValidationError({"id": ["This field is required."]})
        if not request.GET.get("resolution"):
            raise rest_exception.ValidationError(
                {"resolution": ["This field is required."]}
            )
        if request.GET.get("resolution") not in (
            "daily",
            "hourly",
            "minutes",
        ):
            raise rest_exception.ValidationError(
                {"resolution": ["Invalid resolution."]}
            )
        if request.GET.get("start_datetime"):
            try:
                start_datetime = datetime.datetime.strptime(
                    request.GET.get("start_datetime"), "%Y-%m-%dT%H:%M:%S"
                )
            except:
                raise rest_exception.ValidationError(
                    {"start_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]}
                )
        try:
            stop_datetime = datetime.datetime.strptime(
                request.GET.get("stop_datetime"), "%Y-%m-%dT%H:%M:%S"
            )
        except:
            raise rest_exception.ValidationError(
                {"stop_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]}
            )

        if settings.make_timezone_aware:
            start_datetime = make_aware(start_datetime)
            stop_datetime = make_aware(stop_datetime)

        if request.GET.get('utc_offset'):
            if not check_if_utc_format(request.GET.get('utc_offset')):
                raise rest_exception.ValidationError(
                    {"utc_offset": ["Invalid value provided."]}
                )

        return Response(
            {
                "statusCode": 200,
                "response": handle_trend_query(
                    start_datetime,
                    stop_datetime,
                    request.GET.get("id"),
                    request.GET.get("resolution"),
                    utc_offset=request.GET.get("utc_offset"),
                ),
            }
        )


class QueryPatientListView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter('list_of_id', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Accept comma seperated ids'),
        openapi.Parameter('resolution', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=(
            'daily', 'hourly', 'minutes',), required=True),
        openapi.Parameter('date_time', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Acceptable format yyyy-mm-ddThh:mm:ss'),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]


    def get_cache_latest(self,ids_list, date_time, utc_offset,resolution):

        ids = [id.strip() for id in ids_list.split(',')]

        try:
            if not utc_offset:
                # we assume all IDs come from the same Organization
                timezone = common.get_patient_timezone(ids[0])
                offset = datetime.datetime.now(pytz.timezone(timezone)).utcoffset()
            else:
                offset = get_utc_offset(utc_offset)
                offset = datetime.timedelta(hours=utc_offset[0], minutes=utc_offset[1])
        except Exception as e:
            offset = datetime.timedelta(hours=0, minutes=0)

        stop_date_time = date_time

        if resolution == "hourly":
            list_timedelta_resolution = "HOURS"
            start_date_time = stop_date_time - datetime.timedelta(
                hours=settings.list_timedelta[list_timedelta_resolution]
            )
            stop_datetime_updated = ((stop_date_time + offset).replace(minute=0, second=0, microsecond=0) - offset)
            start_datetime_updated = ((start_date_time + offset).replace(minute=0, second=0, microsecond=0) - offset)
        else:
            list_timedelta_resolution = "DAYS"
            start_date_time = stop_date_time - datetime.timedelta(
                days=settings.list_timedelta[list_timedelta_resolution] - 1
            ) 
            stop_datetime_updated = ((stop_date_time + offset).replace(hour=0, minute=0, second=0, microsecond=0) - offset)
            start_datetime_updated = ((start_date_time + offset).replace(hour=0, minute=0, second=0, microsecond=0) - offset)

        latest = {}
        for current_id in ids:

            if resolution == 'hourly':
                query_items = MetricHourlyCache.objects.filter(
                    user_id=current_id, datetime_updated__range=(start_datetime_updated, stop_datetime_updated)
                ).order_by('datetime_updated').values()
            else:

                # Generate datetime range
                pd_start_date = pd.to_datetime(start_datetime_updated)
                pd_end_date = pd.to_datetime(stop_datetime_updated)
                date_range = pd.date_range(start=pd_start_date, end=pd_end_date, freq='D')
                df_date_range = pd.DataFrame({"dateTimeUpdated": date_range})
                df_date_range["dateTimeUpdated"] = df_date_range["dateTimeUpdated"].dt.strftime("%Y-%m-%d %H:%M:%S")
                datetime_updated_list = pd.to_datetime(df_date_range["dateTimeUpdated"]).to_list()
                datetime_list = [ts.to_pydatetime() for ts in datetime_updated_list]

                query_items = MetricDailyCache.objects.filter(
                    user_id=current_id, datetime_updated__in=datetime_updated_list).order_by('datetime_updated').values()

            if len(query_items) > 0:
                df = pd.DataFrame.from_records(query_items)
                last_item = df.sort_values("datetime_updated", ascending=False).apply(
                    lambda col: col.dropna().iloc[0] if col.name != "datetime_updated" and not col.dropna().empty else None
                )

                last_item = last_item.fillna(-1).to_dict()

                latest_item = {k: (v if v is not None else -1) for k, v in last_item.items()}

                # rename fields to accommodate existing logic
                map_fields = {
                    "weight": "weight_manual",
                    "blood_sugar": "blood_sugar_manual",
                    "news": "EWS"
                }
                for old_name, new_name in map_fields.items():
                    if old_name in latest_item:
                        latest_item[new_name] = latest_item.pop(old_name)

            else:
                latest_item = {}
            latest[current_id] = latest_item

        return latest


    def handle_list_query(self, list_id, date_time):
        windowsize_baseline = settings.windowsize_baseline
        startDateTime = date_time - \
            datetime.timedelta(minutes=windowsize_baseline)  # last N minutes
        stopDateTime = date_time
        logging.info("patient list lookback config is {} minutes (from [{}] to [{}])".format(
            windowsize_baseline, startDateTime, stopDateTime))
        val_replace_NaN = settings.val_replace_NaN
        list_demo_id = settings.list_demo_id
        response = {}
        list_id = [i.strip() for i in list_id]
        data_processing_objs = DataProcessing.objects.filter(user_id__in=list_id, date_time__range=[
                                                                startDateTime, stopDateTime]).order_by('date_time')
        for user_id in list_id:

            if user_id in list_demo_id:
                response[user_id] = lib_query.generate_dummy('list_of_patient')
            else:
                data_processing = data_processing_objs.filter(user_id=user_id)
                response[user_id] = lib_query.get_user_metrics(
                    data_processing, user_id, startDateTime, stopDateTime, val_replace_NaN)
                temp_metrics = lib_query.generate_dummy('metrics')
                try:
                    for key in temp_metrics.keys():
                        del response[user_id][key]
                except Exception as e:
                    logging.error(
                        'error while trying to delete key in patient list. error message is {}'.format(e))

        return response

    def has_recent_data(self, data_processing, date_time):
        timeframe_seconds = 24 * 60 * 60
        if data_processing:
            if (date_time - data_processing.date_time).total_seconds() < timeframe_seconds:
                return True
        return False

    def is_all_valid_medians(self, metrics):
        key_attrs = ['RR', 'HR', 'SpO2', 'skinTemp', 'bodyTemp']
        for attr in key_attrs:
            if attr not in metrics or metrics[attr] or metrics[attr] == settings.val_replace_NaN:
                return False

        return True

    def handle_list_query_via_cache(self, list_id, list_resolution, date_time, latest_cache):

        list_id = [i.strip() for i in list_id]

        dict_devices = common.get_devices_data_multiple(list_id)
        print('dict_devices',dict_devices)


        mapping_dict = {
        'rr' : 'RR',
        'hr' : 'HR',
        'spo2' : 'SpO2',
        'rr_td' : 'RR_TD',
        'bp_sys' : 'BP_Sys',
        'bp_dia' : 'BP_Dia',
        }


        response = {}
        data_processing_objs = DataProcessing.objects.filter(user_id__in=list_id).order_by('date_time')

        for user_id in list_id:
            # Case 1 - If user is to generate dummy data on the fly
            data_processing = data_processing_objs.filter(user_id=user_id)
            
            if user_id in settings.list_demo_id:
                response[user_id] = lib_query.generate_dummy('list_of_patient')

            # Case 2 - If user is to be loaded from the cache
            else:
                common.load_from_cache(
                    response, user_id, list_resolution, date_time)
                response[user_id].update(dict_devices[user_id])
                common.get_other_spot_data(
                    response, user_id, list_resolution, date_time, data_processing)

            # TO BE REWORKED, this is just a hack
            # pump in daily cache data into the response
            if (list_resolution == 'hourly' or list_resolution == 'daily') and (user_id not in settings.list_demo_id):
                to_update = {
                    "rr": -1,
                    "hr": -1,
                    "spo2": -1,
                    "body_temperature": -1,
                    "rr_td": -1,
                    "bp_sys": -1,
                    "bp_dia": -1,
                    "weight_manual": -1,
                    "blood_sugar_manual": -1,
                    "EWS": -1,
                    "skin_temperature": -1,
                    "activity": -1,
                }

                # reset fields
                response[user_id].update(to_update)
                #take available fields from daily cache
                for field in to_update:
                    if field in latest_cache[user_id]:
                        response[user_id][field] = latest_cache[user_id][field]
                        if field == 'skin_temperature':
                            response[user_id]['skinTemp'] = latest_cache[user_id]['skin_temperature']
                        if field == 'body_temperature':
                            response[user_id]['bodyTemp'] = latest_cache[user_id]['body_temperature']

                response[user_id] = {mapping_dict.get(k, k): v for k, v in response[user_id].items()}
            display_battery(response[user_id],'list',dict_devices[user_id])
        return response

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get('list_of_id'):
            raise rest_exception.ValidationError(
                {'list_of_id': ['This field is required.']})
        if not request.GET.get('resolution'):
            raise rest_exception.ValidationError(
                {'resolution': ['This field is required.']})
        if request.GET.get('resolution') not in ('daily', 'hourly', 'minutes',):
            raise rest_exception.ValidationError(
                {'resolution': ['Invalid resolution.']})
        if not request.GET.get('date_time'):
                raise rest_exception.ValidationError(
                    {'date_time': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if request.GET.get('date_time'):
            try:
                date_time = datetime.datetime.strptime(
                    request.GET.get('date_time'), '%Y-%m-%dT%H:%M:%S')
                date_time = pytz.UTC.localize(date_time)
            except:
                raise rest_exception.ValidationError(
                    {'date_time': ['Format should be %Y-%m-%dT%H:%M:%S']})

        dateTime = datetime.datetime.strptime(self.request.GET.get('date_time'), '%Y-%m-%dT%H:%M:%S')
        try:
            latest_cache = self.get_cache_latest(
                self.request.GET.get("list_of_id"),
                dateTime,
                self.request.GET.get("utc_offset", None),
                self.request.GET.get("resolution"),
            )
        except:
            latest_cache = self.get_cache_latest(
                self.request.GET.get("list_of_id"),
                dateTime,
                self.request.GET.get("utc_offset", None),
                self.request.GET.get("resolution"),
            )

        response = self.handle_list_query_via_cache(request.GET.get(
            'list_of_id').split(','), request.GET.get('resolution'), date_time,latest_cache)


        # get EWS and BP
        if (self.request.GET.get('resolution') == 'minutes'):
            for current_id, current_metric in response.items():

                # get BP. if resolution is daily -> compyte median, and if resolution is minutes -> check if it is in the last 15 min
                #TODO:Than. implement the logic according to the requirement. current implementaion means for demo only.
                # current logic for BP - display latest BP in the last 24 hrs.

                datetime_start = date_time - datetime.timedelta(minutes=settings.list_timedelta['MINUTES'])

                query_items = HealthData.objects.filter(
                    user_id=current_id,
                    datetime__range=(datetime_start, date_time)
                ).order_by('-datetime') 
                query_items = list(query_items.values())

                try:
                    map_heath_input_metrics_config = {
                        "RR_manual": "rr",
                        "HR_manual": "hr",
                        "SpO2_manual": "spo2",
                        "BP_Sys": "bp_sys",
                        "BP_Dia": "bp_dia",
                        "body_temp_manual": "body_temp",
                        "weight_manual": "weight",
                        "blood_sugar_manual": "blood_sugar",
                    }
                    for metric_key, data_key in map_heath_input_metrics_config.items():
                        current_metric[metric_key] = get_latest_input(
                            query_items, data_key, 'manual-health-input'
                        )
                except Exception as e:
                    logging.error(f"failed to get health input. error message is {e}")

                query_items = OtherDeviceReading.objects.filter(
                    user_id=current_id,
                    datetime__range=(datetime_start, date_time)
                ).order_by('-datetime') 
                query_items = list(query_items.values())


                try:
                    map_other_device_metrics_config = {
                        "bp_sys_device": "bp_sys",
                        "bp_dia_device": "bp_dia",
                    }

                    map_emr_input_metrics_config = {
                        "RR_emr": "rr",
                        "HR_emr": "hr",
                        "SpO2_emr": "spo2",
                        "BP_Sys_emr": "bp_sys",
                        "BP_Dia_emr": "bp_dia",
                        "body_temp_emr": "body_temperature",
                        "weight_emr": "weight",
                        "blood_sugar_emr": "blood_sugar",
                        }
                    
                    config_map = {
                        "emr": map_emr_input_metrics_config,
                        "bp-device": map_other_device_metrics_config,
                    }

                    for device_type in settings.other_device_types:
                        metrics_config = config_map.get(device_type, {})
                        for metric_key, data_key in metrics_config.items():
                            current_metric[metric_key] = get_latest_input(
                                query_items, data_key, device_type
                            )

                except Exception as e:
                    logging.error(f"failed to get {device_type} observations. error message is {e}")


                if "EWS" in latest_cache[current_id]:
                    current_metric["EWS"] = latest_cache[current_id]["EWS"]

                for key, value in current_metric.items():
                    if isinstance(value, datetime.datetime):
                        current_metric[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        current_metric[key] = value

                response[current_id] = current_metric

        return Response({"statusCode": 200, "response": response})


class UpdateCacheView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    @swagger_auto_schema(request_body=UpdateCacheSerializer, responses={200: None})
    def post(self, request, *args, **kwargs):
        serializer_var = UpdateCacheSerializer(data=request.data)
        if serializer_var.is_valid(raise_exception=True):
            pass
        date_time = datetime.datetime.strptime(request.data.get(
            'date_time'), '%Y-%m-%dT%H:%M:%S.%fZ')  # to datetime formatto datetime format
        if settings.make_timezone_aware:
            date_time = make_aware(date_time)
        metric_cache_instances = handle_update_cache_query.delay(
            request.data.get("utc_offset"), request.data.get("ids"), date_time
        )
        return Response({"message": "Data updated successfully"})


class QueryDatasyncingtrendView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter(
            "data_type",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            enum=(
                "dateTimeSensor",
                "dateTimeGateway",
            ),
            required=True,
        ),
        openapi.Parameter(
            "id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False
        ),
        openapi.Parameter(
            "list_of_id",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=False,
            description="Accept comma seperated ids",
        ),
        openapi.Parameter(
            "resolution",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            enum=(
                "daily",
                "hourly",
                "minutes",
            ),
            required=True,
        ),
        openapi.Parameter(
            "start_datetime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "stop_datetime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "utc_offset", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]

    def validate_params(self, request):
        if not request.GET.get("resolution"):
            raise rest_exception.ValidationError(
                {"resolution": ["This field is required."]}
            )
        if request.GET.get("resolution") not in (
            "daily",
            "hourly",
        ):
            raise rest_exception.ValidationError(
                {"resolution": ["Invalid resolution."]}
            )
        if not request.GET.get("data_type"):
            raise rest_exception.ValidationError(
                {"data_type": ["This field is required."]}
            )
        if request.GET.get("data_type") not in (
            "dateTimeSensor",
            "dateTimeGateway",
        ):
            raise rest_exception.ValidationError({"data_type": ["Invalid data_type."]})
        if not request.GET.get("start_datetime"):
            raise rest_exception.ValidationError(
                {"start_datetime": ["This field is required."]}
            )
        if not request.GET.get("stop_datetime"):
            raise rest_exception.ValidationError(
                {"stop_datetime": ["This field is required."]}
            )

        if request.GET.get("utc_offset"):
            if not check_if_utc_format(request.GET.get("utc_offset")):
                raise rest_exception.ValidationError(
                    {"utc_offset": ["Invalid value provided."]}
                )

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        """
        Any one from id and list_of_id is required.
        """

        self.validate_params(request)
        try:
            start_datetime = pytz.UTC.localize(
                datetime.datetime.strptime(
                    request.GET.get("start_datetime"), "%Y-%m-%dT%H:%M:%S"
                )
            )
        except:
            raise rest_exception.ValidationError(
                {"start_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]}
            )

        try:
            stop_datetime = pytz.UTC.localize(
                datetime.datetime.strptime(
                    request.GET.get("stop_datetime"), "%Y-%m-%dT%H:%M:%S"
                )
            )
        except:
            raise rest_exception.ValidationError(
                {"stop_datetime": ["Format should be %Y-%m-%dT%H:%M:%S"]}
            )

        # if settings.make_timezone_aware:
        #     if not is_aware(start_datetime):
        #         start_datetime = make_aware(start_datetime)
        #     if not is_aware(stop_datetime):
        #         stop_datetime = make_aware(stop_datetime)

        data_type = request.GET.get('data_type')
        user_id = request.GET.get('id', '')
        list_of_ids = request.GET.get('list_of_ids', '')
        resolution = request.GET.get('resolution')
        if request.GET.get('utc_offset'):
            utc_offset = get_utc_offset(request.GET.get('utc_offset'))
        else:
            utc_offset = [0,0]

        if list_of_ids:
            list_of_ids = [
                str(item) for item in list_of_ids.split(",")
            ]
            response = get_data_syncing_trends_list(
                list_of_ids,
                start_datetime,
                stop_datetime,
                resolution,
                utc_offset,
            )
        elif user_id:

            response = get_data_syncing_trends(
                user_id,
                start_datetime,
                stop_datetime,
                resolution,
                utc_offset,
            )
        else:
            response = {}
        return Response({"statusCode": 200, "response": response})



class ExportView(APIView):
    authentication_classes = ()
    permission_classes = ()
    openapi_params = [
        openapi.Parameter(
            "users",
            openapi.IN_QUERY,
            type="string",
            required=True,
            description="""List of objects in below format 
                          [
                                {
                                    "username":"username",
                                    "id":id,
                                    "utc_offset":"utc_offset"
                                },
                          ]""",
        ),
        openapi.Parameter(
            "data",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Accept comma seperated values",
        ),
        openapi.Parameter(
            "startTime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "endTime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "resolution",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            enum=(
                "daily",
                "hourly",
                "minutes",
            ),
            required=True,
        ),
        openapi.Parameter(
            "organisationName",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=False,
            description="organisation name",
        ),
    ]

    def validate_params(self):
        if not self.request.GET.get("resolution"):
            raise rest_exception.ValidationError(
                {"resolution": ["this field is required."]}
            )
        if not self.request.GET.get("data"):
            raise rest_exception.ValidationError({"data": ["this field is required."]})
        if not self.request.GET.get("startTime"):
            raise rest_exception.ValidationError(
                {"startTime": ["this field is required."]}
            )
        if not self.request.GET.get("endTime"):
            raise rest_exception.ValidationError(
                {"endTime": ["this field is required."]}
            )

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):

        fe_2_be_map = {
            "RR": "rr",
            "HR": "hr",
            "Spo2": "spo2",
            "tidal depth": "rr_td",
            "dutyCycle": "rr_dc",
            "bodyTemp": "body_temperature",
            "skinTemp": "skin_temperature",
            "activity": "activity",
            "skinContact": "sensor_onskin_status",
            "ews": "ews",
            "flag": "flag",
            "wellness_stress": "wellness_stress",
            "sleep_duration_seconds": "sleep_duration_seconds",
            "sensor_onskin_status": "sensor_onskin_status",
            "signal_quality_status": "signal_quality_status",
        }

        desired_2_cond_attr_map = {
            "rr": "RR",
            "hr": "HR",
            "spo2": "HR",
            "rr_td": "RR",
            "rr_dc": "RR",
            "body_temperature": "RR",
            "skin_temperature": "RR",
            "activity": None,
            "ews": None,
            "flag": None,
            "wellness_stress": None,
            "sleep_duration_seconds": None,
            "sensor_onskin_status": "sensor_onskin_status",
            "signal_quality_status": "signal_quality_status",
        }

        csv_column_heading = {
            "rr": "RR",
            "hr": "HR",
            "spo2": "Spo2",
            "rr_td": "RR_TD",
            "rr_dc": "RR_DC",
            "body_temperature": "body_temperature",
            "skin_temperature": "skin_temperature",
            "activity": "activity",
            "ews": "ews",
            "flag": "flag",
            "wellness_stress": "wellness_stress",
            "sleep_duration_seconds": "sleep_duration_seconds",
            "sensor_onskin_status": "sensor_onskin_status",
            "signal_quality_status": "signal_quality_status",
        }


        mhi_fe_2_be_field_mapping = {
            'HR_manual': 'hr',
            'RR_manual': 'rr',
            'Spo2_manual': 'spo2',
            'body_temperature_manual': 'body_temp',
            'blood_sugar': 'blood_sugar',
            'BP_diastolic_manual': 'bp_dia',
            'BP_systolic_manual': 'bp_sys',
            'weight': 'weight',
          
        }

        mhi_be_to_fe_mapping = {
            'datetime': 'dateTime',
            'hr': 'HR (Manual)',
            'rr': 'RR (Manual)',
            'spo2': 'SpO2 (Manual)',
            'body_temp': 'Body Temperature (Manual)',
            'blood_sugar': 'Blood Sugar',
            'bp_dia': 'BP Diastolic (Manual)',
            'bp_sys': 'BP Systolic (Manual)',
            'weight': 'Weight',
        }

        bp_fe_2_be_field_mapping = {
            'BP_diastolic': 'bp_dia',
            'BP_systolic': 'bp_sys',

        }

        bp_be_to_fe_mapping = {
            'datetime': 'dateTime',
            'bp_dia': 'BP Diastolic',
            'bp_sys': 'BP Systolic',
        }

        cache_be_to_fe_mapping = {
            'datetime_updated': 'dateTime',
            'listdate': 'dateTime',
            'listtime': 'dateTime',
            'rr': 'RR',
            'hr': 'HR',
            'spo2': 'SpO2',
            'skin_temperature': 'skin_temperature',
            'EWS': 'ews',
            'activity': 'activity',
            'rr_td': 'RR_TD',
            'rr_dc': 'RR_DC',
            'bp_dia': 'BP Diastolic',
            'bp_sys': 'BP Systolic'
                }

        cache_columns = {
            'RR': 'rr',
            'HR': 'hr',
            'Spo2': 'spo2',
            'tidal depth': 'rr_td',
            'dutyCycle': 'rr_dc',
            'bodyTemp': 'body_temperature',
            'skinTemp': 'skin_temperature',
            'activity': 'activity',
            'ews': 'EWS',
            'BP_diastolic': 'bp_dia',
            'BP_systolic': 'bp_sys'
        }

        sensor_columns = {
            'flag': 'flag',
            'wellness_stress': 'wellness_stress',
            'sleep_duration_seconds': 'sleep_duration_seconds',
            'sensor_onskin_status': 'sensor_onskin_status',
            'signal_quality_status': 'signal_quality_status', 
        }

        fe_2_ai_map = {
            'predictionScoreRr' : 'Prediction Score: Respiratory Rate Only Model',
            'predictionScoreRrHr' : 'Prediction Score: Respiratory Rate, Heart Rate Model',
            'predictionScoreRrHrSpo2' : 'Prediction Score: Respiratory Rate, Heart Rate, SPO2 Model',
            'predictionScoreRrHrSpo2Bpsys' : 'Prediction Score: Respiratory Rate, Heart Rate, SPO2, Blood Pressure Model',
            'predictionScoreDynamic' : 'Prediction Score: Dynamic Model',
        }

        excel_table_field_mapping = {
            'outcome_rr': 'Prediction Score: Respiratory Rate Only Model',
            'outcome_rr_hr': 'Prediction Score: Respiratory Rate, Heart Rate Model',
            'outcome_rr_hr_spo2': 'Prediction Score: Respiratory Rate, Heart Rate, SPO2 Model',
            'outcome_rr_hr_spo2_bp_sys': 'Prediction Score: Respiratory Rate, Heart Rate, SPO2, Blood Pressure Model',
            'outcome_dynamic_model': 'Prediction Score: Dynamic Model',
        }


        def fetch_predictions(user_id, start_datetime_str, end_datetime_str, resolution, utc_offset):

            PATIENT_PREDICTION_SCORE_URL = urljoin(
                settings.AI_BACKEND_URL, settings.UI_URL_REST_API_getPredictionScore
            )

            start_datetime = start_datetime_str
            end_datetime = end_datetime_str
            if ':' not in utc_offset:
                hours = int(utc_offset)
                minutes = 0
            else:
                parts = utc_offset.split(':')
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
            utc_offset_str = f'{hours:02}:{minutes:02}'
            offset = datetime.timedelta(hours=hours, minutes=minutes)
            start_datetime_with_offset = start_datetime + offset
            end_datetime_with_offset = end_datetime + offset
            start_datetime_str_with_offset = start_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
            end_datetime_str_with_offset = end_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
            params = {
                "user_ids[]": user_id,
                "start_datetime": start_datetime_str_with_offset,
                "end_datetime": end_datetime_str_with_offset,
                "resolution": resolution,
                "utc_offset": utc_offset_str
            }
            try:
                response = requests.get(PATIENT_PREDICTION_SCORE_URL, params=params, headers=HEADERS)
                response.raise_for_status()
                data = response.json().get('data', [])
                return data
            except Exception as e:
                logging.error(f"Error fetching predictions: {e}")
                return []


        self.validate_params()
        resolution = (
            "minutes"
            if request.GET.get("resolution") == "minute"
            else request.GET.get("resolution")
        )
        users = json.loads(unquote(request.GET.get("users")))
        userIDs = [str(x["id"]) for x in users]
        userNames = [str(x["username"]) for x in users]
        utc_offsets = [get_utc_offset(str(x["utc_offset"])) for x in users]

        utc_offsets =  [{'hours': hours, 'minutes': minutes} for hours , minutes in utc_offsets]
        timezone_obj = datetime.timezone(datetime.timedelta(hours=utc_offsets[0]['hours'], minutes=utc_offsets[0]['minutes']))

        startDateTime = datetime.datetime.strptime(
            request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"
        ).strftime("%Y-%m-%d %H:%M:%S")
        stopDateTime = datetime.datetime.strptime(
            request.GET['endTime'], '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
        if 'organisationName' in request.GET:
            OrganisationName = request.GET['organisationName']
        else:
            OrganisationName = None
    
        if settings.make_timezone_aware:
            startDateTime = make_aware(datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"))
            stopDateTime = make_aware(datetime.datetime.strptime(request.GET["endTime"], "%Y-%m-%dT%H:%M:%S"))

        # Filter 3 - Filter by resolution
        # data_length = len(queryItems)
        trends_vital_sign_minutes_resolution = settings.trends_vital_sign_minutes_resolution
        if resolution == 'hourly':
            data_length = math.ceil((stopDateTime - startDateTime).total_seconds()/3600)
        elif resolution == 'daily':
            data_length = (stopDateTime - startDateTime).days + 1
        elif resolution == 'minutes':
            data_length = math.ceil((stopDateTime - startDateTime).total_seconds()/60)
            data_length = math.ceil(data_length/trends_vital_sign_minutes_resolution)

        data_fields = [x.strip() for x in request.GET["data"].split(",")]
        desired_attr = [fe_2_be_map[x] for x in data_fields if x in fe_2_be_map]
        cond_attr = [desired_2_cond_attr_map[x] for x in desired_attr]

        if resolution in ['minutes']:
            mhi_attr = [mhi_fe_2_be_field_mapping[x] for x in data_fields if x in mhi_fe_2_be_field_mapping]
            bp_attr = [bp_fe_2_be_field_mapping[x] for x in data_fields if x in bp_fe_2_be_field_mapping]
            excel_col_order = [
                csv_column_heading[fe_2_be_map[f]] if f in fe_2_be_map else mhi_be_to_fe_mapping[mhi_fe_2_be_field_mapping[f]] if f in mhi_fe_2_be_field_mapping else bp_be_to_fe_mapping[bp_fe_2_be_field_mapping[f]]
                for f in data_fields
                if f in fe_2_be_map or f in mhi_fe_2_be_field_mapping or f in bp_fe_2_be_field_mapping
            ]


        if resolution in ['daily', 'hourly']:
            cache_cols = ['rr', 'rr_dc', 'rr_td', 'hr', 'skin_temperature', 'spo2', 'activity', 'ews']
            cache_fields =  [cache_columns[key] for key in data_fields if key in cache_columns]
            if resolution == 'daily':
                cache_fields.append('listdate')
            if resolution == 'hourly':
                cache_fields.append('listtime')
            sensor_fields = [sensor_columns[key] for key in data_fields if key in sensor_columns]

            excel_col_order = [
                d[f]
                for f in data_fields
                for d in (cache_columns, sensor_columns)
                if f in d
            ]

        if resolution in ['minutes', 'hourly']:
            ai_response = fetch_predictions(userIDs, startDateTime, stopDateTime, resolution, users[0]['utc_offset'])
            prediction_lookup = {item["user_id"]: item["prediction_data"] for item in ai_response}

            print('prediction_lookup',prediction_lookup)

        all_dfs = []
        data_processing_obj = DataProcessing.objects.filter(
            date_time__range=(startDateTime, stopDateTime))
        for index, userID in enumerate(userIDs):
            data_processing = data_processing_obj.filter(user_id=userID)
            queryItems = data_processing.values('user_id','rr','hr','spo2','date_time','dashboard_mode')

            if resolution in ['daily', 'hourly']:
                # Step 4: Calculate the metrics and std dev information
                options = {
                    "data_length": data_length,
                    "resolution": resolution,
                    "valReplaceNaN": settings.val_replace_NaN,
                    "min_hr_finger_required_within_hour": settings.min_hr_finger_required_within_hour,
                    "min_hr_finger_required_within_day": settings.min_hr_finger_required_within_day,
                    "trends_vital_sign_minutes_resolution": settings.trends_vital_sign_minutes_resolution,
                    "utc_offset": utc_offsets[index],
                }
                filtered_query_item = get_trends_export(
                    queryItems,
                    datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"),
                    datetime.datetime.strptime(request.GET["endTime"], "%Y-%m-%dT%H:%M:%S"),
                    desired_attr,
                    cond_attr,
                    options,
                )

                user_dict = {str(userID): {'metrics':{},'metrics_SD':{}}}
                cache_dict = get_trend_from_cache(user_dict, request.GET["startTime"], request.GET["endTime"], options)
                cache_df = pd.DataFrame(cache_dict[userID]['metrics'])
                cache_df = cache_df[cache_fields]
                cache_df.rename(columns=cache_be_to_fe_mapping, inplace=True)
                cache_df = cache_df.fillna(np.nan).head(data_length)
                cache_df['dateTime'] = pd.to_datetime(cache_df['dateTime'])

                append_list_date_export(
                    filtered_query_item,
                    datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"),
                    utc_offsets[index],
                    resolution,
                    data_length,
                )

                filtered_query_item = {
                    k: v for k, v in filtered_query_item.items() if k not in cache_cols
                }
                sensor_df = pd.DataFrame({k: pd.Series(v) for k, v in filtered_query_item.items()})
                sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime'])

                if 'dateTime' in cache_df.columns:
                    cache_df['dateTime'] = pd.to_datetime(cache_df['dateTime'], errors='coerce')
                if 'dateTime' in sensor_df.columns:
                    sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime'], errors='coerce')

                is_cache_empty = cache_df.empty or cache_df['dateTime'].dropna().empty
                is_sensor_empty = sensor_df.empty or sensor_df['dateTime'].dropna().empty

                if is_cache_empty and is_sensor_empty:
                    tmp_df = pd.DataFrame()
                elif is_cache_empty:
                    tmp_df = sensor_df.dropna(subset=['dateTime']).copy()
                elif is_sensor_empty:
                    tmp_df = cache_df.dropna(subset=['dateTime']).copy()
                else:
                    if resolution == 'hourly':
                        tmp_df = merge_dataframes_allow_empty(cache_df, sensor_df, key='dateTime', merge_method='left')
                    else:
                        tmp_df = merge_dataframes_allow_empty(cache_df, sensor_df, key='dateTime', merge_method='left')

                tmp_df = tmp_df.set_index('dateTime')

                # Convert  datetime to local timezone and format to yyyy-mm-dd in daily and format to yyyy-mm-dd hh:mm:ss in hourly
                tmp_df.index = pd.to_datetime(tmp_df.index)
                if resolution == 'daily':
                    tmp_df.index = (tmp_df.index.tz_localize('UTC')  + pd.Timedelta(
                        hours=utc_offsets[index]['hours'],
                        minutes=utc_offsets[index]['minutes']
                    )).strftime('%Y-%m-%d')

                if resolution == 'hourly':
                    tmp_df.index = (tmp_df.index.tz_localize('UTC')  + pd.Timedelta(
                        hours=utc_offsets[index]['hours'],
                        minutes=utc_offsets[index]['minutes']
                    )).strftime('%Y-%m-%d %H:%M:%S')


                # We want the rows to be empty instead of -1 for invalid values
                tmp_df = tmp_df.replace(settings.val_replace_NaN, np.nan)

                # Arrange columns based on selected order
                for col in excel_col_order:
                    if col not in tmp_df.columns:
                        tmp_df[col] = None
                merged_df = tmp_df[excel_col_order]

            """
            quick fix for spot trend 
            if it is minutes trend query, overwrite the response with spot trend
            """

            if resolution == "minutes":
                bp_readings_df = get_bp_device_data(userID, startDateTime, stopDateTime,utc_offsets[index],bp_attr)
                mhi_readings_df = get_manual_health_input(userID, startDateTime, stopDateTime,utc_offsets[index],mhi_attr)
                mhi_readings_df.rename(columns=mhi_be_to_fe_mapping, inplace=True)
                bp_readings_df.rename(columns=bp_be_to_fe_mapping, inplace=True)

                response = lib_query.handle_spot_trend_query(
                    queryItems,
                    desired_attr,
                    True,
                    True,
                    False,
                    True if "signal_quality_status" in cond_attr else False,
                    True if "sensor_onskin_status" in cond_attr else False,
                )
                print('response')
                print(response)
                temp_metrics = response["metrics"]

                # convert to local time
                temp_df = pd.DataFrame(temp_metrics)
                temp_df.rename(columns={"listtime": "dateTime"}, inplace=True)
                temp_df = temp_df.drop(columns=['temperature'], errors='ignore')

                clean_cols = ['sensor_onskin_status', 'signal_quality_status']
                for col in clean_cols:
                    if col in temp_df.columns:
                        temp_df[col] = temp_df[col].replace(['nan', 'NaN', 'NAN'], None).fillna('')
                    
                temp_utc_offset = utc_offsets[index]
                temp_df["dateTime"] = (
                    pd.to_datetime(temp_df["dateTime"])
                    + datetime.timedelta(hours=int(temp_utc_offset['hours']))
                    + datetime.timedelta(minutes=int(temp_utc_offset['minutes']))
                )

                # convert format
                temp_output = temp_df.to_dict("list")

                # convert timestamp to str
                temp_datetime = temp_output["dateTime"]
                temp_datetime = [str(p) for p in temp_datetime]
                temp_output["dateTime"] = temp_datetime

                # overwrite filtered_query_item
                filtered_query_item = temp_output

                # Finally put the filtered queryItems to the output
                tmp_df = pd.DataFrame(filtered_query_item)

                # Convert to datetime type
                tmp_df['dateTime'] = pd.to_datetime(tmp_df['dateTime'])
                mhi_readings_df['dateTime'] = pd.to_datetime(mhi_readings_df['dateTime'])
                bp_readings_df['dateTime'] = pd.to_datetime(bp_readings_df['dateTime'])
                print(tmp_df['dateTime'])
                print(mhi_readings_df['dateTime'])

                # Merge on datetime (outer join to keep all data points)
                merged_sensor_mhi_df = merge_dataframes_allow_empty(tmp_df, mhi_readings_df, key='dateTime')
                print(merged_sensor_mhi_df.columns)
                merged_df = merge_dataframes_allow_empty(merged_sensor_mhi_df, bp_readings_df, key='dateTime')
                print(merged_df.columns)
                print('............................')
                print('excel_col_order....',excel_col_order)

                merged_df = merged_df.set_index('dateTime')

                # Sort by datetime
                merged_df = merged_df.sort_values('dateTime')

                # Arrange columns based on selected order
                merged_df = merged_df[[col for col in excel_col_order if col in merged_df.columns]]

                # We want the rows to be empty instead of -1 for invalid values
                merged_df = merged_df.replace(settings.val_replace_NaN, np.nan)

                print(merged_df.columns)

            if resolution in ['minutes', 'hourly']:
                prediction_data = prediction_lookup.get(int(userID), [])
                if prediction_data:
                    pred_df = pd.DataFrame(prediction_data)
                    outcome_cols = [c for c in excel_table_field_mapping if c in pred_df]
                    pred_df[outcome_cols] = pred_df[outcome_cols].apply(pd.to_numeric, errors='coerce') * 100
                    feature_columns = ["datetime"] + list(excel_table_field_mapping.keys())
                    pred_df = pred_df[feature_columns]
                    pred_df = pred_df.rename(columns=excel_table_field_mapping)
                    pred_df['datetime'] = pd.to_datetime(pred_df['datetime'])
                    pred_df = pred_df.set_index('datetime')
                    pred_df.index = (pred_df.index  + pd.Timedelta(
                        hours=utc_offsets[index]['hours'],
                        minutes=utc_offsets[index]['minutes']
                    )).strftime('%Y-%m-%d %H:%M:%S')
                    merged_df = merged_df.merge(
                        pred_df,
                        left_index=True,
                        right_index=True,
                        how="left"
                    )

                    if "dateTime" in merged_df.columns:
                        merged_df["dateTime"] = merged_df["dateTime"].dt.tz_localize(None)

                ai_columns = [
                    fe_2_ai_map[field] for field in data_fields if field in fe_2_ai_map
                ]
                ordered_columns = ["dateTime"] + excel_col_order + ai_columns
                seen = set()
                columns_to_select = []
                for col in ordered_columns:
                    if col in seen:
                        continue
                    seen.add(col)
                    columns_to_select.append(col)
                merged_df = merged_df[
                    [col for col in columns_to_select if col in merged_df.columns]
                ]


                all_dfs.append(merged_df)

            if resolution == 'daily':
                merged_df = merged_df.reset_index()
                all_dfs.append(merged_df)

        excel_file = IO()
        writer = pd.ExcelWriter(excel_file, engine="xlsxwriter")
        for i, df in enumerate(all_dfs):
            if df.empty:
                empty_df = pd.DataFrame(columns=df.columns)
                empty_df.to_excel(writer, sheet_name=str(userNames[i]), index=False)
                continue

            for col in df.select_dtypes(include=['datetimetz']).columns:
                df[col] = df[col].dt.tz_localize(None)

            if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            df.to_excel(writer, sheet_name="{}".format(userNames[i]))

        writer.close()
        excel_file.seek(0)

        # file name generation
        utc_startDateTime = startDateTime.replace(tzinfo=timezone.utc)
        utc_stopDateTime = stopDateTime.replace(tzinfo=timezone.utc)
        offset = timezone(datetime.timedelta(hours=utc_offsets[0]['hours'], minutes=utc_offsets[0]['minutes']))
        local_startDateTime = utc_startDateTime.astimezone(offset)
        local_stopDateTime = utc_stopDateTime.astimezone(offset)
        date_range = f"{local_startDateTime.strftime('%d%m%Y %H_%M_%S')} to {local_stopDateTime.strftime('%d%m%Y %H_%M_%S')}"

        if OrganisationName:
            filename = f"Respiree_PatientVitals_{OrganisationName}_{date_range}.xlsx"
        else:
            filename = f"Respiree_PatientVitals_{date_range}.xlsx"
        response = HttpResponse(
            excel_file.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        # return response
        return HttpResponse()


class HealthDataView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    @swagger_auto_schema(
        operation_description="Submit health data for a user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the user"
                ),
                "datetime_data_collected": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_DATETIME,
                    description="Datetime when data was collected",
                ),
                "data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "bp_sys": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Systolic blood pressure",
                        ),
                        "bp_dia": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Diastolic blood pressure",
                        ),
                        "weight": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Weight in kg",
                        ),
                        "blood_sugar": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Blood sugar level",
                        ),
                        "rr": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Respiratory rate",
                        ),
                        "hr": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Heart rate",
                        ),
                        "spo2": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Oxygen saturation level",
                        ),
                        "body_temp": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Body temperature",
                        ),
                    },
                    description="Nested data object for health metrics",
                ),
            },
            required=["user_id", "datetime_data_collected", "data"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "Authorization",
                openapi.IN_HEADER,
                description="Authorization header. Format: Bearer <token>",
                type=openapi.TYPE_STRING,
            )
        ],
    )
    def post(self, request):
        """
        Create a new health data record with user metrics.

        This endpoint accepts data on user health metrics and creates a new record in the database.

        Parameters:
        - user_id: ID of the user submitting the data
        - datetime_data_collected: Datetime when data was collected
        - data: Nested dictionary of health metrics (e.g., bp_sys, bp_dia, weight)

        Returns:
        - JSON response with status code and message indicating success or failure.
        """
        datetime_collected = request.data.get("datetime_data_collected", '')
        # if settings.make_timezone_aware:
        #     datetime_collected = make_aware(datetime_collected)
        data = request.data.get("data", {})
        health_data = {
            "user_id": request.data.get("user_id"),
            "datetime": datetime_collected,
            "bp_sys": data.get("bp_sys"),
            "bp_dia": data.get("bp_dia"),
            "weight": data.get("weight"),
            "blood_sugar": data.get("blood_sugar"),
            "rr": data.get("rr"),
            "hr": data.get("hr"),
            "spo2": data.get("spo2"),
            "body_temp": data.get("body_temperature"),
        }
        serializer = HealthDataSerializer(data=health_data)
        if serializer.is_valid():
            obj = serializer.save()
            logging.info("Health data record created successfully",health_data)

            # keep only non-Null/None and not empty values
            mhi_values_dict = model_to_dict(obj, exclude=["id", "user_id", "datetime", "datetime_server_received", "aws_request_id"])
            minute_cache_dict = {}
            for key, val  in mhi_values_dict.items():
                if mhi_values_dict[key] != None:
                    minute_cache_dict[f"manual_data_{key}"] = mhi_values_dict[key]
                    minute_cache_dict[f"datetime_manual_data_{key}"] = obj.datetime
            minute_cache_dict['date_time'] = datetime_collected
            minute_cache_dict["source"] = settings.DATA_SOURCE["MHI"]

            minute_cache_obj = MetricMinutesCache.objects.filter(user_id=obj.user_id)
            if minute_cache_obj.exists():
                minute_cache_obj = minute_cache_obj.first()
                for key, value in minute_cache_dict.items():
                    setattr(minute_cache_obj, key, value)
                minute_cache_obj.save()  # This triggers pre_save and post_save signals
            else:
                minute_cache_obj = MetricMinutesCache(user_id=obj.user_id, **minute_cache_dict)
                minute_cache_obj.save() # This triggers pre_save and post_save signals

            common.insert_to_process_cache(obj.id,'health_input')
            return Response(
                {"statusCode": 200, "message": "Record created successfully"}
            )
        else:
            logging.error(
                "Failed to create health data record",
                extra={"errors": serializer.errors},
            )
            return JsonResponse(
                {"statusCode": status.HTTP_400_BAD_REQUEST, "message": "Invalid data"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProcessInProgressListView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter('user_ids', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Accept comma seperated ids'),
        openapi.Parameter('resolution', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=(
            'daily', 'hourly',), required=True),
        openapi.Parameter('query_time_start', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Acceptable format yyyy-mm-ddThh:mm:ss'),
        openapi.Parameter('query_time_end', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Acceptable format yyyy-mm-ddThh:mm:ss'),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get('user_ids'):
            raise rest_exception.ValidationError(
                {'user_ids': ['This field is required.']})
        if not request.GET.get('resolution'):
            raise rest_exception.ValidationError(
                {'resolution': ['This field is required.']})
        if request.GET.get('resolution') not in ('daily', 'hourly',):
            raise rest_exception.ValidationError(
                {'resolution': ['Invalid resolution.']})
        if not request.GET.get('query_time_start'):
                raise rest_exception.ValidationError(
                    {'query_time_start': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if not request.GET.get('query_time_end'):
                raise rest_exception.ValidationError(
                    {'query_time_end': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if request.GET.get('query_time_start'):
            try:
                query_time_start = datetime.datetime.strptime(
                    request.GET.get('query_time_start'), '%Y-%m-%dT%H:%M:%S')
                query_time_start = pytz.UTC.localize(query_time_start)
            except:
                raise rest_exception.ValidationError(
                    {'query_time_start': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if request.GET.get('query_time_end'):
            try:
                query_time_end = datetime.datetime.strptime(
                    request.GET.get('query_time_end'), '%Y-%m-%dT%H:%M:%S')
                query_time_end = pytz.UTC.localize(query_time_end)
            except:
                raise rest_exception.ValidationError(
                    {'query_time_end': ['Format should be %Y-%m-%dT%H:%M:%S']})
        try:

            user_ids = request.GET.get('user_ids')
            resolution = request.GET.get('resolution')

            user_list = [int(id.strip()) for id in user_ids.split(",")]
            query_time_start = pytz.utc.localize(
                datetime.datetime.strptime(request.GET.get('query_time_start'), "%Y-%m-%dT%H:%M:%S")
            )
            query_time_end = pytz.utc.localize(
                datetime.datetime.strptime(request.GET.get('query_time_end'), "%Y-%m-%dT%H:%M:%S")
            )
            if resolution == "hourly":

                process_list = list(ProcessInProgress.objects.filter(user_id__in = user_list,
                timestamp_hourly__range=(query_time_start, query_time_end)).values_list('user_id', flat = True))

            if resolution == "daily":

                process_list = list(ProcessInProgress.objects.filter(user_id__in = user_list,
                timestamp_daily__range=(query_time_start, query_time_end)).values_list('user_id', flat = True))

            user_in_progress = []
            for user_id in user_list:

                if user_id in process_list:
                    user_in_progress.append(user_id)

            result = {"user_in_progress": user_in_progress}


            return Response(
                {"statusCode": 200, "response": result}
            )

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err = "\n".join(traceback.format_exception(*sys.exc_info()))
            logging.error(f"failed request  /api/processing. error message is {err}")
            return Response(
                {"statusCode": 400, "Error": err}
            )



class SpotBPDeviceReadingsView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter(
            "date_time",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "user_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True
        ),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]


    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get("date_time"):
            raise rest_exception.ValidationError(
                {"date_time": ["this field is required."]}
            )
        if not request.GET.get("user_id"):
            raise rest_exception.ValidationError({"user_id": ["this field is required."]})
        try:
            date_time = datetime.datetime.strptime(
                request.GET.get('date_time'), '%Y-%m-%dT%H:%M:%S')
            if settings.make_timezone_aware:
                date_time = make_aware(date_time)
        except:
            raise rest_exception.ValidationError(
                {"date_time": ["format should be %Y-%m-%dT%H:%M:%S"]}
            )

        response = get_bp_device_spot(request.GET.get("user_id"),'bp-device')

        return Response({"statusCode": 200, "response": response})


class VitalReadingsListView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()
    openapi_params = [
        openapi.Parameter('userid', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Accept comma seperated ids'),
        openapi.Parameter('start', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Acceptable format yyyy-mm-ddThh:mm:ss'),
        openapi.Parameter('end', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Acceptable format yyyy-mm-ddThh:mm:ss'),
        openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Page number'),
        openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          required=True, description='Page size'),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        )
    ]

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):
        if not request.GET.get('userid'):
            raise rest_exception.ValidationError(
                {'userid': ['This field is required.']})
        if not request.GET.get('start'):
                raise rest_exception.ValidationError(
                    {'start': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if not request.GET.get('end'):
                raise rest_exception.ValidationError(
                    {'end': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if not request.GET.get('page'):
            raise rest_exception.ValidationError(
                {'page': ['This field is required.']})
        if not request.GET.get('limit'):
            raise rest_exception.ValidationError(
                {'limit': ['This field is required.']})
        if request.GET.get('start'):
            try:
                start = datetime.datetime.strptime(
                    request.GET.get('start'), '%Y-%m-%dT%H:%M:%S')
                start = pytz.UTC.localize(start)
            except:
                raise rest_exception.ValidationError(
                    {'start': ['Format should be %Y-%m-%dT%H:%M:%S']})
        if request.GET.get('end'):
            try:
                end = datetime.datetime.strptime(
                    request.GET.get('end'), '%Y-%m-%dT%H:%M:%S')
                end = pytz.UTC.localize(end)
            except:
                raise rest_exception.ValidationError(
                    {'end': ['Format should be %Y-%m-%dT%H:%M:%S']})
            
        try:
            userid = request.GET.get('userid')
            page = int(request.GET.get('page'))
            limit = int(request.GET.get('limit'))
            result,error = handle_query_vital_readings(userid, start, end, page, limit)
            if error == False:
                return Response(
                    {"statusCode": 200, "response": result}
                )
            else:
                return Response(
                    {"statusCode": 400, "Error": error}
                )
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err = "\n".join(traceback.format_exception(*sys.exc_info()))
            logging.error(f"failed request  /api/vitals/readings. error message is {err}")
            return Response(
                {"statusCode": 400, "Error": err}
            )


class EMRDataSUbmissionView(APIView):
    """
    Handles creation of EMR data .
    Endpoints:
        - POST /data/emr -> source="emr"
    """
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    @swagger_auto_schema(
        operation_description="Submit EMR data for a user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="ID of the user"
                ),
                "datetime_data_collected": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_DATETIME,
                    description="Datetime when data was collected",
                ),
                "data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "bp_sys": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Systolic blood pressure",
                        ),
                        "bp_dia": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Diastolic blood pressure",
                        ),
                        "weight": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Weight in kg",
                        ),
                        "blood_sugar": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Blood sugar level",
                        ),
                        "rr": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Respiratory rate",
                        ),
                        "hr": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Heart rate",
                        ),
                        "spo2": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Oxygen saturation level",
                        ),
                        "body_temp": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Body temperature",
                        ),
                    },
                    description="Nested data object for health metrics",
                ),
            },
            required=["user_id", "datetime_data_collected", "data"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "Authorization",
                openapi.IN_HEADER,
                description="Authorization header. Format: Bearer <token>",
                type=openapi.TYPE_STRING,
            )
        ],
    )


    def post(self, request, *args, **kwargs):

        source = "emr"

        # Inject source into request data
        data = request.data.copy()
        user_id = data["user_id"]

        _, datetime_utc = common.get_utc_timenow()
        data["datetime"] = datetime_utc

        datetime_data_collected = data.get('datetime_data_collected')
        vital_data = data.get('data', {})

        data_to_save = {
            'user_id': user_id,
            'datetime_data_collected': datetime_data_collected,
            'datetime': datetime_utc,
            'bp_dia': vital_data.get('bp_dia'),
            'bp_sys': vital_data.get('bp_sys'),
            'weight': vital_data.get('weight'),
            'blood_sugar': vital_data.get('blood_sugar'),
            'rr': vital_data.get('rr'),
            'hr': vital_data.get('hr'),
            'spo2': vital_data.get('spo2'),
            'body_temperature': vital_data.get('body_temperature'),
            'source': source,
        }

        serializer = OtherDeviceReadingSerializer(data=data_to_save)

        if serializer.is_valid():
            instance = serializer.save()
            common.insert_to_process_cache(instance.id, source)

            exclude = ["user_id", "datetime", "source", "datetime_data_collected",]

            valid_input = {
                f"{source}_" + key: value
                for key, value in data['data'].items()
                if value and key not in exclude
            }
            valid_input.update({"datetime_" + key: datetime_utc for key in valid_input})

            valid_input["date_time"] = instance.datetime
            valid_input["source"] = settings.DATA_SOURCE[source]
            minute_cache = MetricMinutesCache.objects.filter(user_id=user_id)
            if minute_cache.exists():
                minute_cache = minute_cache.first()
                for key, value in valid_input.items():
                    setattr(minute_cache, key, value)
                minute_cache.save()  # This triggers pre_save and post_save signals
            else:
                minute_cache = MetricMinutesCache(user_id=user_id, **valid_input)
                minute_cache.save() # This triggers pre_save and post_save signals

            spot_item = {}
            spot_item["user_id"] = instance.user_id
            spot_item["hr"] = instance.hr
            spot_item["rr"] = instance.rr
            spot_item["bp_sys"] = instance.bp_sys
            spot_item["bp_dia"] = instance.bp_dia
            spot_item["spo2"] = instance.spo2
            spot_item["body_temperature"] = instance.body_temperature
            spot_item["blood_sugar"] = instance.blood_sugar
            spot_item["weight"] = instance.weight
            spot_item["datetime_server_received"] = instance.datetime
            spot_item["date_time"] = instance.datetime_data_collected
            spot_source = source

            spot_cache_update(spot_item,spot_source)

            return Response(
                {
                    "message": "Reading stored successfully",
                    "id": instance.id,
                    "user_id": instance.user_id,
                    "source": instance.source,
                    "datetime": instance.datetime,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BPDeviceDataSubmissionView(APIView):
    """
    Handles data upload from  BP devices.
    Endpoints:
        - POST /data/other/bp-device -> source="other"
    """
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()
 
    @swagger_auto_schema(
        operation_description="Submit BP device data for a user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "userId": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    format=openapi.FORMAT_FLOAT,
                    description="User ID",
                ),
                "bloodPressureSystolic": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    format=openapi.FORMAT_FLOAT,
                    description="Systolic blood pressure",
                ),
                "bloodPressureDiastolic": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    format=openapi.FORMAT_FLOAT,
                    description="Diastolic blood pressure",
                ),
                "deviceId": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Device ID",
                ),
            },
            required=["userId", "bloodPressureSystolic", "bloodPressureDiastolic", "deviceId"],
        ),
 
    )
 
 
    def post(self, request, *args, **kwargs):
 
        source = "other"
 
        # Inject source into request data
        data = request.data.copy()
        data["source"] = source
        bp_device_id = data.get("deviceId")
        user_id = data["userId"]
 
        _, datetime_utc = common.get_utc_timenow()
        data["datetime"] = datetime_utc
        common.update_device_last_connection(
                        bp_device_id,
                        urljoin(
                            settings.UI_URL_REST_API_BASE,
                            settings.URL_UPDATE_EXTERNAL_DEVICE_LAST_CONNECTION,
                        ),
                        settings.UI_REST_API_HEADER,
                        user_id,
                    )
        serializer = BPDeviceDataSerializer(data=data)
        if serializer.is_valid():
            instance = serializer.save()
            common.insert_to_process_cache(instance.id, source)
            mapping = {
                "userId": 'user_id',
                "bloodPressureSystolic": 'bp_sys',
                "bloodPressureDiastolic": 'bp_dia',
            }
            updated_data = {mapping.get(k, k): v for k, v in data.items()}
            data = updated_data
            exclude = ["user_id", "datetime", "source", "datetime_data_collected", "deviceId"]
            valid_input = {
                f"{source}_" + key: value
                for key, value in data.items()
                if value and key not in exclude
            }
            valid_input.update({"datetime_" + key: datetime_utc for key in valid_input})
            valid_input["date_time"] = instance.datetime
            valid_input["source"] = settings.DATA_SOURCE[source]
            minute_cache = MetricMinutesCache.objects.filter(user_id=user_id)
            if minute_cache.exists():
                minute_cache = minute_cache.first()
                for key, value in valid_input.items():
                    setattr(minute_cache, key, value)
                minute_cache.save()  # This triggers pre_save and post_save signals
            else:
                minute_cache = MetricMinutesCache(user_id=user_id, **valid_input)
                minute_cache.save() # This triggers pre_save and post_save signals
 
            spot_item = {}
            spot_item["user_id"] = instance.user_id
            spot_item["bp_sys"] = instance.bp_sys
            spot_item["bp_dia"] = instance.bp_dia
            spot_item["datetime_server_received"] = instance.datetime
            spot_item["date_time"] = instance.datetime
            spot_source = 'bp-device'
 
            spot_cache_update(spot_item,spot_source)
 
            return Response(
                {
                    "message": "Reading stored successfully",
                    "id": instance.id,
                    "user_id": instance.user_id,
                    "source": instance.source,
                    "datetime": instance.datetime,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class QueryMonitoringDataView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    def get(self, request, *args, **kwargs):

        if not request.GET.get("date_time"):
            raise rest_exception.ValidationError(
                {"date_time": ["This field is required."]}
            )
        if not request.GET.get("user_id"):
            raise rest_exception.ValidationError({"user_id": ["This field is required."]})

        try:
            date_time = datetime.datetime.strptime(
                request.GET.get("date_time"), "%Y-%m-%dT%H:%M:%S"
            )
        except:
            raise rest_exception.ValidationError(
                {"date_time": ["Format should be %Y-%m-%dT%H:%M:%S"]}
            )

        if settings.make_timezone_aware:
            date_time = make_aware(date_time)

        return Response(
            {
                "statusCode": 200,
                "response": handle_query_monitoring_data(
                    date_time,
                    request.GET.get("user_id"),
                    'emr'
                ),
            }
        )



class PatientListCacheView(APIView):
    authentication_classes = (DataProcessAuthentication,)
    permission_classes = ()

    openapi_params = [
        openapi.Parameter(
            "organizationId",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Organization ID",
        ),
        openapi.Parameter(
            "userId",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Accept comma seperated ids",
        ),
        openapi.Parameter(
            "resolution",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Accept resolution separated by comma",
        ),
        openapi.Parameter(
            "timestamp",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "Authorization",
            openapi.IN_HEADER,
            description="Authorization header. Format: Bearer <token>",
            type=openapi.TYPE_STRING,
        ),
    ]

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):

        # validate query paramns
        request_data = self.request.GET.copy()
        resolution = request_data.get("resolution", "")
        if not resolution.strip():
            request_data["resolution"] = ",".join(["minutes", "hourly", "daily"])
        serializer = PatientListCacheQueryParamSerializer(data=request_data)

        if serializer.is_valid(raise_exception=True):
            organisation_id = serializer.validated_data["organizationId"]
            user_list = serializer.validated_data["userId"]
            resolution_list = serializer.validated_data["resolution"]
            timestamp = serializer.validated_data["timestamp"]

            dict_devices = common.get_devices_data_multiple(user_list)
            result = handle_query_master_cache_patient_list(
                organisation_id, user_list, resolution_list, timestamp, dict_devices
            )

            # create data dor dummy users
            for user_id in user_list:
                if user_id in settings.list_demo_id:
                    user_data = lib_query.generate_dummy("list_of_patient")
                    for resolution in resolution_list:
                        result[resolution].append(user_data)
                        
            return Response(result)


class StagingProcessManualView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @swagger_auto_schema(
        operation_description="Trigger manual hourly processing",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_STRING),
                "timestamp": openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=["user_id", "timestamp"]
        ),
    )
    def post(self, request, *args, **kwargs):

        data = request.data
        user_id = data.get("user_id")
        timestamp = data.get("timestamp")
        if isinstance(user_id, str):
            user_ids = [uid.strip() for uid in user_id.split(",") if uid.strip()]
        elif isinstance(user_id, list):
            user_ids = user_id
        response_dict = run_manual_hourly_job(user_ids, timestamp)

        return Response(
            {
                "users": user_ids,
                "message": response_dict.get("message"),
            },
            status=response_dict.get("status", 200)
        )













class NewExportView(APIView):
    authentication_classes = ()
    permission_classes = ()
    openapi_params = [
        openapi.Parameter(
            "users",
            openapi.IN_QUERY,
            type="string",
            required=True,
            description="""List of objects in below format 
                          [
                                {
                                    "username":"username",
                                    "id":id,
                                    "utc_offset":"utc_offset"
                                },
                          ]""",
        ),
        openapi.Parameter(
            "data",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Accept comma seperated values",
        ),
        openapi.Parameter(
            "startTime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "endTime",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Acceptable format yyyy-mm-ddThh:mm:ss",
        ),
        openapi.Parameter(
            "resolution",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            enum=(
                "daily",
                "hourly",
                "minutes",
            ),
            required=True,
        ),
        openapi.Parameter(
            "organisationName",
            openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=False,
            description="organisation name",
        ),
    ]

    def validate_params(self):
        if not self.request.GET.get("resolution"):
            raise rest_exception.ValidationError(
                {"resolution": ["this field is required."]}
            )
        if not self.request.GET.get("data"):
            raise rest_exception.ValidationError({"data": ["this field is required."]})
        if not self.request.GET.get("startTime"):
            raise rest_exception.ValidationError(
                {"startTime": ["this field is required."]}
            )
        if not self.request.GET.get("endTime"):
            raise rest_exception.ValidationError(
                {"endTime": ["this field is required."]}
            )

    @swagger_auto_schema(manual_parameters=openapi_params)
    def get(self, request, *args, **kwargs):



        sensor_mapping_dict = {
            "listtime": {'dp_key':'listtime','col_heading':'dateTime'},
            "RR": {'dp_key':'rr','col_heading':'RR'},
            "HR": {'dp_key':'hr','col_heading':'HR'},
            "Spo2": {'dp_key':'spo2','col_heading':'Spo2'},
            "tidal depth": {'dp_key':'rr_td','col_heading':'RR_TD'},
            "dutyCycle": {'dp_key':'rr_dc','col_heading':'RR_DC'},
            "bodyTemp": {'dp_key':'body_temperature','col_heading':'body_temperature'},
            "skinTemp": {'dp_key':'skin_temperature','col_heading':'skin_temperature'},
            "activity": {'dp_key':'activity','col_heading':'activity'},
            "skinContact": {'dp_key':'sensor_onskin_status','col_heading':'sensor_onskin_status'},
            "ews": {'dp_key':'news','col_heading':'ews'},
            "flag": {'dp_key':'flag','col_heading':'flag'},
            "wellness_stress": {'dp_key':'wellness_stress','col_heading':'wellness_stress'},
            "sleep_duration_seconds": {'dp_key':'sleep_duration_seconds','col_heading':'sleep_duration_seconds'},
            "sensor_onskin_status": {'dp_key':'sensor_onskin_status','col_heading':'sensor_onskin_status'},
            "signal_quality_status": {'dp_key':'signal_quality_status','col_heading':'signal_quality_status'},
        }


        mhi_mapping_dict = {
            "datetime": {'dp_key':'datetime','col_heading':'dateTime'},
            "HR_manual": {'dp_key':'hr','col_heading':'HR (Manual)'},
            "RR_manual": {'dp_key':'rr','col_heading':'RR (Manual)'},
            "Spo2_manual": {'dp_key':'spo2','col_heading':'SpO2 (Manual)'},
            "body_temperature_manual": {'dp_key':'body_temp','col_heading':'Body Temperature (Manual)'},
            "blood_sugar": {'dp_key':'blood_sugar','col_heading':'Blood Sugar'},
            "BP_diastolic_manual": {'dp_key':'bp_dia','col_heading':'BP Diastolic (Manual)'},
            "BP_systolic_manual": {'dp_key':'bp_sys','col_heading':'BP Systolic (Manual)'},
            "weight": {'dp_key':'weight','col_heading':'Weight'},
          
        }


        bp_mapping_dict = {
            "datetime": {'dp_key':'datetime','col_heading':'dateTime'},
            "BP_diastolic": {'dp_key':'bp_dia','col_heading':'BP Diastolic'},
            "BP_systolic": {'dp_key':'bp_sys','col_heading':'BP Systolic'},
          
        }

        cache_mapping_dict = {
            "listtime": {'dp_key':'listtime','col_heading':'dateTime'},
            "listdate": {'dp_key':'listdate','col_heading':'dateTime'},
            "RR": {'dp_key':'rr','col_heading':'RR'},      
            "HR": {'dp_key':'hr','col_heading':'HR'},      
            "Spo2": {'dp_key':'spo2','col_heading':'SpO2'},      
            "skinTemp": {'dp_key':'skin_temperature','col_heading':'skin_temperature'},      
            "ews": {'dp_key':'EWS','col_heading':'EWS'},      
            "activity": {'dp_key':'activity','col_heading':'activity'},      
            "tidal depth": {'dp_key':'rr_td','col_heading':'RR_TD'},      
            "RR_DC": {'dp_key':'rr_dc','col_heading':'RR_DC'},      
            "dutyCycle": {'dp_key':'rr_dc','col_heading':'RR_DC'},      
            "BP_diastolic": {'dp_key':'bp_dia','col_heading':'BP Diastolic'},      
            "BP_systolic": {'dp_key':'bp_sys','col_heading':'BP Systolic'},      
        }

        daily_hourly_sensor_mapping_dict = {
            "dateTime": {'dp_key':'dateTime','col_heading':'dateTime'},
            "flag": {'dp_key':'flag','col_heading':'flag'},
            "wellness_stress": {'dp_key':'wellness_stress','col_heading':'wellness_stress'},
            "sleep_duration_seconds": {'dp_key':'sleep_duration_seconds','col_heading':'sleep_duration_seconds'},
            "sensor_onskin_status": {'dp_key':'sensor_onskin_status','col_heading':'sensor_onskin_status'},
            "signal_quality_status": {'dp_key':'signal_quality_status','col_heading':'signal_quality_status'},
        }

        ai_mapping_dict = {
            # "datetime": {'dp_key':'datetime','col_heading':'dateTime'},
            "predictionScoreRr": {'dp_key':'outcome_rr','col_heading':'Prediction Score: Respiratory Rate Only Model'},
            "predictionScoreRrHr": {'dp_key':'outcome_rr_hr','col_heading':'Prediction Score: Respiratory Rate, Heart Rate Model'},
            "predictionScoreRrHrSpo2": {'dp_key':'outcome_rr_hr_spo2','col_heading':'Prediction Score: Respiratory Rate, Heart Rate, SPO2 Model'},
            "predictionScoreRrHrSpo2Bpsys": {'dp_key':'outcome_rr_hr_spo2_bp_sys','col_heading':'Prediction Score: Respiratory Rate, Heart Rate, SPO2, Blood Pressure Model'},
            "predictionScoreDynamic": {'dp_key':'outcome_dynamic_model','col_heading':'Prediction Score: Dynamic Model'},
          
        }

        desired_2_cond_attr_map = {
            "rr": "RR",
            "hr": "HR",
            "spo2": "HR",
            "rr_td": "RR",
            "rr_dc": "RR",
            "body_temperature": "RR",
            "skin_temperature": "RR",
            "activity": None,
            "news": None,
            "flag": None,
            "wellness_stress": None,
            "sleep_duration_seconds": None,
            "sensor_onskin_status": "sensor_onskin_status",
            "signal_quality_status": "signal_quality_status",
        }

        def fetch_predictions(user_id, start_datetime_str, end_datetime_str, resolution, utc_offset):

            PATIENT_PREDICTION_SCORE_URL = urljoin(
                settings.AI_BACKEND_URL, settings.UI_URL_REST_API_getPredictionScore
            )

            start_datetime = start_datetime_str
            end_datetime = end_datetime_str
            if ':' not in utc_offset:
                hours = int(utc_offset)
                minutes = 0
            else:
                parts = utc_offset.split(':')
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
            utc_offset_str = f'{hours:02}:{minutes:02}'
            offset = datetime.timedelta(hours=hours, minutes=minutes)
            start_datetime_with_offset = start_datetime + offset
            end_datetime_with_offset = end_datetime + offset
            start_datetime_str_with_offset = start_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
            end_datetime_str_with_offset = end_datetime_with_offset.strftime('%Y-%m-%dT%H:%M:%S')
            params = {
                "user_ids[]": user_id,
                "start_datetime": start_datetime_str_with_offset,
                "end_datetime": end_datetime_str_with_offset,
                "resolution": resolution,
                "utc_offset": utc_offset_str
            }
            try:
                response = requests.get(PATIENT_PREDICTION_SCORE_URL, params=params, headers=HEADERS)
                response.raise_for_status()
                data = response.json().get('data', [])


                data=  [
                        {
                            "user_id": 4,
                            "prediction_data": [
                                {
                                    "user_id": 4,
                                    # "datetime": "2025-12-17T04:43:50Z",
                                    "datetime": "2025-12-17T03:00:00Z",
                                    "created_at": "2025-09-15T09:00:53.744034Z",
                                    "threshold": "0.500",
                                    "alert": 0,
                                    "outcome_rr": None,
                                    "outcome_rr_hr": None,
                                    "outcome_rr_hr_spo2": "0.027",
                                    "outcome_rr_hr_spo2_bp_sys": "0.019",
                                    "outcome_dynamic_model": "0.019",
                                    "dynamic_model": "RR, HR, SpO2, BP Sys",
                                    "post_prediction_rr": None,
                                    "post_prediction_rr_hr": None,
                                    "post_prediction_rr_hr_spo2": 0,
                                    "post_prediction_rr_hr_spo2_bp_sys": 0,
                                    "post_prediction_dynamic_model": 0
                                }
                            ]
                        }
                    ]


                return data
            except Exception as e:
                logging.error(f"Error fetching predictions: {e}")
                return []


        self.validate_params()
        resolution = (
            "minutes"
            if request.GET.get("resolution") == "minute"
            else request.GET.get("resolution")
        )
        users = json.loads(unquote(request.GET.get("users")))
        userIDs = [str(x["id"]) for x in users]
        userNames = [str(x["username"]) for x in users]
        utc_offsets = [get_utc_offset(str(x["utc_offset"])) for x in users]

        utc_offsets =  [{'hours': hours, 'minutes': minutes} for hours , minutes in utc_offsets]
        timezone_obj = datetime.timezone(datetime.timedelta(hours=utc_offsets[0]['hours'], minutes=utc_offsets[0]['minutes']))

        startDateTime = datetime.datetime.strptime(
            request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"
        ).strftime("%Y-%m-%d %H:%M:%S")
        stopDateTime = datetime.datetime.strptime(
            request.GET['endTime'], '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
        if 'organisationName' in request.GET:
            OrganisationName = request.GET['organisationName']
        else:
            OrganisationName = None
    
        if settings.make_timezone_aware:
            startDateTime = make_aware(datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"))
            stopDateTime = make_aware(datetime.datetime.strptime(request.GET["endTime"], "%Y-%m-%dT%H:%M:%S"))

        # Filter 3 - Filter by resolution
        # data_length = len(queryItems)
        trends_vital_sign_minutes_resolution = settings.trends_vital_sign_minutes_resolution
        if resolution == 'hourly':
            data_length = math.ceil((stopDateTime - startDateTime).total_seconds()/3600)
        elif resolution == 'daily':
            data_length = (stopDateTime - startDateTime).days + 1
        elif resolution == 'minutes':
            data_length = math.ceil((stopDateTime - startDateTime).total_seconds()/60)
            data_length = math.ceil(data_length/trends_vital_sign_minutes_resolution)

        data_fields = [x.strip() for x in request.GET["data"].split(",")]
        desired_attr = [sensor_mapping_dict[x]['dp_key'] for x in data_fields if x in sensor_mapping_dict]
        cond_attr = [desired_2_cond_attr_map[x] for x in desired_attr]

        if resolution in ['minutes']:
            mhi_attr = [mhi_mapping_dict[x]['dp_key'] for x in data_fields if x in mhi_mapping_dict]
            bp_attr = [bp_mapping_dict[x]['dp_key'] for x in data_fields if x in bp_mapping_dict]
            sensor_attr = [sensor_mapping_dict[x]['dp_key'] for x in data_fields if x in sensor_mapping_dict]

            mhi_be_to_fe_mapping = {
                v["dp_key"]: v['col_heading']
                for k, v in mhi_mapping_dict.items()
            }
            bp_be_to_fe_mapping = {
                v["dp_key"]: v['col_heading']
                for k, v in bp_mapping_dict.items()
            }
            sensor_be_to_fe_mapping = {
                v["dp_key"]: v['col_heading']
                for k, v in sensor_mapping_dict.items()
            }
            print('sensor_be_to_fe_mapping>>>',sensor_be_to_fe_mapping)

            column_order = ['dateTime']
            for col in data_fields:
                if col in sensor_mapping_dict:
                    column_order.append(sensor_mapping_dict[col]['col_heading'])
                if col in mhi_mapping_dict:
                    column_order.append(mhi_mapping_dict[col]['col_heading'])
                if col in bp_mapping_dict:
                    column_order.append(bp_mapping_dict[col]['col_heading'])
                if col in ai_mapping_dict:
                    column_order.append(ai_mapping_dict[col]['col_heading'])

        if resolution in ['daily', 'hourly']:

            cache_fields = [cache_mapping_dict[x]['dp_key'] for x in data_fields if x in cache_mapping_dict]

            if resolution == 'daily':
                cache_fields.append('listdate')
            if resolution == 'hourly':
                cache_fields.append('listtime')
            print('cache_fields>>>',cache_fields)



            column_order = ['dateTime']
            for col in data_fields:
                if col in cache_mapping_dict:
                    column_order.append(cache_mapping_dict[col]['col_heading'])
                if col in daily_hourly_sensor_mapping_dict:
                    column_order.append(daily_hourly_sensor_mapping_dict[col]['col_heading'])
                if col in ai_mapping_dict:
                    column_order.append(ai_mapping_dict[col]['col_heading'])


        all_dfs = []
        data_processing_obj = DataProcessing.objects.filter(
            date_time__range=(startDateTime, stopDateTime))
        for index, userID in enumerate(userIDs):
            data_processing = data_processing_obj.filter(user_id=userID)
            queryItems = data_processing.values('user_id','rr','hr','spo2','date_time','dashboard_mode')



            if resolution in ['daily', 'hourly']:


                cache_be_to_fe_mapping = {
                    v["dp_key"]: v['col_heading']
                    for k, v in cache_mapping_dict.items()
                }

                daily_hourly_sensor_be_to_fe_mapping = {
                    v["dp_key"]: v['col_heading']
                    for k, v in daily_hourly_sensor_mapping_dict.items()
                }

                # Step 4: Calculate the metrics and std dev information
                options = {
                    "data_length": data_length,
                    "resolution": resolution,
                    "valReplaceNaN": settings.val_replace_NaN,
                    "min_hr_finger_required_within_hour": settings.min_hr_finger_required_within_hour,
                    "min_hr_finger_required_within_day": settings.min_hr_finger_required_within_day,
                    "trends_vital_sign_minutes_resolution": settings.trends_vital_sign_minutes_resolution,
                    "utc_offset": utc_offsets[index],
                }
                filtered_query_item = get_trends_export(
                    queryItems,
                    datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"),
                    datetime.datetime.strptime(request.GET["endTime"], "%Y-%m-%dT%H:%M:%S"),
                    desired_attr,
                    cond_attr,
                    options,
                )
                print('filtered_query_item A',filtered_query_item)

                user_dict = {str(userID): {'metrics':{},'metrics_SD':{}}}
                cache_dict = get_trend_from_cache(user_dict, request.GET["startTime"], request.GET["endTime"], options)
                cache_df = pd.DataFrame(cache_dict[userID]['metrics'])
                print('cache_dict')
                print(cache_dict)
                print(cache_df.columns)
                cache_df = cache_df[cache_fields]
                cache_df.rename(columns=cache_be_to_fe_mapping, inplace=True)
                cache_df = cache_df.fillna(np.nan).head(data_length)
                if resolution == 'hourly':
                    cache_df['dateTime'] = pd.to_datetime(cache_df['dateTime'])
                else:
                    cache_df['dateTime'] = pd.to_datetime(cache_df['dateTime']).dt.date

                append_list_date_export(
                    filtered_query_item,
                    datetime.datetime.strptime(request.GET["startTime"], "%Y-%m-%dT%H:%M:%S"),
                    utc_offsets[index],
                    resolution,
                    data_length,
                )


                filtered_query_item = {'rr': [21.0, 21.0, None], 'rr_dc': [None, None, None], 'rr_td': [None, None, None], 'hr': [None, None, None], 'skin_temperature': [None, None, None], 'body_temperature': [None, None, None], 'spo2': [None, None, None], 'activity': [None, None, None], 'news': [None, None, None], 'flag': [None, None, None], 'wellness_stress': [None, None, None], 'sleep_duration_seconds': [None, None, None], 'signal_quality_status': ['X', 'Y', 'Z'], 'dateTime': ['2025-12-17 00:00:00', '2025-12-18 00:00:00']}
                filtered_query_item = {
                    k: v for k, v in filtered_query_item.items() if k  in daily_hourly_sensor_be_to_fe_mapping
                }

                print('filtered_query_item B',filtered_query_item)

                sensor_df = pd.DataFrame({k: pd.Series(v) for k, v in filtered_query_item.items()})
                if resolution == 'hourly':
                    sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime'])
                else:
                    sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime']).dt.date

                # sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime'])
                print(sensor_df)

                # if 'dateTime' in cache_df.columns:
                #     cache_df['dateTime'] = pd.to_datetime(cache_df['dateTime'], errors='coerce')
                # if 'dateTime' in sensor_df.columns:
                #     sensor_df['dateTime'] = pd.to_datetime(sensor_df['dateTime'], errors='coerce')

                is_cache_empty = cache_df.empty or cache_df['dateTime'].dropna().empty
                is_sensor_empty = sensor_df.empty or sensor_df['dateTime'].dropna().empty


                print('-----------------------------')
                print(cache_df['dateTime'])
                print(sensor_df['dateTime'])
                print('-----------------------------')

                if is_cache_empty and is_sensor_empty:
                    print('AAAAAA')
                    tmp_df = pd.DataFrame()
                elif is_cache_empty:
                    print('BBBBBBBBBB')
                    tmp_df = sensor_df.dropna(subset=['dateTime']).copy()
                elif is_sensor_empty:
                    print('CCCCCCCCCCCC')
                    tmp_df = cache_df.dropna(subset=['dateTime']).copy()
                else:
                    print('DDDDDDDDDDDdddd')
                    if resolution == 'hourly':
                        tmp_df = merge_dataframes_allow_empty(cache_df, sensor_df, key='dateTime', merge_method='left')
                    else:
                        tmp_df = merge_dataframes_allow_empty(cache_df, sensor_df, key='dateTime', merge_method='left')

                tmp_df = tmp_df.set_index('dateTime')

                # Convert  datetime to local timezone and format to yyyy-mm-dd in daily and format to yyyy-mm-dd hh:mm:ss in hourly
                tmp_df.index = pd.to_datetime(tmp_df.index)
                if resolution == 'daily':
                    tmp_df['dateTime'] = (tmp_df.index.tz_localize('UTC')  + pd.Timedelta(
                        hours=utc_offsets[index]['hours'],
                        minutes=utc_offsets[index]['minutes']
                    )).strftime('%Y-%m-%d')


                if resolution == 'hourly':
                    # tmp_df.index = (tmp_df.index.tz_localize('UTC')  + pd.Timedelta(
                    #     hours=utc_offsets[index]['hours'],
                    #     minutes=utc_offsets[index]['minutes']
                    # ))#.strftime('%Y-%m-%d %H:%M:%S')

                    tmp_df['dateTime'] = (
                        pd.to_datetime(tmp_df.index) +
                        pd.Timedelta(
                            hours=utc_offsets[index]['hours'],
                            minutes=utc_offsets[index]['minutes']
                        )
                    )
                    print('XXXXXXXXXX')
                    print(tmp_df['dateTime'])


                # We want the rows to be empty instead of -1 for invalid values
                tmp_df = tmp_df.replace(settings.val_replace_NaN, np.nan)

                # # Arrange columns based on selected order
                # for col in excel_col_order:
                #     if col not in tmp_df.columns:
                #         tmp_df[col] = None
                # merged_df = tmp_df[excel_col_order]
                merged_df = tmp_df
                print('****************************')
                print(merged_df.columns)

                # merged_df = merged_df.set_index('dateTime')
                merged_df.reset_index(drop=True, inplace=True)
        
                print(merged_df.index)
                print(merged_df.columns)

                # Sort by datetime
                merged_df = merged_df.sort_values('dateTime')

            """
            quick fix for spot trend 
            if it is minutes trend query, overwrite the response with spot trend
            """

            if resolution == "minutes":
                bp_readings_df = get_bp_device_data(userID, startDateTime, stopDateTime,utc_offsets[index],bp_attr)
                mhi_readings_df = get_manual_health_input(userID, startDateTime, stopDateTime,utc_offsets[index],mhi_attr)
                mhi_readings_df.rename(columns=mhi_be_to_fe_mapping, inplace=True)
                bp_readings_df.rename(columns=bp_be_to_fe_mapping, inplace=True)
                # print(mhi_readings_df.columns)


                response = lib_query.handle_spot_trend_query(
                    queryItems,
                    desired_attr,
                    True,
                    True,
                    False,
                    True if "signal_quality_status" in cond_attr else False,
                    True if "sensor_onskin_status" in cond_attr else False,
                )
                print('response')
                print(response)
                temp_metrics = response["metrics"]

                # convert to local time
                temp_df = pd.DataFrame(temp_metrics)
                print(temp_df.columns)
                temp_df.rename(columns=sensor_be_to_fe_mapping, inplace=True)
                temp_df = temp_df.drop(columns=['temperature'], errors='ignore')
                print('temp_df.columns')
                print(temp_df.columns)

                clean_cols = ['sensor_onskin_status', 'signal_quality_status']
                for col in clean_cols:
                    if col in temp_df.columns:
                        temp_df[col] = temp_df[col].replace(['nan', 'NaN', 'NAN'], None).fillna('')
                    
                temp_utc_offset = utc_offsets[index]
                temp_df["dateTime"] = (
                    pd.to_datetime(temp_df["dateTime"])
                    + datetime.timedelta(hours=int(temp_utc_offset['hours']))
                    + datetime.timedelta(minutes=int(temp_utc_offset['minutes']))
                )

                # convert format
                temp_output = temp_df.to_dict("list")

                # convert timestamp to str
                temp_datetime = temp_output["dateTime"]
                temp_datetime = [str(p) for p in temp_datetime]
                temp_output["dateTime"] = temp_datetime

                # overwrite filtered_query_item
                # filtered_query_item = temp_output

                # Finally put the filtered queryItems to the output
                # tmp_df = pd.DataFrame(filtered_query_item)
                tmp_df = pd.DataFrame(temp_output)

                # Convert to datetime type
                tmp_df['dateTime'] = pd.to_datetime(tmp_df['dateTime'])
                mhi_readings_df['dateTime'] = pd.to_datetime(mhi_readings_df['dateTime'])
                bp_readings_df['dateTime'] = pd.to_datetime(bp_readings_df['dateTime'])
                print(tmp_df.columns)
                print(mhi_readings_df.columns)
                print(bp_readings_df.columns)
                print(tmp_df["dateTime"])
                # tmp_df["dateTime"] = tmp_df["dateTime"].dt.tz_localize(None)

                # Merge on datetime (outer join to keep all data points)
                merged_sensor_mhi_df = merge_dataframes_allow_empty(tmp_df, mhi_readings_df, key='dateTime')
                merged_df = merge_dataframes_allow_empty(merged_sensor_mhi_df, bp_readings_df, key='dateTime')
                print('............................')
                # print('excel_col_order....',excel_col_order)

                # merged_df = merged_df.set_index('dateTime')

                # Sort by datetime
                merged_df = merged_df.sort_values('dateTime')

                # Arrange columns based on selected order
                # merged_df = merged_df[[col for col in excel_col_order if col in merged_df.columns]]

                # We want the rows to be empty instead of -1 for invalid values
                # merged_df = merged_df.replace(settings.val_replace_NaN, np.nan)
                print(merged_df.index)
                print(merged_df.columns)


            if resolution in ['minutes', 'hourly']:

                ai_response = fetch_predictions(userIDs, startDateTime, stopDateTime, resolution, users[0]['utc_offset'])
                prediction_lookup = {item["user_id"]: item["prediction_data"] for item in ai_response}

                print('prediction_lookup',prediction_lookup)

                prediction_data = prediction_lookup.get(int(userID), [])
                print('aaaaaaaaaa',prediction_data)
                if prediction_data:

                    ai_be_to_fe_mapping = {
                        v["dp_key"]: v['col_heading']
                        for k, v in ai_mapping_dict.items()
                    }

                    pred_df = pd.DataFrame(prediction_data)

                    outcome_cols = [v['dp_key'] for v in ai_mapping_dict.values()]
                    pred_df[outcome_cols] = pred_df[outcome_cols].apply(pd.to_numeric, errors='coerce') * 100

                    pred_df = pred_df.rename(columns=ai_be_to_fe_mapping)
                    pred_df['dateTime'] = pd.to_datetime(pred_df['datetime'])
                    pred_df['dateTime'] = (
                        pd.to_datetime(pred_df['dateTime']) +
                        pd.Timedelta(
                            hours=utc_offsets[index]['hours'],
                            minutes=utc_offsets[index]['minutes']
                        )
                    )
                    pred_df['dateTime'] = pred_df['dateTime'].dt.tz_convert(None)

                    merged_df = merged_df.merge(
                        pred_df,
                        on='dateTime',
                        how='left'
                    )

                merged_df = merged_df.filter(items=column_order)
                all_dfs.append(merged_df)

            if resolution == 'daily':
                # merged_df = merged_df.reset_index()
                merged_df = merged_df.filter(items=column_order)
                all_dfs.append(merged_df)

        excel_file = IO()
        writer = pd.ExcelWriter(excel_file, engine="xlsxwriter")
        for i, df in enumerate(all_dfs):
            if df.empty:
                empty_df = pd.DataFrame(columns=df.columns)
                empty_df.to_excel(writer, sheet_name=str(userNames[i]), index=False)
                # continue

            # for col in df.select_dtypes(include=['datetimetz']).columns:
            #     df[col] = df[col].dt.tz_localize(None)

            # if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            #     df.index = df.index.tz_localize(None)

            df.to_excel(writer, sheet_name="{}".format(userNames[i]),index=False)

        writer.close()
        excel_file.seek(0)

        # file name generation
        utc_startDateTime = startDateTime.replace(tzinfo=timezone.utc)
        utc_stopDateTime = stopDateTime.replace(tzinfo=timezone.utc)
        offset = timezone(datetime.timedelta(hours=utc_offsets[0]['hours'], minutes=utc_offsets[0]['minutes']))
        local_startDateTime = utc_startDateTime.astimezone(offset)
        local_stopDateTime = utc_stopDateTime.astimezone(offset)
        date_range = f"{local_startDateTime.strftime('%d%m%Y %H_%M_%S')} to {local_stopDateTime.strftime('%d%m%Y %H_%M_%S')}"

        if OrganisationName:
            filename = f"Respiree_PatientVitals_{OrganisationName}_{date_range}.xlsx"
        else:
            filename = f"Respiree_PatientVitals_{date_range}.xlsx"
        response = HttpResponse(
            excel_file.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
        # return HttpResponse()

