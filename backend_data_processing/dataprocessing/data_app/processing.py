import os
import numpy as np
import pandas as pd
import math
import scipy.fftpack
from scipy.signal import find_peaks
from decimal import Decimal
import logging
import scipy.stats
import joblib
from dataprocessing import lib_settings as settings

# TODO clean up this tools
from data_app.lib_sensor_on_skin_detection import calc_accl_std
from data_app.lib_common import remove_bad_data

from resp_sp.spo2 import CalculateSpo2UsingFrequencyAnalysis
# from resp_sp.sensor_skin_contact import DetectSensorSkinContactUsingTwoLightSources
from resp_sp.ppg_peak_detect import PPGSignalDecomposition
import resp_sp

class signal_processing():
    def __init__(self, Xin=None, params=None):
        if Xin is not None:
            self.time = Xin[:, 0].reshape(-1)
            self.val = Xin[:, 1].reshape(-1)

        if params is not None:
            self.window_mva = params["window_mva"]
            self.window_bl = params["window_bl"]
            self.window_art_mva = params["window_art_mva"]
            self.window_art_bl = params["window_art_bl"]
            self.window_smooth_output = params["window_smooth_output"]
            self.th = params["th_prepro"]

        self.mva_time = []  # moving average
        self.mva_val = []

        self.bl_val = []  # baseline
        self.bl_time = []

        self.blrm_val = []  # baseline removal
        self.blrm_time = []

        self.art_val = []  # artifact
        self.art_time = []

        self.artbl_val = []  # artifact baseline
        self.artbl_time = []

        self.output = []  # output

    def moving_average(self, time, val, window_size):
        """
        If window_size==0: returns input
        """
        if window_size == 0:
            mva_time = time
            mva_val = val
        else:
            temp = pd.Series(val)
            temp_mva = temp.rolling(window=window_size, center=True).mean()
            mva_val = temp_mva[int(math.floor(window_size/2)):(len(temp)-int(math.floor(window_size/2)))]
            mva_val = np.array(mva_val)

            mva_time = time[int(math.floor(window_size/2)):(len(time)-int(math.floor(window_size/2)))]
        return mva_time, mva_val

    def baseline(self, time, val, window_size):
        """
        If window_size==0: returns input
        """
        if window_size == 0:
            bl_time = time
            bl_val = val
        else:
            temp = pd.Series(val)
            temp_bl = temp.rolling(window=window_size, center=True).median()  # median filter
            bl_val = temp_bl[int(math.floor(window_size/2)):(len(temp)-int(math.floor(window_size/2)))]
            bl_val = np.array(bl_val)

            bl_time = time[int(math.floor(window_size/2)):(len(time)-int(math.floor(window_size/2)))]
        return bl_time, bl_val

    def baseline_removal(self, signal_time, signal_val, baseline_time, baseline_val):
        signal_time = list(signal_time)
        baseline_time = list(baseline_time)
        blrm_val = signal_val[signal_time.index(
            baseline_time[0]):signal_time.index(baseline_time[-1])+1] - baseline_val
        return baseline_time, blrm_val

    # Baseline removal followed by zero padding front and back
    def baseline_removal_w_zero_padding(self, signal_time, signal_val, baseline_time, baseline_val):
        signal_time = list(signal_time)
        baseline_time = list(baseline_time)
        blrm_val = signal_val[signal_time.index(
            baseline_time[0]):signal_time.index(baseline_time[-1])+1] - baseline_val
        output1 = np.pad(blrm_val, (555, 555), 'constant',
                         constant_values=0)  # 0 padding for KT, padding
        # 720 for data length of 40s to get
        # exactly 1 result and no need to take median
        # 555 for data length of 60s
        blrm_val = output1
        time_end = max(baseline_time)
        time_ramp = baseline_time[-1] - baseline_time[-2]
        for i in range(2000):
            append_val = time_end + (i + 1) * time_ramp
            # 0 padding for RR calculation
            baseline_time = np.append(baseline_time, append_val)
        return baseline_time, blrm_val

    def artifact(self, time, val, window_size, mva_filt=True):
        output = val[1:len(val)-1]**2 - val[0:len(val)-2] * val[2:len(val)]
        time = time[1:len(val)-1]

        output = np.abs(output)
        if mva_filt == True:  # smoothen the output (optional)
            time, output = self.moving_average(time, output, window_size)
        return time, output

    def artifact_removal(self, signal_time, signal_val, art_time, art_val, artbl_time, artbl_val, th, window_size, mva_filt=True):
        signal_time = list(signal_time)
        art_time = list(art_time)

        signal_val = signal_val[signal_time.index(
            artbl_time[0]):signal_time.index(artbl_time[-1])+1]
        art_val = art_val[art_time.index(
            artbl_time[0]):art_time.index(artbl_time[-1])+1]

        output = signal_val[art_val < th*artbl_val]
        if mva_filt == True:  # smoothen the output (optional)
            time = np.arange(0, len(output))
            _, output = self.moving_average(time, output, window_size)
        return output

    def run_signal_processing(self):
        """
        perform signal processing
        """
        self.mva_time,  self.mva_val = self.moving_average(self.time, self.val, self.window_mva)
        self.bl_time,   self.bl_val = self.baseline(self.mva_time, self.mva_val, self.window_bl)
        self.blrm_time, self.blrm_val = self.baseline_removal(self.mva_time, self.mva_val, self.bl_time, self.bl_val)
        self.art_time,   self.art_val = self.artifact(self.blrm_time, self.blrm_val, self.window_art_mva)
        self.artbl_time, self.artbl_val = self.baseline(self.art_time, self.art_val, self.window_art_bl)

    def run_signal_processing_2(self):
        """
        perform signal processing
        """
        self.mva_time,  self.mva_val = self.moving_average(
            self.time, self.val, self.window_mva)
        self.bl_time,   self.bl_val = self.baseline(
            self.mva_time, self.mva_val, self.window_bl)
        self.blrm_time, self.blrm_val = self.baseline_removal_w_zero_padding(
            self.mva_time, self.mva_val, self.bl_time, self.bl_val)
        self.art_time,   self.art_val = self.artifact(
            self.blrm_time, self.blrm_val, self.window_art_mva)
        self.artbl_time, self.artbl_val = self.baseline(
            self.art_time, self.art_val, self.window_art_bl)

    def run_signal_processing_activity(self):
        """
        perform signal processing
        """
        self.mva_time,  self.mva_val = self.moving_average(
            self.time, self.val, self.window_mva)
        self.art_time,   self.art_val = self.artifact(
            self.mva_time, self.mva_val, self.window_art_mva)  # baseline not removed in this algorithm

    def remove_baseline(self):
        self.mva_time,  self.mva_val = self.moving_average(
            self.time, self.val, self.window_mva)
        self.bl_time,   self.bl_val = self.baseline(
            self.mva_time, self.mva_val, self.window_bl)
        self.blrm_time, self.blrm_val = self.baseline_removal(
            self.mva_time, self.mva_val, self.bl_time, self.bl_val)

    # TODO:Than. this is for "rf_old_model_modified_label.pkl". However, this should be updated to "motion_removal3()"
    def motion_removal2(self, signal, nonactive_time):
        signal_time = list(signal[:, 0])
        signal_val = list(signal[:, 1])
        signal = pd.DataFrame(signal, columns=['timestamp', 'signal'])
        signal['timestamp'].astype(int)
        signal = signal.set_index('timestamp')
        nonactive_time = list(nonactive_time)
        nonactive_time = [int(x) for x in nonactive_time]
        nonactive_time_filter1 = list(
            filter(lambda time: time >= signal_time[0], nonactive_time))
        nonactive_time_filter2 = list(
            filter(lambda time: time <= signal_time[-1], nonactive_time_filter1))
        nonactive_signal = signal.loc[nonactive_time_filter2]
        nonactive_signal = list(nonactive_signal['signal'])
        return nonactive_time_filter2, nonactive_signal

    # NOTE This is for "rf_sqa_160523.pkl"
    def motion_removal3(self, signal, nonactive_time):
        signal_time = list(signal[:, 0])
        signal_val = list(signal[:, 1])
        signal = pd.DataFrame(signal, columns=['timestamp', 'signal'])
        signal['timestamp'].astype(int)
        signal = signal.set_index('timestamp')
        nonactive_time = list(nonactive_time)
        nonactive_time = [int(x) for x in nonactive_time]
        nonactive_time_filter1 = list(
            filter(lambda time: time >= signal_time[0], nonactive_time))
        nonactive_time_filter2 = list(
            filter(lambda time: time <= signal_time[-1], nonactive_time_filter1))
        nonactive_signal = signal.loc[nonactive_time_filter2]
        nonactive_signal = list(nonactive_signal['signal'])
        nonactive_time_update = list(
            np.arange(len(nonactive_signal)) + nonactive_time_filter2[0])
        return nonactive_time_update, nonactive_signal

# %%


class metric_extraction():
    def __init__(self, signal, coef_A, coef_B, lag, sampling_time, m1_min, m1_max):
        self.signal = signal
        self.coef_A = coef_A  # coefficient used in def transforming
        self.coef_B = coef_B  # coefficient used in def transforming

        self.lag = lag

        self.ts = sampling_time
        self.m1_min = m1_min
        self.m1_max = m1_max

        self.idx_change = []  # index
        self.trinary = []

        self.output = []  # dict() # output metrics

    def detect_change(self, data):
        pos = data >= 0
        npos = ~pos
        return ((pos[:-1] & npos[1:]) | (npos[:-1] & pos[1:])).nonzero()[0]

    def transforming(self, signal, coef_A, coef_B, lag):
        signals = np.zeros(len(signal))
        filteredY = np.array(signal)

        avgFilter = [0]*len(signal)
        stdFilter = [0]*len(signal)
        avgFilter[lag-1] = np.mean(signal[0:lag])
        stdFilter[lag-1] = np.std(signal[0:lag])

        for i in range(lag, len(signal) - 1):
            if abs(signal[i] - avgFilter[i-1]) > coef_A * stdFilter[i-1]:
                if signal[i] > avgFilter[i-1]:
                    signals[i] = 1
                else:
                    signals[i] = -1

                filteredY[i] = coef_B * signal[i] + \
                    (1 - coef_B) * filteredY[i-1]
                avgFilter[i] = np.mean(filteredY[(i-lag):i])
                stdFilter[i] = np.std(filteredY[(i-lag):i])
            else:
                signals[i] = 0
                filteredY[i] = signal[i]
                avgFilter[i] = np.mean(filteredY[(i-lag):i])
                stdFilter[i] = np.std(filteredY[(i-lag):i])
        return np.asarray(signals)

    def metric_1(self, idx_change, ts):
        output = []
        for i in range(1, len(idx_change)-2, 2):
            temp = []
            temp = idx_change[i+2]-idx_change[i]
            output = np.append(output, temp*ts)
        return output

    def run_transformation(self):
        # transform signal into value of [-1, 0, 1]
        self.trinary = self.transforming(
            self.signal, self.coef_A, self.coef_B, self.lag)
        # return index when -1 changed to 1 or vice versa
        self.idx_change = self.detect_change(self.trinary)

    def run_metric_extraction(self):

        if len(self.idx_change) >= 6:  # 6 is minimum length to get output m1-m5
            self.output_m1 = self.metric_1(self.idx_change, self.ts)

            self.output_m1 = self.output_m1[(self.output_m1 > self.m1_min) & (
                self.output_m1 < self.m1_max)]

            if len(self.output_m1) == 0:  # if all data in output_m1 is filtered out
                self.output_m1 = np.array([np.nan])
        else:
            self.output_m1 = np.array([np.nan])
        self.output = np.median(self.output_m1)


def run_fft(Xin, fs, n_fft=2**12):
    Xin = Xin*np.hanning(len(Xin))
    yf = scipy.fftpack.fft(Xin, n=n_fft)
    N = int(len(yf)/2+1)

    signal_fft = np.abs(yf[0:N])
    signal_fft = signal_fft*signal_fft

    x_freq = np.linspace(0, fs/2, N)
    return x_freq, signal_fft


