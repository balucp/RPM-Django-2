import os
from django.conf import settings

make_timezone_aware = True if int(os.environ.get("MAKE_TIMEZONE_AWARE")) == 1 else False  # TODO do we need this?
path_raw_data = os.path.join(settings.PATH_FOLDER_STORAGE, 'rawdata')
path_folder_model = os.path.join(settings.BASE_DIR, 'model')

datetime_format = '%Y-%m-%d %H:%M:%S'


SPOT_CACHE_MAX_LEN = 200


wait_for_next_packet = 10

list_test_user_id = ["-1"]

list_demo_id = []

list_nuh_demo_id = []

list_mgh_demo_id_02 = [] # CF
list_mgh_demo_id_03 = [] # Asthma
list_mgh_demo_id_10 = [] # COPD
list_mgh_demo_id_04 = [] # CF
list_mgh_demo_id_13 = []

list_dover_demo_IP234028 = []

list_demo_id = list_demo_id + list_nuh_demo_id + list_mgh_demo_id_02 + list_mgh_demo_id_03 + list_mgh_demo_id_10 + list_mgh_demo_id_04 + list_mgh_demo_id_13 + list_dover_demo_IP234028

list_demo_id_data_from_db = []

# backend request urls
backend_url = os.environ.get("BACKEND_URL")
backend_auth_key = os.environ.get("BACKEND_AUTH_KEY") # backend request tokens # TODO check if this is needed
query_url = os.environ.get("QUERY_URL")


UI_URL_REST_API_updateSensorLastConnectionTime = '/api/sensor/updateSensorLastConnectionTime'
UI_URL_REST_API_updateGatewayLastConnectionTime = '/api/gateway/updateGatewayLastConnectionTime'
UI_URL_REST_API_getPatientDevicesInfo = '/api/data-server/patient-devices'
UI_URL_REST_API_getMultiplePatientDevicesInfo =  '/api/data-server/patient-devices/v2'
UI_URL_REST_API_patientUpdateTriggerList = '/api/data-server/patient-update-trigger/list'
UI_URL_REST_API_patientUpdateTriggerTrend = '/api/data-server/patient-update-trigger/trend'
UI_URL_REST_API_getPatientDetails = '/api/data-server/patient-details'
UI_URL_REST_API_SENSOR = "/api/data-server/sensor"
UI_URL_REST_API_MASTER_CACHE = "/api/data-server/master-cache"

UI_REST_API_HEADER = {
    os.environ.get("BACKEND_SERVER_TO_SERVER_KEY"): os.environ.get("BACKEND_SERVER_TO_SERVER_VALUE")
}



# ML - SQA
model_sqa = 'rf_sqa_160523.pkl' # rf_old_model_modified_label.pkl, rf_sqa_160523.pkl


### TO CHECK ###
PD_max_count = 1024

# range to check signal saturation
sensor_max_count_mean = 1024
sensor_max_count_std = 100


# SQA parameters
sqa_bandpass_rr = [0.13, 0.67]
sqa_bandpass_hr = [0.65, 3.35]

sqa_threshold_rr = [0.3, 0.65]
sqa_threshold_hr = [0.3, 0.65]

sqa_threshold_rr_pos_to_neg_peak = 0.9
sqa_threshold_hr_pos_to_neg_peak = 0.9
sqa_threshold_spo2_pos_to_neg_peak = 0.9 # 0.6 reduced on 26 Mar 2021

sqa_bandpass_hr_individual_frame = 0.65
sqa_bandpass_rr_individual_frame = 0.65
sqa_bandpass_spo2_individual_frame = 0.65

# SpO2
spo2_bandpass = [0.5, 3] #[0.67, 2.0833333] #[0.5, 2.0833333] #[0.8333, 2] #[0.65, 2.5]
# spo2_max = 90
spo2_minmax = [70, 100]

# +/- frequency to check harmonic
harmonic_accpeted = 0.015

# parameter for peak detection algorithm
delta_peakdet = 0.01

