from __future__ import division, print_function

import sys
import pytest

from ..client import SkyPatrolClient

# Initialise client connection
client = SkyPatrolClient()


def test_client_connection():
    # Ensure we get some catalogs back
    assert len(client.catalogs.counts) > 0


def test_random_sample():
    assert len(client.random_sample(100, catalog="aavsovsx")) == 100


def test_adql_query():
    query = """
    SELECT
    * 
    FROM stellar_main 
    WHERE DISTANCE(ra_deg, dec_deg, 270, -88) <= 0.05
    """
    res = client.adql_query(query)
    assert len(res) > 0


def test_list_query():
    tic_ids = [6658326, 46783395, 1021890]
    assert len(client.query_list(tic_ids, catalog="stellar_main", id_col="tic_id")) == 3
