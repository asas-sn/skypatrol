from __future__ import division, print_function
import os
from astropy.timeseries import LombScargle
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from .wavelet import LS_wavelet
from .utils import Vcams, gcams


class LightCurve:
    """
    Object for analysing and visualizing ASAS-SN Sky Patrol light curves.
    """

    def __init__(self, data, meta):
        self._validate(data)
        self.data = data.sort_values("jd").reset_index(
            drop=True
        )  # Ensure times are sorted
        self.meta = meta
        self.epochs = len(data)

    def __repr__(self):
        # f = f"LightCurve of ASAS-SN {self.meta.asas_sn_id[0]} with {self.epochs} epochs \n"
        return self.data.__repr__()

    def __getattr__(self, name, **kwargs):
        """Expose all columns as attributes."""
        if name in self.__dict__["data"].columns:
            return self.__dict__["data"][name]
        raise AttributeError(f"object has no attribute {name}")

    def __getitem__(self, item):
        """Expore all columns as attributes."""
        if item in self.__dict__["data"].columns:
            return self.__dict__["data"][item]
        raise AttributeError(f"object has no attribute {item}")

    @property
    def time(self):
        return self.data.jd

    @staticmethod
    def _validate(obj):
        # verify there is a column latitude and a column longitude
        if (
            "jd" not in obj.columns
            or "mag" not in obj.columns
            or "mag_err" not in obj.columns
        ):
            raise AttributeError("Must have 'jd'(julian date), 'mag' and 'mag_err'")

    def save(self, filename, file_format="parquet"):
        """
        Save the light curve to csv.
        :param filename: filename to save this light curve.
        :param file_format: file format of saved objects ['parquet', 'csv', 'pickle']
        :return: void
        """
        if file_format == "parquet":
            self.data.to_parquet(filename)
        elif file_format == "pickle":
            self.data.to_pickle(filename)
        elif file_format == "csv":
            with open(filename, "w+") as f:
                f.write(f"# {self.meta.to_json(orient='records')[2:-2]}\n")
            self.data.to_csv(filename, mode="a", index=False)
        else:
            raise ValueError(
                f"invalid format: '{file_format}' not in ['parquet', 'csv', 'pickle']"
            )

    def plot(
        self,
        figsize=(12, 8),
        font_size=10,
        save_file=None,
        include_poor_images=False,
        include_non_det=True,
        phot_filter="all",
    ):
        """
        Plots the given light curve with error bars.

        :param figsize: size of the plot.
        :param font_size: font size for the plotting.
        :param save_file: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to all
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :return: void
        """
        # Filter preferences
        data = self.data

        # Filter out pool quality images
        if not include_poor_images:
            data = data[data["quality"] == "G"]

        # Filter detections
        errors = data.mag_err > 99
        detections = data[~errors]

        # Plot
        plt.figure(figsize=figsize)

        # Set font size
        plt.rcParams.update({"font.size": font_size})
        # Diff colors for filters
        if phot_filter in ["g", "all"]:
            plt.errorbar(
                x=detections[detections["phot_filter"] == "g"].jd - 2450000,
                y=detections[detections["phot_filter"] == "g"].mag,
                yerr=detections[detections["phot_filter"] == "g"].mag_err,
                fmt="o",
                c="mediumblue",
                label="g band",
            )
        if phot_filter in ["V", "all"]:
            plt.errorbar(
                x=detections[detections["phot_filter"] == "V"].jd - 2450000,
                y=detections[detections["phot_filter"] == "V"].mag,
                yerr=detections[detections["phot_filter"] == "V"].mag_err,
                fmt="o",
                c="teal",
                label="V band",
            )
        if phot_filter not in ["g", "V", "all"]:
            raise ValueError("phot_filter must be in ['g', 'V', 'all']")

        # Plot non-detections
        if include_non_det:
            plt.errorbar(
                x=data[errors].jd - 2450000,
                y=data[errors].mag,
                fmt="v",
                c="red",
                label="non-detections",
            )
        # Label plots
        self._label_plots(font_size)
        plt.legend()
        plt.xlabel("Date (JD-2450000)")
        plt.ylabel("Magnitude")
        plt.gca().invert_yaxis()

        if save_file:
            plt.savefig(save_file)
        else:
            plt.show()

        # Reset font size (default = 10)
        plt.rcParams.update({"font.size": 10})

    def lomb_scargle(
        self,
        fit_mean=True,
        center_data=True,
        nterms=1,
        normalization="standard",
        minimum_frequency=0.001,
        maximum_frequency=25,
        method="auto",
        samples_per_peak=5,
        nyquist_factor=5,
        plot=True,
        figsize=(12, 8),
        font_size=10,
        save_file=None,
        include_poor_images=False,
        include_non_det=False,
        phot_filter="all",
    ):
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
        :param font_size: font size for the plotting.
        :param save_file: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to all
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :return: power, frequency and the astropy LombScargle object
        """
        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data["mag_err"] < 99]
        if not include_poor_images:
            data = data[data["quality"] == "G"]

        # Filter by filter
        if phot_filter == "g":
            data = data[data["phot_filter"] == "g"]
        elif phot_filter == "V":
            data = data[data["phot_filter"] == "V"]
        elif phot_filter == "all":
            pass
        else:
            raise ValueError("phot_filter must be in ['g', 'V', 'all']")

        ls = LombScargle(
            data.jd,
            data.mag,
            fit_mean=fit_mean,
            center_data=center_data,
            nterms=nterms,
            normalization=normalization,
        )

        frequency, power = ls.autopower(
            minimum_frequency=minimum_frequency,
            maximum_frequency=maximum_frequency,
            method=method,
            samples_per_peak=samples_per_peak,
            nyquist_factor=nyquist_factor,
            normalization=normalization,
        )
        if plot:
            plt.figure(figsize=figsize)
            # Set font size
            plt.rcParams.update({"font.size": font_size})

            plt.plot(frequency, power)
            self._label_plots(font_size)
            plt.xlabel("Frequency")
            plt.ylabel("Power")

            if save_file:
                plt.savefig(save_file)
            else:
                plt.show()

            # Reset font size (default = 10)
            plt.rcParams.update({"font.size": 10})

        return frequency, power, ls

    def wavelet_power(
        self,
        tt=None,
        ff=None,
        include_poor_images=False,
        include_non_det=True,
        phot_filter="all",
        tradeoff=2,
        plot=True,
        font_size=10,
        **kwargs
    ):
        """
        Constructs a wavelet-transform power spectrum.

        :param tt: Array of times at which to evaluate wavelet PS
        :param ff: Array of frequencies at which to evaluate wavelet PS
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to g
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :tradeoff: Tradeoff parameter between frequency and time resolution
        :plot: Construct figure
        :**kwargs: Keyword arguments to pass to plt.imshow()

        :return: numpy array containing wavelet power at provided times and frequencies.
        """

        # Filter preferences for this function call only
        data = self.data

        if not include_non_det:
            data = data[data["mag_err"] < 99]
        if not include_poor_images:
            data = data[data["quality"] == "G"]

        # Filter by filter
        if phot_filter == "g":
            data = data[data["phot_filter"] == "g"]
        elif phot_filter == "V":
            data = data[data["phot_filter"] == "V"]
        elif phot_filter == "all":
            pass
        else:
            raise ValueError("phot_filter must be in ['g', 'V', 'all']")

        # Data for wavelet
        x = data.jd
        y = data.mag
        e_y = data.mag_err

        if tt is None:
            tt = np.linspace(np.min(x), np.max(x), 800)

        if ff is None:
            ff = np.linspace(1/(np.max(x) - np.min(x))/2, 1/np.min(np.diff(x))/2, 600)

        wavelet = LS_wavelet(tt, ff, x, y, e_y, Γ=tradeoff)
        if plot:
            plt.imshow(wavelet.T, origin='lower', aspect='auto',
                       extent=(np.min(tt), np.max(tt), np.min(ff), np.max(ff)), **kwargs)
            plt.xlabel(r"Time/d")
            plt.ylabel(r"Frequency/d$^{-1}$")
            self._label_plots(font_size)
        return wavelet

    def find_period(
        self,
        frequency,
        power,
        best_frequency=None,
        plot=True,
        reference_epoch="max",
        figsize=(12, 8),
        font_size=10,
        save_file=None,
        include_poor_images=False,
        include_non_det=False,
        phot_filter="all",
    ):
        """
        Find the period of the light curve given the power spectrum produced by lomb_scargle.
        Also produces a phase-folded plot of the light curve.

        :param frequency: frequency from lomb_scargle()
        :param power: power from lomb_scargle()
        :param best_frequency: peak frequency for phase folding the light curve
        :param plot: if True, then the function also produces a plot of the phase-folded light curve
        :param reference_epoch: either 'max' or 'min', corresponding to the time of maximum/minimum flux in the light curve
        :param figsize: size of the plot
        :param font_size: font size for the plotting.
        :param save_file: file name to save the plot; if None plot will be directly displayed
        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to all
        :return: period of the light curve
        """
        # Filter preferences for this function call only
        data = self.data
        if not include_non_det:
            data = data[data["mag_err"] < 99]
        if not include_poor_images:
            data = data[data["quality"] == "G"]

        # Get frequency
        if best_frequency is None:
            best_frequency = frequency[np.argmax(power)]

        # Get inverse for period and fold on time-space
        period = 1 / best_frequency

        if plot:
            plt.figure(figsize=figsize)
            # Set font size
            plt.rcParams.update({"font.size": font_size})

            if phot_filter in ["g", "all"]:
                # Filter for filter
                plot_data = data[data["phot_filter"] == "g"]

                # Get reference epoch for phasing
                if reference_epoch == "max":
                    ref_epoch = plot_data["jd"][plot_data.mag.idxmin()]
                elif reference_epoch == "min":
                    ref_epoch = plot_data["jd"][plot_data.mag.idxmax()]
                else:
                    ref_epoch = 0.0

                phase = ((plot_data.jd - ref_epoch) / period) % 1
                # Concatenate for multiple peaks
                x = np.concatenate([phase, phase + 1])
                y = np.concatenate([plot_data.mag, plot_data.mag])
                plt.scatter(x, y, c="mediumblue", label="g band")

            if phot_filter in ["V", "all"]:
                # Filter for filter
                plot_data = data[data["phot_filter"] == "V"]

                # Get reference epoch for phasing
                if reference_epoch == "max":
                    ref_epoch = plot_data["jd"][plot_data.mag.idxmax()]
                elif reference_epoch == "min":
                    ref_epoch = plot_data["jd"][plot_data.mag.idxmin()]
                else:
                    ref_epoch = 0.0

                phase = ((plot_data.jd - ref_epoch) / period) % 1
                # Concatenate for multiple peaks
                x = np.concatenate([phase, phase + 1])
                y = np.concatenate([plot_data.mag, plot_data.mag])
                plt.scatter(x, y, c="teal", label="V band")
            if phot_filter not in ["g", "V", "all"]:
                raise ValueError("phot_filter must be in ['g', 'V', 'all']")

            # Create labels
            self._label_plots(font_size)
            plt.xlabel("Phase")
            plt.ylabel("Magnitude")
            plt.gca().invert_yaxis()

            if save_file:
                plt.savefig(save_file)
            else:
                plt.show()
        # Reset font size (default = 10)
        plt.rcParams.update({"font.size": 10})

        return period

    def _label_plots(self, font_size):
        suptitle = ""
        title = ""
        if "asas_sn_id" in self.meta.columns:
            suptitle += f"SkyPatrol ID: {self.meta.asas_sn_id.item()}"
        if "name" in self.meta.columns:
            suptitle += f"\nSource Name: {self.meta.name.item()}"
        if "ra_deg" in self.meta.columns:
            title += f"Right Ascention: {self.meta.ra_deg.item():.05f}"
        if "dec_deg" in self.meta.columns:
            title += f"\nDeclination: {self.meta.dec_deg.item():.05f}"

        title += f"\nEpochs: {self.epochs}"
        plt.title(title, loc="left", fontsize=font_size - 2)
        plt.suptitle(suptitle, fontsize=font_size + 2)
        plt.grid()

    def normalize(self, method="median", col="mag"):
        data = self.data.copy()
        if method not in ["median", "gp"]:
            raise ValueError("method must be in ['median', 'gp']")
        if col not in ["mag", "flux"]:
            raise ValueError("col must be in ['mag', 'flux']")

        if method == "median":
            data_norm = []
            for camera in data.camera.unique():
                lcx = data[data.camera == camera].copy()
                lcx[col] /= lcx[col].median()
                data_norm.append(lcx)
            return LightCurve(pd.concat(data_norm), self.meta)
        elif method == "gp":
            pass

    def quality_cut(self, sigma_cut=5):
        # Quality cuts
        m = self.flux_err < sigma_cut * np.median(self.flux_err)
        m &= self["flux"] != 99.99
        m &= self["flux"] > 0
        m &= self.mag != "99.990"
        m &= self.mag_err < 99

        return LightCurve(self.data[m].copy(), self.meta)