# fft parameter
nfft = 2**12


# signal quality threshold to display data
threshold_accepted_frame_spo2_ratio = 0.2
threshold_accepted_frame_spo2_frame_number = 8
threshold_signal_sd = 0.4
threshold_median_list_output_stdev = 4.5


# RR bandpass
bandpass_rr = [7, 50] # BPM




trends_vital_sign_minutes_resolution = 5
trends_vital_sign_minutes = 60*2 # /trends_vital_sign_minutes_resolution
trends_vital_sign_hourly = 24 # hours
trends_vital_sign_daily = 14 # days


BOOL_DISPLAY_HR_FROM_CHEST_IN_TREND_MINUTES = True

BOOL_COMPUTE_HR_FROM_CHEST = True

windowsize_baseline = 24*60 # minutes


val_replace_NaN = -1



# # benchmark (spot check)
spot_lookback_window = 60*24 # minutes
spot_lookback_limit_data_point = 60*24

latest_spot_th_delta_temperature = 0.2
latest_spot_min_skin_temperature = 33
latest_spot_window_size = 2
threshold_skin_temperature_on_skin = 0 #33
threshold_chest_skin_temperature_latest_spot = 33


error_handling_minmax_skin_temperature_value = [0.0, 45.0]
error_handling_minmax_skin_temperature_value_bool = True


""" filter data for hourly and minutes trends """
list_quality_to_keep = ['Good', 'Moderate']


# minimum HR from finger required, unless combine with HR from chest (in a day)
min_hr_finger_required_within_day = 1
min_hr_finger_required_within_hour = 1
min_hr_finger_required_within_interval = -1 # for baseline on dashboard list of patient


# step count
stepcount_algo_delta = 20
stepcount_algo_mva_wsize = 5


# activeness
activeness_wsize_mva = 3 #50
activeness_wsize_bl = 9 #150
activeness_threshold = 1000
activeness_mask_size_seconds = 30 #5*60



# check device status
check_sensor_if_online_within = 60*7 #150 # seconds
check_gateway_if_online_within = 60*7 # seconds


params_onoffskin_rr = {
    "threshold": 3,
    "window_size": 500, #167, #500,
    "window_shift": 250, #86, #250,
    "freq_lim": 2,
    "bandpass_lower_lim": 0.18,
    "bandpass_higher_lim": 0.68,
    "signal_stdev_threshold": [1, 20],
}

params_onoffskin_hr = {
    "threshold": 3.3, 
    "window_size": 750,
    "window_shift": 750, #375,
    "freq_lim": 5,
    "bandpass_lower_lim": 0,
    "bandpass_higher_lim": 5,
    "signal_stdev_threshold": [1, 20],
    "threshold_2lightsources_median": 20,
}

#
list_timedelta = {"MINUTES": 60 * 8, "HOURS":24, "DAYS": 7}

#for gateway and sensor statuses
device_code = {
    'OFFLINE': 0,
    'ONLINE': 1,
    'REGISTERING': -1,
    'NOT_ASSIGNED': None
}

sensor_mode =  {'HR': {
    'sensor_status': 'sensor_status_finger', 
    'last_connect_time':'sensor_finger_last_connect_time'
    }
    ,'RR': {
        'sensor_status': 'sensor_status_chest', 
        'last_connect_time': 'sensor_chest_last_connect_time'
    }
    ,'GEN': {
        'sensor_status': 'sensor_status', 
        'last_connect_time': 'last_connect_time'
    }
}

# minimum data length required to computed RR, HR, and SpO2
threshold_min_length_compute_metric = {
    "RR": 1000, # if data length is lesser than threshold, RR and skin contact become NaN
    "HR": 654, # if data length is lesser than threshold, HR and skin contact become NaN
    "SpO2": 505, # if data length is lesser than threshold, SpO2 and skin contact become NaN
    "finger_on_skin_algo": 754 # if data length is lesser than threshold, skin contact become NaN
}


