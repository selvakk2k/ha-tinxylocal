"""Diagnostics support for Tinxy Local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ID, CONF_MQTT_PASS, DOMAIN

TO_REDACT = {
    CONF_API_KEY,
    CONF_HOST,
    CONF_MQTT_PASS,
    CONF_DEVICE_ID,
    "api_key",
    "host",
    "ip_address",
    "mqtt_pass",
    "password",
    "device_id",
    "unique_id",
    "mac",
    "mac_address",
    "auth_token",
    "refresh_token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Tinxy Local config entry."""
    entry_data = (
        getattr(entry, "runtime_data", None)
        or hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    )

    coordinator = entry_data.get("coordinator") if isinstance(entry_data, dict) else None
    hubs = entry_data.get("hubs", []) if isinstance(entry_data, dict) else []
    nodes = entry_data.get("nodes", []) if isinstance(entry_data, dict) else []

    coordinator_info: dict[str, Any] = {}
    if coordinator:
        coordinator_info = {
            "last_update_success": coordinator.last_update_success,
            "data": (
                async_redact_data(dict(coordinator.data), TO_REDACT)
                if coordinator.data and isinstance(coordinator.data, dict)
                else {}
            ),
            "nodes_count": len(getattr(coordinator, "nodes", [])),
        }

    hubs_info: list[dict[str, Any]] = []
    for hub in hubs:
        hubs_info.append(
            {
                "host": "**REDACTED**",
                "timeout": getattr(hub, "timeout", None),
            }
        )

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "pref_disable_new_entities": entry.pref_disable_new_entities,
            "pref_disable_polling": entry.pref_disable_polling,
        },
        "coordinator": coordinator_info,
        "hubs": hubs_info,
        "nodes": [async_redact_data(dict(n), TO_REDACT) for n in nodes if isinstance(n, dict)],
    }

