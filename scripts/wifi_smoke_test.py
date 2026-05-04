#!/usr/bin/env python3
"""End-to-end smoke test for ADB Wi-Fi support in python-androidtv.

This script exercises the new ``connection_type="tls"`` path against a
real Android TV (Android 11+) with Wireless debugging enabled.  It is
the manual counterpart to the unit tests under ``tests/`` — the unit
tests prove the wiring is correct, this proves the wiring works
against a real device.

Run the steps in order.  Each is independent and can be re-run.

    # 0. (One-time) install the wifi extra into your venv
    pip install -e '.[wifi]'

    # 1. Discover devices broadcasting on the LAN
    python scripts/wifi_smoke_test.py discover

    # 2. (Once per device) pair — open the "Pair device with pairing
    #    code" dialog on the TV first, then read off IP/port/code.
    python scripts/wifi_smoke_test.py pair \\
        --host 192.168.1.42 --port 37123 --code 482915 \\
        --adbkey ~/.android/adbkey

    # 3. Connect over TLS and run a shell command.  Use the TLS port
    #    from the discover step (NOT the pairing port from step 2 —
    #    they are different and the TLS port changes on every
    #    "Wireless debugging" toggle).
    python scripts/wifi_smoke_test.py connect \\
        --host 192.168.1.42 --port 41877 \\
        --adbkey ~/.android/adbkey

    # 4. (Regression) confirm the legacy `adb tcpip` path still works
    #    against a device on port 5555.
    python scripts/wifi_smoke_test.py legacy \\
        --host 192.168.1.42 --port 5555 \\
        --adbkey ~/.android/adbkey

    # 5. End-to-end (steps 1 + 3): discover, then connect to the
    #    first matching device.  Skips pairing — assumes already paired.
    python scripts/wifi_smoke_test.py all \\
        --adbkey ~/.android/adbkey

The script uses the *async* code paths because that's what Home
Assistant exercises.  Sync versions exist in ``androidtv`` and behave
the same; if you want to spot-check them, change ``setup_async`` to
``setup`` and remove the ``await``s.
"""

import argparse
import asyncio
import logging
import os
import sys
import traceback


# Allow `python scripts/wifi_smoke_test.py ...` to find the package
# without first installing it.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(levelname)-8s %(name)s: %(message)s"
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


async def cmd_discover(args):
    """Sweep the LAN for ADB Wi-Fi services and print what we find."""
    from androidtv_wifi.wifi import (
        discover_pairing_services_async,
        discover_connect_services_async,
    )

    print("[discover] looking for pairing services (only present while the")
    print("[discover]   'Pair device with pairing code' dialog is open) ...")
    pairing = await discover_pairing_services_async(timeout_s=args.timeout)
    if pairing:
        for s in pairing:
            print(f"  PAIR    name={s.name!r} host={s.host} port={s.port}")
    else:
        print("  (none — that's normal unless the dialog is open right now)")

    print()
    print("[discover] looking for TLS-connect services (paired devices) ...")
    connect = await discover_connect_services_async(timeout_s=args.timeout)
    if connect:
        for s in connect:
            print(f"  CONNECT name={s.name!r} host={s.host} port={s.port}")
    else:
        print("  (none — make sure the device's Wireless debugging is ON,")
        print("   and that mDNS can reach it from this machine)")

    return 0 if (pairing or connect) else 1


async def cmd_pair(args):
    """Pair with a device using the 6-digit code shown in its dialog."""
    from androidtv_wifi.wifi import pair_async, PairingException

    print(f"[pair] pairing with {args.host}:{args.port} using code {args.code!r}")
    try:
        peer = await pair_async(
            host=args.host,
            port=args.port,
            pairing_code=args.code,
            adbkey=args.adbkey,
            timeout_s=args.timeout,
        )
    except PairingException as exc:
        print(f"[pair] FAILED: {type(exc).__name__}: {exc}")
        if args.verbose:
            traceback.print_exc()
        return 2

    print("[pair] OK")
    print(f"[pair] peer info: type={peer.type!r} data={peer.data!r}")
    return 0


