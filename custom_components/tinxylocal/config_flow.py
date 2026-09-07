"""Config flow for Tinxy Local integration with ephemeral cloud setup and offline manual mode."""

from __future__ import annotations

import logging
from typing import Any

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
    CONF_SETUP_MODE,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    SETUP_MODE_CLOUD,
    SETUP_MODE_MANUAL,
    TINXY_BACKEND,
)
from .hub import TinxyLocalHub
from .tinxycloud import TinxyAuthenticationException, TinxyCloud, TinxyHostConfiguration

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Tinxy Local."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.discovered_ip: str | None = None
        self.discovered_chip_id: str | None = None
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
        if user_input is not None:
            if user_input[CONF_SETUP_MODE] == SETUP_MODE_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_manual()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SETUP_MODE, default=SETUP_MODE_CLOUD
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=SETUP_MODE_CLOUD,
                                label="Cloud-Assisted (Fetch local keys via API key, then discard key)",
                            ),
                            selector.SelectOptionDict(
                                value=SETUP_MODE_MANUAL,
                                label="Manual Local (100% Offline with IP and Device Password)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a: Cloud-Assisted setup to query device list and keys."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_token = user_input[CONF_API_KEY]
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
                    # Crucial: API key is kept in memory during flow only and discarded upon save
                    return await self.async_step_select_cloud_device()
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
        """Select a cloud device and assign its local IP."""
        errors: dict[str, str] = {}

        device_options = {
            d["_id"]: f"{d.get('name', 'Device')} ({d.get('typeId', {}).get('name', 'Switch')})"
            for d in self.cloud_devices
            if "_id" in d
        }

        if user_input is not None:
            target_id = user_input[CONF_DEVICE_ID]
            host_ip = user_input[CONF_HOST].strip()

            selected_device = next(
                (d for d in self.cloud_devices if d["_id"] == target_id), None
            )

            if selected_device:
                # Validate local connectivity to /info
                session = async_get_clientsession(self.hass)
                hub = TinxyLocalHub(self.hass, host_ip)
                status = await hub.validate_ip(session)

                if status != "ok":
                    errors["base"] = "cannot_connect_local"
                else:
                    await self.async_set_unique_id(selected_device["_id"])
                    self._abort_if_unique_id_configured()

                    # Save config entry WITHOUT the cloud API token (ephemeral key discarded immediately)
                    return self.async_create_entry(
                        title=selected_device.get("name", "Tinxy Switch"),
                        data={
                            CONF_HOST: host_ip,
                            CONF_DEVICE_ID: selected_device["_id"],
                            CONF_MQTT_PASS: selected_device.get("mqttPassword", ""),
                            CONF_DEVICE: selected_device,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
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

        if user_input is not None:
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

            # Update host IP if modified
            if user_input.get(CONF_HOST):
                updated_data[CONF_HOST] = user_input[CONF_HOST]

            # Update device key if modified
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