def peakdet(v, delta, x=None):
    maxtab = []
    mintab = []

    v = np.asarray(v)

    if x is None:
        x = np.arange(len(v))

    mn, mx = np.Inf, -np.Inf
    mnpos, mxpos = np.NaN, np.NaN

    lookformax = True

    for i in np.arange(len(v)):
        this = v[i]
        if this > mx:
            mx = this
            mxpos = x[i]
        if this < mn:
            mn = this
            mnpos = x[i]

        if lookformax:
            if this < mx-delta:
                maxtab.append((mxpos, mx))
                mn = this
                mnpos = x[i]
                lookformax = False
        else:
            if this > mn+delta:
                mintab.append((mnpos, mn))
                mx = this
                mxpos = x[i]
                lookformax = True
    return np.array(maxtab), np.array(mintab)


def calculate_sqa(windowSignal, nfft, fs, bandpass, delta_peakdet):
    windowSignal = windowSignal - np.mean(windowSignal)

    freq, mag = run_fft(windowSignal, fs, nfft)
    freq_wo_bp, mag_wo_bp = freq.copy(), mag.copy()

    """
    find 1st and 2nd peak
    """
    freq_bp = freq_wo_bp[(freq_wo_bp >= bandpass[0]) &
                         (freq_wo_bp <= bandpass[1])].copy()
    mag_bp = mag_wo_bp[(freq_wo_bp >= bandpass[0]) &
                       (freq_wo_bp <= bandpass[1])].copy()

    maxtab, mintab = peakdet(mag_bp, delta_peakdet, freq_bp)
    try:
        # if first peak is close to cutoff frequency
        if maxtab[0, 0] < bandpass[0]+(freq_bp[2]-freq_bp[1]):
            try:
                maxtab = maxtab[1:, :]
            except:
                pass
    except:
        pass

    if len(maxtab) > 0:
        first_magpeak = [-np.Inf, -np.Inf]
        for i in range(len(maxtab)):
            if maxtab[i, 1] > first_magpeak[1]:
                first_magpeak[0] = maxtab[i, 0]
                first_magpeak[1] = maxtab[i, 1]

        maxtab_remove_max = maxtab[maxtab[:, 1] != np.max(maxtab[:, 1]), :]
        second_magpeak = [-np.Inf, -np.Inf]
        for i in range(len(maxtab_remove_max)):
            if maxtab_remove_max[i, 1] > second_magpeak[1]:
                second_magpeak[0] = maxtab_remove_max[i, 0]
                second_magpeak[1] = maxtab_remove_max[i, 1]

        if second_magpeak[1] == -np.Inf:
            second_magpeak = [0, 0]

        """
        check harmonic
        """
        if (second_magpeak[0] > first_magpeak[0]*2-settings.harmonic_accpeted) and (second_magpeak[0] < first_magpeak[0]*2+settings.harmonic_accpeted):
            second_magpeak[1] = 0

        diffMag = first_magpeak[1]-second_magpeak[1]
        normDiffMag = diffMag/first_magpeak[1]

    else:
        first_magpeak = [0, 0]
        second_magpeak = [0, 0]

        diffMag = 0
        normDiffMag = 0

        maxtab = np.array([[0, 0], [0, 0]])

    """
    check if pos peak to neg peak difference is sufficient
    """
    leftNegativePeak = [None, None]
    rightNegativePeak = [None, None]

    for i in range(len(mintab)-1, -1, -1):
        if (mintab[i, 0] < first_magpeak[0]):
            leftNegativePeak = [mintab[i, 0], mintab[i, 1]]
            break

    if leftNegativePeak[0] == None:
        leftNegativePeak[0] = freq_bp[0]
        leftNegativePeak[1] = mag_bp[0]

    diffMagLeft = first_magpeak[1]-leftNegativePeak[1]
    normDiffMagLeft = diffMagLeft/first_magpeak[1]

    for i in range(0, len(mintab)):
        if (mintab[i, 0] > first_magpeak[0]):
            rightNegativePeak = [mintab[i, 0], mintab[i, 1]]
            break

    if rightNegativePeak[0] == None:
        rightNegativePeak[0] = freq_bp[-1]
        rightNegativePeak[1] = mag_bp[-1]

    diffMagRight = first_magpeak[1]-rightNegativePeak[1]
    normDiffMagRight = diffMagRight/first_magpeak[1]

    return normDiffMag, normDiffMagLeft, normDiffMagRight, first_magpeak, second_magpeak, freq_bp, mag_bp


class getSpO2_FFT():
    def __init__(self, timestamp, dataRED, dataIR, params, enable_sqa=True, th_sqa=settings.sqa_bandpass_spo2_individual_frame, th_sqa_pos_neg_peak=settings.sqa_threshold_spo2_pos_to_neg_peak, bandpass=settings.spo2_bandpass, spo2_minmax=settings.spo2_minmax, delta_peakdet=settings.delta_peakdet, nfft=settings.nfft):

        self.dataRED = dataRED
        self.dataIR = dataIR
        self.time = timestamp

        self.sampling_time = params["sampling_time"]
        self.window_length = params["window_size"]
        self.window_shift = params["window_shift"]
        self.window_mva = params["window_mva"]

        self.outputTime = []
        self.outputVal = []

        self.enable_sqa = enable_sqa
        self.th_sqa = th_sqa
        self.bandpass = bandpass
        self.spo2_minmax = spo2_minmax

        self.delta_peakdet = delta_peakdet

        self.nfft = nfft

        self.th_sqa_pos_neg_peak = th_sqa_pos_neg_peak

    def runSignalProcessing(self):
        preProcessing = signal_processing()

        mvaTimeRED, mvaValRED = preProcessing.moving_average(
            self.time, self.dataRED, self.window_mva)
        mvaTimeIR, mvaValIR = preProcessing.moving_average(
            self.time, self.dataIR, self.window_mva)

        self.red_mva = np.vstack([mvaTimeRED, mvaValRED]).T
        self.ir_mva = np.vstack([mvaTimeIR, mvaValIR]).T

    def calSpO2(self, x):
        try:
            output = -11.55662048527909*x + 102.26367177880022  # 20s new FDA line

            output[output > self.spo2_minmax[1]] = self.spo2_minmax[1]
            output[output < self.spo2_minmax[0]] = np.nan

            for i in range(len(output)):
                if output[i] % 1 >= 0.5:
                    output[i] = np.ceil(output[i])
                else:
                    output[i] = np.floor(output[i])
        except:
            output = []  # np.nan

        return output

    def findMaxPeak(self, x, y, bandpass=None):
        if bandpass != None:
            # remove magnitude outside bandpass
            y = y[(x >= bandpass[0]) & (x <= bandpass[1])]
            x = x[(x >= bandpass[0]) & (x <= bandpass[1])]

        peaks, _ = find_peaks(y, height=0)
        magPeak = -np.Inf
        freqPeak = []
        for i in range(len(peaks)):
            if y[peaks[i]] > magPeak:
                magPeak = y[peaks[i]]
                freqPeak = x[peaks[i]]

        if abs(magPeak) == np.Inf:  # otherwise, it will be 100% in def calSpO2(self, x)
            magPeak = np.nan

        return freqPeak, magPeak

    def extractSpO2(self):
        self.runSignalProcessing()

        signalRed = self.red_mva
        signalIr = self.ir_mva

        wlength = self.window_length
        wshift = self.window_shift

        nfft = self.nfft
        bandpass = self.bandpass
        delta_peakdet = self.delta_peakdet

        fs = 1/self.sampling_time

        self.total_frame = 0
        self.accepted_frame = 0

        for i in range(0, len(signalIr)-wlength, wshift):
            self.total_frame += 1

            windowRed = signalRed[i:i+wlength, :]
            windowIr = signalIr[i:i+wlength, :]

            current_time = signalIr[i+wlength, 0]
            self.outputTime = np.append(
                self.outputTime, current_time)  # timestamp


            red_AC = windowRed[:, 1]
            red_DC = np.mean(red_AC)
            """
            check sqa red
            """
            sqa_index_center_red, sqa_index_left_red, sqa_index_right_red, first_magpeak_red, second_magpeak_red, freq_bp, mag_bp = calculate_sqa(
                red_AC, nfft, fs, bandpass, delta_peakdet)
            if (sqa_index_center_red < self.th_sqa) or (sqa_index_left_red < self.th_sqa_pos_neg_peak) or (sqa_index_right_red < self.th_sqa_pos_neg_peak):
                continue

            ir_AC = windowIr[:, 1]
            ir_DC = np.mean(ir_AC)
            """
            check sqa ir
            """
            sqa_index_center_ir, sqa_index_left_ir, sqa_index_right_ir, first_magpeak_ir, second_magpeak_ir, freq_bp, mag_bp = calculate_sqa(
                ir_AC, nfft, fs, bandpass, delta_peakdet)
            if (sqa_index_center_ir < self.th_sqa) or (sqa_index_left_ir < self.th_sqa_pos_neg_peak) or (sqa_index_right_ir < self.th_sqa_pos_neg_peak):
                continue

            red_freq_DC, red_mag_DC = run_fft(red_AC, fs, nfft)
            ir_freq_DC, ir_mag_DC = run_fft(ir_AC, fs, nfft)

            red_magPeak_DC = red_mag_DC[0]
            ir_magPeak_DC = ir_mag_DC[0]

            red_freq_AC, red_mag_AC = run_fft(red_AC-red_DC, fs, nfft)
            ir_freq_AC, ir_mag_AC = run_fft(ir_AC-ir_DC, fs, nfft)

            red_freqPeak_AC, red_magPeak_AC = self.findMaxPeak(
                red_freq_AC, red_mag_AC, bandpass)
            ir_freqPeak_AC, ir_magPeak_AC = self.findMaxPeak(
                ir_freq_AC, ir_mag_AC, bandpass)

            self.accepted_frame += 1

            R = []
            R = (red_magPeak_AC/red_magPeak_DC) / (ir_magPeak_AC/ir_magPeak_DC)
            self.outputVal = np.append(self.outputVal, R)

        self.outputVal = self.calSpO2(self.outputVal)


class class_calculate_sqa():
    def __init__(self, input_time, input_signal, input_params, bandpass, dashboardMode, nfft=settings.nfft, delta_peakdet=settings.delta_peakdet):

        self.params = input_params.copy()

        prepro_signal = signal_processing()  # input to signal processing
        mva_time, mva_val = prepro_signal.moving_average(input_time, input_signal, self.params['window_mva'])

        bl_time, bl_val = prepro_signal.baseline(mva_time, mva_val, self.params['window_bl'])
        baseline_time, blrm_val = prepro_signal.baseline_removal(mva_time, mva_val, bl_time, bl_val)
        self.signal_input = np.vstack([baseline_time, blrm_val]).T

        self.sampling_time = self.params["sampling_time"]

        self.window_length = self.params["window_size"]
        self.window_shift = self.params["window_shift"]

        self.bandpass = bandpass
        self.nfft = nfft

        self.delta_peakdet = delta_peakdet

        self.mode = dashboardMode

    def run(self):
        self.output_sqa = []

        self.output_good_sqa = []

        self.output_bpm = []
        self.output_bpm_w_sqa = []  # keep bpm only if sqa is good

        self.output_time_w_sqa = []
        self.output_time_wo_sqa = []

        self.list_sd_signal_w_sqa = []

        self.output_td = []
        self.output_dc = []

        if self.mode == 'RR':
            th_sqa = settings.sqa_bandpass_rr_individual_frame
            th_sqa_pos_neg_peak = settings.sqa_threshold_rr_pos_to_neg_peak
        elif self.mode == 'HR':
            th_sqa = settings.sqa_bandpass_hr_individual_frame
            th_sqa_pos_neg_peak = settings.sqa_threshold_rr_pos_to_neg_peak

        # signal = self.signal_mva
        signal = self.signal_input

        wlength = self.window_length
        wshift = self.window_shift

        fs = 1/self.sampling_time

        nfft = self.nfft
        bandpass = self.bandpass
        delta_peakdet = self.delta_peakdet

        self.total_frame = 0
        self.accepted_frame = 0

        for i in range(0, len(signal)-wlength, wshift):

            current_time = signal[i+wlength, 0]

            windowSignal = signal[i:i+wlength, 1]
            normDiffMag, normDiffMagLeft, normDiffMagRight, first_magpeak, second_magpeak, freq_bp, mag_bp = calculate_sqa(
                windowSignal, nfft, fs, bandpass, delta_peakdet)

            """
            get sqa
            """
            self.output_sqa = np.append(self.output_sqa, normDiffMag)

            """
            get bpm
            """
            bpm = first_magpeak[0]*60
            self.output_bpm = np.append(self.output_bpm, bpm)

            self.output_time_wo_sqa = np.append(
                self.output_time_wo_sqa, current_time)

            self.total_frame += 1

            """
            if sqa is good, get bpm
            """
            if (normDiffMag >= th_sqa) and (normDiffMagLeft >= th_sqa_pos_neg_peak) and (normDiffMagRight >= th_sqa_pos_neg_peak):
                self.output_bpm_w_sqa = np.append(self.output_bpm_w_sqa, bpm)
                self.output_good_sqa = np.append(
                    self.output_good_sqa, normDiffMag)

                self.accepted_frame += 1

                self.output_time_w_sqa = np.append(
                    self.output_time_w_sqa, current_time)

                self.list_sd_signal_w_sqa = np.append(
                    self.list_sd_signal_w_sqa, np.std(windowSignal))

                # calculate TD and DC
                output_pattern = extract_breathing_pattern(
                    windowSignal, self.params)

                self.output_td = np.append(
                    self.output_td, output_pattern['TD'])
                self.output_dc = np.append(
                    self.output_dc, output_pattern['DC'])



