"""Config flow for Tinxy Local integration with ephemeral cloud setup and offline manual mode."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any

import aiohttp
import psutil
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_MQTT_PASS,
    CONF_POLLING_INTERVAL,
    CONF_RELAY_COUNT,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    TINXY_BACKEND,
)
from .hub import TinxyLocalHub
from .tinxycloud import TinxyAuthenticationException, TinxyCloud, TinxyHostConfiguration

_LOGGER = logging.getLogger(__name__)


async def async_discover_tinxy_devices(
    hass: HomeAssistant,
    target_chip_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan RFC 1918 private IP ranges and active local subnets for Tinxy devices.

    Covers:
      - Class C: 192.168.0.0/24, 192.168.1.0/24, 192.168.29.0/24 (JioFiber), 192.168.2.0/24, 192.168.31.0/24 (Mi)
      - Class A: 10.0.0.0/24, 10.0.1.0/24
      - Class B: 172.16.0.0/24, 172.16.1.0/24
      - System interfaces: Any actively configured IPv4 subnet on the host/container (psutil)
    Exits early as soon as all target_chip_ids are located.
    """
    discovered: dict[str, dict[str, Any]] = {}
    candidate_subnets: list[ipaddress.IPv4Network] = []

    # 1. Common home IoT and router defaults
    standard_subnets = [
        "192.168.0.0/24",
        "192.168.1.0/24",
        "192.168.29.0/24",
        "10.0.0.0/24",
        "10.0.1.0/24",
        "172.16.0.0/24",
        "192.168.2.0/24",
        "192.168.31.0/24",
    ]
    for s_net in standard_subnets:
        net = ipaddress.IPv4Network(s_net)
        if net not in candidate_subnets:
            candidate_subnets.append(net)

    # 2. Add any active network interfaces detected on the host/container
    try:
        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if getattr(addr, "family", None) in (2, socket.AF_INET) and not addr.address.startswith("127."):
                    net = ipaddress.IPv4Network(f"{addr.address}/24", strict=False)
                    if net not in candidate_subnets:
                        candidate_subnets.append(net)
    except Exception as if_err:
        _LOGGER.debug("Could not inspect network interfaces: %s", if_err)

    # 3. Add default gateway subnet if present in /proc/net/route
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if fields[1] == "00000000":
                    gw = socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
                    net = ipaddress.IPv4Network(f"{gw}/24", strict=False)
                    if net not in candidate_subnets:
                        candidate_subnets.append(net)
    except Exception:
        pass

    async def _probe_ip(session: aiohttp.ClientSession, ip: str) -> tuple[str, dict[str, Any]] | None:
        url = f"http://{ip}/info"
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=0.9, connect=0.5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and "chip_id" in data:
                        cid = str(data["chip_id"]).strip()
                        return cid, {"ip": ip, "info": data}
        except Exception:
            pass
        return None

    conn = aiohttp.TCPConnector(limit=300, force_close=True)
    async with aiohttp.ClientSession(connector=conn) as session:
        for net in candidate_subnets:
            tasks = [_probe_ip(session, str(host_ip)) for host_ip in net.hosts()]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res:
                    cid, val = res
                    discovered[cid] = val

            # Early exit if all target cloud devices have been located on the LAN
            if target_chip_ids and target_chip_ids.issubset(discovered.keys()):
                _LOGGER.debug("Located all %d target device(s) on subnet %s, ending scan early", len(target_chip_ids), net)
                break

    return discovered


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Tinxy Local."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.discovered_ip: str | None = None
        self.discovered_chip_id: str | None = None
        self.discovered_devices: dict[str, dict[str, Any]] = {}
        self.cloud_devices: list[dict[str, Any]] = []

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TinxyLocalOptionsFlowHandler:
        """Get the options flow handler."""
        return TinxyLocalOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Choose between Cloud-Assisted setup and Manual Offline setup."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["cloud", "manual"],
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a: Cloud-Assisted setup to query device list and local keys."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_token = user_input[CONF_API_KEY].strip()
            session = async_get_clientsession(self.hass)

            try:
                host_config = TinxyHostConfiguration(
                    api_token=api_token, api_url=TINXY_BACKEND
                )
                api = TinxyCloud(host_config=host_config, web_session=session)
                dev_list = await api.get_device_list()

                if not dev_list:
                    errors["base"] = "no_devices"
                else:
                    self.cloud_devices = dev_list

                    # Extract target chip IDs from cloud payload to prioritize scan
                    target_chip_ids = set()
                    for d in dev_list:
                        cid = d.get("uuidRef", {}).get("uuid") or d.get("chip_id")
                        if cid:
                            target_chip_ids.add(str(cid).strip())

                    # Auto-discover local device IP addresses across RFC 1918 ranges
                    try:
                        self.discovered_devices = await async_discover_tinxy_devices(
                            self.hass, target_chip_ids=target_chip_ids
                        )
                    except Exception as disc_err:
                        _LOGGER.debug("Local discovery probe failed: %s", disc_err)
                        self.discovered_devices = {}

                    return await self.async_step_select_cloud_device()
            except TinxyAuthenticationException:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Failed connecting to Tinxy cloud: %s", err)
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        autocomplete="off",
                    )
                )
            }
        )

        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

    async def async_step_select_cloud_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a cloud device and confirm its local IP address."""
        errors: dict[str, str] = {}

        # Exclude devices already configured in Home Assistant
        configured_ids = {
            entry.unique_id for entry in self._async_current_entries()
        }
        available_devices = [
            d for d in self.cloud_devices if d.get("_id") not in configured_ids
        ]

        if not available_devices:
            return self.async_abort(reason="already_configured")

        device_options: dict[str, str] = {}
        first_detected_ip: str | None = self.discovered_ip

        for d in available_devices:
            d_id = d["_id"]
            cid = str(d.get("uuidRef", {}).get("uuid") or d.get("chip_id") or "").strip()
            dev_name = d.get("name", "Tinxy Device")
            type_name = d.get("typeId", {}).get("name", "Switch")

            matched_ip = None
            if cid and cid in self.discovered_devices:
                matched_ip = self.discovered_devices[cid]["ip"]
                d["discovered_ip"] = matched_ip
                if not first_detected_ip:
                    first_detected_ip = matched_ip

            if matched_ip:
                device_options[d_id] = f"{dev_name} ({type_name}) — {matched_ip} (Discovered)"
            else:
                device_options[d_id] = f"{dev_name} ({type_name})"

        if not self.discovered_ip and first_detected_ip:
            self.discovered_ip = first_detected_ip

        if user_input is not None:
            target_id = user_input[CONF_DEVICE_ID]
            host_ip = user_input.get(CONF_HOST, "").strip()

            selected_device = next(
                (d for d in available_devices if d["_id"] == target_id), None
            )

            # Auto-fallback to discovered IP if field was left blank
            if not host_ip and selected_device and selected_device.get("discovered_ip"):
                host_ip = selected_device["discovered_ip"]

            if selected_device and host_ip:
                session = async_get_clientsession(self.hass)
                hub = TinxyLocalHub(self.hass, host_ip)
                status = await hub.validate_ip(session)

                if status != "ok":
                    errors["base"] = "cannot_connect_local"
                else:
                    await self.async_set_unique_id(selected_device["_id"])
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=selected_device.get("name", "Tinxy Switch"),
                        data={
                            CONF_HOST: host_ip,
                            CONF_DEVICE_ID: selected_device["_id"],
                            CONF_MQTT_PASS: selected_device.get("mqttPassword", ""),
                            CONF_DEVICE: selected_device,
                        },
                    )
            elif not host_ip:
                errors["base"] = "cannot_connect_local"

        first_device_id = available_devices[0]["_id"] if available_devices else None
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID, default=first_device_id): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=k, label=v)
                            for k, v in device_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_HOST, default=self.discovered_ip or ""
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(
            step_id="select_cloud_device", data_schema=schema, errors=errors
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2b: Manual 100% offline setup using IP and device key."""
        errors: dict[str, str] = {}

        if user_input is None:
            # Pre-fill discovered IP in manual flow if available
            if not self.discovered_ip:
                try:
                    disc = await async_discover_tinxy_devices(self.hass)
                    if disc:
                        self.discovered_ip = next(iter(disc.values()))["ip"]
                except Exception:
                    pass
        else:
            host_ip = user_input[CONF_HOST].strip()
            mqtt_pass = user_input[CONF_MQTT_PASS].strip()
            dev_type = user_input.get("device_type", "switch")
            relay_count = int(user_input.get(CONF_RELAY_COUNT, 1))
            name = user_input.get("name", "Tinxy Device").strip()

            session = async_get_clientsession(self.hass)
            hub = TinxyLocalHub(self.hass, host_ip)
            status = await hub.validate_ip(session)

            if status != "ok":
                errors["base"] = "cannot_connect_local"
            else:
                device_id = f"tinxy_{host_ip.replace('.', '_')}"
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                if dev_type == "fan":
                    synthetic_device = {
                        "_id": device_id,
                        "name": name,
                        "mqttPassword": mqtt_pass,
                        "devices": [name],
                        "deviceTypes": ["Fan"],
                        "typeId": {"name": "Tinxy Fan Controller"},
                    }
                elif dev_type == "lock":
                    synthetic_device = {
                        "_id": device_id,
                        "name": name,
                        "mqttPassword": mqtt_pass,
                        "devices": [name],
                        "deviceTypes": ["Lock"],
                        "typeId": {"name": "Tinxy Door Lock", "gtype": "action.devices.types.LOCK"},
                    }
                else:
                    relays = [f"Switch {i+1}" for i in range(relay_count)]
                    types = ["Switch"] * relay_count
                    synthetic_device = {
                        "_id": device_id,
                        "name": name,
                        "mqttPassword": mqtt_pass,
                        "devices": relays,
                        "deviceTypes": types,
                        "typeId": {"name": f"Tinxy {relay_count}-Node Switch"},
                    }

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host_ip,
                        CONF_DEVICE_ID: device_id,
                        CONF_MQTT_PASS: mqtt_pass,
                        CONF_DEVICE: synthetic_device,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required("name", default="Tinxy Device"): selector.TextSelector(),
                vol.Required(
                    CONF_HOST, default=self.discovered_ip or ""
                ): selector.TextSelector(),
                vol.Required(CONF_MQTT_PASS): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        autocomplete="off",
                    )
                ),
                vol.Required(
                    "device_type", default="switch"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="switch", label="Smart Switch (Relays)"),
                            selector.SelectOptionDict(value="fan", label="Fan Controller (3-Speed)"),
                            selector.SelectOptionDict(value="lock", label="Pulse Door Lock"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_RELAY_COUNT, default=2
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=8, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="manual", data_schema=schema, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle Zeroconf mDNS discovery (tinxy*)."""
        self.discovered_ip = discovery_info.host
        service_name = discovery_info.name.split(".")[0]
        self.discovered_chip_id = service_name

        # Prevent duplicate prompts
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == self.discovered_ip:
                return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {
            "name": f"Tinxy Device ({self.discovered_ip})"
        }
        return await self.async_step_user()


class TinxyLocalOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options to modify polling interval, timeout, and device key."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            updated_data = {**self.config_entry.data}
            updated_options = {**self.config_entry.options}

            if user_input.get(CONF_HOST):
                updated_data[CONF_HOST] = user_input[CONF_HOST]

            if user_input.get(CONF_MQTT_PASS):
                updated_data[CONF_MQTT_PASS] = user_input[CONF_MQTT_PASS]

            updated_options[CONF_REQUEST_TIMEOUT] = user_input[CONF_REQUEST_TIMEOUT]
            updated_options[CONF_POLLING_INTERVAL] = user_input[CONF_POLLING_INTERVAL]

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
                options=updated_options,
            )
            return self.async_create_entry(title="", data=updated_options)

        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_pass = self.config_entry.data.get(CONF_MQTT_PASS, "")
        current_timeout = self.config_entry.options.get(
            CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT
        )
        current_polling = self.config_entry.options.get(
            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): selector.TextSelector(),
                vol.Required(
                    CONF_MQTT_PASS, default=current_pass
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        autocomplete="off",
                    )
                ),
                vol.Required(
                    CONF_REQUEST_TIMEOUT, default=current_timeout
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_POLLING_INTERVAL, default=current_polling
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=3,
                        max=300,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
