import pandas as pd
import numpy as np
from astropy.timeseries import LombScargle
import matplotlib.pyplot as plt


def block_arr(arr, size):
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
        plt.legend()
        plt.grid()
        plt.xlabel("Date (JD-2450000)")
        plt.ylabel("Magnitude")
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

        if savefile:
            plt.savefig(savefile)
        else:
            plt.show()


    def lomb_scargle(self, plot=True, figsize=(12,8), savefile=None):
        frequency, power = LombScargle(self.data['jd'], self.data['mag']).autopower()
        if plot:
            plt.figure(figsize=figsize)

            plt.plot(frequency, power)
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
            plt.xlabel("Frequemcy")
            plt.ylabel("Power")
            plt.grid()

            if savefile:
                plt.savefig(savefile)
            else:
                plt.show()
        return frequency, power