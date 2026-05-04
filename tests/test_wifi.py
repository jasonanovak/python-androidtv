"""Tests for the ``androidtv.wifi`` helper module.

These tests exercise the forwarding semantics — that arguments and
return values flow through the wrappers correctly — without invoking
real pairing / mDNS, both of which require physical hardware.
"""

import asyncio
from contextlib import asynccontextmanager
import sys
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, "..")

from androidtv_wifi import wifi


PEM_PRIV = b"-----BEGIN PRIVATE KEY-----\nfake-priv\n-----END PRIVATE KEY-----\n"
PEM_PUB = b"ssh-rsa fake-pub user@host\n"


class _ReadBytes:
    """Async-readable file stub returning preconfigured bytes."""

    def __init__(self, data):
        self._data = data

    async def read(self):
        return self._data


def _async_open_factory(by_name):
    """Build an `aiofiles.open` substitute that returns bytes by filename."""

    @asynccontextmanager
    async def fake_open(infile, mode="rb"):
        yield _ReadBytes(by_name[infile])

    return fake_open


def _sync_open_factory(by_name):
    """Build a synchronous `open()` substitute keyed by filename."""

    def fake_open(infile, mode="rb"):
        return mock_open(read_data=by_name[infile]).return_value

    return fake_open


def _await(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestPairSync(unittest.TestCase):
    """`wifi.pair` reads the keys from disk and forwards to `_pair`."""

    def test_pair_forwards_args(self):
        captured = {}

        def fake_pair(host, port, code, priv, pub, timeout_s):
            captured.update(
                host=host, port=port, code=code, priv=priv, pub=pub, timeout_s=timeout_s
            )
            return "PEER_INFO_SENTINEL"

        files = {"adbkey": PEM_PRIV, "adbkey.pub": PEM_PUB}
        with patch("androidtv_wifi.wifi._pair", fake_pair), patch(
            "androidtv_wifi.wifi.open", _sync_open_factory(files)
        ):
            result = wifi.pair("HOST", 1234, "ABCDEF", "adbkey", timeout_s=7.5)

        self.assertEqual(result, "PEER_INFO_SENTINEL")
        self.assertEqual(captured["host"], "HOST")
        self.assertEqual(captured["port"], 1234)
        self.assertEqual(captured["code"], "ABCDEF")
        self.assertEqual(captured["priv"], PEM_PRIV)
        self.assertEqual(captured["pub"], PEM_PUB)
        self.assertEqual(captured["timeout_s"], 7.5)

    def test_pair_raises_when_extra_missing(self):
        with patch("androidtv_wifi.wifi._PAIRING_AVAILABLE", False):
            with self.assertRaises(ImportError):
                wifi.pair("HOST", 1234, "ABCDEF", "adbkey")


class TestPairAsync(unittest.TestCase):
    """`wifi.pair_async` reads keys via aiofiles and forwards to `_pair_async`."""

    def test_pair_async_forwards_args(self):
        captured = {}

        async def fake_pair_async(host, port, code, priv, pub, timeout_s):
            captured.update(
                host=host, port=port, code=code, priv=priv, pub=pub, timeout_s=timeout_s
            )
            return "PEER_INFO_SENTINEL"

        files = {"adbkey": PEM_PRIV, "adbkey.pub": PEM_PUB}
        with patch("androidtv_wifi.wifi._pair_async", fake_pair_async), patch(
            "androidtv_wifi.wifi.aiofiles.open", _async_open_factory(files)
        ):
            result = _await(wifi.pair_async("HOST", 1234, "ABCDEF", "adbkey", timeout_s=7.5))

        self.assertEqual(result, "PEER_INFO_SENTINEL")
        self.assertEqual(captured["priv"], PEM_PRIV)
        self.assertEqual(captured["pub"], PEM_PUB)
        self.assertEqual(captured["timeout_s"], 7.5)


class TestDiscovery(unittest.TestCase):
    """Discovery wrappers forward timeout to the underlying adb_shell helpers."""

    def test_discover_connect_services_forwards_timeout(self):
        with patch("androidtv_wifi.wifi._discover_connect_services", return_value=["a", "b"]) as m:
            result = wifi.discover_connect_services(timeout_s=2.5)
        self.assertEqual(result, ["a", "b"])
        m.assert_called_once_with(timeout_s=2.5)

    def test_discover_pairing_services_forwards_timeout(self):
        with patch("androidtv_wifi.wifi._discover_pairing_services", return_value=[]) as m:
            wifi.discover_pairing_services(timeout_s=1.0)
        m.assert_called_once_with(timeout_s=1.0)

    def test_discover_connect_services_async_forwards_timeout(self):
        async def fake(timeout_s):
            return ["service-x"]

        with patch("androidtv_wifi.wifi._discover_connect_services_async", fake):
            result = _await(wifi.discover_connect_services_async(timeout_s=3.0))
        self.assertEqual(result, ["service-x"])

    def test_discover_raises_when_extra_missing(self):
        with patch("androidtv_wifi.wifi._MDNS_AVAILABLE", False):
            with self.assertRaises(ImportError):
                wifi.discover_connect_services()
            with self.assertRaises(ImportError):
                _await(wifi.discover_pairing_services_async())
