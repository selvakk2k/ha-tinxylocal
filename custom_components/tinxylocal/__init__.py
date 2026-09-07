"""The Tinxy Local integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICE,
    CONF_MQTT_PASS,
    CONF_POLLING_INTERVAL,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
)
from .coordinator import TinxyUpdateCoordinator
from .hub import TinxyLocalHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.FAN,
    Platform.LOCK,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tinxy Local from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    web_session = async_get_clientsession(hass)

    request_timeout = entry.options.get(
        CONF_REQUEST_TIMEOUT,
        entry.data.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
    )
    polling_interval = entry.options.get(
        CONF_POLLING_INTERVAL,
        entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
    )

    device_data = entry.data.get(CONF_DEVICE, {})
    device_id = entry.data.get("device_id", device_data.get("_id", "unknown"))
    device_name = device_data.get("name", entry.title)
    mqtt_pass = entry.data.get(CONF_MQTT_PASS, "")
    host_ip = entry.data.get(CONF_HOST, "")

    # Build sub-device relay mapping safely handling null or blank types
    relays = []
    if device_data.get("devices"):
        dev_names = device_data.get("devices") or []
        dev_types = device_data.get("deviceTypes") or []
        for i, raw_name in enumerate(dev_names):
            raw_type = dev_types[i] if i < len(dev_types) and dev_types[i] else "Switch"
            clean_type = str(raw_type) if raw_type else "Switch"
            clean_name = raw_name if raw_name and str(raw_name).lower() != "none" else f"Relay {i + 1}"
            relays.append({"name": clean_name, "type": clean_type})
    elif device_data.get("typeId", {}).get("gtype") == "action.devices.types.LOCK":
        relays.append({"name": device_name, "type": "Lock"})

    nodes = [
        {
            "ip_address": host_ip,
            "mqtt_password": mqtt_pass,
            "device_id": device_id,
            "name": device_name,
            "model": device_data.get("typeId", {}).get("name", "Tinxy Smart Device"),
            "unique_id": device_id,
            "devices": relays,
        }
    ]

    hubs = [TinxyLocalHub(hass, node["ip_address"], request_timeout) for node in nodes]
    coordinator = TinxyUpdateCoordinator(
        hass, nodes, web_session, polling_interval, request_timeout, config_entry=entry
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "hubs": hubs,
        "nodes": nodes,
    }

    # Initial data load
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates (polling/timeout changes)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    hubs = entry_data.get("hubs", [])
    for hub in hubs:
        await hub.shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry to current schema version."""
    _LOGGER.info(
        "Migrating Tinxy Local entry '%s' from version %s to version 2",
        config_entry.title,
        config_entry.version,
    )

    if config_entry.version == 1:
        # Strip legacy plaintext API key if present to enforce ephemeral local privacy
        new_data = {**config_entry.data}
        if "api_key" in new_data:
            new_data.pop("api_key")
            _LOGGER.info("Stripped legacy plaintext api_key from entry '%s' for local privacy", config_entry.title)

        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("Migration of Tinxy Local entry '%s' to version 2 successful", config_entry.title)

    return True
