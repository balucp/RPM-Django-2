import sys
import traceback
import requests
import pandas as pd
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from urllib.parse import urljoin
from dataprocessing import lib_settings as settings


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


def fetch_patient_details(user_id_list):
    """
        Fetch detailed patient information from an external REST API for a list of user IDs.

        This function calls the external patient details API and gathers the following 
        information for each valid user ID (user_id >= 0):
            - Date of birth (dob)
            - Age (calculated from dob)
            - Gender
            - Watchlist status (isOnWatchlist)
            - Patient resolution setting
            - Selected AI model name
            - Model pipeline configuration
            - AI solution flush-out period

        Parameters:
        ----------
        user_id_list : list[int]
            List of user IDs (integers) for which the patient details are to be fetched.

        Returns:
        -------
        dict[int, dict]
            A dictionary mapping each user ID to their corresponding patient detail dictionary. 
            Each entry contains keys: 'dob', 'age', 'gender', 'isonwatchlist', 'resolution', 
            'model', 'modelconfig', and 'flushout_period'.
    """

    def calculate_age(dob):
        if not dob:
            return None
        dob = datetime.strptime(dob, "%Y-%m-%d")
        age = relativedelta(datetime.now().date(), dob)
        return age.years

    user_id_list = [uid for uid in user_id_list if uid > 0]
    user_id_string = ",".join(map(str, user_id_list))

    url = f"{PATIENT_DETAILS_GET_URL}?patientIds={user_id_string}"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            logging.error(f"Backend API {url} failed. Status code is {response.status_code}")
        patient_details = response.json()
    except Exception as e:
        patient_details = []
        logging.error(f"Unexpected error occurred while fetching patient details: {e}")

    user_dob_mapping = {}
    user_dob_mapping = {
        user_id: {
            "dob": None,
            "age": None,
            "gender": None,
            "isonwatchlist": None,
            "resolution": None,
            "modelconfig": None,
        }
        for user_id in user_id_list
    }
    for patient_info in patient_details:
        patient_id = patient_info.get("patientId")
        patient_data = patient_info.get("patient", {})
        ai_solution_settings = patient_info.get("aiSolutionSetting", {})
        resolution = patient_data.get("patientResolution", {}).get("resolution")
        if resolution == 'hourly':
            model_field = 'hourlySelectedModels'
            dyn_model_selection_field = 'dynamicHourlyModelSelectionEnabled'
        else:
            model_field = 'minuteSelectedModels'
            dyn_model_selection_field = 'dynamicMinuteModelSelectionEnabled'
        if patient_id in user_dob_mapping:
            user_dob_mapping[patient_id] = {
                "dob": patient_info.get("dob"),
                "age": calculate_age(patient_info.get("dob")),
                "gender": patient_data.get("gender"),
                "organization_id": patient_data.get("organizationId"),
                "isonwatchlist": patient_data.get("isOnWatchlist"),
                "resolution": resolution,
                "model": ai_solution_settings.get(model_field, []),
                "dyn_model_selection": ai_solution_settings.get(dyn_model_selection_field, False),
                "threshold": ai_solution_settings.get("probabilityThreshold"),
                "flushout_period": ai_solution_settings.get("flushOutPeriod") or None,
                "isactive": ai_solution_settings.get("isActive", False),
            }

    return user_dob_mapping


def generate_ai_prediction_minute(item):
    item["datetime_updated"] = item["date_time"]
    df = pd.DataFrame([item])
    user_id_list = [item["user_id"]]
    user_dob_mapping = fetch_patient_details(user_id_list)

    dob_df = pd.DataFrame.from_dict(user_dob_mapping, orient="index").reset_index()
    dob_df.rename(columns={"index": "user_id"}, inplace=True)

    df = df.merge(dob_df, on="user_id", how="left")
    df["age"] = df["age"].fillna(0).astype(int)

    cols_to_convert = ["rr", "hr", "spo2", "body_temperature", "bp_sys", "bp_dia"]
    # Ensure all columns exist in DataFrame, fill missing ones with None (NaN)
    for col in cols_to_convert:
        if col not in df.columns:
            df[col] = None
    df[cols_to_convert] = (
        df[cols_to_convert].apply(pd.to_numeric, errors="coerce").astype("Float64")
    )

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
            "model": None if pd.isna(row["model"]) else row["model"],
            "model_config": None if pd.isna(row["modelconfig"]) else row["modelconfig"],
            "data": {
                "rr": None if pd.isna(row["rr"]) else row["rr"],
                "hr": None if pd.isna(row["hr"]) else row["hr"],
                "spo2": None if pd.isna(row["spo2"]) else row["spo2"],
                "bp_sys": (
                    None
                    if "bp_sys" not in row or pd.isna(row.get("bp_sys"))
                    else row.get("bp_sys")
                ),
                "bp_dia": (
                    None
                    if "bp_dia" not in row or pd.isna(row.get("bp_dia"))
                    else row.get("bp_dia")
                ),
                "body_temp": (
                    None
                    if pd.isna(row["body_temperature"])
                    else row["body_temperature"]
                ),
            },
            "datetime": row["datetime_updated"].strftime("%Y-%m-%d %H:%M:%S"),
            "flushout_period": (
                None if pd.isna(row["flushout_period"]) else row["flushout_period"]
            ),
        },
        axis=1,
    ).tolist()

    try:
        response = requests.post(
            PATIENT_DEMOGRAPIC_POST_URL, json={"vitals": payloads}, headers=HEADERS
        )
        response.raise_for_status()
        return f"Successfully processed  records"
    except requests.RequestException as e:
        logging.error(f"Failed to send data: {payloads}, Error: {e}")
        return f"Failed to process records: {str(e)}"
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error("Error in function trigger_staging_hourly: {}".format(err))


def format_model_list(val):
    """
    Format the model list field.

    - If val is None or NaN -> return {}.
    - If val is a list of dicts -> return only the "name" fields as a list of dicts.
    - Otherwise -> return {}.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, list) and len(val) == 0):
        return {}
    if isinstance(val, list):
        return [{"name": item["name"]} for item in val if "name" in item]
    return {}
