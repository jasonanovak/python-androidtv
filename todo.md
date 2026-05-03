# ADB Wi-Fi support for python-androidtv — todo

Tracking the implementation of ADB Wi-Fi (TLS) support against the
`adb_shell` fork at `../adb_shell` (branch `wifi_support`).

Decisions locked in:
- `setup.py` pins `adb_shell` via a git ref (no PyPI release of the fork yet).
- Bumping `__version__` to `0.0.76`.
- New code (Wi-Fi module, new tests) targets Python 3.8+; existing
  legacy-style code is left as-is to keep the upstream PR diff small.

---

## Step 1 — Plumb `connection_type` through public API (no behavior change)

- [x] Add `connection_type` kwarg (default `"tcp"`) to `ADBPythonSync.__init__`
- [x] Add `connection_type` kwarg (default `"tcp"`) to `ADBPythonAsync.__init__`
- [x] Add `connection_type` kwarg to `BaseTV.__init__` (store on instance)
- [x] Add `connection_type` kwarg to `BaseTVSync.__init__`, pass to `ADBPythonSync`
- [x] Add `connection_type` kwarg to `BaseTVAsync.__init__`, pass to `ADBPythonAsync`
- [x] Add `connection_type` kwarg to `AndroidTVSync.__init__` + `from_base()`
- [x] Add `connection_type` kwarg to `AndroidTVAsync.__init__` + `from_base()`
- [x] Add `connection_type` kwarg to `FireTVSync.__init__` + `from_base()`
- [x] Add `connection_type` kwarg to `FireTVAsync.__init__` + `from_base()`
- [x] Add `connection_type` kwarg to `setup()` in `androidtv/__init__.py`
- [x] Add `connection_type` kwarg to `setup()` in `androidtv/setup_async.py`
- [x] Run full test suite — confirm zero regressions (231 passed, 1 skipped)

## Step 2 — Add TLS branch in `ADBPython{Sync,Async}`

- [x] Sync: lazy-import `AdbDeviceTls`; build it when `connection_type == "tls"`
- [x] Sync: in `connect()`, when TLS, read `adbkey` PEM and call `connect(rsa_keys=[], tls_priv_pem=…)`
- [x] Sync: raise informative error if `connection_type == "tls"` and `adbkey` is empty
- [x] Async: lazy-import `AdbDeviceTlsAsync`; build it when `connection_type == "tls"`
- [x] Async: in `connect()`, when TLS, read `adbkey` PEM (via `aiofiles`) and call `connect(rsa_keys=[], tls_priv_pem=…)`
- [x] Async: raise informative error if `connection_type == "tls"` and `adbkey` is empty
- [x] Add `AdbDeviceTlsFake` to `tests/patchers.py`
- [x] Add `AdbDeviceTlsAsyncFake` to `tests/async_patchers.py`
- [x] Add `PATCH_ADB_DEVICE_TLS{,_ASYNC}` patches
- [x] Add a focused TLS-path test in `tests/test_adb_manager_sync.py`
- [x] Add a focused TLS-path test in `tests/test_adb_manager_async.py`
- [x] Run full test suite — confirm zero regressions and TLS tests pass (239 passed, 1 skipped)

## Step 3 — Create `androidtv/wifi.py` helper module

- [x] Module skeleton with lazy `_require_pairing()` / `_require_mdns()` helpers
- [x] `pair(host, port, code, adbkey)` — wraps `adb_shell.pairing.pair`
- [x] `pair_async(host, port, code, adbkey)` — wraps `adb_shell.pairing.pair_async`
- [x] `discover_pairing_services(timeout_s)` + async variant
- [x] `discover_connect_services(timeout_s)` + async variant
- [x] Re-export `AdbService`, `PairingException`, `PeerInfo`, service-type constants
- [x] `tests/test_wifi.py` — mock `adb_shell.pairing` / `adb_shell.mdns`, verify forwarding (7 tests)

## Step 4 — Packaging + version bump

- [x] `setup.py`: replace `adb-shell>=0.4.0` with the git ref for the `wifi_support` fork in `install_requires`
- [x] `setup.py`: add `"wifi"` extra mirroring `adb-shell[wifi]`
- [x] Bump `__version__` in `androidtv/__init__.py` to `0.0.76` (and matching `version=` in `setup.py`)
- [x] Update `README.rst` with a brief "ADB Wi-Fi support" section pointing at `androidtv.wifi` and the `[wifi]` extra

## Step 5 — Verification

- [x] Run pytest — 246 passed, 1 skipped, no warnings (231 baseline + 8 TLS + 7 wifi)
- [x] Run `python -c "import androidtv; import androidtv.wifi"` — clean import
- [x] Spot-check that `connection_type="tcp"` (default) path still builds `AdbDeviceTcp(Async)` and `connection_type="tls"` builds `AdbDeviceTls(Async)`
- [x] Self-review the diff: 18 files changed, +418 / -30, purely additive (no renamed or removed public surface)

---

## Status: complete

All five steps are done.  Branch is ready for end-to-end smoke testing
against a real Android TV per WIFI_MIGRATION.md §11 before opening a PR
upstream.

## Real-device smoke test

A runnable smoke-test script lives at ``scripts/wifi_smoke_test.py``.
Subcommands: ``discover`` (mDNS sweep), ``pair`` (one-time, with code),
``connect`` (TLS path), ``legacy`` (regression check on `tcp` 5555),
``all`` (discover + connect).  Run ``python scripts/wifi_smoke_test.py
--help`` for the full walkthrough.
