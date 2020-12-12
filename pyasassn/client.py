from pymongo import MongoClient
from base64 import encodebytes
import requests, os
import pandas as pd
import json
import numpy as np
from multiprocessing import Pool
import re
import pyarrow as pa
from .utils import LightCurveCollection, block_arr, Catalog


class SkyPatrolClient:
    lightcurve_units = {'jd': "Julian Date",
                        'flux': "mJy",
                        'flux_err': "mJy",
                        'mag': "magnitude",
                        'mag_err': "magnitude",
                        'limit': "magnitude",
                        'fwhm': "pixels"}

    def __init__(self, user, password):
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

    def adql_query(self, query_str, mode='index', save_dir=None, threads=1):
        """
        Query the BAD Lookup Table with a SQL string.
        See README.md for more on accepted SQL context and functions.

        :param query_str: SQL query string
        :param mode: specify query return.
                    'index': returns dataframe containing ra, dec, and target ids for all results.
                    'download_curves': pulls light curves from server, either into memory or written to disk.
        :param save_dir: if 'mode' is set to 'download_curves' then this can be set to a directory to save all light curves
                                returns list of filenames for saved light curves (all csv)
                         else if this is left as None while 'mode' is set to 'load curves', then sql_query will
                                return a dataframe containing phot measurements for all targets retrieved
                                hint~ group by 'id' to get individual curves
        :param threads: number of real threads to use for pulling light curves from server.
        :return: 'mode' dependent
        """
        # Check inputs
        if mode not in ['index', 'download_curves']:
            raise ValueError("mode must be 'index', or 'download_curves")

        query_str = re.sub(' +', ' ', query_str).replace("\n", "")
        query_bytes = encodebytes(bytes(query_str, encoding='utf-8')).decode()

        # Query Flask API with SQL bytes
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_sql/{query_bytes}"
        response = requests.post(url, json={'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = re.findall(r'(?<=<p>).*(?=</p>)', response.content.decode())[-1]
            raise RuntimeError(error)

        # Deserialize from arrow
        buff = pa.py_buffer(response.content)
        tar_df = pa.deserialize(buff)
        self.index = tar_df

        if mode == 'index':
            return tar_df

        elif mode == 'download_curves':
            tar_ids = list(tar_df['asas_sn_id'])
            return self._get_curves(tar_ids, "extrasolar", threads, save_dir)

    def cone_search(self, ra_deg, dec_deg, radius, units='deg', catalog='master_list', cols=None,
                    mode='index', save_dir=None, threads=1):
        """
        Query the BAD Lookup Table for all targets within a cone of the sky.
        Does NOT return solar system targets (i.e. asteroids and coma).

        :param ra_deg: right ascension of cone.
                       accepts degree/decimal as float
        :param dec_deg: declination of cone.
                        accepts degree/decimal as float
        :param radius: radius in degrees of cone, float
        :param units: units for cone radius.
                     'deg': degree decimal
                     'arcmin': arcminutes
                     'arcsec' arcseconds
        :param catalog: which catalog are we searching
        :param cols: columns to return from the BAD Lookup Table, if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param mode: specify cone_search return.
                    'index': returns dataframe containing ra, dec, and target ids for all results.
                    'download_curves': pulls light curves from server, either into memory or written to disk.
        :param save_dir: if 'mode' is set to 'download_curves' then this can be set to a directory to save all light curves
                                returns list of filenames for saved light curves (all csv)
                         else if this is left as None while 'mode' is set to 'load curves', then cone_search will
                                return a dataframe containing phot measurements for all targets retrieved
                                hint~ group by 'id' to get individual curves
        :param threads: number of real threads to use for pulling light curves from server.

        :return: 'mode' dependent
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
            radius = SkyPatrolClient.arc_to_deg(np.float(radius), units)

        # Query the Flask server API for cone
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_cone/radius{radius}_ra{ra_deg}_dec{dec_deg}"
        response = requests.post(url, json={'catalog': catalog, 'cols': cols, 'format': 'arrow'})

        # Check response
        if response.status_code == 400:
            error = re.findall(r'(?<=<p>).*(?=</p>)', response.content.decode())[-1]
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
            return self._get_curves(tar_ids, catalog, threads, save_dir)

    def query_list(self, tar_ids, catalog, id_col='name', cols=None, mode='index', save_dir=None, threads=1):
        """
        Query the BAD Lookup Table for all targets with the given ids.
        Available Catalogs: GaiaDR2, Tess Input Catalog (TIC), ATLAS Refcat, Allwise, and SDSS.

        :param tar_ids: list of target ids for query
        :param source: source catalog of the targets,
                       accepts 'asas_sn' for asas_sn internal id's.
                               'gaia' for GaiaDR2
                               'tic' for TESS input catalog
                               'refcat' for ATLAS Refcat
                               'allwise' for Allwise
                               'sdss' for SDSS
        :param cols: columns to return from the BAD Lookup Table, if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param mode: specify query return.
                    'index': returns dataframe containing ra, dec, and target ids for all results.
                    'download_curves': pulls light curves from server, either into memory or written to disk.
        :param save_dir: if 'mode' is set to 'download_curves' then this can be set to a directory to save all light curves
                                returns list of filenames for saved light curves (all csv)
                         else if this is left as None while 'mode' is set to 'load curves', then sql_query will
                                return a dataframe containing phot measurements for all targets retrieved
                                hint~ group by 'id' to get individual curves
        :param threads: number of real threads to use for pulling light curves from server.
        :return: 'mode' dependent
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
            error = re.findall(r'(?<=<p>).*(?=</p>)', response.content.decode())[-1]
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
            return self._get_curves(tar_ids, catalog, threads, save_dir)

    def random_sample(self, n, catalog='master_list', cols=None, mode='index', save_dir=None, threads=1):
        """
        Get n random targets from the BAD Lookup Table

        :param n: number of targets to randomly sample
        :param cols: columns to return from the BAD Lookup Table, if None default = ['asas_sn_id', 'ra_deg', 'dec_deg']
        :param mode: specify query return.
                    'index': returns dataframe containing ra, dec, and target ids for all results.
                    'download_curves': pulls light curves from server, either into memory or written to disk.
        :param save_dir: if 'mode' is set to 'download_curves' then this can be set to a directory to save all light curves
                                returns list of filenames for saved light curves (all csv)
                         else if this is left as None while 'mode' is set to 'load curves', then sql_query will
                                return a dataframe containing phot measurements for all targets retrieved
                                hint~ group by 'ids' to get individual curves
        :param threads: number of real threads to use for pulling light curves from server.
        :return: 'mode' dependent
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
            error = re.findall(r'(?<=<p>).*(?=</p>)', response.content.decode())[-1]
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
            return self._get_curves(tar_ids, catalog, threads, save_dir)

    def _get_curves(self, tar_ids, catalog, threads=1, save_dir=None):
        """
        Queries BAD MongoDB for lightcurves of the target list.
        Either returns a single dataframe with all photometry or downloads lightcurves to save_dir
        :param threads: number or processes to use
        :param save_dir: if None then return list of lightcurve dataframes
                         else save lightcurves to specified directory
        :return: list of lightcurve dataframes or list of files names
        """
        # Make sure we query correct collection
        if catalog not in ["asteroids", "comets"]:
            mongo_collection = "phot"
        else:
            mongo_collection = catalog

        # We will only query 1,000 docs at a time
        tar_id_blocks = block_arr(tar_ids, 10000)

        # Build process pool. Each block of ids gets one worker
        with Pool(processes=threads) as pool:
            # Query one block at a time
            result_blocks = [pool.apply_async(self._query_mongo, args=(id_block, mongo_collection, save_dir))
                             for id_block in tar_id_blocks]

            lcs = [curve for block in result_blocks for curve in block.get()]

        if save_dir is not None:
            self.index.to_csv(os.path.join(save_dir, "index.csv"), index=False)
            return lcs
        else:
            lc_df = pd.concat(lcs)
            return LightCurveCollection(lc_df, self.index, id_col='asas_sn_id' if mongo_collection == 'phot'
                                                                                else 'name')

    def _query_mongo(self, id_block, mongo_collection, save_dir=None):
        """
        Converts BAD_Mongo lightcurve doc into dataframe
        Either returns the raw pandas dataframe of the light curve, or writes the lightcurve to csv

        :return:
        """

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


            if save_dir is None:
                lightcurve_df[id_col] = tar_id
                light_curves.append(lightcurve_df)
            else:
                lightcurve_df.to_csv(os.path.join(save_dir, f"{tar_id}.csv"), index=False)
                light_curves.append(f"{tar_id}.csv")

        return light_curves

    @staticmethod
    def arc_to_deg(arc, unit):
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





