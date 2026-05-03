python-androidtv
================

.. image:: https://travis-ci.com/JeffLIrion/python-androidtv.svg?branch=master
   :target: https://travis-ci.com/JeffLIrion/python-androidtv
   :alt: Build Status
.. image:: https://coveralls.io/repos/github/JeffLIrion/python-androidtv/badge.svg
   :target: https://coveralls.io/github/JeffLIrion/python-androidtv
   :alt: Coverage Status
.. image:: https://pepy.tech/badge/androidtv
   :target: https://pepy.tech/project/androidtv
   :alt: Downloads


Contributions Only
------------------

I no longer have the time to actively work on this project, and so all future development will be from pull requests submitted by the community.  What I will do is:

* review pull requests that pass all of the CI checks
* publish new releases upon request


About
-----

Documentation for this package can be found at `https://androidtv.readthedocs.io <https://androidtv.readthedocs.io>`_.

``androidtv`` is a Python package that provides state information and control of Android TV and Fire TV devices via ADB.  This package is used by the `Android TV <https://www.home-assistant.io/components/androidtv/>`_ integration in Home Assistant.


Installation
------------

.. code-block::

   pip install androidtv


To utilize the async version of this code, you must install into a Python 3.7+ environment via:

.. code-block::

   pip install androidtv[async]


ADB Wi-Fi (TLS) support
-----------------------

Modern Android (11+) deprecates the legacy ``adb tcpip`` flow in favor
of ADB Wi-Fi, which uses a one-shot pairing handshake plus a TLS 1.3
data channel on a randomized port advertised over mDNS.

Install with the ``wifi`` extra:

.. code-block::

   pip install androidtv[wifi]

Then either pass ``connection_type="tls"`` to ``setup()`` /
``BaseTVAsync`` / etc., or construct the device classes directly:

.. code-block:: python

   from androidtv import setup
   from androidtv.wifi import pair, discover_connect_services

   # One-time pairing — user opens "Pair device with pairing code"
   # in Wireless debugging settings on the TV and reads off the code.
   pair(host=PAIR_IP, port=PAIR_PORT, pairing_code="123456",
        adbkey="/path/to/adbkey")

   # Subsequent connects.  Discover the (random) TLS port via mDNS.
   services = discover_connect_services(timeout_s=4.0)
   tv = setup(host=services[0].host, port=services[0].port,
              adbkey="/path/to/adbkey", connection_type="tls")

The legacy ``connection_type="tcp"`` path (default) is unchanged —
existing users on older Android versions or pre-paired devices using
``adb tcpip`` need to do nothing.


ADB Intents and Commands
------------------------

A collection of useful intents and commands can be found `here <https://gist.github.com/mcfrojd/9e6875e1db5c089b1e3ddeb7dba0f304>`_ (credit: mcfrojd).

Acknowledgments
---------------

This is based on `python-firetv <https://github.com/happyleavesaoc/python-firetv>`_ by happyleavesaoc and the `androidtv component for Home Assistant <https://github.com/a1ex4/home-assistant/blob/androidtv/homeassistant/components/media_player/androidtv.py>`_ by a1ex4, and it depends on the Python packages `adb-shell <https://github.com/JeffLIrion/adb_shell>`_ (which is based on `python-adb <https://github.com/google/python-adb>`_) and `pure-python-adb <https://github.com/Swind/pure-python-adb>`_.
