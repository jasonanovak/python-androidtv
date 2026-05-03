# Migrating to `androidtv` with ADB Wi-Fi support

This is a self-contained guide for a future engineer (likely a fresh
Claude instance with no prior context) tasked with adding modern
Android wireless-debugging support to a downstream of `androidtv` —
most importantly, Home Assistant's `androidtv` integration.

The companion document `WIFI_MIGRATION.md` covers the equivalent
migration on the `adb_shell` side. **Read that first if you haven't.**
This document sits one layer up.

---

## 1. TL;DR

- `androidtv` ≥ 0.0.76 (currently on the `wifi_support` branch of
  `jasonanovak/python-androidtv`) adds an opt-in `connection_type="tls"`
  path that uses ADB Wi-Fi instead of legacy `adb tcpip`.
- Default behavior is unchanged: every existing call site continues to
  use `connection_type="tcp"` and gets byte-for-byte identical
  behavior.
- A new `androidtv.wifi` module exposes one-shot pairing and mDNS
  discovery, mirroring `adb_shell.pairing` / `adb_shell.mdns` but with
  a downstream-friendly file-path-based API.
- Wi-Fi support is opt-in via the `[wifi]` extra, which transitively
  pulls in `adb_shell[wifi]` (`spake2-cffi`, `pyOpenSSL`, `zeroconf`).

---

## 2. What's preserved (backwards compatibility)

A downstream that does what it does today **needs to change nothing**
to pick up this version:

- Every constructor (`setup`, `setup_async.setup`, `BaseTV{,Sync,Async}`,
  `AndroidTV{Sync,Async}`, `FireTV{Sync,Async}`, `ADBPython{Sync,Async}`)
  has `connection_type` as a kwarg with a default of `"tcp"`. Positional
  call sites are unaffected.
- The legacy USB path (`host=""`) is unchanged.
- The pure-python-adb / `ADBServer{Sync,Async}` path is unchanged. The
  `connection_type` kwarg is accepted but ignored on that path — the
  external `adb` server already speaks whatever the device speaks.
- No new mandatory dependencies. Skipping the `[wifi]` extra means
  `androidtv.wifi` imports cleanly but raises `ImportError` if you call
  into the pairing / discovery functions.
- Same `~/.android/adbkey` is reused for pairing **and** the TLS data
  channel. There is no new key file to manage.

---

## 3. New public API

### 3.1 `connection_type` kwarg

Accepted on every TV-construction entry point. Valid values live at
`androidtv.constants.VALID_CONNECTION_TYPES` (`("tcp", "tls")`). The
default is `androidtv.constants.DEFAULT_CONNECTION_TYPE` (`"tcp"`).

```python
from androidtv import setup
from androidtv.basetv.basetv_async import BaseTVAsync

# Default — legacy `adb tcpip` on whatever port (typically 5555)
tv = setup(host="192.168.1.42", port=5555, adbkey="…")

# Modern wireless debugging
tv = setup(host="192.168.1.42", port=41877, adbkey="…",
           connection_type="tls")

# Same kwarg propagates through every constructor
btv = BaseTVAsync(host, port, adbkey, connection_type="tls")
```

`connection_type="tls"` requires `adbkey` to be set; constructing
without one raises `ValueError` from `connect()`.

### 3.2 `androidtv.wifi`

```python
from androidtv.wifi import (
    pair, pair_async,
    discover_pairing_services, discover_pairing_services_async,
    discover_connect_services, discover_connect_services_async,
    AdbService, PairingException, PeerInfo,
    SERVICE_TYPE_LEGACY, SERVICE_TYPE_PAIRING, SERVICE_TYPE_TLS_CONNECT,
)
```

Notable shape differences from `adb_shell.pairing.pair` / `pair_async`:

- `pair(host, port, pairing_code, adbkey, timeout_s=30.0)` — `adbkey`
  is a **filesystem path**, not pre-loaded PEM bytes. The wrapper
  reads both `adbkey` and `adbkey + ".pub"` itself.
