How WT <-> CoReRe integration could look like...
################################################

|GitHub Project| |nsf-badge|

Description
===========

A mock CORERE integration

Installation
============

.. code-block:: shell

    virtualenv -p /usr/bin/python3.8 venv  # at least 3.8 required
    . ./venv/bin/activate
    pip install -r requirements.txt

Usage
=====

.. code-block:: shell

    export GIRDER_API_KEY=...  # assumes you have girder.local running and created the key
    python workflow.py

Acknowledgements
================

This material is based upon work supported by the National Science Foundation under Grant No. OAC-1541450.

.. |GitHub Project| image:: https://img.shields.io/badge/GitHub--blue?style=social&logo=GitHub
   :target: https://github.com/whole-tale/tracingfs

.. |nsf-badge| image:: https://img.shields.io/badge/NSF-154150-blue.svg
    :target: https://www.nsf.gov/awardsearch/showAward?AWD_ID=1541450
    :alt: NSF Grant Badge

