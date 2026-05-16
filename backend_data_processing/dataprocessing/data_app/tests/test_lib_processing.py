import os
import numpy as np
import pandas as pd
import joblib
import logging
from django.test import TestCase
from data_app.processing import run_sqa, process_output, calculate_rr_3
from dataprocessing import lib_settings as settings

BASE_PATH = os.path.dirname(__file__)


class ProcessingLibTestCase(TestCase):

    def read_txt(self, filename):
        data = []
        with open(filename, "r") as f:
            for line in f:
                try:
                    line = line.replace("\n", "")
                    line = line.split(",")
                    line = [float(line[i]) for i in range(len(line))]

                    temp_ine = line

                    data.append(temp_ine)
                except:
                    logging.error(f"error and skip {line}")
                    pass
        data = np.array(data)
        return data

    def get_list_file(self, ref_csv, dashboard_mode, raw_data_folder):
        path_to_csv = os.path.join(BASE_PATH, "test_data", "test_data_lib_processing")
        read_csv = pd.read_csv(os.path.join(path_to_csv, ref_csv))
        path_to_raw_data = os.path.join(path_to_csv, raw_data_folder)

        read_csv = read_csv.loc[read_csv["dashboard_mode"] == dashboard_mode]
        return read_csv, path_to_raw_data

    def run_main_test_hr(self, path_to_raw, params_bpm, params_sqa, dashboard_mode):
        """
        run test on the algorithm to calculate HR (version algo_hr_v3.0.0)
        """
        raw_data = self.read_txt(path_to_raw)

        timestamp = raw_data[:, 0]
        data = raw_data[:, 1]
        sqa_bandpass = params_sqa["sqa_bandpass_hr"]
        sqa_threshold = params_sqa["sqa_threshold_hr"]

        _, _, _, bpm_w_sqa, _, _, _, _, _, _ = run_sqa(
            timestamp, data, params_bpm, sqa_bandpass, sqa_threshold, dashboard_mode
        )
        output_bpm_w_sqa = process_output(bpm_w_sqa, decimalPlace=3)
        return output_bpm_w_sqa

    def run_main_test_rr_sqaml(self, path_to_raw, config, trained_model):
        """
        run test on the algorithm to calculate RR (with SQA ML)
        """
        data_all_cols = self.read_txt(path_to_raw)

        index_timestamp = np.arange(len(data_all_cols))
        input_data = np.vstack([index_timestamp, data_all_cols[:, 1]]).T
        sensor2 = data_all_cols[:, 2]
        x_acc = data_all_cols[:, 3]
        y_acc = data_all_cols[:, 4]
        z_acc = data_all_cols[:, 5]

        cls_calculate_rr_3 = calculate_rr_3(
            input_data, sensor2, x_acc, y_acc, z_acc, config, trained_model
        )
        # TODO update on off skin with the status
        (
            timestamp,
            val_bpm_sqaml,
            status,
            feature,
            val_bpm_sqaml_sd,
            debug_list_bpm_round,
            debug_list_status,
        ) = cls_calculate_rr_3.run()

        return val_bpm_sqaml, status, feature

    def test_case_1(self):
        """test RR algorithm"""
        # paramsRRhybrid = settings.initParameters('RR-hybrid-algo-60ms')
        # calculate_rr_and_hr(timestamp, dataLD, paramsRR, item, db_table, settings.sqa_bandpass_rr, settings.sqa_threshold_rr, dashboardMode, decimalPlace=3, paramsHybrid=paramsRRhybrid)

    def test_case_2(self):
        """test HR algorithm"""
        # init params
        params_hr = settings.initParameters("HR")
        params_sqa_hr = {
            "sqa_bandpass_hr": settings.sqa_bandpass_hr,
            "sqa_threshold_hr": settings.sqa_threshold_hr,
        }
        dashboard_mode = "HR"

        # read reference csv
        ref_fname = "test_data_dummy_waveform_001.csv"
        folder_raw_data = "raw_data_dummy_waveform"

        # get list of file
        read_csv, path_to_raw_data = self.get_list_file(
            ref_fname, dashboard_mode, folder_raw_data
        )

        # run algorithm
        for i in range(len(read_csv)):

            current_row = read_csv.iloc[i]
            fname = current_row["filename"]
            expected_output = current_row["expected_output"]
            path_to_raw = os.path.join(path_to_raw_data, fname)

            output = self.run_main_test_hr(
                path_to_raw, params_hr, params_sqa_hr, dashboard_mode
            )
            logging.info(f"fname: {fname}, expected: {expected_output}, output: {output}")
            

    def test_calculate_rr_3_case_1(self):
        """test RR algorithm (RR + SQA ML)"""
        # init params
        dashboard_mode = "RR"

        # read reference csv
        ref_fname = "test_data_rr_algo_ver3_001.csv"
        folder_raw_data = "raw_test_data_test_rr_algo_ver3"

        # get list of file
        read_csv, path_to_raw_data_folder = self.get_list_file(
            ref_fname, dashboard_mode, folder_raw_data
        )

        # define config
        config = {
            "bool_output_rr_regardless_sqa": True,
            "bool_predict_prob": False,  # True - predict probability, False - predict label
            "ml_model_fname": settings.model_sqa,
        }

        # download SQA ML model
        ml_model_fname = config["ml_model_fname"]
        try:
            logging.info(f"Loading model: {ml_model_fname}")
            # trained_model = load_model_from_s3(settings.bucket_name, ml_model_fname)
            trained_model = joblib.load(
                os.path.join(settings.path_folder_model, ml_model_fname)
            )
        except Exception as e:
            logging.error(f"Load model '{ml_model_fname}' failed")

        # run algorithm
        for i in range(len(read_csv)):

            current_row = read_csv.iloc[i]

            fname = current_row["filename"]
            expected_rr = current_row["expected_rr"]
            expected_status = current_row["expected_status"]

            skip_this_data = True if current_row["skip"] == 1 else False
            logging.info(
                f"[test_calculate_rr_3_case_1] processing file {fname} ({i+1}/{len(read_csv)})"
            )
            if skip_this_data:
                logging.info(f"[test_lib_processing] skip processing sample_number {i+1}")
                continue

            path_to_current_raw = os.path.join(
                path_to_raw_data_folder, current_row["file_path"]
            )
            path_to_raw = os.path.join(path_to_current_raw, fname)

            output_bpm_sqaml, output_status, _ = self.run_main_test_rr_sqaml(
                path_to_raw, config, trained_model
            )

            try:
                output_rr = str(int(output_bpm_sqaml[0]))
            except:
                output_rr = (
                    output_bpm_sqaml  # this is the case when reference value is "--"
                )

            # TODO:Than assert readings (with different config)
            # TODO:Than check output from "152_RR_2022-07-14_19-53-27.txt"
            # # assert reading
            # assert output_rr == expected_rr, f"calculated BPM ({output_bpm_sqaml}) does not match the expected BPM ({expected_rr}), filename: {fname}"
            # # assert status
            # assert output_status == expected_status, f"calculated Status ({output_status}) does not match the expected BPM ({expected_status}), filename: {fname}"
