import pandas as pd
import numpy as np
import os
from astropy.timeseries import LombScargle
import matplotlib.pyplot as plt


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

class Catalog(object):

    def __init__(self, schema_msg):
        for name, col_data in schema_msg.items():
            self.__dict__[name] = pd.DataFrame(col_data)

    def __str__(self):
        rep_str = "\n"
        for table_name, df in self.__dict__.items():
            rep_str += f"Table Name: {table_name}\n" \
                       f"Num Columns: {len(df.index)}\n" \
                       f"{df.head(10)}\n\n"
        return rep_str

    def __repr__(self):
        rep_str = "\n"
        for table_name, df in self.__dict__.items():
            rep_str += f"Table Name: {table_name}\n" \
                       f"Num Columns: {len(df.index)}\n\n"
        return rep_str

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def __getitem__(self, item):
        return self.__dict__[item]


class LightCurveCollection(object):

    def __init__(self, data, catalog_info, id_col):

        self.id_col = id_col
        self.data = data
        self.catalog_info = catalog_info

    def apply_function(self, func, col='mag', include_non_det=False):
        if include_non_det:
            data = self.data
        else:
            data = self.data[self.data['mag_err'] < 99]

        return data.groupby(self.id_col).agg({col: func})

    def stats(self, include_non_det=False):
        if include_non_det:
            data = self.data
        else:
            data = self.data[self.data['mag_err'] < 99]

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
        for key, data in self.data.groupby(self.id_col):
            source = self.catalog_info[self.id_col] == key
            meta = self.catalog_info[source]
            yield LightCurve(data, meta)

    def __len__(self):
        return len(self.catalog_info)

    def save(self, save_dir):
        self.catalog_info.to_csv(os.path.join(save_dir, "index.csv"), index=False)
        for lc in self.itercurves():
            lc.save(os.path.join(save_dir, f"{lc.meta[self.id_col].values[0]}.csv"))


class LightCurve:
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


    def save(self, path):
        with open(path, "w+") as f:
            f.write(f"# {self.meta.to_json(orient='records')[2:-2]}\n")

        self.data.to_csv(path, mode='a', index=False)

    def plot(self, figsize=(12,8), savefile=None):

        errors = self.data.mag_err > 99
        plt.figure(figsize=figsize)
        plt.errorbar(x=self.data[~errors].jd - 2450000,
                     y=self.data[~errors].mag,
                     yerr=self.data[~errors].mag_err,
                     fmt="o",
                     c="teal",
                     label="detections")
        plt.errorbar(x=self.data[errors].jd - 2450000,
                     y=self.data[errors].mag,
                     fmt="v",
                     c="red",
                     label="non-detections")
        self.label_plots()
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
                     nyquist_factor=5, plot=True, figsize=(12,8), savefile=None):

        # Don't count nondetections
        errors = self.data.mag_err > 99
        jd = self.data[~errors].jd
        mag = self.data[~errors].mag

        ls = LombScargle(jd, mag,
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
            self.label_plots()
            plt.xlabel("Frequemcy")
            plt.ylabel("Power")

            if savefile:
                plt.savefig(savefile)
            else:
                plt.show()
        return frequency, power, ls

    def find_period(self, frequency, power, best_frequency=None, plot=True, figsize=(12,8), savefile=None):

        # Don't count nondetections
        errors = self.data.mag_err > 99
        jd = self.data[~errors].jd
        mag = self.data[~errors].mag

        if best_frequency is None:
            best_frequency = frequency[np.argmax(power)]

        # Get inverse for period and fold on time-space
        period = 1 / best_frequency

        if plot:
            folded_jd = jd % period

            # Concatenate for multiple peaks
            x = np.concatenate([folded_jd / period, folded_jd / period + 1])
            y = np.concatenate([mag, mag])

            plt.figure(figsize=figsize)
            plt.scatter(x, y)
            self.label_plots()
            plt.xlabel("Phase")
            plt.ylabel("Magnitude")
            plt.gca().invert_yaxis()

            if savefile:
                plt.savefig(savefile)
            else:
                plt.show()

        return period



    def label_plots(self):
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
