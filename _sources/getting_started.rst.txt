Getting Started
===============

Before installation, ensure that you have a working Python => 3.6 environment on your machine.
Since this module enforces specific versions of pandas, numpy, and pyarrow it would also be wise to create a new conda-env.

Installation
------------

While we are still in beta release, the only option to download the module is directly through github.::

        git clone https://github.com/asas-sn/skypatrol.git
        pip3 install skypatrol/


Client
------

Once you have received a username and token password you will be able to create a client.
The client object contains information about all available input catalogs.
Sky Patrol input catalogs are generated directly from NASA's HEASARC archive and are searchable by all original columns.
The stellar_main catalog contains the bulk of our targets (> 98 million) and was built from the ATLAS Refcat2 source list; it is cross-matched with both Gaia DR2 and the TESS Input Catalog (TICv8).
The master_list catalog gives all the targets for which we have lightcurves. Our targets are cross-matched accross all our input catalogs with **2 arc second cones**.

.. doctest ::
   
    >>> from pyasassn.client import SkyPatrolClient
    >>> client = SkyPatrolClient()
    >>> client.catalogs

    Table Name: stellar_main
    Num Columns: 47
    Num Targets: 98932961

    Table Name: master_list
    Num Columns: 4
    Num Targets: 103874668

    Table Name: comets
    Num Columns: 1
    Num Targets: 1825

    Table Name: swift
    Num Columns: 56
    Num Targets: 254936

    Table Name: allwiseagn
    Num Columns: 15
    Num Targets: 1354900

    Table Name: mdwarf
    Num Columns: 32
    Num Targets: 8927

    Table Name: milliquas
    Num Columns: 21
    Num Targets: 1979676

    ...

Before you begin queries you can check each input catalog for available columns and data-types.

.. doctest ::

    >>> client.catalogs.master_list
    
             col_names         dtypes
    0       asas_sn_id         bigint
    1           ra_deg         double
    2          dec_deg         double
    3  catalog_sources  array<string>

    >>> client.catalogs.milliquas
    
            col_names  dtypes
    0      asas_sn_id  bigint
    1          ra_deg  double
    2         dec_deg  double
    3            name  string
    4             lii  double
    5             bii  double
    6      broad_type  string
    7            rmag  double
    8            bmag  double
    9    optical_flag  string
    10   red_psf_flag  string
    11  blue_psf_flag  string
    12       redshift  double
    13       ref_name  string
    14   ref_redshift  string
    15       qso_prob  double
    16     radio_name  string
    17      xray_name  string
    18     alt_name_1  string
    19     alt_name_2  string
    20          class  bigint


Notice that **asas_sn_id** is common to all of our input catalogs. This is the mechanism that allows you to pull lightcurves.

