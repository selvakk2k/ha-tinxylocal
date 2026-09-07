"""The Tinxy Local integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
            "features": device_data.get("typeId", {}).get("features", []),
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

    # Reconcile entity registry before adding entities
    await _async_reconcile_entity_registry(hass, entry, device_id, device_data.get("typeId", {}).get("features", []))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Clean up empty orphaned devices after entities are attached to active device
    _async_clean_orphaned_devices(hass, entry, device_id)

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


async def _async_reconcile_entity_registry(
    hass: HomeAssistant, entry: ConfigEntry, current_node_id: str, features: list[str]
) -> None:
    """Reconcile legacy unique IDs, deduplicate _2 entities, and clean orphans."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    if not entity_entries:
        return

    # 1. Deduplicate _2 entities created by unique_id collisions
    for ent in list(entity_entries):
        if ent.entity_id.endswith("_2"):
            base_entity_id = ent.entity_id[:-2]
            base_ent = ent_reg.async_get(base_entity_id)
            if base_ent and base_ent.config_entry_id == entry.entry_id:
                _LOGGER.info(
                    "Deduplicating entity '%s' in favor of original '%s'",
                    ent.entity_id,
                    base_entity_id,
                )
                ent_reg.async_remove(ent.entity_id)
                entity_entries.remove(ent)

    # 2. Migrate legacy or intermediate unique IDs to {current_node_id}_{relay_num}
    for ent in list(entity_entries):
        uid = ent.unique_id
        new_uid: str | None = None

        if "_relay_" in uid:
            parts = uid.split("_relay_")
            try:
                relay_idx = int(parts[1])
                new_uid = f"{current_node_id}_{relay_idx + 1}"
            except ValueError:
                pass
        elif not uid.startswith(current_node_id) and ("_" in uid):
            parts = uid.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                new_uid = f"{current_node_id}_{parts[1]}"

        if new_uid and new_uid != uid:
            existing = ent_reg.async_get_entity_id(ent.domain, DOMAIN, new_uid)
            if existing and existing != ent.entity_id:
                ent_reg.async_remove(existing)
            _LOGGER.info(
                "Migrating entity '%s' unique_id from '%s' to '%s'",
                ent.entity_id,
                uid,
                new_uid,
            )
            ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_uid)

    # 3. Remove mistakenly registered fan entities on devices without FAN features
    has_any_fan = any("FAN" in str(f).upper() for f in features)
    if not has_any_fan:
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if ent.domain == "fan":
                _LOGGER.info(
                    "Removing fan entity '%s' on pure-switch device",
                    ent.entity_id,
                )
                ent_reg.async_remove(ent.entity_id)

    # 4. Clean up any empty orphaned devices from previous pairings
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        device_entries = er.async_entries_for_device(ent_reg, device.id)
        if not device_entries and (DOMAIN, current_node_id) not in device.identifiers:
            _LOGGER.info("Removing orphaned device '%s' (ID: %s)", device.name, device.id)
            dev_reg.async_remove_device(device.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    _LOGGER.info("Removing device %s from config entry %s", device_entry.id, config_entry.entry_id)
    return True


def _async_clean_orphaned_devices(hass: HomeAssistant, entry: ConfigEntry, current_node_id: str) -> None:
    """Remove empty orphaned devices left over from previous pairings."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        device_entries = er.async_entries_for_device(ent_reg, device.id)
        if not device_entries and (DOMAIN, current_node_id) not in device.identifiers:
            _LOGGER.info("Removing orphaned device '%s' (ID: %s)", device.name, device.id)
            dev_reg.async_remove_device(device.id)
