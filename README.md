# Tinxy Local Integration (`ha-tinxylocal`)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/selvakk2k/ha-tinxylocal)](https://github.com/selvakk2k/ha-tinxylocal/releases)
[![AI-Assisted](https://img.shields.io/badge/AI%20Assisted-Antigravity%20%7C%20Claude-blueviolet?style=flat-square&logo=google)](https://github.com/selvakk2k)
[![AI Attribution](https://img.shields.io/badge/AI%20Attribution-AIA%20PAI%20Nc%20Hin-orange?style=flat-square)](https://aiattribution.github.io/)

A modern, fast, pure-Python Home Assistant custom integration for **100% local LAN control** of **Tinxy Smart Devices** (smart switches, fan controllers, and pulse door locks).

This repository is a modern, pure-Python reimplementation of `arevindh/tinxylocal`, designed to eliminate bundled Go CLI binaries, resolve Home Assistant 2026+ deprecations, and introduce a concurrency-safe sequential command queue.

> [!IMPORTANT]
> This integration is designed for Tinxy devices with **local HTTP control enabled**. It is **not compatible** with Tinxy EVA smart bulbs, which communicate over a proprietary sub-GHz RF mesh back to an EVA hub/node and do not receive a local LAN IP address or run an HTTP server on port 80.

---

## Features

### 1. Pure Python Architecture (Zero Binaries)
* **No Compiled CLI Binaries**: Completely eliminates the ~36 MB of bundled Go CLI executables (`tinxy-cli_*`), shared libraries, and `asyncio.create_subprocess_exec` process forks.
* **In-Memory XXTEA Engine**: Implements the native XXTEA block cipher directly in Python with zero external pip dependencies (< 0.05ms execution time, 100% platform-independent).
* **Instant Dashboard Feedback**: Optimistic state updates ensure switches flip instantaneously in the Lovelace UI without the 0.5s–1.0s network round-trip delay.

### 2. Dual Setup Architecture (Cloud-Assisted or Air-Gapped)
* **Cloud-Assisted Setup**: Uses an ephemeral API key to automatically retrieve device topology and private device keys (`mqttPassword`), then **immediately discards the API key**. Home Assistant never stores your master account token.
* **Manual Offline Setup**: 100% air-gapped setup using local IP and device key with zero outbound internet packets.
* **Configurable Polling & Timeout**: Customize request timeouts and polling intervals directly from the UI, with immediate background reloading.

### 3. Concurrency & Reliability (Fixes Upstream Issue #9)
* **Sequential FIFO Command Queue**: Implements an internal rate-limited queue with connection reuse (HTTP keep-alive), preventing simultaneous "Turn off all switches" scenes from overwhelming the single-threaded ESP web server.
* **Automatic Deduplication**: Rapid repeat toggles for the same relay are automatically superseded in the queue.
* **Safe Credential Handling**: Resolves brittle `nodes[0]` references by passing the device key directly to each entity.

### 4. Diagnostics & HA 2026+ Standards
* **String-Coerced Firmware**: Resolves the `sw_version` integer warning, ensuring compliance ahead of Home Assistant 2026.12.0.
* **Zero Registry Churn**: Eliminates recurring `device_registry.async_get_or_create` calls from the polling loop.
* **Diagnostic Sensors**: Exposes Wi-Fi signal strength in dBm (`SensorDeviceClass.SIGNAL_STRENGTH`), connected SSID, and local IP address under the device card.
* **Native Zeroconf Discovery**: Automatically detects `tinxy*` devices on your local network.

---

## Tested Models

This integration has been tested on the following hardware models:

| Model | Source | Features Verified |
| :--- | :--- | :--- |
| **Tinxy 2-Node Switch** | Tested in this repository | 2x Relay Control, Optimistic UI, RSSI & Diagnostic Sensors, Queue Concurrency |
| **Tinxy 1-Node Switch** | Assumed compatible | Single Relay Control |
| **Tinxy 4-Node Switch** | Assumed compatible | 4x Relay Control, Sequential Dispatch |
| **Tinxy 6-Node Switch** | Assumed compatible | 6x Relay Control, Sequential Dispatch |
| **Tinxy Fan Controllers** | Assumed compatible | 3-Speed Percentage Control (33%, 66%, 100%), Speed Memory on Toggle |
| **Tinxy Door Locks** | Assumed compatible | Pulse Unlock Relay |

---

## Caveats & Integration Limitations

* **Single-Threaded ESP Web Server**: Tinxy devices run on low-power ESP microcontrollers whose local HTTP server cannot handle simultaneous TCP connections. All outgoing control commands are managed through an internal sequential queue (~0.25s spacing) to prevent socket lockups.
* **Local Polling vs. Cloud Push**: Device status is polled over LAN via `GET /info` at your configured interval (default 15 seconds). Dashboard interactions update optimistically in 0ms, but physical wall-switch changes will reflect in Home Assistant on the next poll cycle.
* **EVA Bulbs Unsupported**: Tinxy EVA smart bulbs communicate over a proprietary sub-GHz RF mesh back to an EVA hub or bridge node; they do not have a LAN IP address or a local HTTP server.

---

## Migration from `arevindh/tinxylocal`

Because this integration preserves `DOMAIN = "tinxylocal"`, **all your existing entity IDs (e.g. `switch.living_room_foyer_light`), dashboard cards, recorder statistics, and automations continue working with zero breaking changes.**

To migrate cleanly:

1. In Home Assistant, navigate to **HACS** → **Integrations**.
2. Locate the old **Tinxy Local** integration card.
3. Click the three dots (⋮) on the card and select **Remove** (do **not** delete the integration under *Settings → Devices & Services*; only remove the HACS repository pointer).
4. *(Recommended)* Using the Studio Code Server add-on or terminal, remove the old `custom_components/tinxylocal/build` folder to purge the ~36 MB of legacy Go binaries:
   ```bash
   rm -rf /config/custom_components/tinxylocal/build
   ```
5. In HACS, click the three dots (⋮) in the top-right corner → **Custom repositories**.
6. Under **URL**, add:
   ```text
   https://github.com/selvakk2k/ha-tinxylocal
   ```
7. Select **Integration** as the category and click **Add**.
8. Find **Tinxy Local (LAN)**, click **Download**, and restart Home Assistant.

All your existing devices will automatically load using the new pure-Python engine.

---

## Installation

### Method 1: Using HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** → **Integrations** → click the three dots (⋮) in the top-right corner.
3. Select **Custom repositories**.
4. Under **URL**, add:
   ```text
   https://github.com/selvakk2k/ha-tinxylocal
   ```
5. Select **Integration** as the category and click **Add**.
6. Search for **Tinxy Local (LAN)**, click **Download**, and restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release ZIP from the [Releases](https://github.com/selvakk2k/ha-tinxylocal/releases) page.
2. Copy the folder `custom_components/tinxylocal` into your Home Assistant's `custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings → Devices & Services** → **+ Add Integration**.
2. Search for **Tinxy Local**.

### Option A: Cloud-Assisted Setup (Recommended)
1. Select **Cloud-Assisted**.
2. Paste your Tinxy Cloud API Key (generated from your Tinxy portal).
3. Home Assistant makes an ephemeral HTTPS call to retrieve your device names and private device keys (`mqttPassword`).
4. Select your device from the dropdown and enter its local IP address on your network (e.g. `192.168.0.163`).
5. **The API key is discarded** and the integration switches to 100% local LAN operation.

### Option B: Manual Local Setup (100% Air-Gapped)
1. Select **Manual Local**.
2. Enter:
   * **Device Name** (e.g. "Living Room Switch", "Bedroom Fan", or "Main Door")
   * **Local IP Address** (`192.168.0.x`)
   * **Device Key** (`mqttPassword`)
   * **Device Type**:
     * **Smart Switch (Relays)**: Select channel count (1, 2, 4, 6, or 8 nodes).
     * **Fan Controller**: Automatically configures 3-speed percentage fan control (33%, 66%, 100%).
     * **Pulse Door Lock**: Automatically configures door lock pulse-relay control.
3. Connects directly to `http://<ip>/info` over your LAN. Zero cloud calls made.

### Options & Per-Device Tuning

Click **Configure** on any Tinxy device card to customize:
* **Local IP Address**: Update device IP if it changes.
* **Device Key**: View or update the masked `mqttPassword`.
* **Request Timeout**: Adjust network timeout (1–30 seconds).
* **Polling Interval**: Adjust status polling frequency (3–300 seconds).

---

## Troubleshooting & Logs

### 1. Device Times Out or Shows Unavailable
* **DHCP Reservation**: Assign a static / reserved IP to your Tinxy switch in your router settings.
* **Adjust Timeout & Polling**: If Wi-Fi reception is weak, increase the **Request Timeout** (e.g. 8s) and **Polling Interval** (e.g. 15s) under **Configure**.
* **Microcontroller Recovery**: If the onboard ESP socket crashes due to a network glitch, power-cycle the wall switch or circuit breaker for 10 seconds to reboot the hardware.

### 2. Enabling Debug Logging
Add the following to your `configuration.yaml` and restart Home Assistant:
```yaml
logger:
  default: warning
  logs:
    custom_components.tinxylocal: debug
```

---

## Credits & License

### Upstream Authors & Contributors
* Originally designed and written by [@arevindh](https://github.com/arevindh) and contributors in [`arevindh/tinxylocal`](https://github.com/arevindh/tinxylocal).
* Special thanks to earlier community contributors for reverse-engineering the Tinxy local protocol.

### Project Contributors & AI Attribution
* **Lead Architecture & Hardware Validation**: [@selvakk2k](https://github.com/selvakk2k) — physical testing on Tinxy hardware, design requirements, and integration architecture.
* **Implementation & Engineering**: **Antigravity** (Google DeepMind) — pure-Python XXTEA cryptographic engine, asynchronous queue concurrency architecture, Home Assistant 2026+ lifecycle migrations, and automated test suites.
* **Pre-Release Code Review & Auditing**: **Claude** (Anthropic) — independent architectural review, edge-case analysis, and verification of upstream compatibility.

Licensed under the **GNU Affero General Public License v3.0**. See the [LICENSE](LICENSE) file for the full license text.