- `pair_async` does the same, but reads via `aiofiles`.

`discover_*` are pass-through wrappers; they accept `timeout_s` and
return the same `list[AdbService]` as `adb_shell.mdns`.

---

## 4. Dependency story

### Until the fork is on PyPI

The fork branches are not yet released. Pin to the git refs:

```
adb_shell[wifi] @ git+https://github.com/jasonanovak/adb_shell.git@wifi_support
androidtv[wifi] @ git+https://github.com/jasonanovak/python-androidtv.git@wifi_support
```

### What `[wifi]` brings in

Transitively from `adb_shell[wifi]`:

- `spake2-cffi >= 1.0.0` — wheels for manylinux/musllinux x86_64+aarch64
  and macOS, Python 3.8–3.12. **No Windows wheels.** Builds from sdist
  on 3.13+ given a C toolchain.
- `pyOpenSSL >= 22.0.0` — needed for `Connection.export_keying_material`
  during pairing only.
- `zeroconf >= 0.39` — pure-Python mDNS, already widely used in HA.

For non-pairing downstreams that already know the IP/port, plain
`adb_shell` (no `[wifi]`) is enough to use `connection_type="tls"` —
only the stdlib `ssl` module is touched on the data path. We don't
ship a separate "connect-only" extra; if you want to minimize
footprint, depend on `androidtv` (no extra) and gate calls into
`androidtv.wifi` behind the `[wifi]` extra in your own packaging.

---

## 5. Concrete migration steps for a downstream

### 5.1 — Bump the dependency

Pin to the git ref above. If your project surfaces Wi-Fi to end users,
use the `[wifi]` extra; otherwise leave the existing dep and let users
opt in.

### 5.2 — Add a config setting for the connection type

Don't try to auto-detect Wi-Fi vs. legacy `tcpip` — both look like TCP
and the failure modes are slow. Surface a setting:

```yaml
connection_type: tcp | tls   # default: tcp
```

Existing users default to `tcp`; new users running modern Android pick
`tls`.

### 5.3 — Plumb the kwarg through

Most downstreams already pass `host` / `port` / `adbkey` as a small
config blob. Add `connection_type` to that blob and forward it:

```python
tv = await setup_async.setup(
    host=cfg["host"], port=cfg["port"],
    adbkey=cfg["adbkey"], signer=cfg.get("signer"),
    connection_type=cfg.get("connection_type", "tcp"),
)
```

That's the entire connection-side change.

### 5.4 — Add a one-time pairing flow

Genuinely new — there's no equivalent in legacy ADB. The UX:

1. Tell the user to open *Settings → System → Developer options →
   Wireless debugging → Pair device with pairing code* on the TV.
2. Either (a) ask for IP, port, and the 6-digit code from the dialog,
   or (b) call `discover_pairing_services_async()` to populate IP/port
   and only ask for the code.
3. Call `pair_async(host, port, code, adbkey_path)`. On success, the
   device persists the host's public key — you're done forever (until
   the user revokes USB debugging authorizations on the TV).
4. On `PairingException("decryption of peer PEER_INFO failed")`, the
   code was wrong. Treat as a retryable user error. The pairing
   dialog stays open ~60s, so just ask again.

```python
from androidtv.wifi import pair_async, PairingException

try:
    peer = await pair_async(host=ip, port=port,
                            pairing_code=code, adbkey=adbkey_path)
    # peer.data typically contains the device's GUID — useful for
    # matching this device in mDNS later.
except PairingException as e:
    # "Couldn't pair — wrong code or device not in pairing mode."
    ...
```

### 5.5 — Add discovery for stale ports

The TLS port is randomized every time *Wireless debugging* is toggled
on the device. A fixed port from config will go stale after a TV
reboot. Prefer discovery on every connect:

```python
from androidtv.wifi import discover_connect_services_async

services = await discover_connect_services_async(timeout_s=4.0)
match = next((s for s in services if s.host == known_host), None)
if match:
    tv = await setup_async.setup(host=match.host, port=match.port,
                                 adbkey=adbkey_path,
                                 connection_type="tls")
else:
    # Fall back to last-known port; if that fails, ask the user to
    # re-toggle Wireless debugging.
    ...
```

