import os
import pandas as pd
import logging
import numpy as np
from django.test import TestCase
from data_app.lib_sensor_on_skin_detection import calc_accl_std
from dataprocessing import settings as original_settings

class LibSensorOnSkinDetectionTestCase(TestCase):

    algo_ver = "algo_rr-skin-contact_v4.0.0"


    def read_txt(self, filename):
        data = []
        with open(filename, 'r') as f:
            for line in f:
                try:
                    line = line.replace('\n', '')
                    line = line.split(',')
                    line = [float(line[i]) for i in range(len(line))]

                    temp_ine = line

                    data.append(temp_ine)
                except:
                    logging.error(f"error and skip {line}")
                    pass
        data = np.array(data)
        return data


    def get_list_file(self, ref_csv, dashboard_mode, raw_data_folder):
        try:
            path_to_csv = os.path.join(original_settings.BASE_DIR,'data_app','tests', 'test_data', 'test_data_sensor_onskin_status')
            read_csv = pd.read_csv(os.path.join(path_to_csv, ref_csv))
        except:
            path_to_csv = os.path.join(
                original_settings.BASE_DIR,'data_app','tests', 'test_data', 'test_data_sensor_onskin_status')
            read_csv = pd.read_csv(os.path.join(path_to_csv, ref_csv))
        path_to_raw_data = os.path.join(path_to_csv, raw_data_folder)

        read_csv = read_csv.loc[read_csv['dashboard_mode'] == dashboard_mode]
        return read_csv, path_to_raw_data

    def test_sensor_onskin_status_case_1(self):
        """ validation dataset (algo version 3.0.0) """
        """ test chest sensor on skin status """
        # init params
        dashboard_mode = "RR"

        # read reference csv
        ref_fname = "test_sensor_onskin_status_case_1.csv"
        folder_raw_data = "raw_test_sensor_onskin_status_case_1"

        # get list of file
        read_csv, path_to_raw_data_folder = self.get_list_file(ref_fname, dashboard_mode, folder_raw_data)

        # run algorithm
        for i in range(len(read_csv)):
            current_row = read_csv.iloc[i]

            fname = current_row['filename']

            col_expected_sensor_onskin_status = f"expected_sensor_onskin_status_{self.algo_ver}"
            expected_sensor_onskin_status = current_row[col_expected_sensor_onskin_status]

            path_to_raw = os.path.join(path_to_raw_data_folder, fname)

            raw_data = self.read_txt(path_to_raw)

            sensor_onskin_status = calc_accl_std(raw_data)
            
            # assert result
            assert sensor_onskin_status == expected_sensor_onskin_status, f"calculated sensor_onskin_status ({sensor_onskin_status}) does not match the expected_sensor_onskin_status ({expected_sensor_onskin_status}), filename: {fname}"
        
