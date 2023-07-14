from __future__ import division, print_function
import os
from astropy.timeseries import LombScargle
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from .lightcurve import LightCurve
from .utils import Vcams, gcams


class LightCurveCollection(object):
    """
    Object for storing and analysing ASAS-SN Sky Patrol light curves.
    Returned by any SkyPatrolClient query where download=True
    """

    def __init__(self, data, catalog_info, id_col):
        self.id_col = id_col
        self.data = data
        self.catalog_info = catalog_info

        self.data["phot_filter"] = self.data.camera.apply(
            lambda x: "V" if x in Vcams else "g" if x in gcams else None
        )
        self.data = self.data[self.data["phot_filter"].notna()]

    def __repr__(self):
        f = f"LightCurveCollection with {len(self)} light curves \n"
        return f + self.catalog_info.__repr__()
        # return f"LightCurveCollection with {len(self)} light curves"

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

    def __len__(self):
        return len(self.catalog_info)

    @property
    def ids(self):
        """
        Returns a list of all IDs in the collection.
        :return: list of IDs
        """
        return self.catalog_info[self.id_col].values

    def apply_function(
        self,
        func,
        col="mag",
        include_non_det=False,
        include_poor_images=False,
        phot_filter="all",
    ):
        """
        Apply a custom aggregate function to all light curves in the collection.

        :param func: custom aggregate function
        :param col: column to apply aggregate function; defaluts to 'mag'
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :param include_poor_images whether or not to include images of poor or unknown quality; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to all
        :return: pandas Dataframe with results
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

        return data.groupby(self.id_col).agg({col: func})

    def stats(
        self, include_non_det=False, include_poor_images=False, phot_filter="all"
    ):
        """
        Calculate simple aggregate statistics on the collection.
        Gets the mean and stddev magnitude for each curve as well as the total number of epochs observed.

        :param include_poor_images: whether or not to include images of poor or unknown quality; defaults to False
        :param include_non_det: whether or not to include non-detection events in analysis; defaults to False
        :param phot_filter: specify bandpass filter for photometry, either g, V, or all, defaults to all
        :return: pandas Dataframe with results
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

        return data.groupby(self.id_col).agg(
            mean_mag=("mag", "mean"), std_mag=("mag", "std"), epochs=("mag", "count")
        )

    def itercurves(self):
        """
        Generator to iterate through all light curves in the collection.
        :return: a generator that iterates over the collection
        """
        for key, data in self.data.groupby(self.id_col):
            source = self.catalog_info[self.id_col] == key
            meta = self.catalog_info[source]
            yield LightCurve(data, meta)

    def save(self, save_dir, file_format="parquet", include_index=True):
        """
        Saves entire light curve collection to a given directory.

        :param save_dir: directory name
        :param file_format: file format of saved objects ['parquet', 'csv', 'pickle']
        :param include_index: whether or not to save index (catalog_info)
        :return: a list of file names
        """
        filenames = []
        if file_format == "parquet":
            if include_index:
                self.catalog_info.to_parquet(os.path.join(save_dir, "index.parq"))
                filenames.append("index.parq")
            for lc in self.itercurves():
                file = os.path.join(save_dir, f"{lc.meta[self.id_col].values[0]}.parq")
                lc.save(file, file_format="parquet")
                filenames.append(file)

        elif file_format == "pickle":
            if include_index:
                self.catalog_info.to_pickle(os.path.join(save_dir, "index.pkl"))
                filenames.append("index.pkl")
            for lc in self.itercurves():
                file = os.path.join(save_dir, f"{lc.meta[self.id_col].values[0]}.pkl")
                lc.save(file, file_format="pickle")
                filenames.append(file)

        elif file_format == "csv":
            if include_index:
                self.catalog_info.to_csv(
                    os.path.join(save_dir, "index.csv"), index=False
                )
                filenames.append("index.csv")
            for lc in self.itercurves():
                file = os.path.join(save_dir, f"{lc.meta[self.id_col].values[0]}.csv")
                lc.save(file, file_format="csv")
                filenames.append(file)
        else:
            raise ValueError(
                f"invalid format: '{file_format}' not in ['parquet', 'csv', 'pickle']"
            )

        return filenames

    def merge(self, name):
        """
        Merge a LightCurveCollection or list of LightCurves to a single object.
        Useful for solar system objects with multiple designations.
        :param name: new name of the object
        :return: LightCurve
        """
        # Get all phot data
        lcs_data = [lc.data for lc in self.itercurves()]

        return LightCurve(data=pd.concat(lcs_data), meta=pd.DataFrame({"name": [name]}))
