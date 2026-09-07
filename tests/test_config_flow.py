"""Unit tests for Tinxy Local config flow."""

from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.const import CONF_HOST
from custom_components.tinxylocal.const import (
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_MQTT_PASS,
    CONF_RELAY_COUNT,
)
from custom_components.tinxylocal.config_flow import ConfigFlow as TinxyLocalConfigFlow


@pytest.mark.asyncio
async def test_manual_setup_switch(hass):
    """Test manual setup flow creates correct switch topology."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.150",
        CONF_MQTT_PASS: "secret123",
        "name": "Living Room Switch",
        "device_type": "switch",
        CONF_RELAY_COUNT: 4,
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual(user_input)

    assert result["type"] == "create_entry"
    assert result["title"] == "Living Room Switch"
    data = result["data"]
    assert data[CONF_HOST] == "192.168.0.150"
    assert data[CONF_MQTT_PASS] == "secret123"
    assert data[CONF_DEVICE_ID] == "tinxy_192_168_0_150"

    dev = data[CONF_DEVICE]
    assert len(dev["devices"]) == 4
    assert dev["deviceTypes"] == ["Switch", "Switch", "Switch", "Switch"]
    assert dev["typeId"]["name"] == "Tinxy 4-Node Switch"


@pytest.mark.asyncio
async def test_manual_setup_fan(hass):
    """Test manual setup flow creates correct fan topology."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.151",
        CONF_MQTT_PASS: "secret456",
        "name": "Master Bedroom Fan",
        "device_type": "fan",
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual(user_input)

    assert result["type"] == "create_entry"
    assert result["title"] == "Master Bedroom Fan"
    dev = result["data"][CONF_DEVICE]
    assert dev["deviceTypes"] == ["Fan"]
    assert dev["typeId"]["name"] == "Tinxy Fan Controller"


@pytest.mark.asyncio
async def test_manual_setup_lock(hass):
    """Test manual setup flow creates correct lock topology."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.152",
        CONF_MQTT_PASS: "secret789",
        "name": "Front Gate Lock",
        "device_type": "lock",
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual(user_input)

    assert result["type"] == "create_entry"
    assert result["title"] == "Front Gate Lock"
    dev = result["data"][CONF_DEVICE]
    assert dev["deviceTypes"] == ["Lock"]
    assert dev["typeId"]["gtype"] == "action.devices.types.LOCK"
