import pytz
import json
import logging
from decimal import Decimal
import requests
from .models import *
from . import lib_query

from dataprocessing import lib_settings as settings

from datetime import datetime, timezone, timedelta
import pandas as pd
from urllib.parse import urljoin
from dateutil.relativedelta import relativedelta

from .lib_common_ai import fetch_patient_details, format_model_list
from .lib_common import remove_processing_records, backend_service_post_request

PATIENT_DEMOGRAPIC_POST_URL = urljoin(
    settings.AI_BACKEND_URL, settings.UI_URL_REST_API_postDemographicInfo
)
PATIENT_DETAILS_GET_URL = urljoin(
    settings.UI_URL_REST_API_BASE, settings.UI_URL_REST_API_getPatientDetails
)

HEADERS = {
    "accept": "*/*",
    "server-auth-key": settings.UI_REST_API_HEADER["server-auth-key"],
    "Content-Type": "application/json",
}

response_header = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",  # Allow from anywhere
    "Access-Control-Allow-Methods": "GET",  # Allow only GET request
}


def compute_news_score(row):
    """
    Compute and update the National Early Warning Score (NEWS) for a given vital sign row.

    Parameters:
        row (pd.Series): A pandas Series representing a row of user vital signs.
    Returns:
        int or None: The calculated NEWS score, or None if it couldn't be computed.
    """

    news_score = None
    user_id = str(row["user_id"])

    try:
        row_dict = row.to_dict()
        row_dict = {
            key: None if pd.isna(value) else value for key, value in row_dict.items()
        }

        if any(key in ['rr','hr','spo2','bp_sys','body_temperature'] for key in row_dict) :
            input_for_ews = {
                "rr": row_dict.get("rr", None),
                "hr": row_dict.get("hr", None),
                "spo2": row_dict.get("spo2", None),
                "bp_sys": row_dict.get("bp_sys", None),
                "temp": row_dict.get("body_temperature", None),
            }
            logging.info(f"[{user_id}] Input for EWS: {input_for_ews}")

            class_ews = lib_query.EarlyWarningScore(input_for_ews)
            news_score = class_ews.get_score("NEWS")
            logging.info(f"[{user_id}] Computed NEWS score: {news_score}")
        else:
            logging.info(f"[{user_id}] No relevant vitals found to compute NEWS.")

    except Exception as e:
        logging.warning(f"[{user_id}] Error computing NEWS score: {e}", exc_info=True)
    
    try:
        date_time_updated = row["datetime_updated"]
        
        if news_score is not None:
            news_value = Decimal(str(news_score))
            hourly_records = MetricHourlyCache.objects.filter(user_id = user_id,datetime_updated = date_time_updated)
            patient_cache_records = PatientListCache.objects.filter(user_id = user_id,resolution = 'hourly')
            if hourly_records.exists():
                hourly_records.update(news = news_value)
                patient_cache_records.update(news = news_value)
                logging.info(f"[{user_id}] NEWS score updated in DB at {date_time_updated}")
        else:
            logging.info(f"[{user_id}] NEWS score is None or datetime_updated missing — skipping DB update.")

    except Exception as e:
        logging.error(f"[{user_id}] Failed to update NEWS in DB at {date_time_updated}: {e}", exc_info=True)

    return news_score


def fetch_dynamodb_records():
    """
    Fetch records from DynamoDB 'metric_hourly_staging_table' updated within the last hour.

    Returns:
        tuple: (records: list or None, status_code: int, message: str or None)
    """
    
    current_utc_time = datetime.now(timezone.utc)
    hour_diff_time = current_utc_time - timedelta(hours=1)
    start_time = hour_diff_time.strftime("%Y-%m-%d %H:00:00")
    stop_time = hour_diff_time.strftime("%Y-%m-%d %H:59:59")
    
    logging.info(
        f"Querying DynamoDB for records updated between {start_time} and {stop_time} UTC."
    )

    try:
        staging_hourly_records = StagingHourlyCache.objects.filter(datetime_updated__range = (start_time, stop_time)).values()

        if not staging_hourly_records.exists():
            logging.info("No records found in the specified time range.")
            return [], 200, "No data to process"

        logging.info(f"Retrieved {len(staging_hourly_records)} records from DynamoDB.")    
        return staging_hourly_records, 200, None
    
    except Exception as e:
        logging.error(f"Exception occurred while querying DynamoDB: {e}", exc_info=True)
        return None, 400, f"DynamoDB query error: {e}"


