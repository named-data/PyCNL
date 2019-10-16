# -*- Mode: python; py-indent-offset: 4; indent-tabs-mode: nil; coding: utf-8; -*-

from setuptools import setup, find_packages  # Always prefer setuptools over distutils
import sys

requirements = ['PyNDN']

setup(
    name='PyCNL',

    version='0.1b1',

    description='',

    url='https://github.com/named-data/PyCNL',

    maintainer='Jeff Thompson',
    maintainer_email='jefft0@remap.ucla.edu',

    license='LGPLv3',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries',

        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],

    keywords='NDN',

    packages=find_packages('python'),
    package_dir = {'':'python'},

    install_requires=requirements
)
