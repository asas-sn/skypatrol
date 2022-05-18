from base64 import encodebytes
import requests
import pandas as pd
import json
import numpy as np
import multiprocessing
import re
import pyarrow as pa
import warnings
from .utils import LightCurveCollection


class SkyPatrolClient:
    """
            The SkyPatrolClient allows users to interact with the ASAS-SN Sky Patrol photometry database.
        This client enables users to use ADQL, cone searches, random samples, and catalog ID lookups on the input catalogs.

        Queries to the input catalogs will either be returned as pandas DataFrames containing aggregate information
        on astronomical targets, or they will be returned as LightCurveCollections containing photometry data from all
        queried targets.
    """

    def __init__(self):
        """
        Creates SkyPatrolClient object
        """
        self.index = None
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
        query_str = re.sub(r'(\s+)', ' ', query_str)
        query_hash = encodebytes(bytes(query_str, encoding='utf-8')).decode()

        # Query Flask API with SQL bytes
        url = f"http://asassn-lb01.ifa.hawaii.edu:9006/lookup_sql/{query_hash}"
        response = requests.post(url, json={'format': 'arrow',
                                            'download': download})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        tar_df = _deserialize(response)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            # Get lightcurve ids to pull
            tar_ids = list(tar_df['asas_sn_id'])
            # Returns a LightCurveCollection object
            return self._get_curves(query_hash, tar_ids, "extrasolar", threads)

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
        response = requests.post(url, json={'catalog': catalog,
                                            'cols': cols,
                                            'format': 'arrow',
                                            'download': download})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        tar_df = _deserialize(response)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            # Generate query information
            query_id = f"conectr-{radius}_conera-{ra_deg}_conedec-{dec_deg}|catalog-{catalog}|cols-" + "/".join(cols)
            query_hash = encodebytes(bytes(query_id, encoding='utf-8')).decode()

            # Get lightcurve ids to pull
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])

            # Returns a LightCurveCollection object
            return self._get_curves(query_hash, tar_ids, catalog, threads)

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
                                            'format': 'arrow',
                                            'download': download})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        tar_df = _deserialize(response)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            # Get lightcurve ids to pull
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])

            # Generate query information
            query_id = f"listlen-{len(tar_ids)}_listfirst-{tar_ids[0]}_listend-{tar_ids[-1]}" \
                       f"|catalog-{catalog}|id_col-{id_col}|cols-" + "/".join(cols)
            query_hash = encodebytes(bytes(query_id, encoding='utf-8')).decode()

            # Returns a LightCurveCollection object
            return self._get_curves(query_hash, tar_ids, catalog, threads)

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
        response = requests.post(url, json={'catalog': catalog,
                                            'cols': cols,
                                            'format': 'arrow',
                                            'download': download})

        # Check response
        if response.status_code == 400:
            error = json.loads(response.content)['error_text']
            raise RuntimeError(error)

        # Deserialize from arrow
        tar_df = _deserialize(response)
        self.index = tar_df

        if download is False:
            # Return a dataframe of catalog search results
            return tar_df
        else:
            # Get lightcurve ids to pull
            id_col = 'asas_sn_id' if catalog not in ['asteroids', 'comets'] else 'name'
            tar_ids = list(tar_df[id_col])

            # Generate query information
            query_id = f"random-{n}|catalog-{catalog}|cols-" + "/".join(cols)
            query_hash = encodebytes(bytes(query_id, encoding='utf-8')).decode()

            # Returns a LightCurveCollection object
            return self._get_curves(query_hash, tar_ids, catalog, threads)

    def _get_curves(self, query_hash, tar_ids, catalog, threads=1):
        # Get number of id chunks
        n_chunks = int(np.ceil(len(tar_ids) / 1000))

        # Get targets via mutlithreaded requests

        with multiprocessing.Pool(processes=threads) as pool:
            results = [pool.apply_async(self._get_lightcurve_chunk, args=(query_hash, idx, catalog,))
                       for idx in range(n_chunks)]

            lc_dfs = [r.get() for r in results]

        # lc_dfs = [self._get_lightcurve_chunk(query_hash, idx, catalog) for idx in range(n_chunks)]
        data = pd.concat(lc_dfs)
        return LightCurveCollection(data, self.index,
                                    id_col='asas_sn_id'
                                        if catalog not in ['asteroids', 'comets']
                                        else 'name')


    def _get_lightcurve_chunk(self, query_hash, block_idx, catalog):
        # Query API with (POST METHOD)
        server = (block_idx % 3) + 1
        url = f"http://asassn-data{server:02d}.ifa.hawaii.edu:9006/get_block/" \
              f"query_hash-{query_hash}-block_idx-{block_idx}-catalog-{catalog}"
        response = requests.get(url)

        # Return as dataframe
        return _deserialize(response)


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


def _deserialize(response):
    # Deserialize from arrow
    with warnings.catch_warnings():
        warnings.simplefilter(action='ignore', category=FutureWarning)
        buff = pa.py_buffer(response.content)
        return pa.deserialize(buff)


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

