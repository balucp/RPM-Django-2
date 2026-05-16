import numpy as np
import pandas as pd
import math
import scipy.fftpack
import datetime as datetime
from sklearn.metrics import roc_auc_score



class SignalProcessing():
    """
    Class signal_processing performs preprocessing including filtering and artifact removal

    input: Xin
        Xin[:,0] = timestamp
        Xin[:,1] = sensor value

    input: params
        params = {
        'window_mva': ...,
        'window_bl': ...,
        'window_art_mva': ...,
        'window_art_bl': ...,
        'window_smooth_output': ...,
        'th_prepro': ...
        }            
    """

    def __init__(self, Xin=None, params=None):
        if Xin is not None:
            self.time = Xin[:, 0].reshape(-1)
            self.val = Xin[:, 1].reshape(-1)

        if params is not None:
            self.window_mva = params["window_mva"]
            self.window_mva_activeness = params['window_mva_activeness']
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

    # Baseline removal followed by zero padding front and back
    """
    def baseline_removal(self, signal_time, signal_val, baseline_time, baseline_val):
        signal_time = list(signal_time)
        baseline_time = list(baseline_time)
        blrm_val = signal_val[signal_time.index(baseline_time[0]):signal_time.index(baseline_time[-1])+1] - baseline_val
        output1 = np.pad(blrm_val, (555, 555), 'constant', constant_values=0)  # 0 padding for KT, padding
                                                                               # 720 for data length of 40s to get
                                                                               # exactly 1 result and no need to take median
                                                                               # 555 for data length of 60s
        blrm_val = output1
        time_end = max(baseline_time)
        time_ramp = baseline_time[-1] - baseline_time[-2]
        for i in range(2000):
            append_val = time_end + (i + 1) * time_ramp
            baseline_time = np.append(baseline_time, append_val)   # 0 padding for RR calculation
        return baseline_time, blrm_val

    """
    # Normal baseline removal

    def baseline_removal(self, signal_time, signal_val, baseline_time, baseline_val):
        signal_time = list(signal_time)
        baseline_time = list(baseline_time)
        blrm_val = signal_val[signal_time.index(baseline_time[0]):signal_time.index(
            baseline_time[-1]) + 1] - baseline_val
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
        signal_val = signal_val[signal_time.index(artbl_time[0]):signal_time.index(artbl_time[-1])+1]
        art_val = art_val[art_time.index(artbl_time[0]):art_time.index(artbl_time[-1])+1]

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

    def run_signal_processing_for_activity(self):
        self.mva_time,  self.mva_val = self.moving_average(self.time, self.val, self.window_mva_activeness)
        self.art_time,   self.art_val = self.artifact(self.mva_time, self.mva_val, self.window_art_mva)


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
        blrm_val = signal_val[signal_time.index(baseline_time[0]):signal_time.index(baseline_time[-1])+1] - baseline_val
        return baseline_time, blrm_val

    # Baseline removal followed by zero padding front and back
    def baseline_removal_w_zero_padding(self, signal_time, signal_val, baseline_time, baseline_val):
        signal_time = list(signal_time)
        baseline_time = list(baseline_time)
        blrm_val = signal_val[signal_time.index(baseline_time[0]):signal_time.index(baseline_time[-1])+1] - baseline_val
        output1 = np.pad(blrm_val, (555, 555), 'constant', constant_values=0)  # 0 padding for KT, padding
        # 720 for data length of 40s to get
        # exactly 1 result and no need to take median
        # 555 for data length of 60s
        blrm_val = output1
        time_end = max(baseline_time)
        time_ramp = baseline_time[-1] - baseline_time[-2]
        for i in range(2000):
            append_val = time_end + (i + 1) * time_ramp
            baseline_time = np.append(baseline_time, append_val)   # 0 padding for RR calculation
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

        signal_val = signal_val[signal_time.index(artbl_time[0]):signal_time.index(artbl_time[-1])+1]
        art_val = art_val[art_time.index(artbl_time[0]):art_time.index(artbl_time[-1])+1]

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
        self.mva_time,  self.mva_val = self.moving_average(self.time, self.val, self.window_mva)
        self.bl_time,   self.bl_val = self.baseline(self.mva_time, self.mva_val, self.window_bl)
        self.blrm_time, self.blrm_val = self.baseline_removal_w_zero_padding(
            self.mva_time, self.mva_val, self.bl_time, self.bl_val)
        self.art_time,   self.art_val = self.artifact(self.blrm_time, self.blrm_val, self.window_art_mva)
        self.artbl_time, self.artbl_val = self.baseline(self.art_time, self.art_val, self.window_art_bl)

    def run_signal_processing_activity(self):
        """
        perform signal processing
        """
        self.mva_time,  self.mva_val = self.moving_average(self.time, self.val, self.window_mva)
        self.art_time,   self.art_val = self.artifact(
            self.mva_time, self.mva_val, self.window_art_mva)  # baseline not removed in this algorithm

    def remove_baseline(self):
        self.mva_time,  self.mva_val = self.moving_average(self.time, self.val, self.window_mva)
        self.bl_time,   self.bl_val = self.baseline(self.mva_time, self.mva_val, self.window_bl)
        self.blrm_time, self.blrm_val = self.baseline_removal(self.mva_time, self.mva_val, self.bl_time, self.bl_val)

    def motion_removal2(self, signal, nonactive_time):
        signal_time = list(signal[:, 0])
        signal_val = list(signal[:, 1])
        signal = pd.DataFrame(signal, columns=['timestamp', 'signal'])
        signal['timestamp'].astype(int)
        signal = signal.set_index('timestamp')
        nonactive_time = list(nonactive_time)
        nonactive_time = [int(x) for x in nonactive_time]
        nonactive_time_filter1 = list(filter(lambda time: time >= signal_time[0], nonactive_time))
        nonactive_time_filter2 = list(filter(lambda time: time <= signal_time[-1], nonactive_time_filter1))
        # nonactive_signal = signal.iloc[nonactive_time]
        nonactive_signal = signal.loc[nonactive_time_filter2]
        nonactive_signal = list(nonactive_signal['signal'])
        return nonactive_time_filter2, nonactive_signal



