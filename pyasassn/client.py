from __future__ import division, print_function
from base64 import encodebytes
from glob import glob
import requests
import pandas as pd
import json
import numpy as np
import multiprocessing
import re
import os
import io
from time import sleep

from .collection import LightCurveCollection


class SkyPatrolClient:
    """
        The SkyPatrolClient allows users to interact with the ASAS-SN Sky Patrol photometry database.
    This client enables users to use ADQL, cone searches, random samples, and catalog ID lookups on the input catalogs.

    Queries to the input catalogs will either be returned as pandas DataFrames containing aggregate information
    on astronomical targets, or they will be returned as LightCurveCollections containing photometry data from all
    queried targets.
    """

    def __init__(self, verbose=True):
        """
        Creates SkyPatrolClient object
        """
        self.index = None
        self.verbose = verbose
        try:
            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_current_message"
            url_data = requests.get(url).content
            self.message = url_data.decode()
            self._verbose_print(self.message)

            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_schema"
            url_data = requests.get(url).content
            schema = json.loads(url_data)

            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_counts"
            url_data = requests.get(url).content
            counts = json.loads(url_data)

            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_block_servers"
            url_data = requests.get(url).content
            self.block_servers = json.loads(url_data)

            self.catalogs = SkyPatrolClient.InputCatalogs(schema, counts)

        except ConnectionError as e:
            raise ConnectionError("Unable to connect to ASAS-SN Servers")

    def adql_query(
        self, query_str, download=False, save_dir=None, file_format="parquet", threads=1
    ):
        """
        Query the ASAS-SN Sky Patrol Input Catalogs with an ADQL string.
        See README.md for more on accepted ADQL context and functions.

        :param query_str: ADQL query string
        :param download: return full light curves if True, return catalog information if False
        :param save_dir: if set, then light curves will write to file as they are downloaded
        :param file_format: format to save light curves ['parquet', 'pickle', 'csv']
        :param threads: number of real threads to use for pulling light curves from server.
        :return: if 'download' if False; pandas Dataframe containing catalog information of targets;
                else LightCurveCollection
        """
        # Check inputs
        if type(download) is not bool:
            raise ValueError("'download' must be boolean value")
        if type(threads) is not int:
            raise ValueError("'threads' must be integer value")
        if type(query_str) is not str:
            raise ValueError("'query_str' must me string value")

        # Trim ADQL input
        query_str = re.sub(r"(\s+)", " ", query_str)
        query_hash = encodebytes(bytes(query_str, encoding="utf-8")).decode()

        # Query Flask API with SQL bytes
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_sql/{query_hash}"
        response = requests.post(url, json={"format": "arrow", "download": download})

        self._validate_response(response)

        # Deserialize from arrow
        tar_df = _deserialize(response.content)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            if save_dir:
                self._save_index(save_dir, file_format)
            # Get lightcurve ids to pull
            if "asas_sn_id" in tar_df.columns:
                id_col = "asas_sn_id"
                catalog = "extrasolar"
            elif "comets" in query_str:
                id_col = "name"
                catalog = "comets"
            elif "asteroids" in query_str:
                id_col = "name"
                catalog = "asteroids"
            else:
                raise ValueError("needs propper id column to download lightcurves")
            # Get tar ids
            tar_ids = list(tar_df[id_col])

            # Returns a LightCurveCollection object, or a list of light curve files when save_dir is set
            return self._get_curves(
                query_hash, tar_ids, catalog, save_dir, file_format, threads
            )

    def cone_search(
        self,
        ra_deg,
        dec_deg,
        radius,
        units="deg",
        catalog="master_list",
        cols=None,
        download=False,
        save_dir=None,
        file_format="parquet",
        threads=1,
    ):
        """
        Query the ASAS-SN Sky Patrol Input Catalogs for all targets within a cone of the sky.
        Does NOT return solar system targets (i.e. asteroids and coma).

        :param ra_deg: right ascension of cone.
                       accepts degree-decimal (float) or HH:MM:SS(.SS) sexagesimal (string)
        :param dec_deg: declination of cone.
                        accepts degree/decimal as float or DD:MM:SS(.SS) sexagesimal (string)
        :param radius: radius in degrees of cone, float
        :param units: units for cone radius.
                     'deg': degree decimal
                     'arcmin': arcminutes
                     'arcsec' arcseconds
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param download: return full light curves if True, return catalog information if False
        :param save_dir: if set, then light curves will write to file as they are downloaded
        :param file_format: format to save light curves ['parquet', 'pickle', 'csv']
        :param threads: number of real threads to use for pulling light curves from server.
        :return: if 'download' if False; pandas Dataframe containing catalog information of targets;
                else LightCurveCollection
        """
        # Check inputs
        if type(download) is not bool:
            raise ValueError("'download' must be boolean value")
        if type(threads) is not int:
            raise ValueError("'threads' must be integer value")
        if catalog not in self.catalogs.catalog_names() or catalog in [
            "asteroids",
            "comets",
        ]:
            raise ValueError("invalid catalog")
        if cols is None:
            cols = ["asas_sn_id", "ra_deg", "dec_deg"]
            if catalog == "m_giants":
                cols.append("gaia_id")
            elif catalog == "master_list":
                cols.append("catalog_sources")
            elif catalog not in ["stellar_main", "master_list"]:
                cols.append("name")
        if set(cols).issubset(set(self.catalogs[catalog]["col_names"])) is False:
            raise ValueError(
                "one or more of the listed cols is not a column name in the selected catalog"
            )

        # Change units
        if units != "deg":
            radius = _arc_to_deg(float(radius), units)

        # Query the Flask server API for cone
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_cone/radius{radius}_ra{ra_deg}_dec{dec_deg}"
        response = requests.post(
            url,
            json={
                "catalog": catalog,
                "cols": cols,
                "format": "arrow",
                "download": download,
            },
        )

        # Check response
        self._validate_response(response)

        # Deserialize from arrow
        tar_df = _deserialize(response.content)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            if save_dir:
                self._save_index(save_dir, file_format)
            # Generate query information
            query_id = (
                f"conectr-{radius}_conera-{ra_deg}_conedec-{dec_deg}|catalog-{catalog}|cols-"
                + "/".join(cols)
            )
            query_hash = encodebytes(bytes(query_id, encoding="utf-8")).decode()

            # Get lightcurve ids to pull
            id_col = "asas_sn_id" if catalog not in ["asteroids", "comets"] else "name"
            tar_ids = list(tar_df[id_col])

            # Returns a LightCurveCollection object, or a list of light curve files when save_dir is set
            return self._get_curves(
                query_hash, tar_ids, catalog, save_dir, file_format, threads
            )

    def query_list(
        self,
        target_ids,
        id_col="asas_sn_id",
        catalog="master_list",
        cols=None,
        download=False,
        save_dir=None,
        file_format="parquet",
        threads=1,
    ):
        """
        Query the ASAS-SN Sky Patrol Input Catalogs for all targets with the given identifiers.
        to view the available list of catalogs and identifiers see SkyPatrolClient.catalogs.

        Most of our astronomical targets are in the stellar_main catalog, which has been pre-crossmatched to GaiaDR2,
        ATLAS Refcat2, SDSS, AllWISE, and Tess Input Catalog (TIC v8).

        Thus searching for light curves with a list of Gaia IDs would require catalog='stellar_main', id_col='gaia_id'.
        Our other input catalogs should be searched with id_col='name', or by columns giving alternative ids.

        :param target_ids: list of target ids for query; list
        :param id_col: the column on the given catalog to search against; string
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param download: return full light curves if True, return catalog information if False
        :param save_dir: if set, then light curves will write to file as they are downloaded
        :param file_format: format to save light curves ['parquet', 'pickle', 'csv']
        :param threads: number of real threads to use for pulling light curves from server.
        :return: if 'download' if False; pandas Dataframe containing catalog information of targets;
                else LightCurveCollection
        """
        # Check inputs
        if type(download) is not bool:
            raise ValueError("'download' must be boolean value")
        if type(threads) is not int:
            raise ValueError("'threads' must be integer value")
        # Limit sources
        if catalog not in self.catalogs.catalog_names():
            raise ValueError("invalid catalog")

        # Check catalog columns
        if id_col not in list(self.catalogs[catalog]["col_names"]):
            raise ValueError("invalid column")
        # Set default columns
        if cols is None and catalog not in ["asteroids", "comets"]:
            cols = ["asas_sn_id", "ra_deg", "dec_deg"]
            if catalog == "m_giants":
                cols.append("gaia_id")
            elif catalog == "master_list":
                cols.append("catalog_sources")
            elif catalog not in ["stellar_main", "master_list"]:
                cols.append("name")
        if cols is None and catalog in ["asteroids", "comets"]:
            cols = ["name"]
        # Ensure valid columns
        if set(cols).issubset(set(self.catalogs[catalog]["col_names"])) is False:
            raise ValueError(
                "one or more of the listed cols is not a column name in the selected catalog"
            )
        if id_col not in cols:
            cols.append(id_col)

        if type(target_ids) in [str, int]:
            target_ids = [target_ids]

        # Query API with list (POST METHOD)
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_targets/catalog_list"
        response = requests.post(
            url,
            json={
                "tar_ids": target_ids,
                "catalog": catalog,
                "id_col": id_col,
                "cols": cols,
                "format": "arrow",
                "download": download,
            },
        )

        # Check response
        self._validate_response(response)

        # Deserialize from arrow
        tar_df = _deserialize(response.content)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            if save_dir:
                self._save_index(save_dir, file_format)

            # Generate query information
            query_id = (
                f"listlen-{len(target_ids)}_listfirst-{target_ids[0]}_listend-{target_ids[-1]}"
                f"|catalog-{catalog}|id_col-{id_col}|cols-" + "/".join(cols)
            )
            query_hash = encodebytes(bytes(query_id, encoding="utf-8")).decode()

            # Get lightcurve ids to pull
            id_col = "asas_sn_id" if catalog not in ["asteroids", "comets"] else "name"
            tar_ids = list(tar_df[id_col])

            # Returns a LightCurveCollection object, or a list of light curve files when save_dir is set
            return self._get_curves(
                query_hash, tar_ids, catalog, save_dir, file_format, threads
            )

    def random_sample(
        self,
        n,
        catalog="master_list",
        cols=None,
        download=False,
        save_dir=None,
        file_format="parquet",
        threads=1,
    ):
        """
        Get n random targets from the ASAS-SN Sky Patrol Input Catalogs.

        :param n: number of targets to randomly sample
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param download: return full light curves if True, return catalog information if False
        :param save_dir: if set, then light curves will write to file as they are downloaded
        :param file_format: format to save light curves ['parquet', 'pickle', 'csv']
        :param threads: number of real threads to use for pulling light curves from server.
        :return: if 'download' if False; pandas Dataframe containing catalog information of targets;
                else LightCurveCollection
        """
        # Check inputs
        if type(download) is not bool:
            raise ValueError("'download' must be boolean value")
        if type(threads) is not int:
            raise ValueError("'threads' must be integer value")
        # Valid catalogs
        if catalog not in self.catalogs.catalog_names():
            raise ValueError("invalid catalog")
        # Set default columns
        if cols is None and catalog not in ["asteroids", "comets"]:
            cols = ["asas_sn_id", "ra_deg", "dec_deg"]
            if catalog == "m_giants":
                cols.append("gaia_id")
            elif catalog == "master_list":
                cols.append("catalog_sources")
            elif catalog not in ["stellar_main", "master_list"]:
                cols.append("name")
        if cols is None and catalog in ["asteroids", "comets"]:
            cols = ["name"]
        # Ensure valid columns
        if set(cols).issubset(set(self.catalogs[catalog]["col_names"])) is False:
            raise ValueError(
                "one or more of the listed cols is not a column name in the selected catalog"
            )

        # Limit sample length
        if n >= 1000000:
            raise ValueError("max sample size is 1 million")

        # Query API with list (POST METHOD)
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_targets/random_{n}"
        response = requests.post(
            url,
            json={
                "catalog": catalog,
                "cols": cols,
                "format": "arrow",
                "download": download,
            },
        )

        # Check response
        self._validate_response(response)

        # Deserialize from arrow
        tar_df = _deserialize(response.content)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            if save_dir:
                self._save_index(save_dir, file_format)
            # Get lightcurve ids to pull
            id_col = "asas_sn_id" if catalog not in ["asteroids", "comets"] else "name"
            tar_ids = list(tar_df[id_col])

            # Generate query information
            query_id = f"random-{n}|catalog-{catalog}|cols-" + "/".join(cols)
            query_hash = encodebytes(bytes(query_id, encoding="utf-8")).decode()

            # Returns a LightCurveCollection object, or a list of light curve files when save_dir is set
            return self._get_curves(
                query_hash, tar_ids, catalog, save_dir, file_format, threads
            )

    def _get_curves(
        self, query_hash, tar_ids, catalog, save_dir, file_format, threads=1
    ):
        # Get number of id chunks
        n_chunks = int(np.ceil(len(tar_ids) / 1000))
        self._verbose_print("Downloading Curves...")
        # Get targets via mutlithreaded requests
        with multiprocessing.Pool(processes=threads) as pool:
            results = [
                pool.apply_async(
                    self._get_lightcurve_chunk,
                    args=(
                        query_hash,
                        idx,
                        catalog,
                        save_dir,
                        file_format,
                    ),
                )
                for idx in range(n_chunks)
            ]

            chunks = []
            count = 0
            for r in results:
                data, n = r.get()
                chunks.append(data)
                count += n
                self._verbose_print(
                    f"Pulled {count:,} of {len(self.index):,}", end="\r"
                )

            self._verbose_print("")
        if save_dir is not None:
            # Return list of filenames
            return [file for chunk in chunks for file in chunk]
        else:
            # Return in memory data as LightCurveCollection
            data = pd.concat(chunks)
            id_col = "asas_sn_id" if catalog not in ["asteroids", "comets"] else "name"
            return LightCurveCollection(data, self.index, id_col)

    def _get_lightcurve_chunk(
        self, query_hash, block_idx, catalog, save_dir, file_format
    ):
        # Available servers
        n_servers = len(self.block_servers)
        # Start timeout at 0
        timeout = 1
        # Download server (for balance)
        server_idx = block_idx % n_servers
        # Success flag
        success = False

        # Loop through until we download or timeout
        while success is False and timeout <= 5:
            try:
                # Query API with (POST METHOD)
                url = (
                    f"http://{self.block_servers[server_idx]}:9006/get_block/"
                    f"query_hash-{query_hash}-block_idx-{block_idx}-catalog-{catalog}"
                )
                response = requests.get(url)

                # Pandas dataframe
                data = _deserialize(response.content)
                # ID and count
                id_col = (
                    "asas_sn_id" if catalog not in ["asteroids", "comets"] else "name"
                )
                count = len(data[id_col].unique())

                success = True
            except:
                sleep(timeout)
                server_idx = (server_idx + 1) % n_servers

                # Raise timeout if we've tried all servers once
                if (server_idx % n_servers) == (block_idx % n_servers):
                    timeout += 1

        # If download fails, raise exception
        if success is False:
            raise TimeoutError("Lightcurve servers unavailable, try again later")

        # Write to disk or return in memory
        if save_dir is not None:
            lcs = LightCurveCollection(data, self.index, id_col)
            return lcs.save(save_dir, file_format, include_index=False), count
        else:
            return data, count

    def _save_index(self, save_dir, file_format):
        if file_format == "parquet":
            self.index.to_parquet(os.path.join(save_dir, "index.parq"))
        elif file_format == "pickle":
            self.index.to_pickle(os.path.join(save_dir, "index.pkl"))
        elif file_format == "csv":
            self.index.to_csv(os.path.join(save_dir, "index.csv"), index=False)
        else:
            raise ValueError(
                f"invalid format: '{file_format}' not in ['parquet', 'csv', 'pickle']"
            )

    def _verbose_print(self, msg, end="\n"):
        if self.verbose:
            print(msg, end=end, flush=True)

    def _validate_response(self, response):
        """
        Validate the response before deserialization
        """
        # If the response is not an error (4xx, 5xx), it is true
        if not response:
            response.raise_for_status()

    class InputCatalogs(object):
        """
        Data structure for holding metadata on ASAS-SN Sky Patrol's input catalogs.

        Stores input catalog names as well as their searchable columns and total number of targets.
        """

        def __init__(self, schema, counts):
            for name, col_data in schema.items():
                self.__dict__[name] = pd.DataFrame(col_data)
            self.counts = counts

        def __str__(self):
            rep_str = "\n"
            for table_name, df in self.__dict__.items():
                if table_name == "counts":
                    continue
                rep_str += (
                    f"Table Name:  {table_name}\n"
                    f"Num Columns: {len(df)}\n"
                    f"Num Targets: {self.counts[table_name]}"
                    f"{df.head(10)}\n\n"
                )
            return rep_str

        def __repr__(self):
            rep_str = "\n"
            for table_name, df in self.__dict__.items():
                if table_name == "counts":
                    continue
                rep_str += (
                    f"Table Name:  {table_name}\n"
                    f"Num Columns: {len(df)}\n"
                    f"Num Targets: {self.counts[table_name]}\n\n"
                )
            return rep_str

        def catalog_names(self):
            """
            Get all the names of our available input catalogs

            :return: names of all input catalogs (list)
            """
            return self.__dict__.keys()

        def __getitem__(self, item):
            return self.__dict__[item]


