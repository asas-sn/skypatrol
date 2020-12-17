from setuptools import setup

setup(name='pyasassn',
      version='0.4.12',
      url="https://github.com/asas_sn/skypatrol/",
      author='Kyle Hart',
      author_email='kylehart@hawaii.edu',
      license='GPL v.3',
      packages=['pyasassn'],
      install_requires=['requests', 'pymongo', 'pandas==1.0.5', 'pyarrow==0.17.1', 'astropy==4.0.1', 'numpy==1.16.0'],
      zip_safe=False)