def map_input_data(blrm_val, blrm_time, art_val, art_time, artbl_val, artbl_time):
    blrm_time = list(blrm_time)
    art_time = list(art_time)
    artbl_time = list(artbl_time)

    index_blrm = [blrm_time.index(artbl_time[0]),
                  blrm_time.index(artbl_time[-1])]
    index_ks = [art_time.index(artbl_time[0]), art_time.index(artbl_time[-1])]

    signal = np.array([blrm_time[index_blrm[0]:index_blrm[1]+1],
                      blrm_val[index_blrm[0]:index_blrm[1]+1]]).T
    art = np.array([art_time[index_ks[0]:index_ks[1]+1],
                   art_val[index_ks[0]:index_ks[1]+1]]).T
    artbl = np.array([artbl_time, artbl_val]).T

    return signal, art, artbl


def calculateBPM(readData, params):

    windowSize = params['window_mva']+params['window_bl']-1+3-1+params['window_art_mva'] - \
        1+params['window_art_bl']-1 + \
        params['window_size']-1  # params['window_size']
    windowShift = params['window_shift']

    # outputBPM = []
    outputMetric = {
        'BPM': [],
        'TD': [],
        'DC': [],
        'IBI': []
    }
    outputTime = []

    accepted_frame = 0
    total_frame = 0

    for i in range(0, len(readData)-windowSize-1, windowShift):

        windowReadData = readData[i:i+windowSize, :]

        outputTime = np.append(outputTime, windowReadData[-1, 0])

        # input to signal processing
        clsPrepro = signal_processing(windowReadData, params)
        clsPrepro.run_signal_processing()  # perform signal processing

        Xsignal, Xart, Xartbl = map_input_data(clsPrepro.blrm_val, clsPrepro.blrm_time,
                                               clsPrepro.art_val, clsPrepro.art_time,
                                               clsPrepro.artbl_val, clsPrepro.artbl_time)

        windowSignal = clsPrepro.artifact_removal(Xsignal[:, 0], Xsignal[:, 1],
                                                  Xart[:, 0], Xart[:, 1],
                                                  Xartbl[:, 0], Xartbl[:, 1],
                                                  params['th_prepro'], params['window_smooth_output'],
                                                  mva_filt=True)  # remove artifact and apply mva to smoothen signal

        if len(windowSignal) >= params['lag']:

            clsMetricExtraction = metric_extraction(windowSignal, params['coef_A'], params['coef_B'],
                                                    params['lag'], params['sampling_time'],
                                                    params['val_min'], params['val_max'])

            clsMetricExtraction.run_transformation()
            clsMetricExtraction.run_metric_extraction()  # calculate metric

            output = clsMetricExtraction.output  # get metric
            output = 60/output

            """
            DC and TD
            """

            # TODO:Thanawin This should be moved out
            output_pattern = calculate_patterns_metrics(
                windowSignal, clsMetricExtraction.trinary, clsMetricExtraction.idx_change, params, settings.PD_max_count)

        else:  # size of window_signal is smaller than lag, can't perform transforming function
            output = np.nan

            output_pattern = {}
            output_pattern['TD'] = np.nan
            output_pattern['DC'] = np.nan
            output_pattern['IBI'] = np.nan

        # outputBPM = np.append(outputBPM, output)
        outputMetric['BPM'] = np.append(outputMetric['BPM'], output)
        outputMetric['TD'] = np.append(
            outputMetric['TD'], output_pattern['TD'])
        outputMetric['DC'] = np.append(
            outputMetric['DC'], output_pattern['DC'])
        outputMetric['IBI'] = np.append(
            outputMetric['IBI'], output_pattern['IBI'])

        total_frame += 1
        # if len(Xsignal)==len(windowSignal):
        # if len(Xsignal)>len(windowSignal)*0.9:
        if len(windowSignal) == len(Xsignal)-params['window_smooth_output']+1:
            accepted_frame += 1

    return outputMetric, outputTime, accepted_frame, total_frame


def extract_breathing_pattern(signal, params):

    class_metric_extraction = metric_extraction(
        signal, params['coef_A'], params['coef_B'], params['lag'], params['sampling_time'], params['val_min'], params['val_max']
    )
    class_metric_extraction.run_transformation()
    class_metric_extraction.run_metric_extraction()  # calculate metric

    output_pattern = calculate_patterns_metrics(
        signal, class_metric_extraction.trinary, class_metric_extraction.idx_change, params
    )

    return output_pattern


# extract RR using time domain and freq domain
def calculate_bpm_hybrid(read_data, params, bandpass, dsp_method=1):

    # Preprocess raw signal
    cls_signal_prepro = signal_processing(
        read_data, params)  # input to signal processing
    if dsp_method == 1:
        cls_signal_prepro.run_signal_processing()  # perform signal processing
    elif dsp_method == 2:
        # perform signal processing (baseline removal with zero padding)
        cls_signal_prepro.run_signal_processing_2()

    Xsignal, Xart, Xartbl = map_input_data(cls_signal_prepro.blrm_val, cls_signal_prepro.blrm_time,
                                           cls_signal_prepro.art_val, cls_signal_prepro.art_time,
                                           cls_signal_prepro.artbl_val, cls_signal_prepro.artbl_time)

    """
    Main Loop
    """
    save_trinary = []  # output of def transforming()
    # save_indexchange = [] # detect_change()

    save_time = []  # timestamp of each extraction

    save_bpm = []
    save_bpm_round = []

    window_size = params['window_size']
    window_shift = params['window_shift']

    n_window = 0
    for i in range(0, len(Xsignal)-window_size, window_shift):

        window_signal = cls_signal_prepro.artifact_removal(Xsignal[i:i+window_size, 0], Xsignal[i:i+window_size, 1],
                                                           Xart[i:i+window_size,
                                                                0], Xart[i:i+window_size, 1],
                                                           Xartbl[i:i+window_size,
                                                                  0], Xartbl[i:i+window_size, 1],
                                                           params['th_prepro'], params['window_smooth_output'],
                                                           mva_filt=True)  # remove artifact and apply mva to smoothen signal

        if len(window_signal) >= params['lag']:

            cls_metric_extraction = metric_extraction(window_signal, params['coef_A'], params['coef_B'],
                                                      params['lag'], params['sampling_time'],
                                                      params['val_min'], params['val_max'])

            cls_metric_extraction.run_transformation()
            cls_metric_extraction.run_metric_extraction()  # calculate metric

            output = cls_metric_extraction.output  # get metric

            temp_trinary = cls_metric_extraction.trinary

        else:  # size of window_signal is smaller than lag, can't perform transforming function

            output = {}

            output['m1_1'] = np.nan

            temp_trinary = np.array([np.nan])
            # temp_idx_change = np.array([np.nan])

            # temp_m1 = np.array([np.nan])

        # timestamp of each extraction
        save_time.append(Xsignal[i+window_size, 0])

        """
        1. fft(temp_trinary)
        2. select maximum peak
        3. convert to BPM
        """

        temp_trinary = temp_trinary - np.mean(temp_trinary)  # remove mean

        freq_wo_bp, mag_wo_bp = run_fft(
            temp_trinary, 1/params['sampling_time'])
        # freq_wo_bp, mag_wo_bp = run_welch(temp_trinary, 1/params['sampling_time'], 250, 8)

        freq_bp = freq_wo_bp[(freq_wo_bp >= bandpass[0])
                             & (freq_wo_bp <= bandpass[1])].copy()
        mag_bp = mag_wo_bp[(freq_wo_bp >= bandpass[0]) &
                           (freq_wo_bp <= bandpass[1])].copy()

        # # normalize spectrum to maximum
        mag_bp = mag_bp/np.max(mag_bp)

        # find peak
        peaks, peak_properties = find_peaks(mag_bp)
        list_peak_freq = freq_bp[peaks]
        list_peak_mag = mag_bp[peaks]

        idx_max_peak = np.where(mag_bp == np.max(mag_bp))

        selected_mag = mag_bp[idx_max_peak]
        selected_freq = freq_bp[idx_max_peak]

        """
        convert to BPM
        """
        temp_bpm = []
        temp_bpm = 60*selected_freq
        save_bpm = np.append(save_bpm, temp_bpm)

        temp_bpm_round = []  # rounding the number
        if np.isnan(temp_bpm):
            temp_bpm_round = np.nan
        else:
            if temp_bpm % 1 >= 0.5:
                temp_bpm_round = np.ceil(temp_bpm)
            else:
                temp_bpm_round = np.floor(temp_bpm)
        save_bpm_round = np.append(save_bpm_round, temp_bpm_round)

        n_window += 1

    return save_time, save_bpm_round


def run_sqa(timestamp, signal, params, bandpass, threshold, dashboardMode):
    """
    2 = good
    1 = moderate
    0 = bad
    """
    sqa = class_calculate_sqa(
        timestamp, signal, params, bandpass, dashboardMode)
    sqa.run()

    # cal_sqa = sqa.output_sqa
    cal_sqa = sqa.output_good_sqa  # only good sqa value

    temp_sqa_val = np.median(cal_sqa)
    if np.isnan(temp_sqa_val):
        temp_sqa_val = 0

    list_sd_signal_w_sqa = sqa.list_sd_signal_w_sqa
    val_sd_signal_w_sqa = np.median(list_sd_signal_w_sqa)
    if np.isnan(val_sd_signal_w_sqa):
        val_sd_signal_w_sqa = 0

    """
    BPM
    """
    bpm_wo_sqa = sqa.output_bpm  # every frame, regardless sqa
    bpm_w_sqa = sqa.output_bpm_w_sqa  # only frame with good SQA

    output_sqa = []
    if (temp_sqa_val < threshold[0]):
        output_sqa = 0
    elif (temp_sqa_val >= threshold[0]) & (temp_sqa_val < threshold[1]):
        output_sqa = 1
    elif (temp_sqa_val >= threshold[1]):
        output_sqa = 2

    """
    frame accapted by SQA
    """
    total_frame = sqa.total_frame
    accepted_frame = sqa.accepted_frame

    """
    for debugging
    """
    output_time_w_sqa = sqa.output_time_w_sqa
    output_time_wo_sqa = sqa.output_time_wo_sqa

    """
    extract breathing pattern
    """
    dict_breathing_pattern = {
        "TD": sqa.output_td,
        "DC": sqa.output_dc,
        # "|Ti-Te|/Tt": sqa.output_breathing_a,
    }

    return_output = {
        "val_sd_signal_w_sqa": val_sd_signal_w_sqa,
        "list_sd_signal_w_sqa": list_sd_signal_w_sqa
    }

    return output_sqa, temp_sqa_val, bpm_wo_sqa, bpm_w_sqa, accepted_frame, total_frame, output_time_w_sqa, output_time_wo_sqa, return_output, dict_breathing_pattern


