# Tinxy Local (ha-tinxylocal)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Home Assistant: 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12+-blue.svg)](https://www.home-assistant.io/)

A modern, fast, pure-Python Home Assistant custom integration for **100% local LAN control** of **Tinxy Smart Devices** (smart switches, fan controllers, and pulse door locks).

---

## Key Highlights & Improvements

* **100% Pure Python (Zero Binary Bloat)**: Replaces ~36 MB of bundled precompiled Go CLI binaries and subprocess forks with an in-memory, open-source XXTEA encryption engine (< 40 KB footprint).
* **Tuya-Local Setup Architecture**:
  * **Cloud-Assisted Setup**: Uses an ephemeral API key to automatically retrieve device topology and private device keys (`mqttPassword`), then **immediately discards the API key**. Home Assistant never stores your master account token.
  * **Manual Offline Setup**: 100% air-gapped setup using local IP and device key with zero outbound internet packets.
* **Instant Dashboard Feedback**: Optimistic state updates ensure switches flip instantaneously in Lovelace without the 0.5s–1.0s network delay.
* **Concurrent Command Queue (Fixes Upstream Issue #9)**: Implements an internal FIFO sequential queue with rate-limiting and connection reuse, preventing "Turn off all switches" scenes from overwhelming the single-threaded ESP web server.
* **HA 2026+ Ready**: Fully typed, passes `sw_version` as a string, and eliminates repeated device registry churn from the polling loop.
* **Diagnostic Sensors**: Exposes Wi-Fi signal strength in dBm (`SensorDeviceClass.SIGNAL_STRENGTH`), connected SSID, and local IP.
* **Native Zeroconf Discovery**: Automatically detects `tinxy*` devices on your local network.

---

## Migration from `arevindh/tinxylocal`

Because this integration preserves `DOMAIN = "tinxylocal"`, **all your existing entity IDs (e.g. `switch.living_room_foyer_light`), dashboard cards, recorder statistics, and automations continue working with zero breaking changes.**

To migrate cleanly in HACS:

1. In Home Assistant, open **HACS** > **Integrations**.
2. Find the old **Tinxy Local** integration card.
3. Click the three dots (⋮) in the top-right corner of the card and select **Redownload** or **Remove** (do **not** delete the integration under *Settings > Devices & Services*; only remove the HACS repo pointer).
4. Click the three dots (⋮) in the top right of the main HACS page > **Custom repositories**.
5. Add repository URL:
   ```text
   https://github.com/selvakk2k/ha-tinxylocal
   ```
   Category: **Integration**.
6. Click **Add**, find **Tinxy Local (LAN)**, and click **Download**.
7. Restart Home Assistant.

All your existing devices will automatically load using the new pure-Python engine.

---

## Installation via HACS

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. Go to **HACS** > **Integrations** > **Three dots (top right)** > **Custom repositories**.
3. Add repository:
   ```text
   https://github.com/selvakk2k/ha-tinxylocal
   ```
   Category: **Integration**.
4. Click **Download** and restart Home Assistant.

---

## Setup & Configuration

Go to **Settings** > **Devices & Services** > **Add Integration** > search for **Tinxy Local**.

### Option A: Cloud-Assisted Setup (Recommended)
1. Paste your Tinxy Cloud API Key (generated from your Tinxy portal).
2. Home Assistant makes an ephemeral HTTPS call to retrieve your device names and private device keys (`mqttPassword`).
3. Select your device from the dropdown and enter its local IP address on your network (e.g. `192.168.0.163`).
4. **The API key is discarded** and the integration switches to 100% local LAN operation.

### Option B: Manual Local Setup (100% Air-Gapped)
1. Select **Manual Local**.
2. Enter:
   * Device Name (e.g. "Living Room Switch")
   * Local IP address (`192.168.0.x`)
   * Device Key (`mqttPassword`)
   * Number of relays (e.g. 1, 2, 4, 6)
3. Connects directly to `http://<ip>/info` over your LAN. Zero cloud calls made.

---

## Supported Devices

* **Tinxy 1-Node Switch**
* **Tinxy 2-Node Switch**
* **Tinxy 4-Node Switch**
* **Tinxy 6-Node Switch**
* **Tinxy Fan Controllers** (3-speed percentage control: 33%, 66%, 100%)
* **Tinxy Door Locks** (Pulse unlock relay)

*(Note: EVA Bulbs require cloud MQTT and do not support local HTTP on port 80).*

---

## Troubleshooting

### Device times out or shows Unavailable
1. Assign a **static / reserved DHCP IP** to your Tinxy switch in your router settings.
2. Increase the **Request Timeout** (e.g. 8s) or **Polling Interval** (e.g. 15s) in **Settings > Devices & Services > Tinxy Local > Configure**.
3. If the onboard ESP microcontroller's socket crashes due to a Wi-Fi surge, power cycle the wall switch or circuit breaker for 10 seconds to reboot the hardware.

---

## Acknowledgements & Credits

* Originally based on and inspired by the work of [arevindh/tinxylocal](https://github.com/arevindh/tinxylocal) by **@arevindh** and earlier contributors.
* Licensed under the [GNU Affero General Public License v3.0](LICENSE).
