.. pyasassn documentation master file, created by
   sphinx-quickstart on Wed Dec 16 15:50:52 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.


ASAS-SN Sky Patrol
==========================================

The All-Sky Automated Survey for Supernovae (ASAS-SN) project has been scanning the night sky for years in search of supernovae and other bright transients. With our worldwide network of robotic 14-cm telescopes we can image the enitre sky nightly down to 18.5 magnitudes (g-band). 

The Sky Patrol initiative aims to provide the community with real-time (as well as historical) photometry data for over 100 million targets accross the sky. After each observation clears our image processing pipeline we run photometry on all present targets as given by our input catalogs. These photometric points are appended to the light curves in our database and immediately available to the public.

The pyasassn tool gives astronomers and data scientists a streamlined python client to interact with our photometry database's API. We have included utilities for target lookup, as well as light curve downloads and visualizations.


.. toctree::
   :maxdepth: 8
   :caption: Contents:
   
   getting_started
   queries
   lightcurves
   additional
   website  
   pyasassn
   license

