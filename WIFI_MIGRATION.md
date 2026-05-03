# Migrating to `adb_shell` with ADB Wi-Fi support

This document is a self-contained guide for a future engineer (likely a
fresh Claude instance with no prior context) tasked with updating
**Home Assistant's `androidtv` integration** (or any other downstream of
`adb_shell`) to support modern Android Wi-Fi debugging while keeping the
existing legacy paths working.

---

## 1. Background: what changed in `adb_shell`

`adb_shell` is the Python ADB client that Home Assistant's `androidtv`
integration uses to talk to Android TV devices. Modern Android (11+)
deprecated the legacy `adb tcpip` flow in favor of **ADB Wi-Fi**, which
adds three new protocol layers that legacy `adb_shell` did not implement:

1. **Pairing** — a SPAKE2 + TLS handshake bootstrapped by a 6-digit code
   shown on the device's *Settings → System → Developer options →
   Wireless debugging → Pair device with pairing code* dialog. This
   registers the host's RSA public key in the device's keystore without
   requiring a USB cable + on-device "Allow debugging" tap.
2. **TLS data channel** — after pairing, the device's wireless-debugging
   socket greets new connections with `A_STLS` instead of `A_AUTH`. The
   host must reply with its own `A_STLS`, then both sides perform a
   TLS 1.3 handshake (using the same RSA cert as pairing), and only then
   does normal ADB traffic flow.
3. **mDNS discovery** — devices advertise three service types:
   `_adb._tcp` (legacy `adb tcpip`), `_adb-tls-pairing._tcp` (only while
   the pairing dialog is open), and `_adb-tls-connect._tcp` (TLS data
   channel for paired devices, on a random port chosen by adbd each time
   "Wireless debugging" is toggled).

Without these three pieces, modern Android TVs simply cannot be shelled
remotely.

### The fork

This work lives on a fork:

- **Repo:** `jasonanovak/adb_shell`
- **Branch:** `wifi_support`
- **Upstream reference (read-only):** the AOSP `adb` C++ source at
  `https://android.googlesource.com/platform/packages/modules/adb/`
  (the canonical implementation we ported from).
- **Protocol doc:** `docs/dev/adb_wifi.md` in that AOSP tree.

### The commits

Three sequential, independently-verified PRs landed on `wifi_support`:

| Commit | What it adds |
|---|---|
| `f8c9b3a` | **Pairing** — `pair()` / `pair_async()`, `PairingAuthCtx`, x509 cert generator. |
| `303603e` | **TLS data channel** — `TlsTransport`, `TlsTransportAsync`, `AdbDeviceTls`, `AdbDeviceTlsAsync`, `A_STLS` handling in `_AdbIOManager.connect`. |
| `2f065e1` | **mDNS discovery** — `adb_shell.mdns` package with sync + async `discover_*_services` helpers. |

**Verification status:** all three were end-to-end verified against a
real Android TV (paired, opened a TLS connection, ran a shell command
over the encrypted channel, and discovered the random TLS port via
mDNS). Total test suite: 225 passing (180 pre-existing legacy tests +
45 new). No regressions in the existing USB / `tcpip`-on-5555 flow.

For the implementation plan that drove this work, see
`WIFI_SUPPORT_PLAN.md` in the repo root.

---

## 2. What's preserved (backward compatibility)

A downstream that depends on the released `adb_shell` and continues to
do exactly what it does today **needs to change nothing** to pick up
this branch:

- `AdbDeviceTcp`, `AdbDeviceUsb`, `AdbDeviceTcpAsync`,
  `AdbDeviceUsbAsync` — byte-for-byte unchanged behavior. Existing
  legacy `adb tcpip` (port 5555) and USB users continue to work.
- `_AdbIOManager.connect` — the `AUTH` / `CNXN` paths are byte-for-byte
  unchanged. We added a third branch for `STLS`, gated on the new
  `tls_priv_pem` kwarg (defaults to `None`), so old callers never enter
  it.
