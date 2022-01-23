import pandas as pd
import numpy as np
import os
from astropy.timeseries import LombScargle
import matplotlib.pyplot as plt
import sqlalchemy


def _arc_to_deg(arc, unit):
    """
    Convert arc minutes or seconds to decimal degree units

    :param arc: length of arc, float or np array
    :param unit: 'arcmin' or 'arcsec'
    :return: decimal degrees
    """
    if unit == 'arcmin':
        return arc / 60
    elif unit == 'arcsec':
        return arc / 3600
    else:
        raise ValueError("unit not in ['arcmin', 'arcsec']")


def _block_arr(arr, size):
    return [arr[i:i + size] for i in range(0, len(arr), size)]


def _query_sql_quality(img_ids):
    # Get engine
    engine = sqlalchemy.create_engine("mysql+pymysql://bad_client:a5a55N_CLIENT@rainier.ifa.hawaii.edu/exposures")
    # Create query
    id_str = ', '.join(f'"{i}"' for i in img_ids)
    query = f"SELECT filename AS image_id, goodimg AS quality FROM reduced WHERE filename IN ({id_str})"
    # Query engine
    df = pd.read_sql(query, engine)
    # Remap values
    quality_map = {1: "G", 0: "B"}
    df['image_id'] = df['image_id'].str.decode("utf-8")
    df["quality"].replace(quality_map, inplace=True)
    return df

class LightCurveCollection(object):
    """
    Object for storing and analysing ASAS-SN Sky Patrol light curves.
    Returned by any SkyPatrolClient query where download=True
    """

    def __init__(self, data, catalog_info, id_col):

        self.id_col = id_col
        self.data = data
        self.catalog_info = catalog_info

    def apply_function(self, func, col='mag', include_non_det=False, include_poor_images=False):
        """
        Apply a custom aggregate function to all light curves in the collection.

        :param func: custom aggregate function
        :param col: column to apply aggregate function; defaluts to 'mag'
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :param include_poor_images whether or not to include images of poor or unknown quality; defaults to False
        :return: pandas Dataframe with results
        """

        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data['mag_err'] < 99]
        if not include_poor_images:
            data = data[data['quality'] == 'G']

        return data.groupby(self.id_col).agg({col: func})

    def stats(self, include_non_det=False, include_poor_images=False):
        """
        Calculate simple aggregate statistics on the collection.
        Gets the mean and stddev magnitude for each curve as well as the total number of epochs observed.

        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :return: pandas Dataframe with results
        """
        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data['mag_err'] < 99]
        if not include_poor_images:
            data = data[data['quality'] == 'G']

        return data.groupby(self.id_col).agg(mean_mag=('mag', 'mean'),
                                             std_mag=('mag', 'std'),
                                             epochs=('mag', 'count'))
    def __getitem__(self, item):
        if type(item) == pd.Series or type(item) == list or type(item) == np.ndarray:
            data = self.data[self.data[self.id_col] in item]
            catalog_info = self.catalog_info[self.catalog_info[self.id_col] in item]
            return LightCurveCollection(data, catalog_info, self.id_col)

        else:
            return self.__get_lc(item)

    def __get_lc(self, key):
        source = self.catalog_info[self.id_col] == key
        meta = self.catalog_info[source]
        data = self.data[self.data[self.id_col] == key]
        return LightCurve(data, meta)


    def itercurves(self):
        """
        Generator to iterate through all light curves in the collection.

        :return: a generator that iterates over the collection
        """
        for key, data in self.data.groupby(self.id_col):
            source = self.catalog_info[self.id_col] == key
            meta = self.catalog_info[source]
            yield LightCurve(data, meta)

    def __len__(self):
        return len(self.catalog_info)

    def save(self, save_dir):
        """
        Saves entire light curve collection to a given directory.

        :param save_dir: directory name
        :return: void
        """
        self.catalog_info.to_csv(os.path.join(save_dir, "index.csv"), index=False)
        for lc in self.itercurves():
            lc.save(os.path.join(save_dir, f"{lc.meta[self.id_col].values[0]}.csv"))


