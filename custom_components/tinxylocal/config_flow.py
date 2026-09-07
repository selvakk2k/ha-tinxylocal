"""Config flow for Tinxy Local integration."""

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
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    hass: Any,
    target_chip_ids: set[str] | None = None,
    discovery_timeout: float = 0.9,
) -> dict[str, dict[str, Any]]:
    """Scan candidate subnets and host interfaces via HTTP GET /info."""
    discovered: dict[str, dict[str, Any]] = {}
    candidate_subnets: list[ipaddress.IPv4Network] = []

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

    try:
        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if getattr(addr, "family", None) in (2, socket.AF_INET) and not addr.address.startswith("127."):
                    net = ipaddress.IPv4Network(f"{addr.address}/24", strict=False)
                    if net not in candidate_subnets:
                        candidate_subnets.append(net)
    except Exception as if_err:
        _LOGGER.debug("Could not inspect network interfaces: %s", if_err)

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
                url, timeout=aiohttp.ClientTimeout(total=discovery_timeout, connect=0.5)
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

            if target_chip_ids and target_chip_ids.issubset(discovered.keys()):
                _LOGGER.debug("Located all %d target device(s) on subnet %s, ending scan early", len(target_chip_ids), net)
                break

    return discovered


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Tinxy Local."""

    VERSION = 2

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
        return TinxyLocalOptionsFlowHandler(config_entry)

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

                    target_chip_ids = set()
                    for d in dev_list:
                        cid = d.get("uuidRef", {}).get("uuid") or d.get("chip_id")
                        if cid:
                            target_chip_ids.add(str(cid).strip())

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

        return self.async_show_form(
            step_id="cloud", data_schema=schema, errors=errors
        )

    async def async_step_select_cloud_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Select which device from cloud account to add locally."""
        errors: dict[str, str] = {}

        configured_ids = {
            entry.data.get(CONF_DEVICE_ID)
            for entry in self._async_current_entries()
            if entry.data.get(CONF_DEVICE_ID)
        }

        available_devices = [
            d for d in self.cloud_devices if d.get("_id") not in configured_ids
        ]

        if not available_devices:
            return self.async_abort(reason="already_configured")

        first_detected_ip: str | None = None
        device_options = {}
        for dev in available_devices:
            d_id = dev["_id"]
            d_name = dev.get("name", "Tinxy Device")
            chip_id = str(dev.get("uuidRef", {}).get("uuid") or dev.get("chip_id") or "").strip()

            detected_info = self.discovered_devices.get(chip_id)
            if detected_info and "ip" in detected_info:
                ip = detected_info["ip"]
                if first_detected_ip is None:
                    first_detected_ip = ip
                label = f"{d_name} — {ip} (Discovered)"
            else:
                label = f"{d_name} ({chip_id})" if chip_id else d_name

            device_options[d_id] = label

        if first_detected_ip:
            self.discovered_ip = first_detected_ip

        if user_input is not None:
            selected_id = user_input[CONF_DEVICE_ID]
            host_ip = user_input[CONF_HOST].strip()

            selected_device = next(
                (d for d in available_devices if d["_id"] == selected_id), None
            )

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
        """Step 2b: Manual Offline Setup - device type menu."""
        return self.async_show_menu(
            step_id="manual",
            menu_options=["manual_switch", "manual_fan", "manual_lock"],
        )

    async def async_step_manual_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a multi-node smart switch manually."""
        return await self._handle_manual_device(
            step_id="manual_switch",
            dev_type="switch",
            include_relays=True,
            default_name="Tinxy Switch",
            user_input=user_input,
        )

    async def async_step_manual_fan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a fan controller manually (no relay option)."""
        return await self._handle_manual_device(
            step_id="manual_fan",
            dev_type="fan",
            include_relays=False,
            default_name="Tinxy Fan",
            user_input=user_input,
        )

    async def async_step_manual_lock(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a pulse door lock manually (no relay option)."""
        return await self._handle_manual_device(
            step_id="manual_lock",
            dev_type="lock",
            include_relays=False,
            default_name="Tinxy Lock",
            user_input=user_input,
        )

    async def _handle_manual_device(
        self,
        step_id: str,
        dev_type: str,
        include_relays: bool,
        default_name: str,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Shared handler for manual device creation."""
        errors: dict[str, str] = {}

        if user_input is None:
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
            name = user_input.get("name", default_name).strip()
            relay_count = int(user_input.get(CONF_RELAY_COUNT, 1)) if include_relays else 1

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

        schema_dict: dict[Any, Any] = {
            vol.Required("name", default=default_name): selector.TextSelector(),
            vol.Required(
                CONF_HOST, default=self.discovered_ip or ""
            ): selector.TextSelector(),
            vol.Required(CONF_MQTT_PASS): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.PASSWORD,
                    autocomplete="off",
                )
            ),
        }

        if include_relays:
            schema_dict[vol.Optional(CONF_RELAY_COUNT, default=2)] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=8, mode=selector.NumberSelectorMode.BOX
                )
            )

        return self.async_show_form(
            step_id=step_id, data_schema=vol.Schema(schema_dict), errors=errors
        )


class TinxyLocalOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Tinxy Local integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow handler."""
        if config_entry is not None:
            self._entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return config entry."""
        if hasattr(self, "_entry"):
            return self._entry
        return super().config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage device options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            updated_data = {
                **self.config_entry.data,
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_MQTT_PASS: user_input[CONF_MQTT_PASS].strip(),
            }
            updated_options = {
                CONF_REQUEST_TIMEOUT: int(user_input[CONF_REQUEST_TIMEOUT]),
                CONF_POLLING_INTERVAL: int(user_input[CONF_POLLING_INTERVAL]),
            }

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

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": self.config_entry.title},
        )
