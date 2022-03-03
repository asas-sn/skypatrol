from setuptools import setup

setup(name='pyasassn',
      version='0.5.5',
      url="https://github.com/asas_sn/skypatrol/",
      author='Kyle Hart',
      author_email='kylehart@hawaii.edu',
      license='GPL v.3',
      packages=['pyasassn'],
      install_requires=[
            'requests',
            'pymongo',
            'sqlalchemy',
            'pandas',
            'pyarrow==4.0.1',
            'astropy',
            'numpy',
            'pymysql'],
      zip_safe=False)
