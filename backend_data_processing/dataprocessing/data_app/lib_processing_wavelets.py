
import pandas as pd
import numpy as np
import math

# import myLib_FrequencyDomain_Analysis as mlb_freq
import logging
import pywt

from . import processing

#%%


class calculate_bpm_using_dwt():

    def __init__(self, read_data, params):
    # def __init__(self, input_params=None, prepro_object=None, time_manual_count=None, cal_freqDomain=True, cal_CWT=True, cal_timeDomain=True):
        
        self.data = read_data

        self.sampling_time = params["sampling_time"]

        # self.window_length = params["window_length"]
        # self.window_shift = params["window_shift"]
        
        # self.th_motion = params["th_motion"]
        # self.window_smooth_output = params["window_smooth_output"]



        # self.filter_size = params["filter_size"]

        # self.cwt_bandpass = params["cwt_bandpass"]
        # self.cwt_function = params["cwt_function"]
        # self.cwt_bins = params["cwt_bins"]
        # self.cwt_scale = np.arange(params["cwt_scale"][0], params["cwt_scale"][1]) #params["cwt_scale"]
        # self.select_nth_peak_algo = params["select_nth_peak_algo"]
        # self.th_scaling = params["th_scaling"]

        self.filter_size = params["filter_size"]

        self.cwt_bandpass = params["cwt_bandpass"]
        self.cwt_function = params["cwt_function"]
        self.cwt_bins = params["cwt_bins"]
        self.cwt_scale = np.arange(params["cwt_scale"][0], params["cwt_scale"][1]) #params["cwt_scale"]
        self.select_nth_peak_algo = params["select_nth_peak_algo"]
        self.th_scaling = params["th_scaling"]


        self.params = params


        
        
        self.output_feature = {}
        self.output_feature["time"] = []
        
        self.output_feature["median_maxPeak"] = []
        self.output_feature["median_nthPeak"] = []
        self.output_feature["median_medianFiltMax"] = []
        self.output_feature["median_peakMean"] = []
        self.output_feature["median_meanMax"] = []
        self.output_feature["median_meanFiltMax"] = []

        self.output_feature["mean_maxPeak"] = []
        self.output_feature["mean_nthPeak"] = []
        self.output_feature["mean_medianFiltMax"] = []
        self.output_feature["mean_peakMean"] = []
        self.output_feature["mean_meanMax"] = []
        self.output_feature["mean_meanFiltMax"] = []

        self.output_feature["maxPeak mean + median"] = []
        self.output_feature["nthPeak mean + median"] = []
        self.output_feature["medianFiltMax mean + median"] = []
        self.output_feature["peakMean mean + median"] = []
        self.output_feature["meanMax mean + median"] = []
        self.output_feature["meanFiltMax mean + median"] = []

        self.output_feature["mean of all median"] = []
        self.output_feature["mean of all mean"] = []

        self.output_feature["cwt_time"] = []




        self.temp_outputCWT = {}

        self.temp_outputCWT["bpm_maxPeak"] = []
        self.temp_outputCWT["bpm_nthPeak"] = []
        self.temp_outputCWT["bpm_meanFiltMax"] = []
        self.temp_outputCWT["bpm_meanMax"] = []
        self.temp_outputCWT["bpm_medianFiltMax"] = []
        self.temp_outputCWT["bpm_peakMean"] = []

        self.temp_outputCWT["bpm_time"] = []



        self.temp_outputCWT["median_maxPeak"] = []
        self.temp_outputCWT["median_nthPeak"] = []
        self.temp_outputCWT["median_meanFiltMax"] = []
        self.temp_outputCWT["median_meanMax"] = []
        self.temp_outputCWT["median_medianFiltMax"] = []
        self.temp_outputCWT["median_peakMean"] = []
        self.temp_outputCWT["median_time"] = []

        self.temp_outputCWT["mean_maxPeak"] = []
        self.temp_outputCWT["mean_nthPeak"] = []
        self.temp_outputCWT["mean_meanFiltMax"] = []
        self.temp_outputCWT["mean_meanMax"] = []
        self.temp_outputCWT["mean_medianFiltMax"] = []
        self.temp_outputCWT["mean_peakMean"] = []
        self.temp_outputCWT["mean_time"] = []

        self.temp_outputCWT["maxPeak mean + median"] = []
        self.temp_outputCWT["nthPeak mean + median"] = []
        self.temp_outputCWT["medianFiltMax mean + median"] = []
        self.temp_outputCWT["peakMean mean + median"] = []
        self.temp_outputCWT["meanMax mean + median"] = []
        self.temp_outputCWT["meanFiltMax mean + median"] = []

        self.temp_outputCWT["mean of all median"] = []
        self.temp_outputCWT["mean of all mean"] = []

        self.temp_outputCWT["filtTime"] = []
        


        
    

    def my_CropSignal(self, mva_time, mva_val, blrm_time, blrm_val, ks_time, ks_val, ksbl_time, ksbl_val):
        """
        return [time, signal]
        """
        mva_time = list(mva_time)
        blrm_time = list(blrm_time)
        ks_time = list(ks_time)
        ksbl_time = list(ksbl_time)
        
        index_mva = [mva_time.index(ksbl_time[0]), mva_time.index(ksbl_time[-1])]
        index_blrm = [blrm_time.index(ksbl_time[0]), blrm_time.index(ksbl_time[-1])]
        index_ks = [ks_time.index(ksbl_time[0]), ks_time.index(ksbl_time[-1])] 
        
        mva = np.array([mva_time[index_mva[0]:index_mva[1]+1], mva_val[index_mva[0]:index_mva[1]+1]]).T
        signal = np.array([blrm_time[index_blrm[0]:index_blrm[1]+1], blrm_val[index_blrm[0]:index_blrm[1]+1]]).T
        ks = np.array([ks_time[index_ks[0]:index_ks[1]+1], ks_val[index_ks[0]:index_ks[1]+1]]).T
        ksbl = np.array([ksbl_time, ksbl_val]).T
        
        return signal, ks, ksbl, mva

    


    def filter_coef(self, input_coef, input_freqs, input_bandpass):
        filt_mask = np.zeros(len(input_freqs))
        filt_mask[input_freqs<=input_bandpass[1]] = 1
        filt_mask[input_freqs<=input_bandpass[0]] = 0
        
        filt_coef = np.zeros(input_coef.shape) #run the filter mask
        for j in range(input_coef.shape[1]):
            filt_coef[:,j] = input_coef[:,j]*filt_mask
        return filt_coef
        
        
        
    def filter_and_argmax(self, input_coef, input_freqs, input_bandpass):
        filt_coef = self.filter_coef(input_coef, input_freqs, input_bandpass)

        len_time = input_coef.shape[1]
        coef_max = np.zeros(len_time) #extract intensity
        for w in range(len_time):
            index_max = []
            index_max = filt_coef[:,w].argmax()
            coef_max[w] = input_freqs[index_max]
        return coef_max


        
    
    

    def filtered_histogram(self, input_coef, cal_bins="mean", bins=300, th_scaling=1.00):    
        hist_val, temp_hist_freq = np.histogram(input_coef, bins=bins)   
    
        if cal_bins=="mean":
            hist_freq = np.array([np.mean(temp_hist_freq[q-1:q+1]) for q in range(1, len(temp_hist_freq))])
        elif cal_bins=="min":
            hist_freq = np.array([np.min(temp_hist_freq[q-1:q+1]) for q in range(1, len(temp_hist_freq))])
        elif cal_bins=="max":
            hist_freq = np.array([np.max(temp_hist_freq[q-1:q+1]) for q in range(1, len(temp_hist_freq))])
        else:
            logging.error("Error: parameter cal_bins is invalid")
            
        val_for_threshold = hist_val.copy()[1:-1] # exclude first and last due to filtering their histogram are large
        mean_hist = np.mean(val_for_threshold[val_for_threshold!=0])
        
        stack_hist = np.vstack([hist_val, hist_freq]).T
        filt_hist = []
        for q in range(stack_hist.shape[0]):
            if stack_hist[q,0]>=mean_hist*th_scaling:
                filt_hist = np.append(filt_hist, stack_hist[q,:])
                
        if len(filt_hist)==0:
            filt_hist = [None, None]
        else:
            filt_hist = filt_hist.reshape(-1,2)
             
        return filt_hist, mean_hist






    def median_filter(self, Xinput, Tinput, filterSize):
        output_val = []
        output_time = []
        
        if filterSize>1:
            for q in range(filterSize, len(Tinput)):
                temp_window = []
                temp_window = Xinput[q-filterSize: q]
                
                output_val = np.append(output_val, np.median(temp_window))
                output_time = np.append(output_time, Tinput[q])
        else:
            output_val = Xinput.copy()
            output_time = Tinput.copy()
        return output_val, output_time


    def mean_filter(self, Xinput, Tinput, filterSize):
        output_val = []
        output_time = []
        
        if filterSize>1:
            for q in range(filterSize, len(Tinput)):
                temp_window = []
                temp_window = Xinput[q-filterSize: q]
                
                output_val = np.append(output_val, np.mean(temp_window))
                output_time = np.append(output_time, Tinput[q])
        else:
            output_val = Xinput.copy()
            output_time = Tinput.copy()    
        return output_val, output_time



    # def diff_hist(self, xin):    
    #     output = []
        
    #     diff_mag = xin[0:-1,0]-xin[1:,0]       
    #     diff_mag = np.append(diff_mag, 1)

    #     for k in range(1,len(diff_mag)):
    #         if (diff_mag[k-1]<=0) and (diff_mag[k]>0):
    #             output = np.append(output, xin[k,:])

    #     if len(output)==0:
    #         output = xin[len(xin)-1,:].reshape(-1,2)
    #     else:
    #         output = output.reshape(-1,2)

    #     return output


    def diff_hist_and_find_peak(self, xin):    
        output = []        
        diff_mag = xin[0:-1,0]-xin[1:,0]    
        diff_mag = np.append(diff_mag, 1)
        
        for k in range(1,len(diff_mag)):
            if (diff_mag[k-1]<=0) and (diff_mag[k]>0):
                output = np.append(output, xin[k,:])
               
