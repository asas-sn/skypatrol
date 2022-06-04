Catalog Query Tools
===================


To retreive ASAS-SN light curves you will need to query our input catalogs for the appropriate **asas_sn_id**.
We have included tools for cone searches, ADQL queries, random samples, and external catalog ID lookups.

Cone Searches
-------------

By leveraging state-of-the-art database technologies, ASAS-SN Sky Patrol allows users to run arbitrary cone searches for thousands of targets across the sky in mere seconds.

.. doctest ::

    >>> client.cone_search(ra_deg=270, dec_deg=88, radius=4, catalog='master_list')

             asas_sn_id      ra_deg    dec_deg      catalog_sources
    0        8590494153  270.508480  84.120395  [stellar_main, tic]
    1        8590493551  257.333476  84.119978  [stellar_main, tic]
    2        8590494160  273.628334  84.120183  [stellar_main, tic]
    3        8590494620  282.208531  84.120019  [stellar_main, tic]
    4        8590493763  257.575614  84.119906  [stellar_main, tic]
    ...             ...         ...        ...                  ...
    82247  317828630672  272.518828  89.284092  [stellar_main, tic]
    82248  317828630205    0.339976  89.284143  [stellar_main, tic]
    82249  317828630428  142.968424  89.283984  [stellar_main, tic]
    82250  317828630825  353.474920  89.284470  [stellar_main, tic]
    82251  317828648971   71.616242  89.752714  [stellar_main, tic]

    [82252 rows x 4 columns]


This function accepts both decimal-degree and 'HH:MM:SS(.SS)"/"DD:MM:SS(.SS)" sexigesimal strings for RA and DEC respectively. Moreover, the default unit for the radius is 'degrees'. For more see documentation.

Random Samples
--------------

If the user is interested in random samples of our data, we have included a utility just for them. Random samples upto 1 million targets can be taken from any of our input catalogs.

.. doctest ::

    >>> client.random_sample(1000, catalog="aavsovsx")

          asas_sn_id     ra_deg   dec_deg                          name
    0         1090547  192.31758 -88.18822                  CSTAR 016836
    1     17181184668  299.57819 -86.02709         WISE J195818.7-860137
    2          506225  169.05404 -84.50047         WISE J111612.9-843001
    3          518087  121.09946 -84.43044           ASAS J080423-8425.8
    4          499034  175.15832 -84.10648  ASASSN-V J114038.00-840623.3
    ...            ...        ...       ...                           ...
    995  352188417258  329.85080 -42.80990                    HIP 108556
    996  412317507889  263.86131 -42.64240  ASASSN-V J173526.71-423832.6
    997  661427711166  133.33059 -42.64235           GDS_J0853193-423832
    998  352187588956  118.38509 -42.64223  ASASSN-V J075332.42-423832.0
    999  661427711168  253.03455 -42.64222    [HHR2012] J165208.3-423832

    [1000 rows x 4 columns]

Catalog ID Lookups
------------------

If the user is interested in a particular target or list of targets for which they already have an external ID, they can use our **query_list** function for direct lookups. To use this function, the user must specify the catalog and ID column they are searching against. 

For example, a user searching multiple TIC IDs would run the following code.

.. doctest :: 

    >>> my_tic_ids = [6658326, 46783395, 1021890]
    >>> client.query_list(my_tic_ids, catalog='stellar_main', id_col='tic_id')

         asas_sn_id      ra_deg    dec_deg    tic_id
    0  309238124040  329.260377  -8.035864   1021890
    1  335007699083   97.045759  18.214838  46783395
    2  335007693701   81.164422  18.222147   6658326


.. note::
   These three utilities (cone_search, random_sample, and query_list) allow users to specify catalog and columns of interest    in the parameters.
   
   This is not the case with the following ADQL utiliy. Rather, ADQL will specify columns and catalogs in the query string.

ADQL Queries
------------

To assist astronomers and data scientists with complex queries, we have included a mechinism that accepts ADQL grammar to query our input tables. In addition to the functionality of traditional ADQL, we have included support for Common Table Expressions, WINDOW functions, correlated subqueries and UNIONS. 

Moreover, we have have also removed geometry functions such as BOX, CIRCLE, AREA, POINT and CONTAINS. Instead we have written a DISTANCE function to accomplish cone searches and find nearest neighbors.

A simple cone search to would be written as follows. 

.. doctest ::

    >>> query_str = """
    ...   SELECT
    ...     asas_sn_id, ra_deg, dec_deg
    ...   FROM stellar_main
    ...   WHERE DISTANCE(ra_deg, dec_deg, 270, -88) <= 5.1 """
    >>> client.adql_query(query_str)
              asas_sn_id      ra_deg    dec_deg
    0            1094902   14.059417 -89.846361
    1            1099017  182.038926 -89.804971
    2            1105675  309.260296 -89.743042
    3            1109079   39.243573 -89.709996
    4            1110860  281.009406 -89.701636
    ...              ...         ...        ...
    245123   77310219747  256.853379 -83.001130
    245124   77310248925  260.635568 -82.997364
    245125  266288894288  276.533820 -82.974527
    245126   77310240409  278.626894 -82.946876
    245127   77310268049  263.648603 -82.935546

    [245128 rows x 3 columns]


We can also write more complex queries. Lets say that we were looking for white dwarfs in the stellar_main catalog that have entries in the AAVSO catalog. 

.. doctest ::

    >>> query = """
    ... SELECT 
    ...   asas_sn_id,
    ...   gaia_id,
    ...   pstarrs_g_mag,
    ...   (gaia_mag - (5 * LOG10(plx) - 10)) AS g_mag_abs, 
    ...   name 
    ... FROM stellar_main 
    ... JOIN aavsovsx USING(asas_sn_id)
    ... WHERE 1=1
    ...  AND pstarrs_g_mag < 14 
    ...  AND (gaia_mag - (5 * LOG10(plx) - 10)) > 10
    ...  AND (gaia_b_mag - gaia_r_mag) < 1.5 
    ... """
    >>> client.adql_query(query)
             asas_sn_id              gaia_id  pstarrs_g_mag  g_mag_abs                          name
    0            283310  5784483772687631616         11.838  20.976036  ASASSN-V J132541.88-795516.2
    1            433794  2245186702219362816         13.460  22.189073  ASASSN-V J204415.17+641907.8
    2            570001  2197067464884375040          8.113  14.130535               TYC 4254-2584-1
    3           1350030  2105467632210708096         12.880  20.537968                   KIC 7018521
    4        8590161897  2203889767037608576          4.460  13.575475                       nu. Cep
    ...             ...                  ...            ...        ...                           ...
    86597  661425116212  5351127310598407680         12.337  23.367740           GDS_J1043139-575342
    86598  661425194521  5816920980613874176         12.403  22.073054  ASASSN-V J170046.29-640051.9
    86599  661425300532  5869798938696312320         12.642  22.770550           GDS_J1324289-593640
    86600  661425432124  5241367772080625280         11.742  24.019660           ASAS J104456-6351.7
    86601  661425530752  6055983193972528128          9.316  21.456082                     HD 113013
    
    [86602 rows x 5 columns]

Our full ADQL grammar is available further in the documentation.

