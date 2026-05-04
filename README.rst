python-androidtv-wifi
=====================

This package is a fork of `python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_
that adds support for **modern ADB Wi-Fi pairing** — the 6-digit-code TLS
pairing flow introduced in Android 11's "Wireless debugging" feature, plus
the post-pairing TLS data channel and mDNS-based service discovery.

It exists primarily as a testbed for verifying that Wi-Fi pairing support
can be added to Home Assistant's Android TV integration. If you do not
need Wi-Fi pairing, install upstream ``androidtv`` instead — the upstream
package is the canonical home of all non-Wi-Fi functionality.

Original ``androidtv`` documentation: https://androidtv.readthedocs.io

About
-----

``androidtv_wifi`` is a Python package that provides state information and
control of Android TV and Fire TV devices via ADB, including modern ADB
Wi-Fi pairing. It depends on `adb-shell-wifi <https://pypi.org/project/adb-shell-wifi/>`_
(a corresponding fork of `adb-shell <https://github.com/JeffLIrion/adb_shell>`_).


Installation
------------

.. code-block::

   pip install androidtv-wifi


To utilize the async version of this code, you must install into a Python 3.7+ environment via:

.. code-block::

   pip install androidtv-wifi[async]


ADB Wi-Fi (TLS) support
-----------------------

Modern Android (11+) deprecates the legacy ``adb tcpip`` flow in favor
of ADB Wi-Fi, which uses a one-shot pairing handshake plus a TLS 1.3
data channel on a randomized port advertised over mDNS.

Install with the ``wifi`` extra:

.. code-block::

   pip install androidtv-wifi[wifi]

Then either pass ``connection_type="tls"`` to ``setup()`` /
``BaseTVAsync`` / etc., or construct the device classes directly:

.. code-block:: python

   from androidtv_wifi import setup
   from androidtv_wifi.wifi import pair, discover_connect_services

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

This fork is based on `python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_ by Jeff Irion, which itself is based on `python-firetv <https://github.com/happyleavesaoc/python-firetv>`_ by happyleavesaoc and the `androidtv component for Home Assistant <https://github.com/a1ex4/home-assistant/blob/androidtv/homeassistant/components/media_player/androidtv.py>`_ by a1ex4. This fork depends on `adb-shell-wifi <https://pypi.org/project/adb-shell-wifi/>`_ (a fork of `adb-shell <https://github.com/JeffLIrion/adb_shell>`_, which is based on `python-adb <https://github.com/google/python-adb>`_) and `pure-python-adb <https://github.com/Swind/pure-python-adb>`_.
