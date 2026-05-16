import datetime
import pytz
from celery import shared_task
import logging
from decimal import Decimal
import requests
import numpy as np
from .models import *
from . import lib_query
from . import lib_common as common
from django.db import DatabaseError

from .helpers import get_utc_offset,handle_list_trigger1
from dataprocessing import lib_settings as settings
from data_app.staging_hourly import  staging_hourly


def get_only_valid_medians(medians, user_id):
    previous = MetricDailyCache.objects.filter(user_id=user_id)

    # If there is no previous medians, then no choice but to update it as it is, regardless of validity
    if not previous.exists():
        return medians
    previous = previous.first()
    # If any of the current medians are invalid, we use the previous set of cache instead (assuming the previous set will always contain all valid medians)
    for k, v in medians.items():
        if not v or v == settings.val_replace_NaN:
            medians[k] = getattr(previous, k.lower())
    return medians


def get_daily_medians(start_date, stop_date, utc_offset, dataprocessing_instances):

    data_length = (stop_date - start_date).days + 1

    desired_attr = ['rr', 'hr', 'spo2', 'rr_td',
                    'rr_dc', 'body_temperature', 'skin_temperature']
    cond_attr = ['RR', 'HR', 'HR', 'RR', 'RR', 'RR', 'RR']

    query_ttems = dataprocessing_instances.values()

    list_time_output = []
    for i in range(data_length, 0, -1):
        offset = datetime.timedelta(
            hours=utc_offset[0], minutes=utc_offset[1])
        min_hr_finger_required = settings.min_hr_finger_required_within_day
        temp_date_time = (stop_date + offset).replace(hour=0,
                                                      minute=0, second=0) - datetime.timedelta(days=i - 1)
        temp_date_time = temp_date_time - offset
        list_time_output.append(temp_date_time)

    if not (len(list_time_output) > 0 and list_time_output[-1] == stop_date):
        list_time_output = list_time_output + [stop_date]

    try:
        items = query_ttems.copy()
    except:
        items = list(query_ttems).copy()

    medians = {}
    median_val = {}

    for i, attr in enumerate(desired_attr):
        median_val[attr] = []

    time_lower = list_time_output[0]
    time_upper = list_time_output[1]

    items, temp_item = lib_query.extract_items_in_range_and_remove_from_original(
        items, time_lower, time_upper)
    temp_item = common.remove_bad_data(temp_item)
    temp_item = common.filter_data_based_on_quality_status(
        temp_item, settings.list_quality_to_keep)

    rr_idx_latest = common.get_last_index_with_key_value(
        temp_item, 'dashboard_mode', 'RR')
    hr_idx_latest = common.get_last_index_with_key_value(
        temp_item, 'dashboard_mode', 'HR')

    if rr_idx_latest is not None:
        rr_idx_latest = rr_idx_latest[-1]
        medians['datetime_latest_valid_chest'] = temp_item[rr_idx_latest]["date_time"]

    if hr_idx_latest is not None:
        hr_idx_latest = hr_idx_latest[-1]
        medians['datetime_latest_valid_finger'] = temp_item[hr_idx_latest]["date_time"]

    for i, attr in enumerate(desired_attr):

        # Step 1 - Extract from Sensor information
        attr_val = lib_query.collect_same_key_from_list_of_dict_into_array(
            temp_item, 'dashboard_mode', cond_attr[i], attr)

        # combine HR from finger with chest if number of HR from finger is lesser than threshold
        if attr == 'hr' and len(attr_val) < min_hr_finger_required:
            tempValHR_from_chest = lib_query.collect_same_key_from_list_of_dict_into_array(
                temp_item, 'dashboard_mode', 'RR', 'hr')
            attr_val = np.append(attr_val, tempValHR_from_chest)

        # Step 2 - Calculate the statistics
        tmp_median, _ = lib_query.calculate_stat_np1Darray(
            attr_val, settings.val_replace_NaN, True, 'median')

        # Step 3 - Add it into the list
        if isinstance(tmp_median, float):
            tmp_median = Decimal(str(tmp_median))

        medians[attr] = tmp_median

    return medians


@shared_task(name="handle_update_cache_query")
def handle_update_cache_query(utc_offset, ids, date_time):
    metric_cache_instances = []
    utc_offset = get_utc_offset(utc_offset)
    
    for user_id in ids:

        # Need check if user is in demo_id
        if str(user_id) in settings.list_demo_id:
            msg = 'Specified id {} is not actual user. Cache is not updated.'.format(
                str(user_id))
            logging.info(msg)
            continue
        stop_date = date_time

        # Check vital signs table if within the last day are there any updates
        offset = datetime.timedelta(
            hours=utc_offset[0], minutes=utc_offset[1])
        if (stop_date + offset).hour == 0 and (stop_date + offset).minute == 0:
            start_date = (stop_date + offset) - datetime.timedelta(days=1)
        else:
            start_date = (stop_date + offset).replace(hour=0,
                                                      minute=0, second=0)
        start_date = start_date - offset

        dataprocessing_instances = DataProcessing.objects.filter(
            user_id=user_id, date_time__range=(start_date, stop_date))
        if dataprocessing_instances.exists():
            #   - calculate daily median
            medians = get_daily_medians(
                start_date, stop_date, utc_offset, dataprocessing_instances)
            medians = get_only_valid_medians(medians, user_id)
            cache = {**medians, **{
                'last_sync': lib_query.get_latest_datetime(dataprocessing_instances, 'datetime_gateway_sent'),
                'bp_sys': settings.val_replace_NaN,
                'bp_dia': settings.val_replace_NaN,
                'flag': settings.val_replace_NaN,
                'flag_notification': '--',
                'user_id': user_id
            }}

            metric_cache = MetricDailyCache.objects.update_or_create(
                **cache, defaults={'datetime_updated': stop_date})[0]
            metric_cache_instances.append(metric_cache)

    return metric_cache_instances


@shared_task(name="real_time_trigger")
def real_time_trigger(metric_minutes_cache_id):
    output_response_list = {}
    output_response_trend = {}
    input = MetricMinutesCache.objects.filter(pk=metric_minutes_cache_id).values().first()

    user_id = input['user_id']
    output_response_list = input

    date_now = datetime.datetime.now()
    date_str = date_now.strftime("%Y-%m-%d %H:%M:%S")
    dateTime = pytz.UTC.localize(
        datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S"))    

    list_resolution = 'minutes'
    output_list_trigger = handle_list_trigger1(
        output_response_list, user_id, list_resolution, dateTime)

    date_str = date_now.strftime("%Y-%m-%d %H:%M:%S")
    dateTime = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return { "list_trigger": output_list_trigger}


@shared_task(name="cron_staging_hourly", queue="staging_queue")
def cron_staging_hourly():
    staging_hourly()