def process_output(X, decimalPlace, roundNumber=True):
    if len(X) > 0:
        X = X[~np.isnan(X)]  # remove NaN

    if len(X) > 0:  # if there is data remaining
        # output = np.mean(X)
        output = np.median(X)
        output = np.around(output, decimals=decimalPlace)

        if roundNumber:
            if output % 1 >= 0.5:
                output = np.ceil(output)
            else:
                output = np.floor(output)

            output = int(output)
        else:
            output = Decimal("{:.{}f}".format(output, decimalPlace))
    else:  # remove NaN and no data left (all NaN)
        # output = None
        # output = Decimal(str(np.nan)) #output = "None" #Decimal(str(np.nan)) #
        output = str(np.nan)
    return output


def get_sd_from_array(x, decimal_place, round_number=True):
    """ compute standard deviation (SD)

    Args:
        x (list): input array
        decimal_place (int): number of decimal places after SD computation
        round_number (bool, optional): round the output value. Defaults to True.

    Returns:
        output: standard deviation
    """
    if len(x) > 0:
        x = x[~np.isnan(x)]  # remove NaN from the input

    if len(x) > 0:  # if array is not empty
        output = np.std(x)
        output = np.around(output, decimals=decimal_place)

        if round_number:
            if output % 1 >= 0.5:
                output = np.ceil(output)
            else:
                output = np.floor(output)
            output = int(output)
        else:
            output = Decimal("{:.{}f}".format(output, decimal_place))
    else:  # if array is empty
        output = str(np.nan)
    return output


# TODO:Than function should not save data to DB. It should only run calculation
def calculate_rr_and_hr(timestamp, data, params, item, dbTable, sqaBandpass, sqaThreshold, dashboardMode, decimalPlace=3, dataRED=None, dataIR=None, paramsHybrid=None, data_all_cols=None):

    logging.info({
        "message": "Start calculating RR or HR",
        "level": "info",
        "item": item
    })

    # TODO:Than output dict
    sqa, sqa_index, bpm_wo_sqa, bpm_w_sqa, accepted_frame, total_frame, output_time_w_sqa, output_time_wo_sqa, return_output, dict_breathing_pattern = run_sqa(
        timestamp, data, params, sqaBandpass, sqaThreshold, dashboardMode)

    val_sd_signal_w_sqa = return_output["val_sd_signal_w_sqa"]
    item['val_sd_signal_w_sqa'] = Decimal("{:.4f}".format(val_sd_signal_w_sqa))

    list_sd_signal_w_sqa = return_output["list_sd_signal_w_sqa"]
    try:
        list_sd_signal_w_sqa = [str(list_sd_signal_w_sqa[k])
                                for k in range(len(list_sd_signal_w_sqa))]
        item['list_sd_signal_w_sqa'] = list_sd_signal_w_sqa
    except:
        # pass
        item['list_sd_signal_w_sqa'] = list_sd_signal_w_sqa.tolist()

    # calculate SD of signal after preprocessing - small window size
    try:  # mainly for debugging SpO2 signal quality
        preprocessing_tool = signal_processing()
        mva_time, mva_val = preprocessing_tool.moving_average(
            timestamp, data, params['window_mva'])
        bl_time, bl_val = preprocessing_tool.baseline(
            mva_time, mva_val, params['window_bl'])
        baseline_time, blrm_val = preprocessing_tool.baseline_removal(
            mva_time, mva_val, bl_time, bl_val)
        temp_list_SD = []
        for i in range(0, len(blrm_val), 25):
            temp_window = blrm_val[i:i+125]
            temp_list_SD = np.append(temp_list_SD, np.std(temp_window))
        temp_median_list_SD = np.median(temp_list_SD)

        item['val_sd_signal_wo_sqa'] = Decimal(
            "{:.4f}".format(temp_median_list_SD))
    except Exception as e:
        logging.error({
            "message": "Error when calculating optical signal SD for debugging.",
            "level": "error",
            "error_message": str(e)
        })

    val_metric, time_bpm, accepted_frame_tdomain, total_frame_tdomain = calculateBPM(
        np.array([timestamp, data]).T, params)
    val_bpm = val_metric['BPM']

    if len(val_metric['TD']) == 0:
        logging.info(
            f"data lengh is too short ({len(data)}) to compute breathing parameters (TD and DC) in the first attempt. Use params for 2nd attempt.")

        val_rr_td = dict_breathing_pattern['TD']
        val_rr_dc = dict_breathing_pattern['DC']
        val_rr_ibi = []
    else:
        val_rr_td = val_metric['TD']
        val_rr_dc = val_metric['DC']
        val_rr_ibi = val_metric['IBI']

    output_val_bpm = process_output(val_bpm, decimalPlace)
    output_bpm_wo_sqa = process_output(bpm_wo_sqa, decimalPlace)
    output_bpm_w_sqa = process_output(bpm_w_sqa, decimalPlace)

    output_val_td = process_output(val_rr_td, 8, False)
    output_val_dc = process_output(val_rr_dc, decimalPlace)
    output_val_ibi = process_output(val_rr_ibi, decimalPlace)

    # set value of 0 to 'nan'
    if output_bpm_wo_sqa == 0:
        output_bpm_wo_sqa = str(np.nan)

    # get standard deviation
    output_bpm_w_sqa_sd = get_sd_from_array(
        bpm_w_sqa, decimal_place=decimalPlace, round_number=False)

    if dashboardMode == 'RR':
        try:
            # 1 = fda 3 min
            # 2 = modified fda 1min (zero padding)
            _, val_bpm_hybrid = calculate_bpm_hybrid(
                np.array([timestamp, data]).T, paramsHybrid, paramsHybrid['sqa_bandpass'], 2)
        except Exception as e:
            logging.error(f"error when compute RR --> {e}. assign empty list ")
            val_bpm_hybrid = []
        output_bpm_hybrid = process_output(val_bpm_hybrid, decimalPlace)
        try:
            # input_data = np.vstack([timestamp, data]).T
            index_timestamp = np.arange(len(timestamp))
            input_data = np.vstack([index_timestamp, data]).T
            sensor2 = data_all_cols[:, 2]
            x_acc = data_all_cols[:, 3]
            y_acc = data_all_cols[:, 4]
            z_acc = data_all_cols[:, 5]

            config = {
                'bool_output_rr_regardless_sqa': True,
                'bool_predict_prob': False,  # True - predict probability, False - predict label
                'ml_model_fname': settings.model_sqa
            }

            cls_calculate_rr_3 = calculate_rr_3(
                input_data, sensor2, x_acc, y_acc, z_acc, config)
            # _, val_bpm_sqaml, status, feature = cls_calculate_rr_3.run() #TODO update on off skin with the status
            # TODO update on off skin with the status
            _, val_bpm_sqaml, status, feature, val_bpm_sqaml_sd, debug_list_bpm_round, debug_list_status = cls_calculate_rr_3.run()

            # TODO function calculate_rr_3 should not return "--"
            if val_bpm_sqaml == "--":
                val_bpm_sqaml = []

            """ save signal quality status """
            item["signal_quality_status"] = status

            item['debug_list_bpm_round'] = str(
                debug_list_bpm_round)  # for debugging
            item['debug_list_status'] = str(debug_list_status)  # for debugging

            """ save val_bpm_sqaml_sd """
            if str(val_bpm_sqaml_sd) != str(np.nan):
                item['rr_sqaml_sd'] = Decimal(
                    "{:.2f}".format(val_bpm_sqaml_sd))

        except Exception as e:
            logging.error(
                f"error when compute RR (SQA ML) --> {e}. assign empty list ")
            val_bpm_sqaml = []
            item["debug_rr_calulation_error"] = str(e)  # for debugging

        output_bpm_sqaml = process_output(val_bpm_sqaml, decimalPlace)

    # ON/OFF SKIN ALGO AND LOGIC
    try:
        # sensor_onskin_status, onskin_peak_ratio = detect_sensor_onskin(np.array([timestamp, data]).T, params, dashboardMode)

        class_sensor_onskin_algo = detect_sensor_onskin(
            np.array([timestamp, data]).T, params, dashboardMode)

        class_sensor_onskin_algo.run_calculation()  # fft approach

        list_sensor_onskin_status = class_sensor_onskin_algo.list_onskin_status
        sensor_onskin_status = class_sensor_onskin_algo.onskin_status
        list_sensor_onskin_status_ratio = sum(
            list_sensor_onskin_status)/len(list_sensor_onskin_status)

        list_output_peakratio = class_sensor_onskin_algo.list_output_peakratio
        median_list_output_peakratio = np.median(list_output_peakratio)
        """ handle Inf which will cause error in this issue https://github.com/Respiree/rpm_data_processing_backend/issues/146 """
        """ assign invalid value to median_list_output_peakratio if it is Inf or NaN """
        if (median_list_output_peakratio == np.Inf) or (np.isnan(median_list_output_peakratio)):
            median_list_output_peakratio = -1

        item['list_sensor_onskin_status_ratio'] = Decimal(
            "{:.2f}".format(list_sensor_onskin_status_ratio))

        try:
            item['median_list_output_peakratio'] = Decimal(
                "{:.2f}".format(median_list_output_peakratio))
        except:
            pass

        list_output_peakratio = class_sensor_onskin_algo.list_output_peakratio
        try:
            list_output_peakratio = [
                str(list_output_peakratio[k]) for k in range(len(list_output_peakratio))]
            item['list_output_peakratio'] = list_output_peakratio
        except:
            # pass
            item['list_output_peakratio'] = list_output_peakratio.tolist()

        try:
            class_sensor_onskin_algo.run_calculation_2()  # stdev approach
            list_onskin_status_stdev = class_sensor_onskin_algo.list_onskin_status_stdev

            sensor_onskin_status_stdev = class_sensor_onskin_algo.onskin_status_stdev
            list_onskin_status_stdev_ratio = sum(
                list_onskin_status_stdev)/len(list_onskin_status_stdev)

            item['sensor_onskin_status_stdev'] = sensor_onskin_status_stdev
            item['list_onskin_status_stdev_ratio'] = Decimal(
                "{:.2f}".format(list_onskin_status_stdev_ratio))

            list_output_stdev = class_sensor_onskin_algo.list_output_stdev

            median_list_output_stdev = np.median(list_output_stdev)
            """ assign invalid value to median_list_output_stdev if it is Inf or NaN """
            if (median_list_output_stdev == np.Inf) or (np.isnan(median_list_output_stdev)):
                median_list_output_stdev = -1

            try:
                item['median_list_output_stdev'] = Decimal("{:.2f}".format(
                    median_list_output_stdev))  # algo_rr-skin-contact_v1.x.x
            except Exception as e:
                logging.error(
                    f"error when running on/off skin algo (median_list_output_stdev). {e}")

            try:
                list_output_stdev = [str(list_output_stdev[k])
                                     for k in range(len(list_output_stdev))]
                item['list_output_stdev'] = list_output_stdev
            except:
                item['list_output_stdev'] = list_output_stdev.tolist()

            list_output_skewness = class_sensor_onskin_algo.list_output_skewness
            median_list_output_skewness = np.median(list_output_skewness)
            """ assign invalid value to median_list_output_skewness if it is Inf or NaN """
            if (median_list_output_skewness == np.Inf) or (np.isnan(median_list_output_skewness)):
                median_list_output_skewness = -1

            try:
                item['median_list_output_skewness'] = Decimal(
                    "{:.2f}".format(median_list_output_skewness))
            except Exception as e:
                logging.error(
                    f"error when running on/off skin algo (median_list_output_skewness). {e}")

            try:
                list_output_skewness = [
                    str(list_output_skewness[k]) for k in range(len(list_output_skewness))]
                item['list_output_skewness'] = list_output_skewness
            except:
                item['list_output_skewness'] = list_output_skewness.tolist()

            list_output_kurtosis = class_sensor_onskin_algo.list_output_kurtosis
            median_list_output_kurtosis = np.median(list_output_kurtosis)
            """ assign invalid value to median_list_output_kurtosis if it is Inf  or NaN """
            if (median_list_output_kurtosis == np.Inf) or (np.isnan(median_list_output_kurtosis)):
                median_list_output_kurtosis = -1

            try:
                item['median_list_output_kurtosis'] = Decimal(
                    "{:.2f}".format(median_list_output_kurtosis))
            except Exception as e:
                logging.error(
                    f"error when running on/off skin algo (median_list_output_kurtosis). {e}")

            try:
                list_output_kurtosis = [
                    str(list_output_kurtosis[k]) for k in range(len(list_output_kurtosis))]
                item['list_output_kurtosis'] = list_output_kurtosis
            except:
                item['list_output_kurtosis'] = list_output_kurtosis.tolist()

            list_phase_diff = class_sensor_onskin_algo.list_phase_diff
            try:
                list_phase_diff = [str(list_phase_diff[k])
                                   for k in range(len(list_phase_diff))]
                item['list_phase_diff'] = list_phase_diff
            except:
                item['list_phase_diff'] = list_phase_diff.tolist()

        except Exception as e:
            logging.error(
                f"error when running on/off skin algo (class_sensor_onskin_algo.run_calculation_2()). {e}")

        if dashboardMode == 'RR':

            """ Uncomment this to use chest on skin detection version "algo_rr-skin-contact_v1.x.x" """
            # try:
            #     if median_list_output_stdev>settings.threshold_median_list_output_stdev:
            #         sensor_onskin_status = 1
            #     else:
            #         sensor_onskin_status = 0
            # except:
            #     pass

            """ Uncomment this to use chest on skin detection version "algo_rr-skin-contact_v3.0.0" """
            try:
                sensor_onskin_status = calc_accl_std(data_all_cols)
            except:
                pass

            item['sensor_onskin_status'] = sensor_onskin_status

            """ store chest on/off skin status """
            if sensor_onskin_status == 1:
                sensor_contact_status = "Good"
            else:
                sensor_contact_status = "Poor"

            item['sensor_contact_status'] = sensor_contact_status

        # on/off skin detection using 2 light sources for HR
        # elif dashboardMode == 'HR':
        #     class_sensor_onskin_2_lightsources_algo = detect_sensor_onskin_2_lightsources(
        #         dataRED, dataIR, timestamp, params, settings.params_onoffskin_hr)
        #     class_sensor_onskin_2_lightsources_algo.run_calculation()

        #     list_diff_mean = class_sensor_onskin_2_lightsources_algo.list_diff_mean
        #     list_diff_median = class_sensor_onskin_2_lightsources_algo.list_diff_median
        #     list_diff_sd = class_sensor_onskin_2_lightsources_algo.list_diff_sd
        #     list_diff_cv = class_sensor_onskin_2_lightsources_algo.list_diff_cv

        #     onskin_status_diff_median = class_sensor_onskin_2_lightsources_algo.onskin_status_diff_median

        #     try:
        #         # detector = DetectSensorSkinContactUsingTwoLightSources(params=None)
        #         # detector.extract_features(dataRED, dataIR)
        #         # detector.extract_ppg_quality_features(dataRED, dataIR)
        #         # skin_contact = detector.determine_skin_contact_using_lda()

        #         detector = DetectSensorSkinContactUsingTwoLightSources(params=None)
        #         skin_contact, list_skin_contact = detector.extract_features_and_skin_contact(dataRED, dataIR)

        #         if skin_contact is None:
        #             skin_contact = 0

        #         item['list_skin_contact'] = list_skin_contact

        #     except Exception as e:
        #         logging.error(f"DetectSensorSkinContactUsingTwoLightSources: {e}.")
        #         skin_contact = 0

        #     item['sensor_onskin_status'] = skin_contact

    except Exception as e:
        logging.error(
            f"error when computing on/off skin. error message is {e}.")
        item['error_sensor_onskin_status'] = str(e)

    if dashboardMode == 'RR':
        item['rr'] = output_bpm_sqaml
        item['rr_tdomain'] = output_val_bpm
        item['rr_fdomain'] = output_bpm_wo_sqa
        item['rr_fdomain_w_good_sqa'] = output_bpm_w_sqa
        item['rr_hybrid'] = output_bpm_hybrid
        item['rr_sqaml'] = output_bpm_sqaml

        item['rr_td'] = output_val_td
        item['rr_dc'] = output_val_dc
        item['rr_ibi'] = output_val_ibi

        # bandpass RR
        try:
            bandpass_rr = settings.bandpass_rr
            if (item['rr'] < bandpass_rr[0]) or (item['rr'] > bandpass_rr[1]):
                item['rr'] = str(np.nan)
        except:
            pass

        # add RR_SD
        try:
            item['rr_sd'] = item['rr_sqaml_sd']
        except:
            # item['RR_sd'] = None
            item['rr_sd'] = str(np.nan)

    elif dashboardMode == 'HR':
        item['hr'] = output_bpm_w_sqa
        item['hr_tdomain'] = output_val_bpm
        item['hr_fdomain'] = output_bpm_wo_sqa
        item['hr_fdomain_w_good_sqa'] = output_bpm_w_sqa

        item['hr_fdomain_w_good_sqa_sd'] = output_bpm_w_sqa_sd
        item['hr_sd'] = output_bpm_w_sqa_sd

    item['sqa'] = sqa
    item['sqa_index'] = Decimal("{:.2f}".format(
        sqa_index))  # Decimal(str(sqa_index))
    item['accepted_frame'] = accepted_frame
    item['total_frame'] = total_frame
    try:
        item['accepted_frame_ratio'] = Decimal("{:.2f}".format(
            accepted_frame/total_frame))  # Decimal(str(accepted_frame/total_frame))
    except:
        pass

    item['accepted_frame_tdomain'] = accepted_frame_tdomain
    item['total_frame_tdomain'] = total_frame_tdomain

    try:
        # Decimal(str(accepted_frame_tdomain/total_frame_tdomain))
        item['accepted_frame_tdomain_ratio'] = Decimal(
            "{:.2f}".format(accepted_frame_tdomain/total_frame_tdomain))
    except:
        pass

    # """ store data in the database """
    # dbTable.put_item(Item=item)
    # logging.info(f"Updated {dashboardMode} data ({item['filename']})")
    dbTable.update(**item)
    return item