If the device isn't on a flat broadcast domain (mDNS doesn't cross
VLAN boundaries), `discover_*` returns empty. Always provide a manual
port input as a fallback.

### 5.6 — Persist what you need

Save at pairing time:

- The `adbkey` path (you already do this for legacy ADB).
- The user's chosen `host` and a `port` (to fall back to if mDNS is
  unavailable).
- Optionally `peer.data` (device GUID) for matching the right
  `_adb-tls-connect` instance via mDNS later.

The device side persists the host's public key automatically. If the
user does *Revoke USB debugging authorizations* on the TV, pairing is
dropped and they must re-pair.

---

## 6. Recommended fallback pattern (only if you can't add a config setting)

If your downstream really cannot expose `connection_type`, you can try
TLS first and fall back to legacy TCP:

```python
async def connect_androidtv(host, port, adbkey, signer):
    try:
        tv = await setup_async.setup(host=host, port=port, adbkey=adbkey,
                                     connection_type="tls",
                                     auth_timeout_s=2.0)  # short!
        if tv.available:
            return tv
    except Exception:
        pass
    return await setup_async.setup(host=host, port=port, adbkey=adbkey,
                                   signer=signer,
                                   connection_type="tcp")
```

This is **not** as clean as an explicit setting:

- TLS-against-legacy-port hangs until `auth_timeout_s` because the
  device never sends `A_STLS`. The short timeout above is a
  papered-over heuristic.
- The user has no signal that they're on the legacy path until
  something else breaks.

**Prefer an explicit `connection_type` config field whenever you
can.**

---

## 7. Error handling

| Symptom | Cause | What to surface |
|---|---|---|
| `setup()` returns a `tv` with `tv.available == False` on the TLS path | Wrong port, device not in wireless-debugging mode, or you pointed TLS at a legacy port | "Could not establish a wireless-debugging connection. Check the device IP/port and that Wireless debugging is enabled." |
| `ValueError: connection_type='tls' requires adbkey to be set` | Forgot to pass `adbkey` on the TLS path | "An ADB key is required for wireless debugging." |
| `PairingException`: "decryption of peer PEER_INFO failed" | Wrong pairing code | "Pairing code didn't match. Try again." (Retry without re-issuing — dialog stays open ~60s.) |
| `PairingException`: "TLS error during pairing" | Pairing dialog timed out / port closed | "Reopen *Pair device with pairing code* on the TV and try again." |
| `ImportError: Wi-Fi support requires the [wifi] extra` | Tried to call `androidtv.wifi.pair()` etc. without installing extras | "Install `androidtv[wifi]` to enable wireless-debugging features." |
| `discover_connect_services_async()` returns `[]` despite the device being on | mDNS doesn't cross VLAN / IoT subnet | Fall back to a stored port; warn the user to use a manual port if mDNS is unreliable. |

---

## 8. Non-obvious gotchas

- **The TLS port is randomized on every Wireless-debugging toggle.**
  Caching the port from config is fine for short-term reconnects but
  goes stale after a TV reboot. Always rediscover on connection
  failure.
- **mDNS doesn't traverse VLANs.** Common in enterprise / IoT-VLAN
  setups. Always have a manual-port fallback.
- **Same RSA key is used for pairing and the TLS data channel.** Don't
  generate a separate key for TLS — it would just confuse the user.