def _deserialize(buffer):
    # Deserialize from bytes
    return pd.read_parquet(io.BytesIO(buffer))


def _arc_to_deg(arc, unit):
    """
    Convert arc minutes or seconds to decimal degree units

    :param arc: length of arc, float or np array
    :param unit: 'arcmin' or 'arcsec'
    :return: decimal degrees
    """
    if unit == "arcmin":
        return arc / 60
    elif unit == "arcsec":
        return arc / 3600
    else:
        raise ValueError("unit not in ['arcmin', 'arcsec']")


def load_collection(save_dir, file_format="parquet"):
    """
    Loads a LightCurveCollection from directory.
    Requires an index and light curve files saved from previous collection
    :param save_dir: path where collection is saved
    :param file_format: format of saved light curves
    :return: LightCurveCollection
    """
    if file_format == "parquet":
        index = pd.read_parquet(os.path.join(save_dir, "index.parq"))
        files = glob(os.path.join(save_dir, "*.parq"))
        lc_files = list(filter(lambda i: os.path.basename(i) != "index.parq", files))
        data = pd.concat(pd.read_parquet(file) for file in lc_files)

    elif file_format == "pickle":
        index = pd.read_pickle(os.path.join(save_dir, "index.pkl"))
        files = glob(os.path.join(save_dir, "*.pkl"))
        lc_files = list(filter(lambda i: os.path.basename(i) != "index.pkl", files))
        data = pd.concat(pd.read_pickle(file) for file in lc_files)

    elif file_format == "csv":
        index = pd.read_csv(os.path.join(save_dir, "index.csv"))
        files = glob(os.path.join(save_dir, "*.csv"))
        lc_files = list(filter(lambda i: os.path.basename(i) != "index.csv", files))
        data = pd.concat(pd.read_csv(file) for file in lc_files)

    else:
        raise ValueError(
            f"invalid format: '{file_format}' not in ['parquet', 'csv', 'pickle']"
        )

    id_col = "asas_sn_id" if "asas_sn_id" in index.columns else "name"
    return LightCurveCollection(data, index, id_col)