def calculate_SpO2(timestamp, dataRED, dataIR, params, item, dbTable, decimalPlace=3):
    # def calculate_SpO2(record, filePathRaw, previousPacketSize, timestamp, dataRED, dataIR, params, dateTime, decimalPlace=3):

    SpO2 = getSpO2_FFT(timestamp, dataRED, dataIR, params)
    SpO2.extractSpO2()
    timeSpO2, valSpO2 = SpO2.outputTime, SpO2.outputVal

    outputSpO2 = process_output(valSpO2, decimalPlace)

    # get standard deviation
    outputSpO2_sd = get_sd_from_array(
        valSpO2, decimal_place=decimalPlace, round_number=True)

    item['spo2'] = outputSpO2
    item['accepted_frame_spo2'] = SpO2.accepted_frame
    item['total_frame_spo2'] = SpO2.total_frame
    item['spo2_sd'] = outputSpO2_sd

    try:
        item['accepted_frame_spo2_ratio'] = Decimal("{:.2f}".format(
            SpO2.accepted_frame/SpO2.total_frame))  # Decimal(str(SpO2.accepted_frame/SpO2.total_frame))
    except:
        pass

    dbTable.update(**item)

    logging.info(f"Updated SpO2 data ({item['filename']})")

    return item


def pipeline_calculation(dashboardMode, hardwareMode, data, filename, item, db_table):

    item["resp_sp_version"] = resp_sp.__version__

    upperBound = settings.sensor_max_count_mean + settings.sensor_max_count_std
    lowerBound = settings.sensor_max_count_mean - settings.sensor_max_count_std

    if dashboardMode == 'RR':

        if hardwareMode == 'respiratory-rate':
            paramsRR = settings.initParameters('RR-60ms')
            logging.info('{} ===> RR parameters 60ms'.format(filename))

            dataLD = data[:, 1]

        # TODO: return proper error message and remove this. As sensor is toggled to the wrong mode, it should not compute RR
        # elif hardwareMode=='pulse-oximetry':
        #     paramsRR = settings.initParameters('RR-40ms')

        #     if (np.mean(data[:,1])<upperBound) and (np.mean(data[:,1])>lowerBound):
        #         dataLD = data[:, 2] # use IR for calculation
        #     else:
        #         dataLD = data[:, 1] # use RED for calculation

        timestamp = np.arange(len(dataLD))*paramsRR['sampling_time']

        # if data length is too short, reduce window size
        if len(dataLD) < paramsRR['buffer']:
            paramsRR['window_size'] = paramsRR['window_size_reduced']
            paramsRR['window_art_mva'] = paramsRR['window_art_mva_reduced']
            paramsRR['window_art_bl'] = paramsRR['window_art_bl_reduced']
            new_buffer_size = paramsRR['window_mva']+paramsRR['window_bl']-1+3-1 + \
                paramsRR['window_art_mva']-1 + \
                paramsRR['window_art_bl']-1+paramsRR['window_size']-1
            logging.info('{} ===> data length = {} ===> reduce buffer size to: {}'.format(
                filename, len(dataLD), new_buffer_size))

        # call calculation function
        # calculate_RR(timestamp, dataLD, item)
        # calculate_rr_and_hr(timestamp, dataLD, paramsRR, item, db_table, settings.sqa_bandpass_rr, settings.sqa_threshold_rr, dashboardMode, decimalPlace=3)

        paramsRRhybrid = settings.initParameters('RR-hybrid-algo-60ms')
        item = calculate_rr_and_hr(timestamp, dataLD, paramsRR, item,
                                   db_table, settings.sqa_bandpass_rr,
                                   settings.sqa_threshold_rr, dashboardMode, decimalPlace=3,
                                   paramsHybrid=paramsRRhybrid, data_all_cols=data)

        try:
            display_label = 0 if len(remove_bad_data([item]))==0 else 1
            item['display_label'] = display_label

            # item["sensor_onskin_status"] = display_label
        except Exception as e:
            logging.error(f"error occurs when getting display_label for the chest data. error message is {e}")

        """ store data in the database """
        logging.info(f"Updated {dashboardMode} data ({item['filename']})")

    elif dashboardMode == 'HR':
        dataRED = data[:, 1]
        dataIR = data[:, 2]

        paramsHR = settings.initParameters('HR')
        paramsSpO2_fft = settings.initParameters('SpO2-fft')

        timestamp = np.arange(len(dataIR))*paramsHR['sampling_time']

        # if (np.mean(dataIR) < upperBound) and (np.mean(dataIR) > lowerBound):
        #     dataHR = dataRED  # use IR for calculation
        #     logging.info("{} ===> USE RED for HR (IR saturation)".format(filename))
        # else:
        #     dataHR = dataIR  # use IR for calculation
        #     logging.info("{} ===> USE IR for HR".format(filename))

        item = calculate_rr_and_hr(timestamp, dataIR, paramsHR, item, db_table, settings.sqa_bandpass_hr,
                                   settings.sqa_threshold_hr, dashboardMode, decimalPlace=3, dataRED=dataRED, dataIR=dataIR)
        # logging.info(f"Updated {dashboardMode} data ({item['filename']})")

        sensor_version = item.get("sensor_version", None) # default to V2.0 if not set
        dict_norm_r = None
        # item["debug_norm_r"] = "norm_r is set to None"

        try:
            Spo2Calculation = CalculateSpo2UsingFrequencyAnalysis(params_set=1)
            # dict_output_spo2 = Spo2Calculation.calculate_spo2(
            #     timestamp,
            #     dataRED,
            #     dataIR,
            #     spo2_equation=8, # check
            #     enable_quality_check=True,
            #     spo2_bandpass=[0,100], # check
            #     round_value=False,
            #     norm_r=dict_norm_r
            # )
            dict_output_spo2 = Spo2Calculation.calculate_spo2(
                timestamp,
                dataRED,
                dataIR,
                spo2_equation=9,
                enable_quality_check=True,
                spo2_bandpass=settings.spo2_minmax, #[70,100],
                round_value=False,
                norm_r=None
            )

            # if (dict_output_spo2.get("processed_spo2") is not None) and (dict_output_spo2.get("processed_spo2") < 70):
            #     dict_output_spo2["processed_spo2"] = str(np.nan)
            #     dict_output_spo2["processed_spo2_sd"] = str(np.nan)
            #     logging.debug(f"Warning: SpO2 value is below 70 for userId {item['userId']}.")

            item['spo2'] = dict_output_spo2["processed_spo2"]
            item['accepted_frame_spo2'] = dict_output_spo2["accepted_frame"]
            item['total_frame_spo2'] = dict_output_spo2["total_frame"]
            item['spo2_sd'] = dict_output_spo2["processed_spo2_sd"]
            item['is_spo2_calc_error'] = False

        except Exception as e:
            logging.error(f"error when running SpO2 calculation. error message is {e}")
            item['spo2'] = str(np.nan)
            item['accepted_frame_spo2'] = str(np.nan)
            item['total_frame_spo2'] = str(np.nan)
            item['spo2_sd'] = str(np.nan)
            item['is_spo2_calc_error'] = True


        try:
            slicer = PPGSignalDecomposition(max_sse=1, diff_edge_threshold=0.7)
            result = slicer.run(
                signal_ir=dataIR,
                signal_red=dataRED,
                window_size_sec=5,
                overlap_sec=2.5,
                flip_signals=True,
                filter_signals=True,
            )


            skin_contact = int(result['skin_contact'])

            if skin_contact is None:
                skin_contact = 0
        
        except Exception as e:
            logging.error(f"PPGSignalDecomposition: {e}.")
            skin_contact = 0

        item['sensor_onskin_status'] = skin_contact


        try:
            display_label = 0 if len(remove_bad_data([item])) == 0 else 1
            item['display_label'] = display_label

            if display_label == 1:
                item['signal_quality_status'] = "Good"
            elif display_label == 0:
                item['signal_quality_status'] = "Poor"
                
        except Exception as e:
            logging.error(
                f"error occurs when getting display_label for the finger data. error message is {e}")

        logging.info(f"Updated HR and SpO2 data ({item['filename']})")


    return item