class LightCurve:
    """
    Object for analysing and visualizing ASAS-SN Sky Patrol light curves.
    """
    def __init__(self, pandas_obj, meta):

        self._validate(pandas_obj)
        self.data = pandas_obj
        self.meta = meta
        self.epochs = len(pandas_obj)

    @staticmethod
    def _validate(obj):
        # verify there is a column latitude and a column longitude
        if 'jd' not in obj.columns or 'mag' not in obj.columns or 'mag_err' not in obj.columns:
            raise AttributeError("Must have 'jd'(julian date), 'mag' and 'mag_err'")


    def save(self, filename):
        """
        Save the light curve to csv.

        :param filename: filename to save this light curve.
        :return: void
        """
        with open(filename, "w+") as f:
            f.write(f"# {self.meta.to_json(orient='records')[2:-2]}\n")

        self.data.to_csv(filename, mode='a', index=False)

    def plot(self, figsize=(12,8), savefile=None, include_poor_images=False):
        """
        Plots the given light curve with error bars.

        :param figsize: size of the plot
        :param savefile: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :return: void
        """
        # Filter preferences
        data = self.data
        if not include_poor_images:
            data = data[data['quality'] == 'G']

        errors = data.mag_err > 99

        plt.figure(figsize=figsize)
        plt.errorbar(x=data[~errors].jd - 2450000,
                     y=data[~errors].mag,
                     yerr=data[~errors].mag_err,
                     fmt="o",
                     c="teal",
                     label="detections")
        plt.errorbar(x=data[errors].jd - 2450000,
                     y=data[errors].mag,
                     fmt="v",
                     c="red",
                     label="non-detections")
        self._label_plots()
        plt.legend()
        plt.xlabel("Date (JD-2450000)")
        plt.ylabel("Magnitude")
        plt.gca().invert_yaxis()


        if savefile:
            plt.savefig(savefile)
        else:
            plt.show()


    def lomb_scargle(self, fit_mean=True, center_data=True, nterms=1, normalization='standard',
                     minimum_frequency=0.001, maximum_frequency=25, method='auto', samples_per_peak=5,
                     nyquist_factor=5, plot=True, figsize=(12,8), savefile=None,
                     include_poor_images=False, include_non_det=False):
        """
        Thin wrapper around the astropy LombScargle utility to determine frequency and power spectra of the given
        light curve. Default values work for most variable sources.

        :param fit_mean: if True, include a constant offset as part of the model at each frequency. This can lead to more accurate results, especially in the case of incomplete phase coverage.
        :param center_data: if True, pre-center the data by subtracting the weighted mean of the input data. This is especially important if fit_mean = False
        :param nterms: number of terms to use in the Fourier fit
        :param normalization: Normalization to use for the periodogram.
        :param minimum_frequency: If specified, then use this minimum frequency rather than one chosen based on the size of the baseline.
        :param maximum_frequency: If specified, then use this maximum frequency rather than one chosen based on the average nyquist frequency.
        :param method: specify the lomb scargle implementation to use. Options are:

            -  ‘auto’: choose the best method based on the input

            -  ‘fast’: use the O[N log N] fast method. Note that this requires evenly-spaced frequencies: by default this will be checked unless assume_regular_frequency is set to True.

            -  ‘slow’: use the O[N^2] pure-python implementation

            -  ‘cython’: use the O[N^2] cython implementation. This is slightly faster than method=’slow’, but much more memory efficient.

            -  ‘chi2’: use the O[N^2] chi2/linear-fitting implementation

            -  ‘fastchi2’: use the O[N log N] chi2 implementation. Note that this requires evenly-spaced frequencies: by default this will be checked unless assume_regular_frequency is set to True.

            -  ‘scipy’: use scipy.signal.lombscargle, which is an O[N^2] implementation written in C. Note that this does not support heteroskedastic errors.

        :param samples_per_peak: The approximate number of desired samples across the typical peak
        :param nyquist_factor: The multiple of the average nyquist frequency used to choose the maximum frequency if maximum_frequency is not provided.
        :param plot: if True, then the function also produces a plot of the power spectrum.
        :param figsize: size of the plot.
        :param savefile: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :return: power, frequency and the astropy LombScargle object
        """
        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data['mag_err'] < 99]
        if not include_poor_images:
            data = data[data['quality'] == 'G']

        ls = LombScargle(data.jd, data.mag,
                         fit_mean=fit_mean,
                         center_data=center_data,
                         nterms=nterms,
                         normalization=normalization)

        frequency, power = ls.autopower(minimum_frequency=minimum_frequency,
                                        maximum_frequency=maximum_frequency,
                                        method=method,
                                        samples_per_peak=samples_per_peak,
                                        nyquist_factor=nyquist_factor,
                                        normalization=normalization)
        if plot:
            plt.figure(figsize=figsize)

            plt.plot(frequency, power)
            self._label_plots()
            plt.xlabel("Frequency")
            plt.ylabel("Power")

            if savefile:
                plt.savefig(savefile)
            else:
                plt.show()
        return frequency, power, ls

    def find_period(self, frequency, power, best_frequency=None, plot=True, figsize=(12,8), savefile=None,
                    include_poor_images=False, include_non_det=False):
        """
        Find the period of the light curve given the power spectrum produced by lomb_scargle.
        Also produces a phase-folded plot of the light curve.

        :param frequency: frequency from lomb_scargle()
        :param power: power from lomb_scargle()
        :param best_frequency: peak frequency for phase folding the light curve
        :param plot: if True, then the function also produces a plot of the phase-folded light curve
        :param figsize: size of the plot
        :param savefile: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :return: period of the light curve
        """
        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data['mag_err'] < 99]
        if not include_poor_images:
            data = data[data['quality'] == 'G']


        if best_frequency is None:
            best_frequency = frequency[np.argmax(power)]

        # Get inverse for period and fold on time-space
        period = 1 / best_frequency

        if plot:
            folded_jd = data.jd % period

            # Concatenate for multiple peaks
            x = np.concatenate([folded_jd / period, folded_jd / period + 1])
            y = np.concatenate([data.mag, data.mag])

            plt.figure(figsize=figsize)
            plt.scatter(x, y)
            self._label_plots()
            plt.xlabel("Phase")
            plt.ylabel("Magnitude")
            plt.gca().invert_yaxis()

            if savefile:
                plt.savefig(savefile)
            else:
                plt.show()

        return period


    def _label_plots(self):
        suptitle = ""
        title = ""
        if 'asas_sn_id' in self.meta.columns:
            suptitle += f"SkyPatrol ID: {self.meta.asas_sn_id.item()}"
        if 'name' in self.meta.columns:
            suptitle += f"\nSource Name: {self.meta.name.item()}"
        if 'ra_deg' in self.meta.columns:
            title += f"Right Ascention: {self.meta.ra_deg.item():.05f}"
        if 'dec_deg' in self.meta.columns:
            title += f"\nDeclination: {self.meta.dec_deg.item():.05f}"

        title += f"\nEpochs: {self.epochs}"
        plt.title(title, loc="left", fontsize=10)
        plt.suptitle(suptitle, fontsize=14)
        plt.grid()