def initParameters(mode):
    params = {}

    if mode=='RR-60ms': 
        # CGH A params - Original
        params['sampling_time'] = 0.06 # second

        # parameters for signal processing
        params['window_mva'] = 15
        params['window_bl'] = 250
        params['window_art_mva'] = 83 # 3
        params['window_art_bl'] = 666 # 5
        params['window_smooth_output'] = 9 #3# # smoothen output after artifact removal
        params['th_prepro'] = 3 #1e10000# # coefficient for artifact removal
            
        # parameters for metric extraction
        params['lag'] = 2
        params['coef_A'] = 1.2
        params['coef_B'] = 0.08
        params['val_min'] = 1.5
        params['val_max'] = 15

        # window for metric extraction data streaming
        params['window_size'] = 1083 #500 #1083
        params['window_shift'] = 17 #41

        params['buffer'] = params['window_mva']+params['window_bl']-1+3-1+params['window_art_mva']-1+params['window_art_bl']-1+params['window_size']-1

        params['window_size_reduced'] = 333 #500 #700 #450
        params['window_art_mva_reduced'] = 83
        params['window_art_bl_reduced'] = 666
    
    elif mode=='RR-hybrid-algo-60ms': 
        params = {}

        params['sampling_time'] = 0.06 # second

        # parameters for signal processing
        params['window_mva'] =15
        params['window_bl'] = 250
        params['window_art_mva'] = 83
        params['window_art_bl'] = 667
        params['window_smooth_output'] = 9 # smoothen output after artifact removal
        params['th_prepro'] = 3 # coefficient for artifact removal

        # parameters for metric extraction
        params['lag'] = 2 #2
        params['coef_A'] = 0.8 #0.8
        params['coef_B'] = 0.5 #0.2 #0.08 !!!
        params['val_min'] = 1.0 #1.5
        params['val_max'] = 30 #15

        # window for metric extraction data streaming
        params['window_size'] = 1083
        params['window_shift'] = 16*1 #16


        # # freq domain processing params
        # params['delta_peakdet'] = 0.01 # parameter for peak detection algorithm
        # params['nfft'] = 2**12 # fft parameter
        params['sqa_bandpass'] = [0.05, 1.167] #[0.13, 0.67] # SQA parameters

        # params['threshold_diff_local_maxima_mimima'] = 0.85 #0.5

        # params['sqa_threshold_rr'] = [0.3, 0.65]
        # params['sqa_bandpass_rr_individual_frame'] = 0.65
        # params['sqa_threshold_rr_pos_to_neg_peak'] = 0.9
        # params['harmonic_accpeted'] = 0.015 # +/- frequency to check harmonic

    elif mode=='RR-40ms': 
        # CGH B params 46 participants
        params['sampling_time'] = 0.04 # second

        # parameters for signal processing
        params['window_mva'] = 21
        params['window_bl'] = 250
        params['window_art_mva'] = 187
        params['window_art_bl'] = 750
        params['window_smooth_output'] = 13 # smoothen output after artifact removal
        params['th_prepro'] = 2 # coefficient for artifact removal
            
        # parameters for metric extraction
        params['lag'] = 2
        params['coef_A'] = 1.2
        params['coef_B'] = 0.12
        params['val_min'] = 1.5
        params['val_max'] = 10

        # window for metric extraction data streaming
        params['window_size'] = 1500
        params['window_shift'] = 25 #*10

        params['buffer'] = params['window_mva']+params['window_bl']-1+3-1+params['window_art_mva']-1+params['window_art_bl']-1+params['window_size']-1

        params['window_size_reduced'] = 350
        params['window_art_mva_reduced'] = 100
        params['window_art_bl_reduced'] = 350


    elif mode=='HR':

        # CGH B - 43 patients
        params = {}

        params['sampling_time'] = 0.04 # second

        # parameters for signal processing
        params['window_mva'] = 5 #3
        params['window_bl'] = 25
        params['window_art_mva'] = 125
        params['window_art_bl'] = 250
        params['window_smooth_output'] = 3 # smoothen output after artifact removal
        params['th_prepro'] = 1.5 # coefficient for artifact removal
            
        # parameters for metric extraction
        params['lag'] = 2
        params['coef_A'] = 1
        params['coef_B'] = 0.08
        params['val_min'] = 0.3
        params['val_max'] = 1.5

        # window for metric extraction data streaming
        params['window_size'] = 625
        params['window_shift'] = 25 #* 10

    
    elif mode=='SpO2': 
        """
        SpO2
        """
        params['sampling_time'] = 0.04
        params['window_mva'] = 11
        params['window_size'] = 750
        params['window_shift'] = 25
        # params['rawdata_size'] = params['spo2_window_mva']+params['spo2_window_size']-1
    
    elif mode=='SpO2-fft':
        params['sampling_time'] = 0.04
        params['window_mva'] = 5 #11
        params['window_size'] = int(20/0.04)#125 [5,30,45]
        params['window_shift'] = 25 #+175# shift every 1s



    elif mode=='wavelets_HR_60ms':
        params = {
            "sampling_time": 0.06,
            
            "window_size": 167,
            "window_shift": 50,
            "window_mva": 0,
            "window_bl": 17,
            "window_art_mva": 83,
            "window_art_bl": 167,
            "window_smooth_output": 3,
            "th_prepro": 1.5,
            
            "filter_size": 22,
            "cwt_bandpass": [0.7, 2], #[0.7, 1.67], #[0.7, 2],
            "cwt_function": "morl",
            "cwt_bins": 300,
            "cwt_scale": [1,50],
            "select_nth_peak_algo": 2,
            "th_scaling": 1
        }
    

    elif mode=='wavelets_HR_40ms':
        params = {
            "sampling_time": 0.04,

            "window_size": 625,
            "window_shift": 25,
            "window_mva": 5,
            "window_bl": 25,
            "window_art_mva": 125,
            "window_art_bl": 250,
            "window_smooth_output": 3,
            "th_prepro": 1.5,
            
            "filter_size": 90,
            "cwt_bandpass": [0.8, 1.67], #[0.8, 2],
            "cwt_function": "morl",
            "cwt_bins": 300,
            "cwt_scale": [1,50],
            "select_nth_peak_algo": 2,
            "th_scaling": 0.8
        }

    
    return params
    
