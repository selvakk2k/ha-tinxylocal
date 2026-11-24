"""Unit tests for Tinxy Local diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.tinxylocal.const import (
    CONF_DEVICE_ID,
    CONF_MQTT_PASS,
    DOMAIN,
)
from custom_components.tinxylocal.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.const import CONF_API_KEY, CONF_HOST


@pytest.mark.asyncio
async def test_diagnostics_redacts_sensitive_keys():
    """Test diagnostics redacts host, api_key, mqtt_pass, device_id, and node IP."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "tinxy_entry_42"
    entry.version = 1
    entry.domain = DOMAIN
    entry.title = "Living Room Switch"
    entry.pref_disable_new_entities = False
    entry.pref_disable_polling = False
    entry.data = {
        CONF_HOST: "192.168.1.120",
        CONF_API_KEY: "super_secret_tinxy_token_abc",
        CONF_MQTT_PASS: "mqtt_pass_secret",
        CONF_DEVICE_ID: "tinxy_device_999",
        "name": "Living Room Switch",
    }
    entry.options = {
        "polling_interval": 15,
        "request_timeout": 5,
    }

    mock_hub = MagicMock()
    mock_hub.timeout = 5

    mock_node = {
        "device_id": "tinxy_device_999",
        "ip_address": "192.168.1.120",
        "name": "Ceiling Fan",
        "relay_count": 4,
    }

    mock_coordinator = MagicMock()
    mock_coordinator.last_update_success = True
    mock_coordinator.nodes = [mock_node]
    mock_coordinator.data = {
        "tinxy_device_999": {"state": 1, "power": 65},
    }

    entry_data = {
        "coordinator": mock_coordinator,
        "hubs": [mock_hub],
        "nodes": [mock_node],
    }

    entry.runtime_data = entry_data
    hass.data = {DOMAIN: {entry.entry_id: entry_data}}

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Check entry data redactions
    entry_data_dict = diag["entry"]["data"]
    assert entry_data_dict[CONF_HOST] == "**REDACTED**"
    assert entry_data_dict[CONF_API_KEY] == "**REDACTED**"
    assert entry_data_dict[CONF_MQTT_PASS] == "**REDACTED**"
    assert entry_data_dict[CONF_DEVICE_ID] == "**REDACTED**"
    assert entry_data_dict["name"] == "Living Room Switch"

    # Check coordinator info
    coord = diag["coordinator"]
    assert coord["last_update_success"] is True
    assert coord["nodes_count"] == 1
    assert coord["data"]["tinxy_device_999"]["state"] == 1

    # Check hubs info
    assert len(diag["hubs"]) == 1
    assert diag["hubs"][0]["host"] == "**REDACTED**"
    assert diag["hubs"][0]["timeout"] == 5

    # Check nodes info
    node_out = diag["nodes"][0]
    assert node_out["ip_address"] == "**REDACTED**"
    assert node_out["device_id"] == "**REDACTED**"
    assert node_out["name"] == "Ceiling Fan"
    assert node_out["relay_count"] == 4


@pytest.mark.asyncio
async def test_diagnostics_without_coordinator():
    """Test diagnostics works gracefully before entry is loaded."""
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "tinxy_unloaded"
    entry.version = 1
    entry.domain = DOMAIN
    entry.title = "Unloaded Tinxy"
    entry.pref_disable_new_entities = False
    entry.pref_disable_polling = False
    entry.data = {
        CONF_HOST: "192.168.1.121",
        CONF_API_KEY: "secret",
    }
    entry.options = {}
    entry.runtime_data = None

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["title"] == "Unloaded Tinxy"
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_API_KEY] == "**REDACTED**"
    assert diag["coordinator"] == {}
    assert diag["hubs"] == []
    assert diag["nodes"] == []

