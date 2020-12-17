from pymongo import MongoClient
from base64 import encodebytes
import requests, os
import pandas as pd
import json
import numpy as np
from multiprocessing import Pool
import re
import pyarrow as pa
from .utils import LightCurveCollection, _block_arr, Catalog


class SkyPatrolClient:
    lightcurve_units = {'jd': "Julian Date",
                        'flux': "mJy",
                        'flux_err': "mJy",
                        'mag': "magnitude",
                        'mag_err': "magnitude",
                        'limit': "magnitude",
                        'fwhm': "pixels"}

    def __init__(self, user, password):
        """
        The SkyPatrolClient allows users to interact with the ASAS-SN Skypatrol photometry database.
        This client enables users to use ADQL, conesearches, and catalog ID searches on the input catalogs.
        Queries to the input catalogs will either be returned as pandas DataFrames containing aggregate information
        on astronomical targets, or they will be returned as LightCurveCollections containing photometry data from all
        queried targets.
        :param user: username to interact with the light curve database; string.
        :param password: password to interact with the light curve database; string.
        """
        self.index = None
        self.user_name = user
        self.password = password
        try:
            url = "http://asassn-lb01.ifa.hawaii.edu:9006/get_schema"
            url_data = requests.get(url).content

            schema_msg = json.loads(url_data)

            self.catalogs = Catalog(schema_msg)

        except ConnectionError as e:
            raise ConnectionError("Unable to connect to ASAS-SN Servers")

    def adql_query(self, query_str, mode='index', threads=1):
        """
        Query the ASAS-SN SkyPatrol Input Catalogs with an ADQL string.
        See README.md for more on accepted ADQL context and functions.

        :param query_str: ADQL query string
        :param mode:
                    'index': queries input catalogs for information on targets
                    'download_curves': pulls light curves from server.
        :param threads: number of real threads to use for pulling light curves from server.
        :return: pandas DataFrame if 'mode' = 'index'; else LightCurveCollection
        """
        # Check inputs
        if mode not in ['index', 'download_curves']:
            raise ValueError("mode must be 'index', or 'download_curves")

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
        buff = pa.py_buffer(response.content)
        tar_df = pa.deserialize(buff)
        self.index = tar_df

        if mode == 'index':
            return tar_df

        elif mode == 'download_curves':
            tar_ids = list(tar_df['asas_sn_id'])
            return self._get_curves(tar_ids, "extrasolar", threads)

    def cone_search(self, ra_deg, dec_deg, radius, units='deg', catalog='master_list', cols=None,
                    mode='index',  threads=1):
        """
        Query the ASAS-SN SkyPatrol Input Catalogs for all targets within a cone of the sky.
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
        :param mode:
                    'index': queries input catalogs for information on targets
                    'download_curves': pulls light curves from server.
        :param threads: number of real threads to use for pulling light curves from server.
        :return: pandas DataFrame if 'mode' = 'index'; else LightCurveCollection
        """
        # Check inputs
        if mode not in ['index', 'download_curves']:
            raise ValueError("mode must be 'index' OR 'download_curves")
        if catalog not in self.catalogs.keys() or catalog in ['asteroids', 'comets']:
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
            radius = SkyPatrolClient._arc_to_deg(np.float(radius), units)

        # Query the Flask server API for cone
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_cone/radius{radius}_ra{ra_deg}_dec{dec_deg}"
        response = requests.post(url, json={'catalog': catalog, 'cols': cols, 'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        buff = pa.py_buffer(response.content)
        tar_df = pa.deserialize(buff)
        self.index = tar_df

        if mode == 'index':
            return tar_df

        elif mode == 'download_curves':
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])
            return self._get_curves(tar_ids, catalog, threads)

    def query_list(self, tar_ids,  id_col='asas_sn_id', catalog='master_list', cols=None, mode='index', threads=1):
        """
        Query the ASAS-SN SkyPatrol Input Catalogs for all targets with the given identifiers.
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
        :param mode:
                    'index': queries input catalogs for information on targets
                    'download_curves': pulls light curves from server.
        :param threads: number of real threads to use for pulling light curves from server.
        :return: pandas DataFrame if 'mode' = 'index'; else LightCurveCollection
        """
        # Check inputs
        if mode not in ['index', 'download_curves']:
            raise ValueError("mode must be 'index', 'load_curves'. or 'download_curves")
        # Limit sources
        if catalog not in self.catalogs.keys():
            raise ValueError("invalid catalog")
        # If catalog is master or stellar_main, default is 'asas_sn_id'
        if catalog in ['master_list', 'stellar_main']:
            id_col = 'asas_sn_id'

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
        buff = pa.py_buffer(response.content)
        tar_df = pa.deserialize(buff)
        self.index = tar_df

        if mode == 'index':
            return tar_df

        elif mode == 'download_curves':
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])
            return self._get_curves(tar_ids, catalog, threads)

    def random_sample(self, n, catalog='master_list', cols=None, mode='index', threads=1):
        """
        Get n random targets from the ASAS-SN SkyPatrol Input Catalogs.

        :param n: number of targets to randomly sample
        :param catalog: which catalog are we searching
        :param cols: columns to return from the given input catalog;
                     if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param mode:
                    'index': queries input catalogs for information on targets
                    'download_curves': pulls light curves from server.
        :param threads: number of real threads to use for pulling light curves from server.
        :return: pandas DataFrame if 'mode' = 'index'; else LightCurveCollection
        """
        # Valid modes
        if mode not in ['index', 'download_curves']:
            raise ValueError("mode must be 'index', 'download_curves'. or 'download_curves")
        # Valid catalogs
        if catalog not in self.catalogs.keys():
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
        buff = pa.py_buffer(response.content)
        tar_df = pa.deserialize(buff)

        self.index = tar_df

        if mode == 'index':
            return tar_df

        elif mode == 'download_curves':
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
            collection = db.phot
            colnames = ['jd', 'flux', 'flux_err', 'mag', 'mag_err', 'limit', 'fwhm']

        elif mongo_collection == 'asteroids':
            id_col = 'name'
            collection = db.asteroids
            colnames = ['jd', 'flux', 'flux_err', 'mag', 'mag_err', 'limit', 'fwhm']

        elif mongo_collection == 'comets':
            id_col = 'name'
            collection = db.comets
            colnames = ['jd',
                       'flux', 'flux_err', 'mag', 'mag_err', 'limit',
                       'flux_1', 'flux_err_1', 'mag_1', 'mag_err_1', 'limit_1',
                       'flux_2', 'flux_err_2', 'mag_2', 'mag_err_2', 'limit_2',
                       'flux_3', 'flux_err_3', 'mag_3', 'mag_err_3', 'limit_3',
                       'flux_4', 'flux_err_4', 'mag_4', 'mag_err_4', 'limit_4',
                       'flux_5', 'flux_err_5', 'mag_5', 'mag_err_5', 'limit_5',
                       'flux_6', 'flux_err_6', 'mag_6', 'mag_err_6', 'limit_6',
                       'fwhm']
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
            light_curves.append(lightcurve_df)

        return light_curves

    @staticmethod
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