#            if len(output)==0:
#                output = xin[len(xin)-1,:].reshape(-1,2)
#            else:
#                output = output.reshape(-1,2)
        
        
        if len(output)==0:
#                output = xin[len(xin)-1,:]
            if xin.shape[0]<=1:
                output = xin
            elif xin.shape[0]==2:
                output = xin[1,:]
            else:
                count = 0
                sumVal = 0
                for xi in range(1, xin.shape[0]):
                    count+=xin[xi,0]
                    sumVal = sumVal + (xin[xi,0]*xin[xi,1])
                sumVal = sumVal/count
                
                difference = []
                difference = abs(xin[:,1]-sumVal)
                for xi in range(len(difference)):
                    if difference[xi]==np.min(difference):
    #                        idxmin = xi
                        if xin[xi,1]-sumVal<0:
                            output = np.array([(xin[xi,0]+xin[xi-1,0])/2, (xin[xi,1]+xin[xi-1,1])/2])
                        elif xin[xi,1]-sumVal>0:
                            output = np.array([(xin[xi,0]+xin[xi+1,0])/2, (xin[xi,1]+xin[xi+1,1])/2])
                        elif xin[xi,1]-sumVal==0:
                            output = np.array([xin[xi,0], xin[xi,1]])
                        break   
            
        output = output.reshape(-1,2)

        return output


    
    
    
    def algo_max_peak(self, xin):
        max_val = np.max(xin[:,0])
        corr_freq = []
        for num in range(xin.shape[0]):
            if xin[num,0]==max_val:
                corr_freq = np.append(corr_freq, xin[num,1])
                
        max_freq = np.max(corr_freq)

        output = xin[xin[:,1]==max_freq,:].reshape(-1)

        return output#[1]
    
    
    
    def algo_median_peak(self, xin):
        med_val = np.median(xin[:,0])
        diff=[]
        for p in range(xin.shape[0]):
            diff.append(abs(med_val-xin[p,0]))
        diff = np.array(diff)
        for p in range(xin.shape[0]):
            if diff[p]==np.min(diff):
                med_val = xin[p,0]
        
        corr_freq = []
        for num in range(xin.shape[0]):
            if xin[num,0]==med_val:
                corr_freq = np.append(corr_freq, xin[num,1])
        
        selected_freq = np.median(corr_freq)
        output = np.array([med_val, selected_freq])
        return output 



    def algo_nth_peak(self, xin, nth):
        try:
            output = xin[nth-1,:]
        except:
            output = xin[-1,:]
        return output#[1]



    def algo_avg_then_max_and_peak(self, input_coef, input_freqs, input_bandpass):
        filt_coef = self.filter_coef(input_coef, input_freqs, input_bandpass)
        
        avg_mag = np.mean(filt_coef, axis=1)
        max_mag = np.max(avg_mag)
        
        for m in range(len(avg_mag)):
            if avg_mag[m]==max_mag:
                max_freq = input_freqs[m]