- No new mandatory dependencies. Wi-Fi support lives behind a `[wifi]`
  extra. Users who don't `pip install adb_shell[wifi]` pay nothing.
- No renames, no removals. Pure additions to the public surface.
- Same `~/.android/adbkey` file is reused for pairing **and** the TLS
  data channel. There is no new key file to manage.
- Existing signers (`PythonRSASigner`, `CryptographySigner`,
  `PycryptodomeSigner`) are still used for the legacy `AUTH` flow on USB
  and on `_adb._tcp` ports. They are *not* used on the Wi-Fi path —
  TLS 1.3 + the previously-paired key authenticate the host, so signing
  challenges is unnecessary.

---

## 3. What's new (additions to the public API)

### `adb_shell.adb_device`

- `AdbDeviceTls(host, port, default_transport_timeout_s=None, banner=None)`
  — sync client for a paired device's wireless-debugging port. Internal
  transport is `TlsTransport`; the connection stays cleartext until the
  device greets it with `A_STLS`, at which point `connect()` upgrades
  the socket in place to TLS 1.3.
- `AdbDevice.connect(...)` gains an optional `tls_priv_pem=None` kwarg
  (PEM-encoded RSA private key bytes — the contents of `adbkey`).
  Required when the device replies with `A_STLS`, ignored otherwise.

### `adb_shell.adb_device_async`

- `AdbDeviceTlsAsync(host, port, ...)` — async equivalent.
- `AdbDeviceAsync.connect(...)` gains the same `tls_priv_pem` kwarg.

### `adb_shell.transport`

- `tls_transport.TlsTransport(host, port)` — sync TCP transport with an
  explicit `tls_upgrade(cert_pem, key_pem)` method. Uses stdlib `ssl`.
- `tls_transport_async.TlsTransportAsync(host, port)` — async
  equivalent. Uses `loop.start_tls()` to upgrade an existing asyncio
  stream in place.

### `adb_shell.pairing`

```python
from adb_shell.pairing import pair, pair_async, PairingException, PeerInfo
```

- `pair(host, port, pairing_code, private_key_pem, public_key, timeout_s=30.0)`
  → `PeerInfo`. Performs the SPAKE2 + TLS pairing handshake and
  registers the host's public key on the device. Raises
  `PairingException` on any failure.
- `pair_async(...)` — async wrapper (runs the sync handshake in a
  thread executor; pairing is one-shot, so this is fine).
- `PeerInfo(type, data)` — value type returned by `pair()`. Typically
  contains the device's GUID after a successful pairing.
- `PairingException` — subclass of `AdbConnectionError`.

### `adb_shell.mdns`

```python
from adb_shell.mdns import (
    AdbService,
    SERVICE_TYPE_LEGACY,         # "_adb._tcp.local."
    SERVICE_TYPE_PAIRING,         # "_adb-tls-pairing._tcp.local."
    SERVICE_TYPE_TLS_CONNECT,     # "_adb-tls-connect._tcp.local."
    discover_pairing_services,
    discover_connect_services,
    discover_services,
    discover_pairing_services_async,
    discover_connect_services_async,
    discover_services_async,
)
```

- `AdbService = namedtuple(name, type, host, port)` — value type for a
  resolved service.
- `discover_connect_services(timeout_s=4.0)` — find paired devices
  currently advertising a TLS data port.
- `discover_pairing_services(timeout_s=4.0)` — find devices currently
  advertising a pairing server (only while the pair-with-code dialog is
  open).
- `discover_services(types, timeout_s=4.0)` — sweep across an arbitrary
  set of service types in one pass.
- All have `_async` equivalents using `AsyncZeroconf`.

### `adb_shell.auth.x509`