def process_and_send_records(records):
    """
    Process a batch of patient vital records, compute NEWS scores, 
    filter relevant records, and send the processed data to the AI backend.

    Args:
        records (list of dict): Raw patient vital records.

    Returns:
        tuple: (status_code:int, message:str)
    """

    df = pd.DataFrame(records)
    df["user_id"] = pd.to_numeric(df["user_id"], errors="coerce").astype("Int64")
    logging.info(f"Process record {len(df)} in staging. Content {df}")

    # Ensure required vital sign columns exist and convert them to Float64
    cols_to_convert = ["rr", "hr", "spo2", "body_temperature", "bp_sys", "bp_dia"]
    for col in cols_to_convert:
        if col not in df.columns:
            df[col] = None
    df[cols_to_convert] = (
        df[cols_to_convert].apply(pd.to_numeric, errors="coerce").astype("Float64")
    )

    # Compute NEWS for each record in the DataFrame
    logging.info("Calculating NEWS scores for each record.")
    df["news"] = df.apply(lambda row: compute_news_score(row), axis=1)

    user_id_list = df["user_id"].unique()
    user_dob_mapping = fetch_patient_details(user_id_list)

    dob_df = pd.DataFrame.from_dict(user_dob_mapping, orient="index").reset_index()
    dob_df.rename(columns={"index": "user_id"}, inplace=True)
    df = df.merge(dob_df, on="user_id", how="left")
    df["age"] = df["age"].fillna(0).astype(int)

    for organization_id, user_id, news in zip(df['organization_id'], df['user_id'], df['news']):
        if news != None:
            try:
                updated_rows = PatientListCache.objects.filter(
                        organization=organization_id, user_id=user_id, resolution='hourly'
                    ).update(news=news)
                if updated_rows:
                    logging.info(f"[{organization_id}#{user_id}#hourly] NEWS score updated in patient list cache")
                else:
                    logging.warning(f"[{organization_id}#{user_id}#hourly] No matching record found to update")
            except Exception as e:
                logging.error(f"[{organization_id}#{user_id}#hourly] Failed to update NEWS score: {e}", exc_info=True)

    #send news value to BE master cache
    try:
        if news != None:
            payload = {
                    "data": [
                        {
                            "userId": int(user_id),
                            "source": settings.datasource_to_payload_mapping.get("sensor"),
                            "latestVitals": {
                                "hourly": {"news": int(news)}
                            },
                        }
                    ]
                }
            mastercache_post_url = urljoin(
                settings.backend_url, settings.UI_URL_REST_API_MASTER_CACHE
            )
            status_code, message = backend_service_post_request(mastercache_post_url, payload)
            if status_code in range(200, 300):
                logging.info(f"[NEWS] Master Cache updated successfully for user {user_id}. {message}")
            else:
                logging.warning(f"[NEWS] Failed to update Master Cache for user {user_id}. {message}")
    except Exception as e:
        logging.error(f"Error while preparing payload for Master Cache update for user {user_id}. Error: {str(e)}")

    # LOGIC : Keep only rows where 'isonwatchlist' is True, 'resolution' is 'hourly', and 'isactive' is True
    df = df[(df['isonwatchlist'] == True) & (df['resolution'] == 'hourly') & (df['isactive'] == True)]
    logging.info(f"Filtered records to {len(df)} for watchlist and hourly resolution.")


    if df.empty:
        logging.info("No eligible records found for processing after filtering.")
        return 200, "No eligible records found for processing"

    payloads = df.apply(
        lambda row: {
            "user_id": row["user_id"],
            "age": None if pd.isna(row["age"]) else row["age"],
            "gender": None if pd.isna(row["gender"]) else row["gender"].capitalize(),
            "is_watchlist": (
                False if pd.isna(row["isonwatchlist"]) else row["isonwatchlist"]
            ),
            "resolution_setting": (
                None if pd.isna(row["resolution"]) else row["resolution"]
            ),
            "model_list": format_model_list(row["model"]),
            "threshold": None if pd.isna(row["threshold"]) else row["threshold"],
            "source": settings.DATA_SOURCE["Sensor"],
            "data": {
                "rr": None if pd.isna(row["rr"]) else row["rr"],
                "hr": None if pd.isna(row["hr"]) else row["hr"],
                "spo2": None if pd.isna(row["spo2"]) else row["spo2"],
                "bp_sys": None if "bp_sys" not in row or pd.isna(row.get("bp_sys")) else row.get("bp_sys"),
                "bp_dia": None if "bp_dia" not in row or pd.isna(row.get("bp_dia")) else row.get("bp_dia"),
                "body_temp": (
                    None
                    if pd.isna(row["body_temperature"])
                    else row["body_temperature"]
                ),
            },
            "dynamic_model_selection_enabled": row["dyn_model_selection"],
            "datetime": row["datetime_updated"],
            "flushout_period": None if pd.isna(row["flushout_period"]) else row["flushout_period"],
        },
        axis=1,
    ).tolist()
    logging.info(f"Constructed payloads for {len(payloads)} records. Sending to AI backend.")

    try:
        response = requests.post(
            PATIENT_DEMOGRAPIC_POST_URL, json={"vitals": payloads}, headers=HEADERS
        )
        response.raise_for_status()
        logging.info(f"Successfully sent data. Records : {payloads}.")

        record_ids = df["id"].tolist()
        StagingHourlyCache.objects.filter(id__in=record_ids).delete()
        logging.info(f"Deleted {len(record_ids)} records from staging after successful processing.")

        return 200, f"Successfully processed {len(records)} records"

    except requests.RequestException as e:
        logging.error(f"Failed to send data to AI backend: {e}", exc_info=True)
        return 400, f"Failed to process records: {str(e)}"


