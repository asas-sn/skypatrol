from setuptools import setup

setup(name='pyasassn',
      version='0.3.13',
      url="https://github.com/gonzodeveloper/bad_asas_sn/",
      author='Kyle Hart',
      author_email='kylehart@hawaii.edu',
      license='GPL v.3',
      packages=['pyasassn'],
      install_requires=['requests', 'pymongo', 'pandas==1.0.5', 'pyarrow'],
      zip_safe=False)
