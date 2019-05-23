====================
Outpost Django Video
====================

.. start-badges

.. list-table::
    :stub-columns: 1

    * - docs
      - |docs|
    * - tests
      - | |travis| |requires|
        | |codecov|

.. |docs| image:: https://readthedocs.org/projects/outpost/badge/?style=flat
    :target: https://readthedocs.org/projects/outpost.django.video
    :alt: Documentation Status

.. |travis| image:: https://travis-ci.org/medunigraz/outpost.django.video.svg?branch=master
    :alt: Travis-CI Build Status
    :target: https://travis-ci.org/medunigraz/outpost.django.video

.. |requires| image:: https://requires.io/github/medunigraz/outpost.django.video/requirements.svg?branch=master
    :alt: Requirements Status
    :target: https://requires.io/github/medunigraz/outpost.django.video/requirements/?branch=master

.. |codecov| image:: https://codecov.io/github/medunigraz/outpost.django.video/coverage.svg?branch=master
    :alt: Coverage Status
    :target: https://codecov.io/github/medunigraz/outpost.django.video

.. end-badges

Manage video recording equipment and recordings.

* Free software: BSD license

Documentation
=============

https://outpost.django.video.readthedocs.io/

Development
===========

To run the all tests run::

    tox

Note, to combine the coverage data from all the tox environments run:

.. list-table::
    :widths: 10 90
    :stub-columns: 1

    - - Windows
      - ::

            set PYTEST_ADDOPTS=--cov-append
            tox

    - - Other
      - ::

            PYTEST_ADDOPTS=--cov-append tox