def remove_processing_records_from_df(df: pd.DataFrame):
    """
    Iterates over a DataFrame and removes processing records for both
    'sensor' and 'health_input' data sources using the provided userId
    and timestamp.
    Expected columns in df:
        - userId
        - dateTimeUpdated
    :param df: pandas DataFrame with userId and dateTimeUpdated
    """
    df["user_id"] = pd.to_numeric(df["user_id"], errors="coerce").astype("Int64")
    logging.info(f"Processing {len(df)} records for removal from process-in-progress. Content : {df}")
    
    for index, row in df.iterrows():
        user_id = row['user_id']
        timestamp = row['datetime_updated']
        logging.info(f"Processing record {row}")

        try:
            logging.info(f"Started removing processing record for user_id {user_id} at {timestamp}")
            remove_processing_records(user_id, timestamp)

            test_user_id_list = settings.list_test_user_id
            if user_id in test_user_id_list:
                logging.info(f"User ID {user_id} is a test user. Removing processing records without timestamp.")
                remove_processing_records(user_id)

        except Exception as e:
            logging.error(
                f"Failed to remove processing records for user_id {user_id} at timestamp {timestamp}. Error: {e}",
                exc_info=True
            )

    logging.info("Processing complete for all records.")


def staging_hourly():

    logging.info(f"triggered main_upload_staging at UTC {str(datetime.now(timezone.utc))}")

    records, status, error_message = fetch_dynamodb_records()
    logging.info(f"processing main_upload_staging of records of patients: {str(records)}")

    if error_message:
        return {
            "statusCode": status,
            "body": json.dumps({"statusCode": status, "response": error_message}),
        }

    status, message = process_and_send_records(records)
    records_df = pd.DataFrame(records)
    remove_processing_records_from_df(records_df)

    return {
        "statusCode": status,
        "body": json.dumps({"statusCode": status, "response": message}),
    }
