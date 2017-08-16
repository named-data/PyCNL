PyCNL: An NDN Common Name Library for Python
============================================

Prerequisites
=============
* Required: Python 2.7 or later
* Required: PyNDN 2.x

Build
=====
Follow the [PyNDN INSTALL](https://github.com/named-data/PyNDN2/blob/master/INSTALL.md)
instructions for your platform, including installing the cryptography package.

You need PyNDN and PyCNL on the Python path.  To temporarily set it, do the following.
If `<PyNDN root>` is the path to the root of the PyNDN distribution, and
`<PyCNL root>` is the path to the root of the PyCNL distribution in a terminal enter:

    export PYTHONPATH=$PYTHONPATH:<PyNDN root>/python:<PyCNL root>/python

Example files are in `<PyCNL root>/examples`. For example in a terminal enter:

    cd <PyCNL root>/examples
    python test_segmented.py

To make the Sphinx documentation, in a terminal change to the doc subdirectory. Enter:
  
    make html

The documentation output is in `doc/_build/html/index.html`.

Files
=====
This has the following example programs:

* examples/test_segmented.py: Connect to an NDN hub with a large file and fetch
  it using SegmentedContent.
* examples/test_nac_producer.py: Connect to the local NFD hub, accept interests
  with prefix /Prefix/SAMPLE (and related encryption key packets) and publish a
  small encrypted, segmented content. See test_nac_consumer.py.
* examples/test_nac_consumer.py: Use SegmentedContent and NacConsumerHandler to
  send interests for the encrypted, segmented content (and related encryption
  key packets) produced by test_nac_producer.py. Print the decrypted content.