# %%

def calories_burned(stepcount):
    return Decimal("{:.2f}".format(0.05*stepcount))


def extract_temperature(array_temperature, error_handling_minmax_skin_temperature_value_bool=False, error_handling_minmax_skin_temperature_value=None):

    len_array_temperature = len(array_temperature)

    if error_handling_minmax_skin_temperature_value_bool:
        min_temperature = error_handling_minmax_skin_temperature_value[0]*10
        max_temperature = error_handling_minmax_skin_temperature_value[1]*10

        array_temperature = array_temperature[(array_temperature >= min_temperature) & (
            array_temperature <= max_temperature)]

    num_temperature_out_of_range = len_array_temperature - \
        len(array_temperature)

    # temperature = np.median(array_temperature)
    temperature = np.max(array_temperature)
    temperature = temperature/10
    # return temperature #Decimal("{:.2f}".format(temperature))
    return temperature, num_temperature_out_of_range

# %% Step Count


def calculate_stepcount(motion, delta=20, wsize=5):
    lookformax = True

    output_val = []
    filt_val = []

    stepcount = 0

    val_max = 0
    val_min = 0

    for i in range(len(motion)-wsize):
        window_motion = motion[i:i+wsize]
        filt_val = np.append(filt_val, np.mean(window_motion))

    for i in range(len(filt_val)):
        temp_val = filt_val[i]

        if temp_val > val_max:
            val_max = temp_val

        if temp_val < val_min:
            val_min = temp_val

        if lookformax == True:
            if temp_val < (val_max-delta):
                stepcount += 1

                val_min = temp_val
                lookformax = False

        else:
            val_max = temp_val
            lookformax = True

    # stepcount = Decimal(
    return stepcount


# %%


def calculate_activeness(xaccl, threshold, params, mask_size_seconds):

    mask_size = int(mask_size_seconds/params['sampling_time'])  # 1 minute
    params['window_mva'] = int(params['window_mva']/params['sampling_time'])
    params['window_bl'] = int(params['window_bl']/params['sampling_time'])

    Xinput = np.array([np.arange(len(xaccl)), xaccl]).T

    cls_sp = signal_processing(Xinput, params)
    cls_sp.run_signal_processing()

    motion = np.abs(cls_sp.blrm_val)

    time_motion = cls_sp.blrm_time

    # point_total = len(motion)

    activeness = []
    t_activeness = []

    if mask_size >= len(motion):
        mask_size = len(motion) - 1


    """
    active vs inactive
    """
    data_window_sum = []
    for i in range(mask_size, len(motion)):
        # temp = motion[i-mask_size:i]
        # window_sum = np.sum(temp)

        window_sum = np.sum(motion[i-mask_size:i])

        # temp_above_threshold = window_sum>threshold

        if window_sum > threshold:
            activeness = np.append(activeness, 1)
        else:
            activeness = np.append(activeness, 0)

        t_activeness = np.append(t_activeness, time_motion[i])
        data_window_sum = np.append(data_window_sum, window_sum)

    point_total = len(activeness)

    point_active_high = len(activeness[activeness == 1])
    point_active_low = point_total - point_active_high


    return point_active_low, point_active_high


# %%

def calculate_patterns_metrics(Xin, trinary, zero_cross, params, max_PD=None):
    # duty cycle
    # tidal depth

    sampling_time = params['sampling_time']
    period_min = params['val_min']
    period_max = params['val_max']

    """
    Extract primary features
    """
    # Find the first zero crossing that signal decrease
    index_zerocross_Tup = None
    for j in range(len(zero_cross)):
        if trinary[zero_cross[j]+1] == -1:
            index_zerocross_Tup = j
            break

    Tup = []
    Tdown = []
    Ttotal = []

    Dmax = []
    Dmin = []
    Vt = []

    if index_zerocross_Tup != None:

        for k in range(index_zerocross_Tup, len(zero_cross)-2, 2):
            idx0, idx1, idx2 = [], [], []

            idx0 = zero_cross[k]
            idx1 = zero_cross[k+1]
            idx2 = zero_cross[k+2]

            temp_period = []
            temp_period = (idx2-idx0)*sampling_time

            if (temp_period >= period_min) & (temp_period <= period_max):

                Tup = np.append(Tup, (idx2-idx1)*sampling_time)
                Tdown = np.append(Tdown, (idx1-idx0)*sampling_time)

                Ttotal = np.append(Ttotal, temp_period)

                temp_window = []
                temp_window = Xin[idx0+1:idx2+1]
                temp_window = temp_window-np.mean(temp_window)

                Dmax = np.append(Dmax, abs(np.max(temp_window)))
                Dmin = np.append(Dmin, abs(np.min(temp_window)))

                Vt = np.append(Vt, Dmax[-1]+Dmin[-1])


    output = {}

    try:
        output['RR'] = 60/Ttotal
    except:
        output['RR'] = np.nan

    try:
        # output['TD'] = Vt/max_PD #*100
        output['TD'] = Vt
    except:
        output['TD'] = np.nan

    try:
        output['DC'] = (Tdown/Ttotal)*100
    except:
        output['DC'] = np.nan

    try:
        output['IBI'] = Ttotal*1000  # convert to ms
    except:
        output['IBI'] = np.nan

    for key in output.keys():
        output[key] = np.median(output[key])

    return output


class detect_sensor_onskin():
    def __init__(self, val, prepro_params, dashboardMode):
        if dashboardMode == 'HR':
            self.is_ppg = True
            params_onoffskin = settings.params_onoffskin_hr
        elif dashboardMode == 'RR':
            self.is_ppg = False
            params_onoffskin = settings.params_onoffskin_rr

        self.T = prepro_params['sampling_time']
        self.freq_lim = params_onoffskin['freq_lim']
        self.window_size = params_onoffskin['window_size']
        self.window_shift = params_onoffskin['window_shift']
        self.threshold_onoff_skin = params_onoffskin['threshold']
        self.bandpass_lower_lim = params_onoffskin['bandpass_lower_lim']
        self.bandpass_higher_lim = params_onoffskin['bandpass_higher_lim']
        self.fs = 1/self.T
        self.signal_stdev_threshold = params_onoffskin["signal_stdev_threshold"]

        self.val = val
        self.prepro_params = prepro_params

    def run_fft(self, Xin, fs, n_fft=2**12):
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
        # if sum(list_onskin)>=int(len(list_onskin)/2):
        if len(list_onskin) > 1:
            if sum(list_onskin) >= math.ceil(len(list_onskin)/2):
                output = 1
            else:
                output = 0
        else:
            output = list_onskin[0]
        return int(output)

    def run_calculation(self):

        prepro_signal = signal_processing(
            self.val, self.prepro_params)  # input to signal processing
        prepro_signal.remove_baseline()

        # x = prepro_signal.blrm_time
        y = prepro_signal.blrm_val

        self.list_output_peakratio = []
        self.list_onskin_status = []
        self.list_phase_diff = []

        for i in range(0, len(y), self.window_shift):

            temp_window = y[i:i+self.window_size]

            # if len(temp_window)<self.window_size:
            #     continue

            # sensor_status, peak_ratio = self.calculate_peak_ratio(temp_window, self.fs, self.freq_lim, self.is_ppg, self.threshold_onoff_skin)
            sensor_status, peak_ratio = self.calculate_peak_ratio(
                temp_window, self.fs, self.freq_lim, self.is_ppg, self.threshold_onoff_skin, self.bandpass_lower_lim, self.bandpass_higher_lim)

            temp_phase_diff = self.calculate_phase_diff(temp_window, self.fs)

            self.list_output_peakratio = np.append(
                self.list_output_peakratio, peak_ratio)
            self.list_onskin_status = np.append(
                self.list_onskin_status, sensor_status)
            self.list_phase_diff = np.append(
                self.list_phase_diff, temp_phase_diff)

        self.onskin_status = self.determine_onskin(self.list_onskin_status)
        return

    def run_calculation_2(self):
        prepro_signal = signal_processing(self.val, self.prepro_params)
        bl_time, bl_val = prepro_signal.baseline(
            prepro_signal.time, prepro_signal.val, prepro_signal.window_bl)
        baseline_time, blrm_val = prepro_signal.baseline_removal(
            prepro_signal.time, prepro_signal.val, bl_time, bl_val)

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

            # if (rr_stdev <= 1) | (rr_stdev >= 20):
            if (temp_stdev <= self.signal_stdev_threshold[0]) | (temp_stdev >= self.signal_stdev_threshold[1]):
                sensor_status = 0
            else:
                sensor_status = 1

            self.list_output_stdev = np.append(
                self.list_output_stdev, temp_stdev)
            self.list_output_skewness = np.append(
                self.list_output_skewness, temp_skew)
            self.list_output_kurtosis = np.append(
                self.list_output_kurtosis, temp_kurtosis)

            self.list_onskin_status_stdev = np.append(
                self.list_onskin_status_stdev, sensor_status)

        self.onskin_status_stdev = self.determine_onskin(
            self.list_onskin_status_stdev)

        return


class detect_sensor_onskin_2_lightsources():
    def __init__(self, sensor1, sensor2, timestamp, prepro_params, params_onoffskin):

        self.window_size = params_onoffskin['window_size']
        self.window_shift = params_onoffskin['window_shift']

        self.th_median = params_onoffskin['threshold_2lightsources_median']

        self.sensor1 = sensor1
        self.sensor2 = sensor2
        self.timestamp = timestamp

        self.prepro_params = prepro_params

    def determine_onskin(self, value, threshold):
        if value > threshold:
            output = 1  # onskin
        else:
            output = 0  # offskin
        return int(output)

    def run_calculation(self):

        prepro_signal = signal_processing()  # input to signal processing

        mva_time_s1, mva_val_s1 = prepro_signal.moving_average(
            self.timestamp, self.sensor1, self.prepro_params['window_mva'])
        mva_time_s2, mva_val_s2 = prepro_signal.moving_average(
            self.timestamp, self.sensor2, self.prepro_params['window_mva'])

        diff_s1s2 = mva_val_s1-mva_val_s2
        diff_s1s2 = np.abs(diff_s1s2)

        # prepro_signal = signal_processing(self.val, self.prepro_params) # input to signal processing
        # prepro_signal.remove_baseline()

        # # x = prepro_signal.blrm_time
        # y = prepro_signal.blrm_val

        self.list_diff_mean = []
        self.list_diff_median = []
        self.list_diff_sd = []
        self.list_diff_cv = []

        self.onskin_status_diff_median = []

        y = diff_s1s2.copy()

        for i in range(0, len(y), self.window_shift):

            temp_window = y[i:i+self.window_size]

            if len(temp_window) < self.window_size:
                continue

            temp_diff_mean = np.mean(temp_window)
            temp_diff_median = np.median(temp_window)
            temp_diff_sd = np.std(temp_window)

            temp_diff_cv = temp_diff_sd/temp_diff_mean

            self.list_diff_mean = np.append(
                self.list_diff_mean, temp_diff_mean)
            self.list_diff_median = np.append(
                self.list_diff_median, temp_diff_median)
            self.list_diff_sd = np.append(self.list_diff_sd, temp_diff_sd)
            self.list_diff_cv = np.append(self.list_diff_cv, temp_diff_cv)

        # median_diff_mean = np.median(list_diff_mean)
        # median_diff_median = np.median(list_diff_median)
        # median_diff_sd = np.median(list_diff_sd)

        self.onskin_status_diff_median = self.determine_onskin(
            np.median(self.list_diff_median), self.th_median)
        return