```python
from adb_shell.auth.x509 import (
    generate_x509_certificate,    # RSAPrivateKey -> x509.Certificate
    certificate_to_pem,            # Certificate -> PEM bytes
    load_rsa_private_key_pem,     # PEM bytes -> RSAPrivateKey
    private_key_to_pem,            # RSAPrivateKey -> PKCS#8 PEM bytes
)
```

These are exposed for downstream code that wants to pre-generate the
self-signed cert / private key for pairing or TLS instead of letting the
high-level `pair()` / `connect()` do it lazily.

### Constants

In `adb_shell.constants`:
- `STLS = b'STLS'`
- `STLS_VERSION = 0x01000000`
- `STLS` is now in `IDS`.

---

## 4. The `[wifi]` extra and its dependencies

```
adb_shell[wifi] >= X.Y.Z
```

pulls in three packages on top of `adb_shell`'s base deps:

- **`spake2-cffi >= 1.0.0`** — CFFI wrapper around BoringSSL's
  SPAKE2-edwards25519 (wire-compatible with Android's pairing server).
  Wheels published for manylinux + musllinux x86_64/aarch64 and macOS,
  Python 3.8–3.12. **No Windows wheels** — Windows users need a C
  toolchain to install. Verified to build cleanly from sdist on Python
  3.14.
- **`pyOpenSSL >= 22.0.0`** — exposes `Connection.export_keying_material`
  (RFC 5705 / RFC 8446 TLS exporter), which Python's stdlib `ssl` does
  not. Used only during pairing to bind the SPAKE2 PAKE to the TLS
  session.
- **`zeroconf >= 0.39`** — pure-Python mDNS, well-maintained, already
  widely used in the Home Assistant ecosystem.

### Reduced-extra option

If you build a downstream that never pairs (devices were already paired
out-of-band) and never discovers (you have a known IP/port), you only
need stdlib `ssl` for `AdbDeviceTls`. We don't ship a separate
"connect-only" extra, but if your project wants to minimize footprint,
you can:

- Depend on `adb_shell` (no `[wifi]`).
- Use `AdbDeviceTls` directly — it works without pyOpenSSL/spake2-cffi.
- Catch `ImportError` if the user's environment is missing pyOpenSSL or
  zeroconf and they try to use those features.

In practice, the `[wifi]` extra is the recommended path for any
downstream that exposes pairing as an end-user flow.

---

## 5. Migration plan for a downstream

Concrete steps in priority order:

### 5.1 — Bump the version

Pin `adb_shell` to a version that contains these PRs. If your project's
end users want Wi-Fi support:
```
adb_shell[wifi] >= X.Y.Z
```
otherwise leave the existing `adb_shell >= X.Y.Z` and let users opt in.

### 5.2 — Add a config setting for the connection type

Don't try to auto-detect Wi-Fi vs. legacy `tcpip` — both look like TCP
and the failure modes are slow/awkward. Surface a setting like:

```yaml
connection_type: tcp | tls | usb
```

The legacy default stays `tcp` (port 5555). Users who turn on Wi-Fi
debugging on their TV pick `tls`.

### 5.3 — Branch the device construction

```python
if connection_type == "tls":
    device = AdbDeviceTlsAsync(host, port)   # async; sync exists too
elif connection_type == "tcp":
    device = AdbDeviceTcpAsync(host, 5555)   # legacy, unchanged
else:
    device = AdbDeviceUsbAsync(...)
```

### 5.4 — Branch the connect call

```python
if connection_type == "tls":
    await device.connect(rsa_keys=[], tls_priv_pem=priv_pem,
                         auth_timeout_s=10.0)
else:
    await device.connect(rsa_keys=[signer], auth_timeout_s=10.0)
```

`rsa_keys=[]` is correct for the TLS path — TLS 1.3 + the previously
paired key authenticate the host, so signing the legacy auth challenge
is not needed.

### 5.5 — Add a one-time pairing flow

This is genuinely new — there's no equivalent in legacy ADB. UI flow:

1. Tell the user to open *Settings → System → Developer options →
   Wireless debugging → Pair device with pairing code* on the TV.
2. Show three input fields: IP, port, 6-digit code (all displayed on
   the device). Or use `discover_pairing_services()` to populate IP/port
   automatically and only ask for the code.
3. Call `pair(...)`. On success, you're done — the device persists the
   host's public key.
4. On failure, the most common cause is a wrong/stale pairing code
   (manifests as `PairingException: decryption of peer PEER_INFO
   failed`). Treat as a retryable user error.

```python
from adb_shell.pairing import pair, PairingException

with open(adbkey_path, "rb") as f:
    priv = f.read()
with open(adbkey_path + ".pub", "rb") as f:
    pub = f.read()

try:
    peer_info = pair(host, pairing_port, code,
                     private_key_pem=priv, public_key=pub)
    # peer_info.data typically contains the device's GUID
except PairingException as e:
    # Surface to user as "couldn't pair — wrong code or device not in
    # pairing mode".
    ...
```

### 5.6 — Add discovery to avoid stale ports

The TLS port is randomized every time "Wireless debugging" is toggled.
A fixed port from config will go stale. After pairing, prefer
discovery on every connect:

```python
from adb_shell.mdns import discover_connect_services_async

async def find_device(known_serial_or_host):
    services = await discover_connect_services_async(timeout_s=4.0)
    for s in services:
        # Match on whatever you persisted at pairing time. Reasonable
        # choices: host (works on a stable LAN), or device_guid
        # extracted from the service instance name.
        if s.host == known_host:
            return s
    return None
```

If the user's device isn't on a flat broadcast domain (mDNS doesn't
cross VLAN boundaries / many enterprise networks), discovery returns
empty. In that case fall back to a manually-entered port and warn the
user that they may need to update it after a TV reboot.

### 5.7 — Persist what you need

At pairing time, save:

- The host's `adbkey` path (you already do this for legacy ADB).
- Optionally the device's GUID from `peer_info.data` — useful for
  matching the right `_adb-tls-connect` instance via mDNS later.
- The user's chosen `host` (and a `port` if discovery isn't reliable on
  their network).