"""define auth key for device - gateway communincation"""
VALID_REFERER = ["OtjwMcfM1RH+Tl65wKPciB73HXFKpJkWhap2ZlF4fE3PB36bLCnnG1tePXLBdcrlTmPNcGM+1pfhw2NlyWpjL4cpfC7HPJjPhYSFhDQkR83nN95A9cR"]

AI_BACKEND_URL = "http://52.221.50.176:8000"
UI_URL_REST_API_getPatientDetails = "/api/data-server/patient-details"

UI_URL_REST_API_postDemographicInfo = "/api/save_vitals_data"
UI_URL_REST_API_getPredictionScore = "/api/prediction_scores"
UI_URL_REST_API_BASE = "https://sg-dev.respiree.com:7788"
URL_UPDATE_EXTERNAL_DEVICE_LAST_CONNECTION = "/api/external-sensor/updateSensorLastConnectionTime"

DATA_SOURCE = {
    "emr": "EMR",
    "Sensor": "Sensor",
    "MHI": "MHI",
    "other": "Other"
}

other_device_types = [
        'bp-device',
        'emr'
    ]

DATA_PROCESSING_URL = os.environ.get("DATA_PROCESSING_URL")

max_retry = 3
retry_delay_seconds = 2
status_forcelist = [500, 502, 503, 504, 429]
max_timeout = 10
skin_contact_cache_window_minutes = 15

datasource_to_payload_mapping = {
    "sensor" : "device",
    "mhi" : "manual",
    "emr" : "emr",
    "other" : "bp",
}