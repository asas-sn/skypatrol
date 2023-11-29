#!/usr/bin/env python

import os
import sys
from setuptools import setup, Extension

# Prepare and send a new release to PyPI
# if "release" in sys.argv[-1]:
#     os.system("python setup.py sdist bdist_wheel")
#     os.system("twine upload dist/*")
#     os.system("rm -rf dist/skypatrol*")
#     sys.exit()

# Load the __version__ variable without importing the package already
# exec(open("skypatrol/version.py").read())

# Get dependencies
with open("requirements.txt") as f:
    install_requires = f.read().splitlines()

setup(
    name="skypatrol",
    version="0.6.16",
    url="https://github.com/asas_sn/skypatrol/",
    author="ASAS-SN",
    author_email="kylehart@hawaii.edu",
    license="GPL v.3",
    packages=["pyasassn"],
    install_requires=install_requires,
    zip_safe=False,
)