The device side persists the host's public key automatically; you don't
need to track that. But if the user does *Settings → System → Developer
options → Revoke USB debugging authorizations* on the TV, the pairing is
dropped and the user has to re-pair.

---

## 6. Recommended fallback / dual-mode pattern

If you want one config field instead of `connection_type`:

```python
async def connect_androidtv(host, port, signer, priv_pem):
    """Try Wi-Fi (TLS) first, fall back to legacy TCP."""
    try:
        device = AdbDeviceTlsAsync(host, port,
                                   default_transport_timeout_s=10.0)
        await device.connect(rsa_keys=[], tls_priv_pem=priv_pem,
                             auth_timeout_s=2.0)
        return device
    except (DeviceAuthError, TcpTimeoutException, ssl.SSLError):
        try:
            await device.close()
        except Exception:
            pass
    device = AdbDeviceTcpAsync(host, port,
                               default_transport_timeout_s=10.0)
    await device.connect(rsa_keys=[signer], auth_timeout_s=10.0)
    return device
```

This is **not** as clean as an explicit setting:

- Failure on the TLS path against a legacy port can be slow (TCP
  connects, but `STLS` never arrives — you wait for the auth timeout).
- `auth_timeout_s=2.0` on the first attempt mitigates this but is a
  papered-over heuristic.

Prefer the explicit `connection_type` config when you can.

---

## 7. Error handling specifics

Things to know about the failure modes:

| Symptom | Cause | What to surface |
|---|---|---|
| `DeviceAuthError`: "Device greeted with A_STLS but no tls_priv_pem was supplied" | User pointed `AdbDeviceTcp` at a Wi-Fi port, or forgot to pass `tls_priv_pem`. | "This device requires Wi-Fi debugging — switch the connection type to TLS or pair first." |
| `DeviceAuthError`: "transport does not support tls_upgrade" | User passed a non-TLS transport but the device speaks STLS. | Use `AdbDeviceTls` instead of `AdbDeviceTcp`. |
| `PairingException`: "decryption of peer PEER_INFO failed" | Wrong pairing code. | "Pairing code didn't match. Try again." Retry without re-issuing the code is fine — the device's pairing dialog is still active for ~60s. |
| `PairingException`: "TLS error during pairing" | Network issue, or the pairing port closed. | The dialog likely closed on the device. Have the user reopen *Pair device with pairing code*. |
| `TcpTimeoutException` on TLS handshake | Device unreachable, or wireless debugging was toggled off. | Re-discover via mDNS; ask user to re-enable wireless debugging if no service is advertised. |
| `cryptography.exceptions.InvalidTag` (escapes from pairing) | Bug — should always be wrapped in `PairingException`. Report. | n/a |

---

## 8. Non-obvious gotchas

These were learned the hard way during implementation. Save yourself the
debug time:

- **The TLS exporter label is `b"adb-label\x00"` with a trailing NUL,
  not `b"adb-label"`.** The C++ reference passes
  `sizeof(kExportedKeyLabel)` to `SSL_export_keying_material`, which is
  10 bytes including the NUL. This goes into TLS 1.3's exporter HKDF, so
  it must match byte-for-byte. (See `adb_shell/pairing/constants.py`
  comment for context.)
- **`spake2-cffi` is imported as `spake2`, not `spake2_cffi`.** The
  package name on PyPI is `spake2-cffi` but it installs a `spake2/`
  directory. There's a name collision with Brian Warner's pure-Python
  `spake2` package — they cannot both be installed. `spake2-cffi` is the
  one wire-compatible with Android.
- **SPAKE2 password mismatch does NOT fail at `process_msg` time.** Both
  sides derive *different* keys; the mismatch surfaces as an AES-GCM
  tag failure on the first decrypt. This matches the C++ reference's
  behavior; it's not a bug.
- **`tls_priv_pem` accepts either PKCS#1 or PKCS#8 PEM.** The
  high-level `connect()` re-encodes to PKCS#8 internally before handing
  to stdlib `ssl`. Don't worry about the source format.
- **stdlib `ssl` requires file paths to load cert/key**, so
  `TlsTransport._make_ssl_context` writes to `tempfile.mkstemp` files
  and unlinks them after `load_cert_chain` returns. This is the
  ugliest part of the implementation, but it's contained.
- **pyOpenSSL doesn't auto-loop on `WantReadError`/`WantWriteError`**
  even with a blocking socket. The pairing-side wrapping uses a
  select-driven retry loop in `pairing_device.py:_retry_on_want`. If
  you're tempted to "just call `do_handshake()` again", make sure to
  select first.
- **The same RSA key is used for both pairing and TLS data channel.**
  Pairing registers the host's public key on the device; the TLS data
  channel uses the same key + a fresh self-signed cert (regenerated on
  each `connect()` — sub-ms cost). Do not generate two separate keys.
- **Random TLS port changes on every "Wireless debugging" toggle.**
  Caching `port` from config is fine for short-term reconnects but will
  go stale after a TV reboot. Always rediscover on connection failure.
- **mDNS doesn't traverse VLANs.** If the user's TV is on a different
  broadcast domain (common in enterprise/IoT-VLAN setups), discovery
  returns empty. Fall back to a manual port.
- **The async pairing implementation is `loop.run_in_executor(None,
  pair, ...)` under the hood** — not a true asyncio TLS implementation.
  This is fine because pairing is one-shot. Don't be alarmed by it.
- **The async TLS data path (`TlsTransportAsync.tls_upgrade`) does use
  native asyncio** via `loop.start_tls()`. This is the per-message hot
  path and we want native I/O there.