- **Pairing is one-shot AND persistent.** After a successful `pair()`,
  the device persists the host's public key. The downstream does not
  need to repair on every connect (and shouldn't try).
- **`PairingException` is a subclass of `AdbConnectionError`.** Catch
  the more specific class to distinguish "wrong code" from "device
  unreachable."
- **`tv.adb_close()` should be called even if `setup()` failed**,
  since the TLS device may have a partially-established socket.
- **The pairing dialog on the TV stays open ~60s.** If your UX has
  the user typing the code into a different device, build for retries.
- **Don't auto-detect Wi-Fi vs. TCP at runtime.** See §6 — failures
  are slow and confusing. Prefer an explicit config setting.

---

## 9. Where to read in `androidtv` source

- `androidtv/adb_manager/adb_manager_sync.py` and
  `adb_manager_async.py` — the only place the new TLS branch lives.
  Look at `ADBPython{Sync,Async}.__init__` for device dispatch and
  `connect()` for the `tls_priv_pem` flow.
- `androidtv/wifi.py` — façade over `adb_shell.pairing` and
  `adb_shell.mdns`. The `_require_pairing()` / `_require_mdns()`
  helpers are how the optional-extra story is enforced.
- `androidtv/constants.py` — `CONN_TYPE_TCP`, `CONN_TYPE_TLS`,
  `VALID_CONNECTION_TYPES`, `DEFAULT_CONNECTION_TYPE`.
- `tests/patchers.py` and `tests/async_patchers.py` —
  `AdbDeviceTls{,Async}Fake` patchers and
  `PATCH_ADB_DEVICE_TLS{,_ASYNC}` constants. **Mirror these patterns
  when writing tests for your own TLS-aware code.**
- `tests/test_wifi.py` — example mocking of `adb_shell.pairing` /
  `adb_shell.mdns` for unit tests that don't need real hardware.
- `scripts/wifi_smoke_test.py` — runnable end-to-end test for use
  against a real device.

---

## 10. Quick-reference end-to-end example

```python
from androidtv import setup_async
from androidtv.wifi import pair_async, discover_connect_services_async, PairingException

ADBKEY = "/path/to/adbkey"

# --- One-time pairing (UI flow) ---
try:
    peer = await pair_async(
        host=user_entered_pair_ip,
        port=user_entered_pair_port,
        pairing_code=user_entered_code,
        adbkey=ADBKEY,
    )
    # Persist user_entered_pair_ip + peer.data (device GUID) in config.
except PairingException:
    # Surface as "wrong code or device not in pairing mode"
    raise

# --- Each subsequent connection ---
services = await discover_connect_services_async(timeout_s=4.0)
svc = next((s for s in services if s.host == known_host), None)
if svc is None:
    # Fall back to stored port; if that fails, ask user to re-toggle
    # Wireless debugging.
    host, port = stored_host, stored_port
else:
    host, port = svc.host, svc.port

tv = await setup_async.setup(
    host=host, port=port, adbkey=ADBKEY,
    connection_type="tls",
    transport_timeout_s=10.0, auth_timeout_s=10.0,
)
if not tv.available:
    raise RuntimeError("connection failed")

# Use tv exactly as you would today
await tv.update()
await tv.adb_close()
```

---

## 11. Smoke testing

Before integrating end-to-end, point `scripts/wifi_smoke_test.py` at a
real device:

```
venv/bin/python scripts/wifi_smoke_test.py discover
venv/bin/python scripts/wifi_smoke_test.py pair    --host … --port … --code … --adbkey …
venv/bin/python scripts/wifi_smoke_test.py connect --host … --port … --adbkey …
venv/bin/python scripts/wifi_smoke_test.py legacy  --host … --port 5555 --adbkey …
venv/bin/python scripts/wifi_smoke_test.py all     --adbkey …
```

`-v` enables DEBUG logging from `adb_shell` and `androidtv`. The
`legacy` subcommand is the regression check: prove nothing broke for
existing users.

---

## 12. Summary

- **Backwards compatibility:** zero-effort. Legacy paths are
  byte-for-byte unchanged.
- **Forward path:** add a `connection_type` config field; pass it to
  `setup()`; add a one-time `pair()` UI; prefer mDNS for discovery.
- **Dependencies:** opt-in via `androidtv[wifi]`. No new mandatory
  deps for the legacy path.
- **Verification:** 246 unit tests passing (231 baseline + 15 new),
  no regressions. Real-device verification via
  `scripts/wifi_smoke_test.py`.