# %% function for RR with SQA ML and motion

# TODO move this to class object
# Below is the function to map the timestamp between optical sensor and accelerometer
# One thing to take note is the signal processing of optical sensor data and accelerometer data are done separately
# However, based on the signal processing window size, most likely, the data length of acceleromter is longer than the data length of optical sensor
def map_input_data_55s(blrm_val, blrm_time, accl_time):
    """
    crop blrm and art to be same length and timestamp as artbl
    """
    blrm_time = list(blrm_time)
    accl_time = list(accl_time)

    if len(blrm_time) > len(accl_time):
        index_blrm = [blrm_time.index(
            accl_time[0]), blrm_time.index(accl_time[-1])]
        signal = np.array([blrm_time[index_blrm[0]:index_blrm[1] + 1],
                          blrm_val[index_blrm[0]:index_blrm[1] + 1]]).T
    else:
        index_accl = [accl_time.index(
            blrm_time[0]), accl_time.index(blrm_time[-1])]
        signal = np.array(
            [accl_time[index_accl[0]:index_accl[1] + 1], blrm_val]).T

    return signal


def calc_mag_var(peaks, throughs):
    if len(peaks) == 0:
        return 1000, 1000
    x_peak, y_peak = [], []
    x_throughs, y_throughs = [], []
    for peak in peaks:
        x, y = peak
        x_peak.append(x)
        y_peak.append(y)
    for through in throughs:
        x, y = through
        x_throughs.append(x)
        y_throughs.append(y)
    mag_var = []
    for k in range(len(peaks)):
        if k < len(throughs):
            mag_diff = y_peak[k] - y_throughs[k]
        else:
            mag_diff = y_peak[k] - 0
        mag_var.append(mag_diff)
        if k + 1 < len(peaks):
            mag_diff_next = y_peak[k + 1] - y_throughs[k]
            mag_var.append(mag_diff_next)
    if len(mag_var) == 0:
        return 1000, 1000
    else:
        mag_var = np.array(mag_var)
        std = np.std(mag_var)
        if np.mean(mag_var) == 0:
            cv = 1000
        else:
            cv = std / np.mean(mag_var)
    return std, cv


def calc_sqa(signal_time, optical_signal_val, percentage_of_ones, binary_signal_val, index_change, params, trained_model=None, **kwargs):
    ml_model_fname = kwargs['ml_model_fname']
    bool_predict_prob = kwargs['bool_predict_prob']

    delta_peakdet = 0.01
    bl_peaks, bl_throughs = peakdet(
        optical_signal_val, delta_peakdet, signal_time)
    std_bl, cv_bl = calc_mag_var(bl_peaks, bl_throughs)
    
    time_of_change, mag_of_change = [], []
    for i in index_change:
        time_of_change.append(signal_time[i])
        mag_of_change.append(binary_signal_val[i])
    list_of_periods = []

    bandpass = [0.05, 1.167]
    if len(time_of_change) > 3:
        for i in range(len(time_of_change) - 2):
            period = time_of_change[i + 2] - time_of_change[i]
            list_of_periods.append(period)
        std_of_periods = np.std(np.array(list_of_periods))
        cv_of_periods = std_of_periods / (np.mean(np.array(list_of_periods)))
        
    else:
        std_of_periods = 60
        cv_of_periods = 60

    freq_wo_bp, mag_wo_bp = run_fft(
        binary_signal_val, 1 / params['sampling_time'])
    freq_bp = freq_wo_bp[(freq_wo_bp >= bandpass[0]) &
                         (freq_wo_bp <= bandpass[1])].copy()
    mag_bp = mag_wo_bp[(freq_wo_bp >= bandpass[0]) &
                       (freq_wo_bp <= bandpass[1])].copy()
    peaks, throughs = peakdet(mag_bp, delta_peakdet, freq_bp)
    x_peak, y_peak = [], []
    x_through, y_through = [], []
    for peak in peaks:
        x, y = peak
        x_peak.append(x)
        y_peak.append(y)
    for through in throughs:
        x, y = through
        x_through.append(x)
        y_through.append(y)

    no_of_peaks = 0
    for i in y_peak:
        if i >= 2500:
            no_of_peaks = no_of_peaks + 1
    try:
        # if first peak is close to cutoff frequency
        if peaks[0, 0] < bandpass[0] + (freq_bp[2] - freq_bp[1]):
            try:
                peaks = peaks[1:, :]
            except:
                pass
    except:
        pass
    peak_index = 0
    if len(peaks) > 0:
        first_magpeak = [-np.Inf, -np.Inf]
        for i in range(len(peaks)):
            if peaks[i, 1] > first_magpeak[1]:
                first_magpeak[0] = peaks[i, 0]
                first_magpeak[1] = peaks[i, 1]
                peak_index = i
    else:
        first_magpeak = [0, 0]
    magnitude = first_magpeak[1]

    # TODO load model and pass to function
    if trained_model is None:
        try:
            # trained_model = joblib.load(os.path.join('.', 'model', 'random_forest_model'))
            # model_name = settings.model_sqa #"model/sqa_model_v1"

            logging.info(f"Loading model: {ml_model_fname}")
            trained_model = joblib.load(os.path.join(
                settings.path_folder_model, ml_model_fname))
        except Exception as e:
            logging.error(f"Load model '{ml_model_fname}' failed")

    features = np.array((no_of_peaks, magnitude, std_of_periods,
                        cv_of_periods, percentage_of_ones, cv_bl, std_bl)).reshape(1, -1)
    pred_proba = trained_model.predict_proba(features)
    if bool_predict_prob:
        pred_proba = trained_model.predict_proba(features)
        if pred_proba[0][1] > 0.80:
            pred_label = 1
        else:
            pred_label = 0
    else:
        pred_label = trained_model.predict(features)
    return pred_label, features


def calculate_activeness_2(mag_accl, xaccl, yaccl, zaccl, threshold_x01, threshold_y01, threshold_z01, threshold_x12, threshold_y12, threshold_z12, params, integration_window, title_timestamp=None):
    Xinput, Yinput, Zinput = np.array([np.arange(len(xaccl)), xaccl]).T, np.array(
        [np.arange(len(yaccl)), yaccl]).T, np.array([np.arange(len(zaccl)), zaccl]).T

    # print("The length of X, Y, Z input are: ", len(Xinput), len(Yinput), len(Zinput))
    # print(params)
    cls_sp_x = signal_processing(Xinput, params)
    cls_sp_y = signal_processing(Yinput, params)
    cls_sp_z = signal_processing(Zinput, params)
    cls_sp_x.run_signal_processing_activity()
    cls_sp_y.run_signal_processing_activity()
    cls_sp_z.run_signal_processing_activity()
    kt_val_x, kt_time_x, kt_val_y, kt_val_z = cls_sp_x.art_val, cls_sp_x.art_time, cls_sp_y.art_val, cls_sp_z.art_val
    # print('The length of the KT value of ACCL is: ', len(kt_val_x))
    activeness, t_activeness = [], []
    active_time, nonactive_time = [], []
    for i in range(0, len(kt_val_x)):
        window_sum_x = np.mean(kt_val_x[i])
        window_sum_y = np.mean(kt_val_y[i])
        window_sum_z = np.mean(kt_val_z[i])
        if ((window_sum_x > threshold_x12 and window_sum_y > threshold_y12) or (window_sum_x > threshold_x12 and window_sum_z > threshold_z12) or (window_sum_y > threshold_y12 and window_sum_z > threshold_z12)):
            activeness = np.append(activeness, 2)
            active_time = np.append(active_time, kt_time_x[i])
        elif ((window_sum_x > threshold_x01 and window_sum_y > threshold_y01) or (window_sum_x > threshold_x01 and window_sum_z > threshold_z01) or (window_sum_y > threshold_y01 and window_sum_z > threshold_z01)):
            activeness = np.append(activeness, 1)
            nonactive_time = np.append(nonactive_time, kt_time_x[i])
        else:
            activeness = np.append(activeness, 0)
            nonactive_time = np.append(nonactive_time, kt_time_x[i])
        t_activeness = np.append(t_activeness, kt_time_x[i])
    # print('The length of 0s, 1s, and 2s are: ', len(activeness[activeness == 0]), len(activeness[activeness == 1]), len(activeness[activeness == 2]))
    # print('The maximum value of the three axis KT value of accelerometer are: ', window_sum_x.max(), window_sum_y.max(), window_sum_z.max())
    manual_label = np.zeros((len(mag_accl),), dtype=int)
    # Manual label adjustment change below

    return kt_time_x, nonactive_time, activeness


def handle_accl_issue(data_input, value_to_detect=0):
    # This function handles accelerometer data issues based on the following rules:
    # test 1: first point is 0
    # test 2: last point is 0
    # test 3: middle single 0 with non-zero neighbors
    # test 4: middle single 0 with one zero neighbor
    # test 5: middle multiple 0s
    # if is_error_detected == 1, then there was at least one imputation

    data_output = data_input.copy()
    is_error_detected = 0

    n_rows = data_input.shape[0]
    if n_rows == 0:
        return data_output, is_error_detected

    def impute_axis(axis_values):
        nonlocal is_error_detected
        x = axis_values.copy()
        n = len(x)
        zero_idx = np.where(x == value_to_detect)[0]
        if len(zero_idx) == 0:
            return x

        # group consecutive zero indices into runs
        runs = []
        start = None
        prev = None
        for idx in zero_idx:
            if start is None:
                start = idx
                prev = idx
            elif idx == prev + 1:
                prev = idx
            else:
                runs.append((start, prev))
                start = idx
                prev = idx
        if start is not None:
            runs.append((start, prev))

        for s, e in runs:
            run_len = e - s + 1
            # rule 4: leave multi-zero runs unchanged
            if run_len > 1:
                continue

            i = s  # single zero index
            # rule 1: first point
            if i == 0:
                if n > 1 and x[1] != 0:
                    x[0] = x[1]
                    is_error_detected = 1
            # rule 2: last point
            elif i == n - 1:
                if x[n - 2] != 0:
                    x[n - 1] = x[n - 2]
                    is_error_detected = 1
            # rule 3: middle single zero: average of neighbors if both non-zero
            else:
                if (x[i - 1] != 0) and (x[i + 1] != 0):
                    x[i] = (x[i - 1] + x[i + 1]) / 2.0
                    is_error_detected = 1
                # otherwise leave as-is (neighbor zero => part of longer run scenario)
        return x

    # process acc_x (col 3), acc_y (col 4), acc_z (col 5)
    data_output[:, 3] = impute_axis(data_input[:, 3])
    data_output[:, 4] = impute_axis(data_input[:, 4])
    data_output[:, 5] = impute_axis(data_input[:, 5])

    return data_output, is_error_detected


def calculate_euclidean_distance(data_x, data_y, data_z):
    """
    Calculate the Euclidean distance for three data arrays.
    
    Parameters:
    - data_x: Array of x-axis data
    - data_y: Array of y-axis data
    - data_z: Array of z-axis data
    
    Returns:
    - distances: Array of Euclidean distances
    """
    # Ensure all input arrays are of the same length
    if len(data_x) != len(data_y) or len(data_x) != len(data_z):
        raise ValueError("Input arrays must have the same length.")

    # Calculate the Euclidean distance
    distances = np.sqrt(np.square(data_x) + np.square(data_y) + np.square(data_z))
    return distances