---

## 9. Where to read in `adb_shell` source for protocol details

When in doubt, the most authoritative thing in this repo is the C++
reference at `../adb` (sibling read-only checkout, see
`CLAUDE.md`). Within `adb_shell` itself:

- `adb_shell/pairing/auth.py` — SPAKE2 + AES-128-GCM (HKDF info, nonce
  layout, SPAKE2 names).
- `adb_shell/pairing/connection.py` — protocol state machine
  (`PairingPacketHeader`, `PeerInfo`, exchange order).
- `adb_shell/pairing/pairing_device.py` — TLS 1.3 client setup +
  `_retry_on_want`.
- `adb_shell/pairing/constants.py` — every magic number used by
  pairing, with a comment pointing at the line in the C++ that defines
  it.
- `adb_shell/transport/tls_transport.py` —
  `_make_ssl_context()` is the only place that touches stdlib SSL
  context configuration.
- `adb_shell/adb_device.py:_AdbIOManager._do_stls_upgrade` — exactly
  what happens when the device greets with STLS.
- `adb_shell/mdns/discovery.py` — service-type strings and resolution
  logic (sync; async is a near-mirror).

Tests:
- `tests/test_pairing.py` — 30 tests, includes a full protocol
  round-trip with a mocked transport.
- `tests/test_stls_handshake.py` — 9 tests, sync + async STLS path
  unit tests using fake transports.
- `tests/test_mdns_discovery.py` — 6 tests, mocked Zeroconf.

Demo scripts (under `scripts/`):
- `pair_demo.py <host> <port> <code> <adbkey>` — runs `pair()`.
- `connect_tls_demo.py <host> <tls-port> <adbkey> [shell-cmd]` — runs
  `AdbDeviceTls.connect()` and optionally a shell command.
- `mdns_demo.py [pair|connect|all]` — discovers services on the LAN.

---

## 10. Specific notes for the Home Assistant `androidtv` integration

The `androidtv` HA integration uses an external Python library named
`androidtv` (`https://github.com/JeffLIrion/python-androidtv`) which is
the actual consumer of `adb_shell`. Two layers to update:

### Layer 1: the `androidtv` Python library

This is where the `adb_shell` API surface gets touched. Likely changes:

- Add a `wifi` extra that pulls in `adb_shell[wifi]`.
- Add a constructor or factory that produces an `AdbDeviceTlsAsync`
  instead of `AdbDeviceTcpAsync` when the user has opted into Wi-Fi.
- Plumb `tls_priv_pem` from the user's adbkey through to
  `device.connect()`.
- Optionally expose a `pair_async()` wrapper for HA's setup flow.
- Optionally expose a discovery helper for HA's config flow.

**Verify before writing code:** the exact structure of the `androidtv`
library (Bridge classes, `AndroidTV` vs. `BaseTVAsync`, etc.) — it has
moved around historically. Read `androidtv/__init__.py`,
`androidtv/adb_manager/`, and `androidtv/setup.py` first.

### Layer 2: the `homeassistant.components.androidtv` integration

In HA core, the integration sits at
`homeassistant/components/androidtv/`. Likely changes:

- **Config flow** (`config_flow.py`): add a "connection type" step or a
  new "Pair with code" step in the existing flow. HA's config flow
  framework supports multi-step UIs and persisting credentials in
  config entries.
- **Init / setup** (`__init__.py`, `media_player.py`): branch on the
  stored `connection_type` and construct the right `androidtv`
  bridge.
- **Discovery**: HA already has a zeroconf integration that listens for
  service types globally. Consider registering
  `_adb-tls-pairing._tcp` and/or `_adb-tls-connect._tcp` in HA's
  zeroconf manifest so the integration can offer "discovered devices"
  in the config flow without needing `adb_shell.mdns`'s standalone
  scanner.
