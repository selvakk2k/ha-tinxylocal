# Tinxy Local Python (`ha-tinxylocal`)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/selvakk2k/ha-tinxylocal?style=flat-square)](https://github.com/selvakk2k/ha-tinxylocal/releases)
[![AI-Assisted](https://img.shields.io/badge/AI%20Assisted-Antigravity%20%7C%20Claude-blueviolet?style=flat-square&logo=google)](https://github.com/selvakk2k)
[![AI Attribution](https://img.shields.io/badge/AI%20Attribution-AIA%20PAI%20Nc%20Hin-orange?style=flat-square)](https://aiattribution.github.io/interpret-attribution)

A fast, pure-Python Home Assistant integration for **100% local control** of **Tinxy Smart Devices** (smart switches, fan controllers, and pulse door locks) over your home Wi-Fi network.

This repository is a modern, pure-Python rewrite of `arevindh/tinxylocal`. It removes external compiled binaries, adds safe command spacing, and supports Home Assistant 2026+ standards.

> [!IMPORTANT]
> This integration works with Tinxy devices that have **local HTTP control enabled**. It is **not compatible** with Tinxy EVA smart bulbs, which communicate over a proprietary RF mesh back to an EVA hub and do not have a local Wi-Fi IP address.

> [!IMPORTANT]
> ### Finding Your API Token
> In the Tinxy mobile app, tap the **hamburger menu icon (☰) in the top-right corner** and select **API Token**.

> [!CAUTION]
> ### Critical Security & Credential Warnings
> * **Never Share Your Tinxy API Token**: Tinxy account API tokens have **no expiration date and cannot be revoked** from the app or portal. If your API token is ever leaked publicly (e.g. in GitHub issues, forum posts, or diagnostic logs), the **only** way to invalidate it is to create a completely new Tinxy account.
> * **Never Share Your Device Key (`mqttPassword`)**: Device keys do not expire. If a device key is exposed, the only way to invalidate it and generate a new key is to completely remove and re-pair the physical device in the Tinxy mobile app.


---

## Table of Contents

1. [Features](#features)
2. [Tested Hardware Models](#tested-hardware-models)
3. [Important Notes & Hardware Limits](#important-notes--hardware-limits)
4. [How to Migrate from `arevindh/tinxylocal`](#how-to-migrate-from-arevindhtinxylocal)
5. [Installation](#installation)
6. [Setup & Configuration](#setup--configuration)
   - [Automatic Discovery (Zeroconf / mDNS)](#automatic-discovery-zeroconf--mdns)
   - [Manual Setup Workflow](#manual-setup-workflow)
   - [Updating Settings & Keys In-Place](#updating-settings--keys-in-place)
7. [Troubleshooting](#troubleshooting)
8. [My Integrations & Lovelace Cards](#my-integrations--lovelace-cards)
9. [Credits & License](#credits--license)

---

## Features

### 1. Pure Python (No Extra Binaries or Drivers)
* **Zero External Binaries**: Completely eliminates the ~36 MB of bundled Go CLI executables (`tinxy-cli`), helper scripts, and background terminal processes.
* **Built-in Encryption**: Uses pure Python to handle Tinxy's local XXTEA encryption directly in memory with zero extra dependencies (< 0.05ms execution time).
* **Instant Dashboard Feedback**: Switches respond instantly in the Home Assistant dashboard without waiting for network delays.

### 2. Simple & Private Setup
* **Automatic Discovery (Zeroconf / mDNS)**: Automatically detects Tinxy devices on your local network and offers a two-step choice between Cloud-Assisted or Manual Offline setup:
  * **Cloud-Assisted Setup**: Uses your Tinxy account token once during setup to discover devices, fetch their private local keys (`mqttPassword`), and automatically find their IP addresses on your home network. **The token is never stored in Home Assistant.**
  * **Manual Offline Setup**: Set up devices directly with their local IP address and private key—no internet connection or cloud account needed.
* **Official Reconfigure Flow**: Click the **⋮** menu on any device card → **Reconfigure** to update the local IP address or Device Key in-place with instant validation.
* **Automatic DHCP IP Sync**: Automatically updates device IP addresses when your router assigns a new DHCP address, without breaking automations or entity IDs.

### 3. Reliability & Hardware Protection
* **Smart Command Queue**: Manages outgoing commands with safe spacing (~0.35s) and closes connections immediately (`Connection: close`). This prevents rapid button presses or automations from overloading the small microcontroller inside the switch.
* **Hardware Replay Protection**: Automatically manages unique timestamps so the switch never rejects back-to-back toggles with `HTTP 400 Bad Request`.
* **Subnet Auto-Detection**: Automatically searches across home IP ranges (`192.168.x.x`, `10.x.x.x`, `172.16.x.x`) to pre-fill device IP addresses during setup.

### 4. Diagnostics & Home Assistant Standards
* **Multi-Node Diagnostic Sensors**: Monitors Wi-Fi signal strength in dBm, connected Wi-Fi network (SSID), and local IP address for every node on the device card.
* **Actionable Error Diagnostics**: Provides clear guidance in logs if a command is rejected (HTTP 400), directing you to verify the Device Key in options or check time synchronization.
* **Zero Database Clutter**: Eliminates recurring database writes and device registry churn during polling.

---

## Tested Hardware Models

| Model | Source | Features Verified |
| :--- | :--- | :--- |
| **Tinxy 2-Node Switch** (`WIFI_2SWITCH_V3`) | Tested in this repository | 2x Switch/Relay Control, Fast UI, Wi-Fi Diagnostics, Queue Spacing |
| **Tinxy 1-Node Switch** | Compatible | Single Relay Control |
| **Tinxy 4-Node Switch** | Compatible | 4x Relay Control, Queue Spacing |
| **Tinxy 6-Node Switch** | Compatible | 6x Relay Control, Queue Spacing |
| **Tinxy Fan Controllers** | Compatible | 3-Speed Control (33%, 66%, 100%), Speed Memory on Toggle |
| **Tinxy Door Locks** | Compatible | Pulse Unlock Relay |

---

## Important Notes & Hardware Limits

> [!IMPORTANT]
> ### Cloud Commissioning & App Retention
> * **Initial Wi-Fi Pairing**: Tinxy devices must initially be paired using the official Tinxy mobile app to connect them to your 2.4 GHz Wi-Fi network and generate their communication credentials. Devices fresh out of the box or in setup hotspot mode (`Tinxy-XXXX`) cannot be detected by Home Assistant until joined to Wi-Fi.
> * **Keep Devices in the App**: Do **not** delete the device from your Tinxy mobile app after adding it to Home Assistant. Deleting a device from the cloud account triggers a factory password reset on the device, breaking local authentication.
> * **Optional Internet Isolation**: Once paired with Home Assistant, you can safely block the device's IP address from accessing the internet in your Wi-Fi router or firewall settings. Because this integration operates 100% locally over LAN, the device will continue functioning offline, preventing accidental cloud resets or remote updates.
* **Microcontroller Capacity**: Tinxy devices run on lightweight ESP microcontrollers that handle one connection at a time. The integration uses a queue to send commands safely one after another.
* **Local Polling**: Home Assistant checks device status over your home Wi-Fi every 15 seconds (configurable). Dashboard toggles update immediately, while flips of the physical wall switch update on the next poll cycle.
* **EVA Bulbs Unsupported**: Tinxy EVA smart bulbs use a proprietary RF mesh back to an EVA bridge and do not have an IP address on your Wi-Fi network.

---

## How to Migrate from `arevindh/tinxylocal`

Because this integration uses the exact same domain (`tinxylocal`), **all your existing entity names (e.g. `switch.living_room_foyer_light`), dashboard cards, and automations continue working with zero changes.**

### Migration Steps:

1. In Home Assistant, open **HACS** → **Integrations**.
2. Find the old **Tinxy Local** integration card.
3. Click the three dots (⋮) on the card and select **Remove**.
   > [!TIP]
   > **Handling the HACS Warning Dialog**: When you click Remove, HACS will detect existing configured devices and display a dialog stating *"This integration is currently configured... navigate to the integration to remove it or ignore"*. **Click IGNORE**. Do **not** remove the integration under *Settings → Devices & Services*, otherwise your entity IDs, automations, and dashboard cards will be deleted. Clicking **Ignore** safely unlinks the old repository from HACS while preserving all your configured devices in Home Assistant.
4. *(Recommended)* Open your Home Assistant terminal or Studio Code Server add-on, and delete the old binary build folder to free up ~36 MB of disk space:
   ```bash
   rm -rf /config/custom_components/tinxylocal/build
   ```
5. In HACS, click the three dots (⋮) in the top-right corner → **Custom repositories**.
6. Under **Repository**, enter:
   ```text
   https://github.com/selvakk2k/ha-tinxylocal
   ```
7. Select **Integration** as the category and click **Add**.
8. Find **Tinxy Local Python**, click **Download**, and restart Home Assistant.

Home Assistant will automatically run the upgrade migration, strip any old plaintext account tokens from storage for privacy, and load your devices using the new code.

---

## Installation

### Method 1: Via HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=selvakk2k&repository=ha-tinxylocal&category=integration)

1. Click the **Open repository in HACS** button above, or open **HACS** from your Home Assistant sidebar.
2. Click the top-right menu (⋮) → **Custom repositories** → Add `https://github.com/selvakk2k/ha-tinxylocal` with category **Integration**.
3. Search for **Tinxy Local Python**, click **Download**, and restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release zip file from the [Releases](https://github.com/selvakk2k/ha-tinxylocal/releases) page.
2. Unzip and copy the `custom_components/tinxylocal` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Setup & Configuration

> [!IMPORTANT]
> **Do Not Remove Devices from the Mobile App**:
> Tinxy hardware requires initial pairing via the official Tinxy app to connect to Wi-Fi and create device credentials. Keep the device registered in your app; deleting it resets the hardware's internal encryption key. If you want pure local isolation with zero cloud contact, block the device's internet access at your Wi-Fi router instead.

### Automatic Discovery (Zeroconf / mDNS)

> [!NOTE]
> **Only Discovers Already-Commissioned Devices**: Auto-detection discovers Tinxy devices that are already connected to your home Wi-Fi network. If a device is unboxed or factory-reset, it broadcasts its own temporary Wi-Fi access point (`Tinxy-XXXX`) and cannot be seen by Home Assistant until you join it to your home Wi-Fi via the Tinxy mobile app.

Tinxy devices on your Wi-Fi network are automatically discovered by Home Assistant. When a discovery notification appears:
1. Click **Configure**.
2. Choose your preferred setup path:
   * **Cloud-Assisted**: Enter your Tinxy API Token to automatically look up the Device Key (`mqttPassword`), official name, and channel topology from your account.
   * **Manual Offline**: Enter the 10-character Device Key directly for 100% local, air-gapped onboarding.

### Manual Setup Workflow

1. In Home Assistant, go to **Settings → Devices & Services** → **+ Add Integration**.
2. Search for **Tinxy Local Python**.

### Option A: Cloud-Assisted Setup (Recommended)
1. Choose **Cloud-Assisted Setup**.
2. Paste your Tinxy API Token (found in the Tinxy mobile app by tapping the hamburger menu ☰ in the top-right corner → **API Token**).
3. Home Assistant connects once to fetch your devices and automatically scans your local network to find and pre-fill their IP addresses.
4. Select your device from the list and submit.
5. The API token is immediately discarded, and all communication continues 100% locally on your home network.

### Option B: Manual Offline Setup (No Internet Required)
1. Choose **Manual Offline Setup**.
2. Select your device type:
   * **Smart Switch (1 to 8 Relays)**: Enter name, local IP, device key, and number of relays.
   * **Fan Controller (3-Speed)**: Enter name, local IP, and device key.
   * **Pulse Door Lock**: Enter name, local IP, and device key.
3. Home Assistant connects directly to the device on your local network.

### Updating Settings & Keys In-Place

You can update device connection settings at any time without removing or re-adding the device:
* **Reconfigure Flow (Recommended)**: Click the **⋮** menu on the Tinxy device card → **Reconfigure** to update the Local IP address or Device Key with immediate local reachability validation.
* **Options Flow (Gear Icon)**: Click **Configure** on the integration card to adjust the request timeout (default: 5s) or background polling interval (default: 5s).
* **Automatic DHCP IP Sync**: If your home router assigns a new local IP address to a paired device, Home Assistant detects the change via Zeroconf (mDNS) and updates the IP automatically without breaking automations.

---

## Troubleshooting

### 1. Device Shows Unavailable
* **DHCP Reservation**: In your Wi-Fi router settings, reserve a static IP for your Tinxy switch so its address never changes.
* **Weak Wi-Fi**: If reception is weak, increase the **Request Timeout** (e.g. 8 seconds) under **Configure**.
* **Device Restart**: If the device stops responding on Wi-Fi, turn off the physical wall switch or breaker for 10 seconds and turn it back on.

### 2. Enabling Debug Logs
To view detailed logs for troubleshooting, add this to your `configuration.yaml` and restart Home Assistant:
```yaml
logger:
  default: warning
  logs:
    custom_components.tinxylocal: debug
```

---

## My Integrations & Lovelace Cards

| Integration / Card | Category | Description | Status |
| :--- | :--- | :--- | :--- |
| [Panasonic AC India](https://github.com/selvakk2k/ha-miraie-ac-in) | Integration | Local IR & Cloud MQTT control for Panasonic MirAIe Air Conditioners | `Beta` |
| [Panasonic AC India Card](https://github.com/selvakk2k/miraie-ac-card-in) | Lovelace Card | Modern Lovelace card for Panasonic ACs (MirAIe platform) | `Beta` |
| [Indian BLDC Fan IR](https://github.com/selvakk2k/superfan_ir) | Integration | Native Home Assistant integration for Indian BLDC ceiling fans (Superfan, Atomberg) | `Beta` |
| [Indian BLDC Fan Card](https://github.com/selvakk2k/superfan-card) | Lovelace Card | Interactive Lovelace card with speed dial & mode toggles for BLDC fans | `Beta` |
| [IFB Washer Local](https://github.com/selvakk2k/ifb-washer-local) | Integration | Local Wi-Fi integration for IFB Front Load Washing Machines & Washer Dryers | `Beta` |
| [IFB Washer Card](https://github.com/selvakk2k/ifb-washer-card) | Lovelace Card | Dedicated Lovelace card for IFB washers & dryers with cycle controls | `Beta` |
| [Tinxy Local Python](https://github.com/selvakk2k/ha-tinxylocal) | Integration | Pure-Python local control for Tinxy smart switches and modules | `Stable` |

---

## Credits & License

### Upstream Authors & Contributors
* Originally created by [@arevindh](https://github.com/arevindh) and community contributors in [`arevindh/tinxylocal`](https://github.com/arevindh/tinxylocal).

### Fork Maintainers & Contributors
* **Lead Architecture & Hardware Testing**: [@selvakk2k](https://github.com/selvakk2k) — hardware validation on physical Tinxy switches, requirements, and release maintenance.
* **Implementation & Engineering**: **Antigravity** (Google DeepMind) — pure-Python XXTEA encryption, asynchronous queue concurrency architecture, Home Assistant lifecycle migration, and automated test suite.
* **Code Review & Auditing**: **Claude** (Anthropic) — architectural review, edge-case analysis, and upstream compatibility validation.

Licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE) for details.