class calculate_rr_3():
    def __init__(self, data, accl_euclidean, accl_x, accl_y, accl_z, config, trained_model=None): # extract RR using time domain and freq domain

        self.data = data
        self.accl_euclidean = accl_euclidean
        self.accl_x = accl_x
        self.accl_y = accl_y
        self.accl_z = accl_z

        # embeded parameters
        self.bandpass = [0.05, 1.167]

        self.params = {
            'sampling_time': 0.06, # second
            'window_mva': 15,
            'window_bl': 250,
            'window_art_mva': 83,
            'window_art_bl': 667, 
            'window_smooth_output': 9, 
            'th_prepro': 3, 
            'lag': 10, 
            'coef_A': 1.4, 
            'coef_B': 0.7, 
            'val_min': 1.0, 
            'val_max': 30, 
            'window_size': 1000,
            'window_shift': 16, 
        }

        self.params_activeness = {
            'sampling_time': 0.06, # second
            'window_mva': 25,
            'window_bl': 250,
            'window_art_mva': 83,
            'window_art_bl': 666,
            'window_smooth_output': 9, # smoothen output after artifact removal
            'th_prepro': 3, # coefficient for artifact removal
            'lag': 2,
            'coef_A': 1.2,
            'coef_B': 0.08,
            'val_min': 1.5,
            'val_max': 15,
            'window_size': 1083,
            'window_shift': 41,
        }
        
        # activeness parameters
        self.dict_threshold_activeness = {
            'activeness_thresholdx01': 300, 
            'activeness_thresholdy01': 310, 
            'activeness_thresholdz01': 1060, 
            'activeness_thresholdx12': 1700, 
            'activeness_thresholdy12': 2400, 
            'activeness_thresholdz12': 1600, 
            'activeness_integration_window_size_seconds': 0.06 
        }

        self.bool_output_rr_regardless_sqa = config['bool_output_rr_regardless_sqa'] # 1 or True calculate rr as long as it can be computed regradless SQA good or bad
        self.config = config
        self.trained_model = trained_model


    def run(self):

        # extrct varaibles
        read_data = self.data
        params = self.params
        ACCL = self.accl_euclidean
        x_acc = self.accl_x
        y_acc = self.accl_y
        z_acc = self.accl_z
        activeness_thresholdx01 = self.dict_threshold_activeness['activeness_thresholdx01']
        activeness_thresholdy01 = self.dict_threshold_activeness['activeness_thresholdy01']
        activeness_thresholdz01 = self.dict_threshold_activeness['activeness_thresholdz01']
        activeness_thresholdx12 = self.dict_threshold_activeness['activeness_thresholdx12']
        activeness_thresholdy12 = self.dict_threshold_activeness['activeness_thresholdy12']
        activeness_thresholdz12 = self.dict_threshold_activeness['activeness_thresholdz12']
        activeness_integration_window_size_seconds = self.dict_threshold_activeness['activeness_integration_window_size_seconds']
        params_activeness = self.params_activeness
        bandpass = self.bandpass

        window_size = self.params['window_size']
        window_shift = self.params['window_shift']

        """ download SQA ML model """
        trained_model = self.trained_model

        if trained_model == None:
            ml_model_fname = self.config['ml_model_fname']
            try:
                print(f"Loading model: {ml_model_fname}")
                trained_model = load_model_from_s3(settings.bucket_name, ml_model_fname)
            except Exception as e:
                print(f"Load model '{ml_model_fname}' failed")
            

    
        global ML_feature

        list_bpm_round = []
        list_status = []
        
        """ apply sliding window """
        for i in range(window_size, len(read_data)+1, window_shift):

            temp_read_data = read_data[i-window_size:i, :]

            # Preprocess raw signal
            cls_signal_prepro = signal_processing(temp_read_data, params) # input to signal processing
            cls_signal_prepro.run_signal_processing() # perform signal processing
            
            MD_time, t_nonactive, activeness = calculate_activeness_2(ACCL, x_acc, y_acc, z_acc, activeness_thresholdx01, activeness_thresholdy01, activeness_thresholdz01,
                        activeness_thresholdx12, activeness_thresholdy12, activeness_thresholdz12,
                        params_activeness, activeness_integration_window_size_seconds)
            
            # MD_time, t_nonactive, activeness = calculate_activeness(temp_ACCL, temp_x_acc, temp_y_acc, temp_z_acc, activeness_thresholdx01, activeness_thresholdy01, activeness_thresholdz01,
            #             activeness_thresholdx12, activeness_thresholdy12, activeness_thresholdz12,
            #             params_activeness, activeness_integration_window_size_seconds)

            # print('The length of baseline removed signal is: ', len(cls_signal_prepro.blrm_val))
            # print('The length of motion detection time and nonactivetime are: ', len(MD_time), len(t_nonactive))
            # print('The beginning and ending timestamp of Blrm values: ', cls_signal_prepro.blrm_time[0], cls_signal_prepro.blrm_time[-1])
            # print('The beginning and ending timestamp of motion detection values: ', MD_time[0], MD_time[-1])

            # Below is the part to check the percentage of the non-active signal
            # If the portion is less than 50%, the output will be ACTIVE BAD with both time and bpm as '--'

            # status = []

            if len(t_nonactive) <= round(0.5*len(MD_time)): #TODO:Than do not hardcode threshold. use variable for the threshold
                status = 'Motion' # 'Active BAD'
                save_time = np.nan #TODO:Than return NaN #
                save_bpm_round = np.nan #TODO:Than return NaN
                ML_feature = np.nan
                temp_bpm_round = np.nan
            else:
                Xsignal = map_input_data_55s(cls_signal_prepro.blrm_val, cls_signal_prepro.blrm_time, MD_time)
                # print('Length of mapped blrm signal: ', len(Xsignal))
                Percent_of_ones = len(activeness[activeness ==1])/len(activeness)
                # print('The ratio of ones in the activeness is: ', Percent_of_ones)
                save_time = [] # timestamp of each extraction

                save_bpm = []
                save_bpm_round = []

                n_window = 0 #TODO:Than. What is this for?

                nonactive_time, window_signal = cls_signal_prepro.motion_removal3(Xsignal, t_nonactive)

                smooth_nonactive_time, smooth_window_signal = cls_signal_prepro.moving_average(nonactive_time, window_signal,
                                                                                            params['window_smooth_output'])

                # print('The length of signal after motion detection removal: ', len(window_signal))
                # print('The length of the smoothed time is: ', len(smooth_window_signal))
                # # print('The first few values of the signal is: ', window_signal[2400:2500])

                if len(smooth_window_signal)>=params['lag']:

                    cls_metric_extraction = metric_extraction(smooth_window_signal, params['coef_A'], params['coef_B'],
                                                            params['lag'], params['sampling_time'],
                                                            params['val_min'], params['val_max'])

                    cls_metric_extraction.run_transformation()
                    cls_metric_extraction.run_metric_extraction() # calculate metric
                    temp_idx_change = cls_metric_extraction.idx_change
                    index_change = list(temp_idx_change)
                    # print('The index of change are: ', index_change)
                    #TODO:Than. This checking of temp_idx_change is not available in the SQA code
                    if len(temp_idx_change) >= 6:
                        output = cls_metric_extraction.output # get metric
                        temp_trinary = cls_metric_extraction.trinary
                        # print('The number of complete cycles is: ', len(temp_idx_change)/2)
                    else:
                        output = {} #TODO:Than. not used. can be deleted
                        status = 'Motion' # 'Active BAD'
                        output['m1_1'] = np.nan #TODO:Than. not used. can be deleted

                        temp_trinary = np.array([np.nan])

                else: # size of window_signal is smaller than lag, can't perform transforming function

                    output = {}

                    output['m1_1'] = np.nan

                    temp_trinary = np.array([np.nan])
                    
                    status = 'Motion' # 'Active BAD'

                save_time.append(nonactive_time) # timestamp of each extraction


                """
                1. fft(temp_trinary)
                2. select maximum peak
                3. convert to BPM
                """

                temp_trinary = temp_trinary - np.mean(temp_trinary) # remove mean

                # SQA_output, ML_feature = calc_sqa(nonactive_time, window_signal, Percent_of_ones, temp_trinary, index_change)
                try:
                    SQA_output, ML_feature = calc_sqa(smooth_nonactive_time, 
                                                      smooth_window_signal, 
                                                      Percent_of_ones, 
                                                      temp_trinary, 
                                                      index_change, 
                                                      params,
                                                      trained_model,
                                                      **self.config)
                except Exception as e: #TODO:Than logs when it returns error
                    logging.error(f"error when running calc_sqa function. error message is {e}")
                    SQA_output = 0 # return bad sqa
                    ML_feature = 'nan'
                # print('The starting and ending time after smoothing: ', smooth_nonactive_time[0], smooth_nonactive_time[-1])
                # print('The SQA output is: ', SQA_output)


                """ calculate output value """

                freq_wo_bp, mag_wo_bp = run_fft(temp_trinary, 1/params['sampling_time'])

                freq_bp = freq_wo_bp[(freq_wo_bp>=bandpass[0])&(freq_wo_bp<=bandpass[1])].copy()
                mag_bp = mag_wo_bp[(freq_wo_bp>=bandpass[0])&(freq_wo_bp<=bandpass[1])].copy()

                # # normalize spectrum to maximum
                mag_bp = mag_bp/np.max(mag_bp)

                # find peak
                peaks, peak_properties = find_peaks(mag_bp)
                list_peak_freq = freq_bp[peaks]
                list_peak_mag = mag_bp[peaks]

                idx_max_peak = np.where(mag_bp==np.max(mag_bp))

                selected_mag = mag_bp[idx_max_peak]
                selected_freq = freq_bp[idx_max_peak]

                """ convert to BPM """
                temp_bpm = []
                temp_bpm = 60*selected_freq
                save_bpm = np.append(save_bpm, temp_bpm)

                temp_bpm_round = [] # rounding the number
                if np.isnan(temp_bpm) or len(temp_bpm)==0:
                    temp_bpm_round = np.nan
                else:
                    if temp_bpm%1>=0.5:
                        temp_bpm_round = np.ceil(temp_bpm)
                    else:
                        temp_bpm_round = np.floor(temp_bpm)
                save_bpm_round = np.append(save_bpm_round, temp_bpm_round)


                if SQA_output == 2:
                    status = 'Good'
                    n_window+=1
                elif SQA_output == 1:
                    status = 'Moderate'
                elif SQA_output == 0:
                    status = 'Poor'
                else:
                    status = 'Unknown'

                    if not self.bool_output_rr_regardless_sqa:
                        save_time = '--'
                        save_bpm_round = '--'

            list_bpm_round = np.append(list_bpm_round, temp_bpm_round)
            # list_status.append(status)
            list_status = np.append(list_status, status)


        if len(list_bpm_round)==0 and len(list_status)==0: # data length is shorter than window_size
            save_time = np.nan
            output_bpm = np.nan
            output_bpm_sd = str(np.nan)
            output_status = str(np.nan)
            ML_feature = np.nan
        else:
            """ remove Poor and Motion BPM """

            list_check_status = [
                ['Good', 'Moderate'],
                ['Poor'],
                ['Motion']
                ] # check and filter status in order

            output_status = str(np.nan)

            for check_status in list_check_status:
                # print(check_status)
                idx_keep, idx_remove = self.find_index_in_list(list_status, check_status)
                
                list_bpm_round_keep = list_bpm_round[idx_keep]
                list_status_keep = list(list_status[idx_keep])
                list_status_remove = list(list_status[idx_remove])

                """ avearge BPM """
                output_bpm = np.mean(list_bpm_round_keep)
                output_bpm_sd = np.std(list_bpm_round_keep)
            
                """ find mode of the status """
                # if len(list_status_keep)==0:
                #     output_status = max(list_status_remove, key=list_status_remove.count)
                # else:
                #     output_status = max(list_status_keep, key=list_status_keep.count)
                
                # print(list_bpm_round_keep)
                # print(list_status_keep)

                if len(list_status_keep) != 0:
                    output_status = max(list_status_keep, key=list_status_keep.count)
                    break

        # keep output the same format
        output_bpm = np.array([output_bpm])
        # output_status = [output_status]
        if type(save_time) is not list:
            save_time = [save_time]

        # return save_time, save_bpm_round, status, ML_feature
        return save_time, output_bpm, output_status, ML_feature, output_bpm_sd, list_bpm_round, list_status
    
    def find_index_in_list(self, list_item, list_to_find):
        idx_in = [] # indices item in the searching list
        idx_out = [] # indices item NOT in the searching list
        for j, elem in enumerate(list_item):
            if elem not in list_to_find:
                idx_out.append(j)
            else:
                idx_in.append(j)
        return idx_in, idx_out