def moving_average(time, val, window_size):
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


def define_params_tdomain():
    params = {
        'sampling_time': 0.06,
        'window_mva': 15,
        'window_mva_activeness': 25,
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
        'window_size': 1083,
        'window_shift': 16*1,
        'threshold_x_01': 300,
        'threshold_y_01': 310,
        'threshold_z_01': 1060,
        'threshold_x_12': 1700,
        'threshold_y_12': 2400,
        'threshold_z_12': 1600
    }
    return params


def run_fft(Xin, fs, n_fft=2**12):
    Xin = Xin*np.hanning(len(Xin))  # Reduce energy leakage effect when fft is applied on discrete signal
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


def calculate_activeness(xaccl, yaccl, zaccl, params):
    Xinput, Yinput, Zinput = np.array([np.arange(len(xaccl)), xaccl]).T, np.array(
        [np.arange(len(yaccl)), yaccl]).T, np.array([np.arange(len(zaccl)), zaccl]).T
    threshold_x_01, threshold_y_01, threshold_z_01 = params['threshold_x_01'], params['threshold_y_01'], params['threshold_z_01']
    threshold_x_12, threshold_y_12, threshold_z_12 = params['threshold_x_12'], params['threshold_y_12'], params['threshold_z_12']
    cls_sp_x = SignalProcessing(Xinput, params)
    cls_sp_y = SignalProcessing(Yinput, params)
    cls_sp_z = SignalProcessing(Zinput, params)
    cls_sp_x.run_signal_processing_for_activity()
    cls_sp_y.run_signal_processing_for_activity()
    cls_sp_z.run_signal_processing_for_activity()
    activeness, t_activeness = np.zeros(len(cls_sp_x.art_val)), []
    for i in range(0, len(cls_sp_x.art_val)):
        window_sum_x = cls_sp_x.art_val[i]
        window_sum_y = cls_sp_y.art_val[i]
        window_sum_z = cls_sp_z.art_val[i]
        if ((window_sum_x > threshold_x_01 and window_sum_y > threshold_y_01) or (window_sum_x > threshold_x_01 and window_sum_z > threshold_z_01) or (window_sum_y > threshold_y_01 and window_sum_z > threshold_z_01)):
            activeness[i] = 1
        if ((window_sum_x > threshold_x_12 and window_sum_y > threshold_y_12) or (window_sum_x > threshold_x_12 and window_sum_z > threshold_z_12) or (window_sum_y > threshold_y_12 and window_sum_z > threshold_z_12)):
            activeness[i] = 2
        t_activeness = np.append(t_activeness, cls_sp_x.art_time[i])
    return t_activeness, activeness


def calc_metrics(true_label, y_pred):
    tp, fp, tn, fn = 0, 0, 0, 0
    for i in range(len(true_label)):
        if true_label[i] == 1:
            if y_pred[i] == 1:
                tp = tp + 1
            else:
                fn = fn + 1
        else:
            if y_pred[i] == 0:
                tn = tn + 1
            else:
                fp = fp + 1
    accuracy = (tp+tn)/(tp+tn+fp+fn)
    try:
        sensitivity = tp/(tp+fn)
    except:
        sensitivity = 1
    try:
        specificity = tn/(tn+fp)
    except:
        specificity = 1
    try:
        precision = tp/(tp+fp)
    except:
        precision = 1
    try:
        roc = roc_auc_score(true_label, y_pred)
    except:
        roc = 1
    return accuracy, precision, specificity, sensitivity, roc
