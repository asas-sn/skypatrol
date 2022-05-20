from setuptools import setup

setup(name='pyasassn',
      version='0.6.4',
      url="https://github.com/asas_sn/skypatrol/",
      author='Kyle Hart',
      author_email='kylehart@hawaii.edu',
      license='GPL v.3',
      packages=['pyasassn'],
      install_requires=[
            'requests',
            'pandas',
            'pyarrow==4.0.1',
            'astropy',
            'numpy'],
      zip_safe=False)
