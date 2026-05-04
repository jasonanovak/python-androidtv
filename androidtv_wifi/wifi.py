"""ADB Wi-Fi (TLS) helpers for ``androidtv``.

Modern Android (11+) replaces the legacy ``adb tcpip`` flow with three
new pieces:

1. **Pairing** — a one-shot SPAKE2 + TLS handshake bootstrapped by a
   6-digit code shown on the device's *Settings → System → Developer
   options → Wireless debugging → Pair device with pairing code* dialog.
2. **TLS data channel** — the established connection itself, used after
   pairing.  This is what ``connection_type="tls"`` enables on the
   regular ``ADBPython{Sync,Async}`` managers.
3. **mDNS discovery** — devices advertise pairing and TLS-connect ports
   as ``_adb-tls-pairing._tcp`` and ``_adb-tls-connect._tcp`` services
   on the local network.

This module is a thin façade over the corresponding APIs in
:mod:`adb_shell.pairing` and :mod:`adb_shell.mdns`, exposed so
downstreams import a single stable surface from ``androidtv`` instead
of reaching across to ``adb_shell`` directly.

Requires the ``[wifi]`` extra (``pip install androidtv[wifi]``).  All
public functions raise :class:`ImportError` with a clear hint if the
extra is not installed.
"""

import aiofiles


_WIFI_EXTRA_HINT = (
    "Wi-Fi support requires the [wifi] extra. "
    "Install it with: pip install androidtv[wifi]"
)


try:
    from adb_shell_wifi.pairing import (  # noqa: F401  (re-exported)
        PairingException,
        PeerInfo,
        pair as _pair,
        pair_async as _pair_async,
    )

    _PAIRING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without [wifi]
    PairingException = None
    PeerInfo = None
    _pair = None
    _pair_async = None
    _PAIRING_AVAILABLE = False

try:
    from adb_shell_wifi.mdns import (  # noqa: F401  (re-exported)
        AdbService,
        SERVICE_TYPE_LEGACY,
        SERVICE_TYPE_PAIRING,
        SERVICE_TYPE_TLS_CONNECT,
        discover_connect_services as _discover_connect_services,
        discover_connect_services_async as _discover_connect_services_async,
        discover_pairing_services as _discover_pairing_services,
        discover_pairing_services_async as _discover_pairing_services_async,
    )

    _MDNS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without [wifi]
    AdbService = None
    SERVICE_TYPE_LEGACY = None
    SERVICE_TYPE_PAIRING = None
    SERVICE_TYPE_TLS_CONNECT = None
    _discover_connect_services = None
    _discover_connect_services_async = None
    _discover_pairing_services = None
    _discover_pairing_services_async = None
    _MDNS_AVAILABLE = False


def _require_pairing():
    if not _PAIRING_AVAILABLE:
        raise ImportError(_WIFI_EXTRA_HINT)


def _require_mdns():
    if not _MDNS_AVAILABLE:
        raise ImportError(_WIFI_EXTRA_HINT)


def _read_keys_sync(adbkey):
    with open(adbkey, "rb") as f:
        priv = f.read()
    with open(adbkey + ".pub", "rb") as f:
        pub = f.read()
    return priv, pub


async def _read_keys_async(adbkey):
    async with aiofiles.open(adbkey, "rb") as f:
        priv = await f.read()
    async with aiofiles.open(adbkey + ".pub", "rb") as f:
        pub = await f.read()
    return priv, pub


def pair(host, port, pairing_code, adbkey, timeout_s=30.0):
    """Pair with a device's wireless-debugging pairing port.

    Reads the user's ``adbkey`` (and ``adbkey.pub``) from disk and runs
    the SPAKE2 + TLS pairing handshake against the device.  On success
    the device persists the host's public key, and subsequent TLS
    connections via ``connection_type="tls"`` will succeed without any
    further user interaction.

    Parameters
    ----------
    host : str
        IP / hostname of the device's pairing port (typically discovered
        via :func:`discover_pairing_services`).
    port : int
        TCP port of the pairing server (also from mDNS).
    pairing_code : str
        The 6-digit code displayed on the device's pairing dialog.
    adbkey : str
        Filesystem path to the user's ``adbkey`` private key.  The
        public key is read from ``adbkey + ".pub"``.
    timeout_s : float
        Pairing handshake timeout in seconds.

    Returns
    -------
    PeerInfo
        Information about the paired device (typically containing its
        GUID in ``peer_info.data``).

    Raises
    ------
    ImportError
        If the ``[wifi]`` extra is not installed.
    PairingException
        If the pairing handshake fails (most commonly: wrong code or
        the device's pairing dialog has timed out).
    """
    _require_pairing()
    priv, pub = _read_keys_sync(adbkey)
    return _pair(host, port, pairing_code, priv, pub, timeout_s=timeout_s)


async def pair_async(host, port, pairing_code, adbkey, timeout_s=30.0):
    """Async equivalent of :func:`pair`.

    See :func:`pair` for parameter and exception semantics.
    """
    _require_pairing()
    priv, pub = await _read_keys_async(adbkey)
    return await _pair_async(host, port, pairing_code, priv, pub, timeout_s=timeout_s)


def discover_pairing_services(timeout_s=4.0):
    """Discover devices currently advertising an ADB pairing service.

    Devices only advertise ``_adb-tls-pairing._tcp`` while the *Pair
    device with pairing code* dialog is open on the TV.

    Returns
    -------
    list[AdbService]
    """
    _require_mdns()
    return _discover_pairing_services(timeout_s=timeout_s)


def discover_connect_services(timeout_s=4.0):
    """Discover paired devices currently advertising a TLS data port.

    The TLS port is randomized every time "Wireless debugging" is
    toggled on the device, so caching it across reboots is unsafe —
    rediscover via mDNS on connection failure.

    Returns
    -------
    list[AdbService]
    """
    _require_mdns()
    return _discover_connect_services(timeout_s=timeout_s)


async def discover_pairing_services_async(timeout_s=4.0):
    """Async equivalent of :func:`discover_pairing_services`."""
    _require_mdns()
    return await _discover_pairing_services_async(timeout_s=timeout_s)


async def discover_connect_services_async(timeout_s=4.0):
    """Async equivalent of :func:`discover_connect_services`."""
    _require_mdns()
    return await _discover_connect_services_async(timeout_s=timeout_s)


__all__ = [
    "AdbService",
    "PairingException",
    "PeerInfo",
    "SERVICE_TYPE_LEGACY",
    "SERVICE_TYPE_PAIRING",
    "SERVICE_TYPE_TLS_CONNECT",
    "discover_connect_services",
    "discover_connect_services_async",
    "discover_pairing_services",
    "discover_pairing_services_async",
    "pair",
    "pair_async",
]
