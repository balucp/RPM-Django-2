import numpy as np
import math
import scipy
from scipy.signal import find_peaks

from . import utilities as util
from .utilities import signal_processing


class DetectSensorOnskin():
    def __init__(self, val, dashboard_mode):  # TODO allow to modify params
        if dashboard_mode == 'HR':  # finger sensor
            self.is_ppg = True
            params_onoffskin = {
                "threshold": 3.3,
                "window_size": 750,
                "window_shift": 750,
                "freq_lim": 5,
                "bandpass_lower_lim": 0,
                "bandpass_higher_lim": 5,
                "signal_stdev_threshold": [1, 20],
                "threshold_2lightsources_median": 20,
            }

            prepro_params = {  # TODO clean up params that is not needed
                'sampling_time': 0.04,  # second
                'window_mva': 21,
                'window_bl': 250,
                'window_art_mva': 187,
                'window_art_bl': 750,
                'window_smooth_output': 13,  # smoothen output after artifact removal
                'th_prepro': 2,  # coefficient for artifact removal
                'lag': 2,
                'coef_A': 1.2,
                'coef_B': 0.12,
                'val_min': 1.5,
                'val_max': 10,
                # 'window_size': 1500,
                # 'window_shift': 25,
            }

        elif dashboard_mode == 'RR':  # chest sensor
            self.is_ppg = False
            params_onoffskin = {
                "threshold": 3,
                "window_size": 500,
                "window_shift": 250,
                "freq_lim": 2,
                "bandpass_lower_lim": 0.18,
                "bandpass_higher_lim": 0.68,
                "signal_stdev_threshold": [1, 20],
            }

            prepro_params = {  # TODO clean up params that is not needed
                'sampling_time': 0.06,  # second
                'window_mva': 15,
                'window_bl': 250,
                'window_art_mva': 83,
                'window_art_bl': 666,
                'window_smooth_output': 9,  # smoothen output after artifact removal
                'th_prepro': 3,  # coefficient for artifact removal
                'lag': 2,
                'coef_A': 1.2,
                'coef_B': 0.08,
                'val_min': 1.5,
                'val_max': 15,
                # 'window_size': 1083,
                # 'window_shift': 17,
            }

        self.freq_lim = params_onoffskin['freq_lim']
        self.window_size = params_onoffskin['window_size']
        self.window_shift = params_onoffskin['window_shift']
        self.threshold_onoff_skin = params_onoffskin['threshold']
        self.bandpass_lower_lim = params_onoffskin['bandpass_lower_lim']
        self.bandpass_higher_lim = params_onoffskin['bandpass_higher_lim']
        self.signal_stdev_threshold = params_onoffskin["signal_stdev_threshold"]

        self.val = val
        self.prepro_params = prepro_params
        self.T = prepro_params['sampling_time']
        self.fs = 1/self.T

    def run_fft(self, Xin, fs, n_fft=2**12):  # TODO remove this and have it as utils
        Xin = Xin*np.hanning(len(Xin))
        yf = scipy.fftpack.fft(Xin, n=n_fft)
        N = int(len(yf)/2+1)
        signal_fft = np.abs(yf[0:N])
        signal_fft = signal_fft*signal_fft
        signal_fft = self.minmaxscale(signal_fft)
        x_freq = np.linspace(0, fs/2, N)
        return x_freq, signal_fft

    def minmaxscale(self, x):
        min_val = np.min(x)
        max_val = np.max(x)
        y = [(x[i]-min_val) / (max_val-min_val) for i in range(len(x))]
        return np.array(y)

    def modified_fft(self, Xin, fs, n_fft=2**12, phase=False):
        Xin = Xin*np.hanning(len(Xin))
        yf = scipy.fftpack.fft(Xin, n=n_fft)
        yf = scipy.fftpack.fftshift(yf)
        N = len(yf)

        signal_fft = np.abs(yf)
        signal_fft = signal_fft*signal_fft
        signal_fft = self.minmaxscale(signal_fft)
        x_freq = np.linspace(-fs/2, fs/2, N)
        if phase == False:
            return x_freq, signal_fft
        else:
            p = np.angle(yf)
            # p = p[0:N]
            # p = np.unwrap(p)
            return x_freq, signal_fft, p/np.pi

    def calculate_phase_diff(self, y, fs):
        y = y - np.mean(y)
        freq, mag, p = self.modified_fft(y, fs, phase=True)
        peaks_fft, _ = find_peaks(mag, height=0.001)

        if len(peaks_fft) == 0:
            peak_phase = []
        else:
            sorted_mag_peaks = sorted(mag[peaks_fft], reverse=True)
            phase_idx = np.where(mag == sorted_mag_peaks[0])
            peak_phase = p[phase_idx]

        if len(peak_phase) == 2:
            phase_diff = np.abs(peak_phase[0] - peak_phase[1])
        else:
            phase_diff = 0
        return phase_diff

    def calculate_peak_ratio(self, y, fs, freq_lim, is_ppg, threshold_onoff_skin, bandpass_lower_lim, bandpass_higher_lim):
        y = y - np.mean(y)
        freq, mag = self.run_fft(y, fs)
        freq = freq[np.where(freq <= freq_lim)]
        mag = mag[:len(freq)]

        idx_higher = np.where(freq <= bandpass_higher_lim)
        freq = freq[idx_higher]
        idx_h = [x for xs in idx_higher for x in xs]
        idx_lower = np.where(freq >= bandpass_lower_lim)
        freq = freq[idx_lower]
        idx_l = [x for xs in idx_lower for x in xs]
        mag = mag[idx_l[0]:idx_h[-1]+1]

        peaks_fft, _ = find_peaks(mag, height=0.001)
        sorted_mag_peaks = sorted(mag[peaks_fft], reverse=True)
        if len(sorted_mag_peaks) >= 2:
            peak_ratio = sorted_mag_peaks[0]/sorted_mag_peaks[1]
            peak_ratio = np.clip(peak_ratio, 0, 1000)
        elif len(sorted_mag_peaks) == 1:
            peak_ratio = math.inf
        else:
            peak_ratio = 1

        if is_ppg:
            if (peak_ratio <= threshold_onoff_skin) | (peak_ratio == math.inf):
                sensor_status = 0  # 'off-skin'
            else:
                sensor_status = 1  # 'on-skin'
        else:
            if (peak_ratio <= threshold_onoff_skin) | (peak_ratio == math.inf):
                sensor_status = 0  # 'off-skin'
            else:
                sensor_status = 1  # 'on-skin'

        return sensor_status, peak_ratio

    def determine_onskin(self, list_onskin):

        if len(list_onskin) > 1:
            if sum(list_onskin) >= math.ceil(len(list_onskin)/2):
                output = 1
            else:
                output = 0
        else:
            output = list_onskin[0]
        return int(output)

    def run_calculation(self):

        prepro_signal = signal_processing(self.val, self.prepro_params)  # input to signal processing
        prepro_signal.remove_baseline()

        y = prepro_signal.blrm_val

        self.list_output_peakratio = []
        self.list_onskin_status = []
        self.list_phase_diff = []

        for i in range(0, len(y), self.window_shift):

            temp_window = y[i:i+self.window_size]

            sensor_status, peak_ratio = self.calculate_peak_ratio(
                temp_window, self.fs, self.freq_lim, self.is_ppg, self.threshold_onoff_skin, self.bandpass_lower_lim, self.bandpass_higher_lim)

            temp_phase_diff = self.calculate_phase_diff(temp_window, self.fs)

            self.list_output_peakratio = np.append(self.list_output_peakratio, peak_ratio)
            self.list_onskin_status = np.append(self.list_onskin_status, sensor_status)
            self.list_phase_diff = np.append(self.list_phase_diff, temp_phase_diff)

        self.onskin_status = self.determine_onskin(self.list_onskin_status)
        return

    def run_calculation_2(self):
        prepro_signal = signal_processing(self.val, self.prepro_params)
        bl_time, bl_val = prepro_signal.baseline(prepro_signal.time, prepro_signal.val, prepro_signal.window_bl)
        baseline_time, blrm_val = prepro_signal.baseline_removal(prepro_signal.time, prepro_signal.val, bl_time, bl_val)

        y = blrm_val

        self.list_output_stdev = []
        self.list_onskin_status_stdev = []

        self.list_output_skewness = []
        self.list_output_kurtosis = []

        for i in range(0, len(y), self.window_shift):

            temp_window = y[i:i+self.window_size]

            if len(temp_window) < self.window_size:
                continue

            temp_stdev = np.std(temp_window)

            temp_skew = scipy.stats.skew(temp_window)
            temp_kurtosis = scipy.stats.kurtosis(temp_window)

            if (temp_stdev <= self.signal_stdev_threshold[0]) | (temp_stdev >= self.signal_stdev_threshold[1]):
                sensor_status = 0
            else:
                sensor_status = 1

            self.list_output_stdev = np.append(self.list_output_stdev, temp_stdev)
            self.list_output_skewness = np.append(self.list_output_skewness, temp_skew)
            self.list_output_kurtosis = np.append(self.list_output_kurtosis, temp_kurtosis)

            self.list_onskin_status_stdev = np.append(self.list_onskin_status_stdev, sensor_status)

        self.onskin_status_stdev = self.determine_onskin(self.list_onskin_status_stdev)

        return