- **Existing user migration**: HA users who already have a working
  legacy ADB config should not be forced to repair. Their
  `connection_type` defaults to legacy `tcp`. They opt into Wi-Fi by
  re-running the config flow if their TV stops responding to the legacy
  port.

**Verify before writing code:** HA's coding conventions
(`async`-first, `entry.data` vs. `entry.options`, the config-flow
result types, error strings, translation keys), and the integration's
current shape — these change between HA versions. Read the integration's
current `manifest.json`, `config_flow.py`, and `__init__.py` first; do
not assume the structure based on this guide alone.

### HA-specific gotchas

- **HA Core targets Python 3.13 today, moving to 3.14.** `spake2-cffi`
  has prebuilt wheels through 3.12. From 3.13 on, pip will build from
  the published sdist. HA's container has a C toolchain so this works,
  but it adds install time. If this becomes a real problem, the
  fallback is a pure-Python SPAKE2 reimplementation (~300–500 lines of
  careful crypto) — see the prior plan for a discussion.
- **HA's add-on / supervisor setups vary widely** in what system
  libraries they include. The `[wifi]` deps' wheels handle most cases
  (manylinux x86_64/aarch64, musllinux for Alpine-based supervisors).
  Verify on Home Assistant Operating System (HAOS) specifically.
- **HA users frequently run on segmented networks** (IoT VLAN, etc.).
  mDNS may not work for everyone. Always provide a manual-port input
  fallback.
- **Don't use the upstream `adb_shell` package directly until these
  changes land in `JeffLIrion/adb_shell` master and are released to
  PyPI.** Until then, point at the fork
  (`pip install git+https://github.com/jasonanovak/adb_shell.git@wifi_support`)
  or vendor the branch.

---

## 11. Quick-reference end-to-end example

Combining all three PRs, this is the canonical "modern Wi-Fi
connection" path a downstream should produce:

```python
from adb_shell.adb_device import AdbDeviceTlsAsync
from adb_shell.mdns import discover_connect_services_async
from adb_shell.pairing import pair_async, PairingException

# --- One-time pairing (UI flow) ---
with open(adbkey_path, "rb") as f:
    priv = f.read()
with open(adbkey_path + ".pub", "rb") as f:
    pub = f.read()

try:
    peer_info = await pair_async(
        host=user_entered_ip,
        port=user_entered_port,
        pairing_code=user_entered_code,
        private_key_pem=priv,
        public_key=pub,
    )
    # Store user_entered_ip + peer_info.data (device GUID) in config.
except PairingException:
    # Surface "wrong code or device not in pairing mode".
    raise

# --- Each subsequent connection ---
services = await discover_connect_services_async(timeout_s=4.0)
svc = next((s for s in services if s.host == known_host), None)
if svc is None:
    # Fall back to a stored port; if that fails, ask user to reopen
    # wireless debugging.
    svc = AdbService(name="", type="", host=known_host, port=stored_port)

device = AdbDeviceTlsAsync(svc.host, svc.port,
                           default_transport_timeout_s=10.0)
await device.connect(rsa_keys=[], tls_priv_pem=priv,
                     auth_timeout_s=10.0)
out = await device.shell("getprop ro.build.version.release")
await device.close()
```

---

## 12. Summary

- **Backwards compatibility:** zero-effort. Legacy paths are byte-for-byte
  unchanged.
- **Forward path:** swap `AdbDeviceTcp` → `AdbDeviceTls`, pass
  `tls_priv_pem`, add a one-time `pair()` call, prefer mDNS for
  discovery.
- **Dependencies:** opt-in via `adb_shell[wifi]`. Three new packages
  total.
- **Verification:** all three PRs landed and were end-to-end verified
  against a real Android TV. 225 tests passing, no regressions.

When in doubt, read the source — every magic number in
`adb_shell/pairing/constants.py` and `adb_shell/transport/tls_transport.py`
has a comment pointing at the line in the C++ AOSP reference that
defines it.
