from pymongo import MongoClient
from base64 import encodebytes
import requests
import pandas as pd
import json
import numpy as np
from multiprocessing import Pool
import re
import pyarrow as pa
import warnings
from .utils import LightCurveCollection, _block_arr, _arc_to_deg


class SkyPatrolClient:
    """
            The SkyPatrolClient allows users to interact with the ASAS-SN Sky Patrol photometry database.
        This client enables users to use ADQL, cone searches, random samples, and catalog ID lookups on the input catalogs.

        Queries to the input catalogs will either be returned as pandas DataFrames containing aggregate information
        on astronomical targets, or they will be returned as LightCurveCollections containing photometry data from all
        queried targets.
    """

    def __init__(self, user, password):
        """
        Creates SkyPatrolClient object
        :param user: username to interact with the light curve database; string.
        :param password: password to interact with the light curve database; string.
        """
        self.index = None
        self.user_name = user
        self.password = password
        try:
            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_schema"
            url_data = requests.get(url).content
            schema = json.loads(url_data)

            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_counts"
            url_data = requests.get(url).content
            counts = json.loads(url_data)

            self.catalogs = SkyPatrolClient.InputCatalogs(schema, counts)

        except ConnectionError as e:
            raise ConnectionError("Unable to connect to ASAS-SN Servers")

    def adql_query(self, query_str, download=False, threads=1):
        """
        Query the ASAS-SN Sky Patrol Input Catalogs with an ADQL string.
        See README.md for more on accepted ADQL context and functions.

        :param query_str: ADQL query string
        :param download: return full light curves if True, return catalog information if False
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
        query_str = re.sub(' +', ' ', query_str).replace("\n", "")
        query_bytes = encodebytes(bytes(query_str, encoding='utf-8')).decode()

        # Query Flask API with SQL bytes
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_sql/{query_bytes}"
        response = requests.post(url, json={'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        with warnings.catch_warnings():
            warnings.simplefilter(action='ignore', category=FutureWarning)
            buff = pa.py_buffer(response.content)
            tar_df = pa.deserialize(buff)

        self.index = tar_df

        if download is False:
            return tar_df

        else:
            tar_ids = list(tar_df['asas_sn_id'])
            return self._get_curves(tar_ids, "extrasolar", threads)

    def cone_search(self, ra_deg, dec_deg, radius, units='deg', catalog='master_list', cols=None,
                    download=False,  threads=1):
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
        :param threads: number of real threads to use for pulling light curves from server.
        :return: if 'download' if False; pandas Dataframe containing catalog information of targets;
                else LightCurveCollection
        """
        # Check inputs
        if type(download) is not bool:
            raise ValueError("'download' must be boolean value")
        if type(threads) is not int:
            raise ValueError("'threads' must be integer value")
        if catalog not in self.catalogs.catalog_names() or catalog in ['asteroids', 'comets']:
            raise ValueError("invalid catalog")
        if cols is None:
            cols = ['asas_sn_id', 'ra_deg', 'dec_deg']
            if catalog not in ['stellar_main', 'master_list']:
                cols.append('name')
            elif catalog == 'master_list':
                cols.append('catalog_sources')
        if set(cols).issubset(set(self.catalogs[catalog]['col_names'])) is False:
            raise ValueError("one or more of the listed cols is not a column name in the selected catalog")

        # Change units
        if units != "deg":
            radius = _arc_to_deg(np.float(radius), units)

        # Query the Flask server API for cone
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_cone/radius{radius}_ra{ra_deg}_dec{dec_deg}"
        response = requests.post(url, json={'catalog': catalog, 'cols': cols, 'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        with warnings.catch_warnings():
            warnings.simplefilter(action='ignore', category=FutureWarning)
            buff = pa.py_buffer(response.content)
            tar_df = pa.deserialize(buff)

        self.index = tar_df

        if download is False:
            return tar_df

        else:
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])
            return self._get_curves(tar_ids, catalog, threads)

    def query_list(self, tar_ids,  id_col='asas_sn_id', catalog='master_list', cols=None, download=False, threads=1):
        """
        Query the ASAS-SN Sky Patrol Input Catalogs for all targets with the given identifiers.
        to view the available list of catalogs and identifiers see SkyPatrolClient.catalogs.

        Most of our astronomical targets are in the stellar_main catalog, which has been pre-crossmatched to GaiaDR2,
        ATLAS Refcat2, SDSS, AllWISE, and Tess Input Catalog (TIC v8).

        Thus searching for light curves with a list of Gaia IDs would require catalog='stellar_main', id_col='gaia_id'.
        Our other input catalogs should be searched with id_col='name', or by columns giving alternative ids.

        :param tar_ids: list of target ids for query; list
        :param id_col: the column on the given catalog to search against; string
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param download: return full light curves if True, return catalog information if False
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
        if cols is None and catalog not in ['asteroids', 'comets']:
            cols = ['asas_sn_id', 'ra_deg', 'dec_deg']
            if catalog not in ['stellar_main', 'master_list']:
                cols.append('name')
            elif catalog == 'master_list':
                cols.append('catalog_sources')
        if cols is None and catalog in ['asteroids', 'comets']:
            cols = ['name']
        # Ensure valid columns
        if set(cols).issubset(set(self.catalogs[catalog]['col_names'])) is False:
            raise ValueError("one or more of the listed cols is not a column name in the selected catalog")
        if id_col not in cols:
            cols.append(id_col)

        if type(tar_ids) in [str, int]:
            tar_ids = [tar_ids]

        # Query API with list (POST METHOD)
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_targets/catalog_list"
        response = requests.post(url, json={'tar_ids': tar_ids,
                                            'catalog': catalog,
                                            'id_col': id_col,
                                            'cols': cols,
                                            'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        with warnings.catch_warnings():
            warnings.simplefilter(action='ignore', category=FutureWarning)
            buff = pa.py_buffer(response.content)
            tar_df = pa.deserialize(buff)

        self.index = tar_df

        if download is False:
            return tar_df

        else:
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])
            return self._get_curves(tar_ids, catalog, threads)

    def random_sample(self, n, catalog='master_list', cols=None, download=False, threads=1):
        """
        Get n random targets from the ASAS-SN Sky Patrol Input Catalogs.

        :param n: number of targets to randomly sample
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param download: return full light curves if True, return catalog information if False
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
        if cols is None and catalog not in ['asteroids', 'comets']:
            cols = ['asas_sn_id', 'ra_deg', 'dec_deg']
            if catalog not in ['stellar_main', 'master_list']:
                cols.append('name')
            elif catalog == 'master_list':
                cols.append('catalog_sources')
        if cols is None and catalog in ['asteroids', 'comets']:
            cols = ['name']
        # Ensure valid columns
        if set(cols).issubset(set(self.catalogs[catalog]['col_names'])) is False:
            raise ValueError("one or more of the listed cols is not a column name in the selected catalog")

        # Limit sample length
        if n >= 1000000:
            raise ValueError("max sample size is 1 million")

        # Query API with list (POST METHOD)
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_targets/random_{n}"
        response = requests.post(url, json={'catalog': catalog, 'cols': cols, 'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        with warnings.catch_warnings():
            warnings.simplefilter(action='ignore', category=FutureWarning)
            buff = pa.py_buffer(response.content)
            tar_df = pa.deserialize(buff)

        self.index = tar_df

        if download is False:
            return tar_df

        else:
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])
            return self._get_curves(tar_ids, catalog, threads)

    def _get_curves(self, tar_ids, catalog, threads=1):
        # Make sure we query correct collection
        if catalog not in ["asteroids", "comets"]:
            mongo_collection = "phot"
        else:
            mongo_collection = catalog

        # We will only query 1,000 docs at a time
        tar_id_blocks = _block_arr(tar_ids, 10000)

        # Build process pool. Each block of ids gets one worker
        with Pool(processes=threads) as pool:
            # Query one block at a time
            result_blocks = [pool.apply_async(self._query_mongo, args=(id_block, mongo_collection))
                             for id_block in tar_id_blocks]

            lcs = [curve for block in result_blocks for curve in block.get()]
            lc_df = pd.concat(lcs)
            return LightCurveCollection(lc_df, self.index, id_col='asas_sn_id' if mongo_collection == 'phot'
                                                                                else 'name')

    def _query_mongo(self, id_block, mongo_collection):

        # Connect Mongo Client
        client = MongoClient(f"mongodb://{self.user_name}:{self.password}"
                             f"@asassn-lb01.ifa.hawaii.edu:27020/asas_sn")
        db = client.asas_sn

        if mongo_collection == 'phot':
            id_col = 'asas_sn_id'
            collection = db.deep_space
            colnames = ['jd', 'flux', 'flux_err', 'mag', 'mag_err', 'limit', 'fwhm', 'quality']

        elif mongo_collection == 'asteroids':
            id_col = 'name'
            collection = db.asteroid
            colnames = ['jd', 'flux', 'flux_err', 'mag', 'mag_err', 'limit', 'fwhm', 'quality']

        elif mongo_collection == 'comets':
            id_col = 'name'
            collection = db.comet
            colnames = ['jd',
                       'flux', 'flux_err', 'mag', 'mag_err', 'limit',
                       'flux_1', 'flux_err_1', 'mag_1', 'mag_err_1', 'limit_1',
                       'flux_2', 'flux_err_2', 'mag_2', 'mag_err_2', 'limit_2',
                       'flux_3', 'flux_err_3', 'mag_3', 'mag_err_3', 'limit_3',
                       'flux_4', 'flux_err_4', 'mag_4', 'mag_err_4', 'limit_4',
                       'flux_5', 'flux_err_5', 'mag_5', 'mag_err_5', 'limit_5',
                       'flux_6', 'flux_err_6', 'mag_6', 'mag_err_6', 'limit_6',
                       'fwhm', 'quality']
        else:
            raise ValueError("Invalid curve type")

        # Query Mongo
        docs = list(collection.find({id_col: {"$in": id_block}}, {"_id": False}))
        light_curves = []
        for doc in docs:
            # Identifier
            tar_id = doc[id_col]
            # Base lists
            phot_measurments = []
            cam_ids = []

            # Parse individual lightcurve
            for key, value in doc.items():
                if key == id_col:
                    continue
                cam_ids.append(key[:2])
                phot_measurments.append(value)

            lightcurve_df = pd.DataFrame(phot_measurments, columns=colnames)
            lightcurve_df["cam"] = cam_ids
            lightcurve_df[id_col] = tar_id

            # Reorder columns
            cols = list(lightcurve_df.columns)
            cols = [cols[-1]] + cols[:-1]
            lightcurve_df = lightcurve_df[cols]

            light_curves.append(lightcurve_df)

        return light_curves



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
                if table_name == 'counts':
                    continue
                rep_str += f"Table Name:  {table_name}\n" \
                           f"Num Columns: {len(df)}\n" \
                           f"Num Targets: {self.counts[table_name]}" \
                           f"{df.head(10)}\n\n"
            return rep_str

        def __repr__(self):
            rep_str = "\n"
            for table_name, df in self.__dict__.items():
                if table_name == 'counts':
                    continue
                rep_str += f"Table Name:  {table_name}\n" \
                           f"Num Columns: {len(df)}\n" \
                           f"Num Targets: {self.counts[table_name]}\n\n"
            return rep_str

        def catalog_names(self):
            """
            Get all the names of our available input catalogs

            :return: names of all input catalogs (list)
            """
            return self.__dict__.keys()


        def __getitem__(self, item):
            return self.__dict__[item]