def calc_accl_std(data):
    """ define parameters """
    SLIDING_WINDOW_SIZE = 16
    WINDOW_SIZE = 1000
    ON_OFF_SKIN_ACCL_THRESHOLD = 0.35
    ON_OFF_SKIN_OPTICAL_THRESHOLD = 1.5
    MINIMUM_DATA_LENGTH_AFTER_MOTION_REMOVAL = 250
    MAJORITY_THRESHOLD = 0.5
    MINIMUM_DATA_LENGTH_FOR_EVAL = 200
    TEMPERATURE_THRESHOLD = 27

    params = util.define_params_tdomain()

    final_labels_list = []
    for start in range(0, len(data), SLIDING_WINDOW_SIZE):
        end = start + WINDOW_SIZE
        if end > len(data):
            break
        data_window = data[start:end]

        temp = data_window[:,6]
        optical = data_window[:,1]
        optical_signal = np.array([np.arange(len(optical)), optical]).T
        accl_plot = data_window[:,2]
        accl_euclidean = data_window[:,2]
        xaccl = data_window[:,3]
        yaccl = data_window[:,4]
        zaccl = data_window[:,5]

        class_sensor_onskin_algo = DetectSensorOnskin(optical_signal, 'RR')
        class_sensor_onskin_algo.run_calculation_2()
        median_list_output_stdev = np.median(class_sensor_onskin_algo.list_output_stdev)
        if median_list_output_stdev > ON_OFF_SKIN_OPTICAL_THRESHOLD:
            opt_label = 1
        else:
            opt_label = 0
        if max(temp)/10 > TEMPERATURE_THRESHOLD:
            temp_label = 1
        else:
            temp_label = 0
        t_sensor = np.arange(len(optical_signal))
        t_activeness, activeness = util.calculate_activeness(xaccl, yaccl, zaccl, params)
        t_mva_accl, mva_accl = util.moving_average(t_sensor, accl_euclidean, params['window_mva'])
        if len(t_activeness) > 2:
            cut_start = int(t_activeness[0])
            cut_end = int(t_activeness[-1]+1)
            t_sensor = t_sensor[cut_start:cut_end]
            accl_euclidean = accl_euclidean[cut_start:cut_end]
            t_mva_accl = t_mva_accl[cut_start:cut_end]
            mva_accl = mva_accl[cut_start:cut_end]
            if 2 in activeness:
                index_to_remove = np.where(activeness == 2)[0]
                t_activeness = np.delete(t_activeness, index_to_remove)
                activeness = np.delete(activeness, index_to_remove)
                t_sensor = np.delete(t_sensor, index_to_remove)
                mva_accl = np.delete(mva_accl, index_to_remove)
                t_mva_accl = np.delete(t_mva_accl, index_to_remove)
                if len(mva_accl) < MINIMUM_DATA_LENGTH_FOR_EVAL:
                    accl_label = 1
                else:
                    start_chunk = 0
                    std_eval_chunks = []
                    for j in range(1, len(t_mva_accl)):
                        if t_mva_accl[j] - t_mva_accl[j-1] != 1:
                            chunk_to_eval = mva_accl[start_chunk:j]
                            std_eval_chunks.append(np.std(chunk_to_eval))
                            start_chunk = j
                    std_eval_chunks.append(np.std(mva_accl[start_chunk:]))
                    for std in std_eval_chunks:
                        if std > ON_OFF_SKIN_ACCL_THRESHOLD:
                            accl_label = 1
                            break
                        else:
                            accl_label = 0
            else:
                std_eval = np.std(mva_accl)
                if std_eval > ON_OFF_SKIN_ACCL_THRESHOLD:
                    accl_label = 1
                else:
                    accl_label = 0
        else:
            std_eval = np.std(mva_accl)
            if std_eval > ON_OFF_SKIN_ACCL_THRESHOLD:
                accl_label = 1
            else:
                accl_label = 0
        if accl_label == 1 and opt_label == 1 and temp_label == 1:
            final_labels_list.append(1)
        else:
            final_labels_list.append(0)
    if len(final_labels_list) == 0:
        final_label = 0
    else:
        average_list = sum(final_labels_list)/len(final_labels_list)
        if average_list >= MAJORITY_THRESHOLD:
            final_label = 1
        else:
            final_label = 0

    return final_label