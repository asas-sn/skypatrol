# The Big Astronomy Database for ASAS-SN Light Curves

The pyasassn client allows users to query the ASAS-SN input catalog and retrieve light curves from our database. These light curves are subject to live updates as we are running continuous photometry on our nightly images.

Our input catalog was built on top of ATLAS Refcat v.2 and is cross-matched with GaiaDR2, Tess Input Catalog v.8, Pan-STARRS DR2, and, SDSS (among others). We also include mean astrometry data from Gaia and Pan-STARRS as provided in ATLAS Refcat. This client provides utilities for complex queries based on these values.


## Installation

Make sure your pip points to the appropriate Python >= 3.6 installation...
<pre><code>
    git clone https://github.com/gonzodeveloper/bad_asas_sn.git
    pip3 install bad_asas_sn/
</code></pre>


## Tutorial

Make sure you run this in Python >= 3.6

<pre><code>
  from pyasassn import BadClient
  
  client = BadClient(user="USER", passwd="PASSWORD")
  
  # Show available columns in ASAS-SN Input Catalog
  client.catalog_cols
  
  ['asas_sn_id', 'refcat_id', 'gaia_id', 'tyc_id', 'tmass_id', 'sdss_id', 'allwise_id', 'tic_id', 
   'ra_deg', 'dec_deg', 'plx', 'plx_d', 'pm_ra', 'pm_ra_d', 'pm_dec', 'pm_dec_d', 
   'gaia_mag', 'gaia_mag_d', 'gaia_b_mag', 'gaia_b_mag_d', 'gaia_r_mag', 'gaia_r_mag_d', 
   'gaia_eff_temp', 'gaia_g_extinc', 'gaia_var', 'sfd_g_extinc', 'rp_00_1', 'rp_01', 'rp_10', 
   'pstarrs_g_mag', 'pstarrs_g_mag_d', 'pstarrs_g_mag_chi', 'pstarrs_g_mag_contrib', 
   'pstarrs_r_mag', 'pstarrs_r_mag_d', 'pstarrs_r_mag_chi', 'pstarrs_r_mag_contrib', 
   'pstarrs_i_mag', 'pstarrs_i_mag_d', 'pstarrs_i_mag_chi', 'pstarrs_i_mag_contrib', 
   'pstarrs_z_mag', 'pstarrs_z_mag_d', 'pstarrs_z_mag_chi', 'pstarrs_z_mag_contrib']
  
</code></pre>

There are three utilities which allow us to query the ASAS-SN Input Catalog and download light curves.

### Cone Search
With given center coordinates in decimal degrees (J2000) we can run a cone search of arbitrary radius with units of degrees, arcmin, or arcsec.

<pre>
<code>
client.cone_search(185, -88, radius=5, units='deg')

          asas_sn_id      ra_deg    dec_deg
0            1094902   14.059417 -89.846361
1            1099017  182.038926 -89.804971
2            1105675  309.260296 -89.743042
3            1109079   39.243573 -89.709996
4            1110860  281.009406 -89.701636
5            1113933  118.787441 -89.677189
6            1125650  187.000753 -89.610306
7            1126863  135.324726 -89.603958
8            1129733   61.005088 -89.588192
9            1136069  233.224446 -89.562793
...              ...         ...        ...
249176   77310295457  177.890152 -83.194816
249177        970802  193.425940 -83.183269
249178   77310225365  169.098504 -83.161506
249179   77310282256  192.055578 -83.143194
249180   77310309194  180.884440 -83.134782
249181  266288899297  186.522708 -83.129058
249182        957559  198.861855 -83.127044
249183        984101  184.151716 -83.122621
249184   77310270700  199.919524 -83.097495
249185   77310224936  184.238288 -83.054113


[249186 rows x 3 columns]

</code>
</pre>

### SQL Query 
The BAD severs can parse SQL queries on the targets table. Complex SQL such as nested selects and correlated sub-queries are also supported. 

<pre>
<code>
query = """
        SELECT 
          asas_sn_id,
          tic_id,
          allwise_id,
          ra_deg,
          dec_deg
        FROM targets
        WHERE 1=1
          AND allwise_id IS NOT NULL
          AND pstarrs_g_mag &lt 15
       """

client.sql_query(query)

           asas_sn_id     tic_id           allwise_id      ra_deg    dec_deg
0        335007692536   29672224  J054720.68+181245.5   86.836242  18.212632
1        335007711317  175232392  J083856.50+181238.2  129.735429  18.210610
2        335007722570  355927639  J170355.89+181248.0  255.982901  18.213350
3        335007723070  361655780  J194555.19+181253.4  296.479989  18.214856
4        206159731552  258784214  J221104.82+181239.1  332.770081  18.210851
5        335007693701    6658326  J052439.46+181319.7   81.164422  18.222147
6        335007728881  383621370  J163306.57+181301.9  248.277438  18.217186
7        206159695117  256356113  J195959.47+181322.7  299.997786  18.223022
8        335007688516   27438894  J051128.04+181355.4   77.866858  18.232072
9        335007704147   57127916  J064745.82+181343.6  101.940962  18.228807
...               ...        ...                  ...         ...        ...
2622005  309238127672  169848348  J080211.56-080118.3  120.548191  -8.021806
2622006  292058838531  187311455  J134837.86-080107.2  207.157786  -8.018711
2622007  292058848628  145961671  J171224.21-080124.8  258.101040  -8.023628
2622008  292058846883  443370873  J062722.29-080032.2   96.842904  -8.008945
2622009  292058847558   25189326  J063220.25-080031.4   98.084387  -8.008735
2622010  292058865968  242900779  J194323.54-080037.6  295.848131  -8.010480
2622011  309238127813  318557583  J071848.09-080015.0  109.700389  -8.004193
2622012  292058850385  192717646  J150230.19-080023.7  225.625805  -8.006642
2622013  309238116904  124460100  J191314.47-080020.5  288.310276  -8.005748
2622014  292058841663  250974865  J223239.69-080007.7  338.165461  -8.002239