async def _connect_and_probe(host, port, adbkey, connection_type, transport_timeout, auth_timeout):
    """Shared connect+probe used by `connect` and `legacy`."""
    from androidtv_wifi import setup_async

    print(f"[connect] {connection_type.upper()} {host}:{port} adbkey={adbkey}")
    tv = await setup_async.setup(
        host=host,
        port=port,
        adbkey=adbkey,
        device_class="auto",
        connection_type=connection_type,
        transport_timeout_s=transport_timeout,
        auth_timeout_s=auth_timeout,
    )
    try:
        if not tv.available:
            print(f"[connect] FAILED: setup returned but tv.available is False")
            return 3

        props = tv.device_properties or {}
        print(f"[connect] OK — type={type(tv).__name__}")
        print(f"[connect]   manufacturer={props.get('manufacturer')!r}")
        print(f"[connect]   model={props.get('model')!r}")
        print(f"[connect]   sw_version={props.get('sw_version')!r}")
        print(f"[connect]   serialno={props.get('serialno')!r}")

        # An extra round-trip to prove the channel keeps working.
        out = await tv.adb_shell("getprop ro.product.brand")
        print(f"[connect] shell 'getprop ro.product.brand' -> {out!r}")
        return 0
    finally:
        try:
            await tv.adb_close()
        except Exception:
            pass


async def cmd_connect(args):
    return await _connect_and_probe(
        args.host, args.port, args.adbkey, "tls",
        args.transport_timeout, args.auth_timeout,
    )


async def cmd_legacy(args):
    return await _connect_and_probe(
        args.host, args.port, args.adbkey, "tcp",
        args.transport_timeout, args.auth_timeout,
    )


async def cmd_all(args):
    """Discover, then connect to the first TLS service found."""
    from androidtv_wifi.wifi import discover_connect_services_async

    print("[all] step 1: discover")
    services = await discover_connect_services_async(timeout_s=args.timeout)
    if not services:
        print("[all] FAILED: no TLS-connect services found on the LAN.")
        print("[all]   Make sure 'Wireless debugging' is enabled on the TV")
        print("[all]   and that this machine is on the same broadcast domain.")
        return 1

    svc = services[0]
    print(f"[all] using {svc.name!r} at {svc.host}:{svc.port}")
    print()
    print("[all] step 2: connect via TLS")
    return await _connect_and_probe(
        svc.host, svc.port, args.adbkey, "tls",
        args.transport_timeout, args.auth_timeout,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser():
    p = argparse.ArgumentParser(
        description="ADB Wi-Fi smoke test for python-androidtv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("-v", "--verbose", action="store_true",
                   help="enable DEBUG logging from adb_shell_wifi / androidtv")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="sweep the LAN for ADB Wi-Fi services")
    d.add_argument("--timeout", type=float, default=4.0,
                   help="mDNS sweep duration in seconds (default: 4.0)")
    d.set_defaults(func=cmd_discover)

    pa = sub.add_parser("pair", help="pair with a device using a 6-digit code")
    pa.add_argument("--host", required=True, help="pairing IP")
    pa.add_argument("--port", required=True, type=int, help="pairing port")
    pa.add_argument("--code", required=True, help="6-digit pairing code")
    pa.add_argument("--adbkey", required=True,
                    help="path to your adbkey (e.g. ~/.android/adbkey)")
    pa.add_argument("--timeout", type=float, default=30.0,
                    help="pairing handshake timeout (default: 30.0)")
    pa.set_defaults(func=cmd_pair)

    co = sub.add_parser("connect", help="connect via TLS and run a shell probe")
    co.add_argument("--host", required=True, help="device IP")
    co.add_argument("--port", required=True, type=int, help="device TLS port")
    co.add_argument("--adbkey", required=True, help="path to your adbkey")
    co.add_argument("--transport-timeout", type=float, default=10.0,
                    help="transport timeout (default: 10.0)")
    co.add_argument("--auth-timeout", type=float, default=10.0,
                    help="auth timeout (default: 10.0)")
    co.set_defaults(func=cmd_connect)

    le = sub.add_parser("legacy", help="connect via legacy TCP (regression check)")
    le.add_argument("--host", required=True, help="device IP")
    le.add_argument("--port", required=True, type=int, help="device port (5555)")
    le.add_argument("--adbkey", required=True, help="path to your adbkey")
    le.add_argument("--transport-timeout", type=float, default=10.0)
    le.add_argument("--auth-timeout", type=float, default=10.0)
    le.set_defaults(func=cmd_legacy)

    al = sub.add_parser("all",
                        help="discover then connect (assumes already paired)")
    al.add_argument("--adbkey", required=True, help="path to your adbkey")
    al.add_argument("--timeout", type=float, default=4.0)
    al.add_argument("--transport-timeout", type=float, default=10.0)
    al.add_argument("--auth-timeout", type=float, default=10.0)
    al.set_defaults(func=cmd_all)

    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    args.adbkey = os.path.expanduser(getattr(args, "adbkey", "")) or args.adbkey

    try:
        rc = asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\n[abort] interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 — top-level smoke test
        print(f"[FAIL] unexpected {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 99
    return rc


if __name__ == "__main__":
    sys.exit(main())