#                    break

        xfilt = avg_mag[avg_mag!=0]
        ffilt = input_freqs[avg_mag!=0]
        
        
        detpeak =  self.peakdet((xfilt-np.min(xfilt))/(np.max(xfilt)-np.min(xfilt)), 0.01)[0]
        if len(detpeak)==0:
            detpeak = np.array([[0,0]])
     
        idx = int(detpeak[0][0])
        peak_mag = xfilt[idx]
        peak_freq = ffilt[idx]
        
        
        return [max_mag, max_freq], [peak_mag, peak_freq], avg_mag




    def peakdet(self, v, delta, x = None):
        import sys
        maxtab = []
        mintab = []
           
        if x is None:
            x = np.arange(len(v))
        
        v = np.asarray(v)
        
        if len(v) != len(x):
            sys.exit('Input vectors v and x must have same length')
        
        if not np.isscalar(delta):
            sys.exit('Input argument delta must be a scalar')
        
        if delta <= 0:
            sys.exit('Input argument delta must be positive')
        
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



    


    def map_input_data(self, blrm_val, blrm_time, art_val, art_time, artbl_val, artbl_time):
        blrm_time = list(blrm_time)
        art_time = list(art_time)
        artbl_time = list(artbl_time)
        
        index_blrm = [blrm_time.index(artbl_time[0]), blrm_time.index(artbl_time[-1])]
        index_ks = [art_time.index(artbl_time[0]), art_time.index(artbl_time[-1])]
        
        signal = np.array([blrm_time[index_blrm[0]:index_blrm[1]+1], blrm_val[index_blrm[0]:index_blrm[1]+1]]).T
        art = np.array([art_time[index_ks[0]:index_ks[1]+1], art_val[index_ks[0]:index_ks[1]+1]]).T
        artbl = np.array([artbl_time, artbl_val]).T

        return signal, art, artbl
    


    def run_calculation_wt(self):
        

        
        

        readData = self.data
        params = self.params

        windowSize = self.params['window_mva']+self.params['window_bl']-1+3-1+self.params['window_art_mva']-1+self.params['window_art_bl']-1+self.params['window_size']-1 #params['window_size']
        windowShift = self.params['window_shift']


        
        
        

        outputBPM = []
        outputTime = []

        for i in range(0, len(readData)-windowSize-1, windowShift):

            windowReadData = readData[i:i+windowSize, :]

            outputTime = np.append(outputTime, windowReadData[-1,0])

            clsPrepro = processing.signal_processing(windowReadData, params) # input to signal processing
            clsPrepro.run_signal_processing() # perform signal processing

            Xsignal, Xart, Xartbl = self.map_input_data( clsPrepro.blrm_val, clsPrepro.blrm_time,
                                                clsPrepro.art_val, clsPrepro.art_time,
                                                clsPrepro.artbl_val, clsPrepro.artbl_time)


            windowSignal = clsPrepro.artifact_removal(  Xsignal[:, 0], Xsignal[:, 1],
                                                        Xart[:, 0], Xart[:, 1],
                                                        Xartbl[:, 0], Xartbl[:, 1],
                                                        params['th_prepro'], params['window_smooth_output'], 
                                                        mva_filt=True) # remove artifact and apply mva to smoothen signal


            coef, freqs = pywt.cwt(windowSignal, self.cwt_scale, self.cwt_function, self.sampling_time)
            coef = abs(coef)

            coef_max = self.filter_and_argmax(coef, freqs, self.cwt_bandpass)

            
            
            filt_coefMax, temp_mean = self.filtered_histogram(coef_max, cal_bins="mean", bins=self.cwt_bins, th_scaling=self.th_scaling)


            hist_diff = []
            hist_diff = self.diff_hist_and_find_peak(filt_coefMax)
            


            freq_maxPeak = []
            freq_maxPeak = self.algo_max_peak(hist_diff)
            
            freq_nthPeak = []
            freq_nthPeak = self.algo_nth_peak(hist_diff, self.select_nth_peak_algo)


            freq_meanFiltMax = []
            if len(filt_coefMax)==1:
                freq_meanFiltMax = filt_coefMax[0][1]
            else:
                freq_meanFiltMax = np.mean(filt_coefMax[1:,1])

            
            temp_val = []
            temp_val = coef_max[coef_max!=np.min(coef_max)]
            temp_val = temp_val[temp_val!=np.max(coef_max)]
            freq_meanMax = []
            freq_meanMax = np.mean(temp_val)
            


            freq_medianFiltMax = []
            freq_medianFiltMax = self.algo_median_peak(filt_coefMax)
            

            

            freq_peakMean = []
            _, freq_peakMean, avg_filt = self.algo_avg_then_max_and_peak(coef, freqs, self.cwt_bandpass)



            self.temp_outputCWT["bpm_maxPeak"] = np.append(self.temp_outputCWT["bpm_maxPeak"], freq_maxPeak[1]*60)
            self.temp_outputCWT["bpm_nthPeak"] = np.append(self.temp_outputCWT["bpm_nthPeak"], freq_nthPeak[1]*60)
            self.temp_outputCWT["bpm_medianFiltMax"] = np.append(self.temp_outputCWT["bpm_medianFiltMax"], freq_medianFiltMax[1]*60)
            self.temp_outputCWT["bpm_peakMean"] = np.append(self.temp_outputCWT["bpm_peakMean"], freq_peakMean[1]*60)
            self.temp_outputCWT["bpm_meanMax"] = np.append(self.temp_outputCWT["bpm_meanMax"], freq_meanMax*60)
            self.temp_outputCWT["bpm_meanFiltMax"] = np.append(self.temp_outputCWT["bpm_meanFiltMax"], freq_meanFiltMax*60)

            
            self.temp_outputCWT["bpm_time"] = np.append(self.temp_outputCWT["bpm_time"], outputTime[-1])

    

        self.temp_outputCWT["median_maxPeak"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_maxPeak"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["median_nthPeak"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_nthPeak"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["median_meanFiltMax"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_meanFiltMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["median_meanMax"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_meanMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["median_medianFiltMax"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_medianFiltMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["median_peakMean"], self.temp_outputCWT["filtTime"]  = self.median_filter(self.temp_outputCWT["bpm_peakMean"], self.temp_outputCWT["bpm_time"], self.filter_size)
        

        self.temp_outputCWT["mean_maxPeak"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_maxPeak"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["mean_nthPeak"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_nthPeak"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["mean_meanFiltMax"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_meanFiltMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["mean_meanMax"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_meanMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["mean_medianFiltMax"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_medianFiltMax"], self.temp_outputCWT["bpm_time"], self.filter_size)
        self.temp_outputCWT["mean_peakMean"], self.temp_outputCWT["filtTime"]  = self.mean_filter(self.temp_outputCWT["bpm_peakMean"], self.temp_outputCWT["bpm_time"], self.filter_size)
        

         


        for w in range(len(self.temp_outputCWT["filtTime"])):
            # if self.temp_outputCWT["filtTime"][w] in val_t:
            self.output_feature["median_maxPeak"] = np.append(self.output_feature["median_maxPeak"], self.temp_outputCWT["median_maxPeak"][w])
            self.output_feature["median_nthPeak"] = np.append(self.output_feature["median_nthPeak"], self.temp_outputCWT["median_nthPeak"][w])
            self.output_feature["median_medianFiltMax"] = np.append(self.output_feature["median_medianFiltMax"], self.temp_outputCWT["median_medianFiltMax"][w])
            self.output_feature["median_peakMean"] = np.append(self.output_feature["median_peakMean"], self.temp_outputCWT["median_peakMean"][w])
            self.output_feature["median_meanMax"] = np.append(self.output_feature["median_meanMax"], self.temp_outputCWT["median_meanMax"][w])
            self.output_feature["median_meanFiltMax"] = np.append(self.output_feature["median_meanFiltMax"], self.temp_outputCWT["median_meanFiltMax"][w])

            self.output_feature["mean_maxPeak"] = np.append(self.output_feature["mean_maxPeak"], self.temp_outputCWT["mean_maxPeak"][w])
            self.output_feature["mean_nthPeak"] = np.append(self.output_feature["mean_nthPeak"], self.temp_outputCWT["mean_nthPeak"][w])
            self.output_feature["mean_medianFiltMax"] = np.append(self.output_feature["mean_medianFiltMax"], self.temp_outputCWT["mean_medianFiltMax"][w])
            self.output_feature["mean_peakMean"] = np.append(self.output_feature["mean_peakMean"], self.temp_outputCWT["mean_peakMean"][w])
            self.output_feature["mean_meanMax"] = np.append(self.output_feature["mean_meanMax"], self.temp_outputCWT["mean_meanMax"][w])
            self.output_feature["mean_meanFiltMax"] = np.append(self.output_feature["mean_meanFiltMax"], self.temp_outputCWT["mean_meanFiltMax"][w])

            self.output_feature["cwt_time"] = np.append(self.output_feature["cwt_time"], self.temp_outputCWT["filtTime"][w])
        


        # self.output_feature["bpm_avg_max_and_nth"] = np.mean([self.output_feature["bpm_max_peak_algo"], self.output_feature["bpm_nth_peak_algo"]], axis=0)

        self.output_feature["maxPeak mean + median"] = np.mean([self.output_feature["median_maxPeak"], self.output_feature["mean_maxPeak"]], axis=0)
        self.output_feature["nthPeak mean + median"] = np.mean([self.output_feature["median_nthPeak"], self.output_feature["mean_nthPeak"]], axis=0)
        self.output_feature["medianFiltMax mean + median"] = np.mean([self.output_feature["median_medianFiltMax"], self.output_feature["mean_medianFiltMax"]], axis=0)
        self.output_feature["peakMean mean + median"] = np.mean([self.output_feature["median_peakMean"], self.output_feature["mean_peakMean"]], axis=0)
        self.output_feature["meanMax mean + median"] = np.mean([self.output_feature["median_meanMax"], self.output_feature["mean_meanMax"]], axis=0)
        self.output_feature["meanFiltMax mean + median"] = np.mean([self.output_feature["median_meanFiltMax"], self.output_feature["mean_meanFiltMax"]], axis=0)

        self.output_feature["mean of all median"] = np.mean([self.output_feature["median_maxPeak"], 
                                                            self.output_feature["median_nthPeak"],
                                                            self.output_feature["median_medianFiltMax"],
                                                            self.output_feature["median_peakMean"],
                                                            self.output_feature["median_meanMax"],
                                                            self.output_feature["median_meanFiltMax"]], axis=0)

        self.output_feature["mean of all mean"] = np.mean([self.output_feature["mean_maxPeak"], 
                                                            self.output_feature["mean_nthPeak"],
                                                            self.output_feature["mean_medianFiltMax"],
                                                            self.output_feature["mean_peakMean"],
                                                            self.output_feature["mean_meanMax"],
                                                            self.output_feature["mean_meanFiltMax"]], axis=0)