[2622015 rows x 5 columns]

</code>
</pre>

### Catalog ID Lists
Users can directly query the ASAS-SN input catalog with lists of IDs from our cross-matched catalogs. 

<pre>
<code>
tic_ids = [6658326, 46783395, 1021890]

client.query_list(tic_ids, source='tic')
     asas_sn_id      ra_deg    dec_deg
0  335007699083   97.045759  18.214838
1  335007693701   81.164422  18.222147
2  309238124040  329.260377  -8.035864


</code>
</pre>

### Random Sample 
We can also sample n random curves. **Note**, in this case we are going to actually load the light curves.

<pre>
<code>
client.random_sample(n=100, mode='load_curves')
     cams            jd      flux  flux_err        mag    mag_err      limit  fwhm    asas_sn_id
0      bB  2.458628e+06  3.282811  0.051306  15.109451   0.016988  17.877222  2.10  137439074977
1      bB  2.458643e+06  3.061332  0.023908  15.185290   0.008489  18.706295  2.07  137439074977
2      bB  2.458775e+06  3.300841  0.080369  15.103504   0.026465  17.389923  2.03  137439074977
3      bB  2.458647e+06  3.092052  0.020001  15.174448   0.007031  18.900014  1.98  137439074977
4      bB  2.458683e+06  3.187874  0.109550  15.141313   0.037353  17.053613  2.02  137439074977
5      bB  2.458646e+06  3.191097  0.024217  15.140216   0.008249  18.692344  2.03  137439074977
6      bB  2.458660e+06  3.165176  0.043094  15.149071   0.014799  18.066601  2.06  137439074977
7      bB  2.458679e+06  3.021726  0.070765  15.199428   0.025455  17.528091  2.11  137439074977
8      bB  2.458465e+06  3.124673  0.018656  15.163054   0.006490  18.975604  2.25  137439074977
9      bB  2.458780e+06  3.310110  0.045485  15.100459   0.014936  18.007975  2.02  137439074977
...   ...           ...       ...       ...        ...        ...        ...   ...           ...
8750   bH  2.458576e+06  0.801258  0.043365  16.640635   0.058827  18.059795  1.40  644245325039
8751   bH  2.458864e+06 -0.123485  0.141682  16.774357  99.999000  16.774357  1.38  644245325039
8752   bH  2.458744e+06  0.911320  0.121939  16.500889   0.145440  16.937285  2.07  644245325039
8753   bH  2.458570e+06  1.059508  0.066840  16.337305   0.068572  17.590043  1.43  644245325039
8754   bH  2.458742e+06  0.745269  0.061878  16.719283   0.090247  17.673803  1.45  644245325039
8755   bH  2.458722e+06  0.898726  0.048800  16.515997   0.059020  17.931600  1.48  644245325039
8756   bH  2.458658e+06  0.721557  0.067586  16.754389   0.101811  17.578007  1.43  644245325039
8757   bH  2.458646e+06  0.868027  0.054198  16.553733   0.067867  17.817688  1.45  644245325039
8758   bH  2.458572e+06  0.838636  0.051550  16.591132   0.066814  17.872071  1.41  644245325039
8759   bH  2.458873e+06  1.244925  0.297442  15.969134  99.999000  15.969134  1.52  644245325039
8760   bH  2.458597e+06  1.019070  0.098528  16.379555   0.105092  17.168739  1.44  644245325039

</code>
</pre>

### Downloading Light Curves
The previous three functions also accept parameters to download light curves. The function will return the csv filenames in the save dir. An index file will also be created in the **save_dir**.
<pre>
<code>
tic_ids = [6658326, 46783395, 1021890]

client.query_list(tic_ids, source='tic', mode='load_curves', save_dir='tmp/')

['309238124040.csv', '335007693701.csv', '335007699083.csv']

</code>
</pre>


### Notes

For any of these functions the client can run in two modes **index or load_curves**: 
**index** will simply return the subset of the ASAS-SN Input Catalog as a dataframe
**load_curves** will either return a dataframe containg photometry for all selected targets, or will save the light curves as csv files in a specified directory if **save_dir** is set.

Any function called with **load_curves** will acccept **threads** as as parameter. This will fork the process to speed up the de-serialization and formatting for larger numbers of curves. Do not use more **threads** than you have available CPUs on your local machine.

For the **cone_search**, **query_list**, and **random_sample** functions, we can pass a parameter to specify which columns of the ASAS-SN Input Catalog we want returned. If none are specified, then the **asas_sn_id**, **ra_deg**, and **dec_deg** will be returned.
