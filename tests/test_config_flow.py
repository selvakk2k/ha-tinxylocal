"""Unit tests for Tinxy Local config flow."""

from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from custom_components.tinxylocal.const import (
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_MQTT_PASS,
    CONF_RELAY_COUNT,
)
from custom_components.tinxylocal.config_flow import ConfigFlow as TinxyLocalConfigFlow


@pytest.fixture(autouse=True)
def mock_discovery():
    """Mock network discovery to prevent real socket usage during tests."""
    with patch(
        "custom_components.tinxylocal.config_flow.async_discover_tinxy_devices",
        new_callable=AsyncMock,
    ) as mock_disc:
        mock_disc.return_value = {
            "6707357": {
                "ip": "192.168.0.163",
                "info": {"chip_id": "6707357", "type": "WIFI_2SWITCH_V3"},
            }
        }
        yield mock_disc


@pytest.mark.asyncio
async def test_user_step_shows_menu(hass):
    """Test the initial user step shows the setup choice menu."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "user"
    assert "cloud" in result["menu_options"]
    assert "manual" in result["menu_options"]


@pytest.mark.asyncio
async def test_manual_step_shows_device_menu(hass):
    """Test the manual step shows the device type choice menu."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    result = await flow.async_step_manual()
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "manual"
    assert "manual_switch" in result["menu_options"]
    assert "manual_fan" in result["menu_options"]
    assert "manual_lock" in result["menu_options"]


@pytest.mark.asyncio
async def test_cloud_flow_discovery_and_entry_creation(hass):
    """Test cloud flow discovers IP and creates entry successfully."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    mock_devices = [
        {
            "_id": "tinxy_dev_1",
            "name": "Living Room Switch",
            "mqttPassword": "test_password",
            "uuidRef": {"uuid": "6707357"},
            "devices": ["Light 1", "Light 2"],
            "deviceTypes": ["Switch", "Switch"],
            "typeId": {"name": "Tinxy 2-Node Switch"},
        }
    ]

    with patch(
        "custom_components.tinxylocal.config_flow.TinxyCloud.get_device_list",
        new_callable=AsyncMock,
    ) as mock_get_list:
        mock_get_list.return_value = mock_devices

        # 1. User enters API token
        result = await flow.async_step_cloud({CONF_API_KEY: "valid_token_123"})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_cloud_device"
        assert flow.discovered_ip == "192.168.0.163"

        # 2. User confirms device and host IP
        with patch(
            "custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip",
            new_callable=AsyncMock,
        ) as mock_val:
            mock_val.return_value = "ok"
            create_result = await flow.async_step_select_cloud_device(
                {CONF_DEVICE_ID: "tinxy_dev_1", CONF_HOST: "192.168.0.163"}
            )

        assert create_result["type"] == FlowResultType.CREATE_ENTRY
        assert create_result["title"] == "Living Room Switch"
        assert create_result["data"][CONF_HOST] == "192.168.0.163"
        assert create_result["data"][CONF_DEVICE_ID] == "tinxy_dev_1"
        assert create_result["data"][CONF_MQTT_PASS] == "test_password"


@pytest.mark.asyncio
async def test_manual_setup_switch(hass):
    """Test manual switch setup flow creates correct switch topology."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.150",
        CONF_MQTT_PASS: "secret123",
        "name": "Living Room Switch",
        CONF_RELAY_COUNT: 4,
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual_switch(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
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
    """Test manual fan setup flow creates correct fan topology without relay count."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.151",
        CONF_MQTT_PASS: "secret456",
        "name": "Master Bedroom Fan",
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual_fan(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Master Bedroom Fan"
    dev = result["data"][CONF_DEVICE]
    assert dev["deviceTypes"] == ["Fan"]
    assert dev["typeId"]["name"] == "Tinxy Fan Controller"


@pytest.mark.asyncio
async def test_manual_setup_lock(hass):
    """Test manual lock setup flow creates correct lock topology without relay count."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    user_input = {
        CONF_HOST: "192.168.0.152",
        CONF_MQTT_PASS: "secret789",
        "name": "Front Gate Lock",
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        result = await flow.async_step_manual_lock(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front Gate Lock"
    dev = result["data"][CONF_DEVICE]
    assert dev["deviceTypes"] == ["Lock"]
    assert dev["typeId"]["gtype"] == "action.devices.types.LOCK"


@pytest.mark.asyncio
async def test_options_flow_description_placeholders(hass):
    """Test options flow provides name placeholder to avoid translation missing_value error."""
    from unittest.mock import MagicMock
    from custom_components.tinxylocal.config_flow import TinxyLocalOptionsFlowHandler

    mock_entry = MagicMock()
    mock_entry.title = "Living Room"
    mock_entry.data = {CONF_HOST: "192.168.0.163", CONF_MQTT_PASS: "secret"}
    mock_entry.options = {}

    handler = TinxyLocalOptionsFlowHandler(mock_entry)
    handler.hass = hass

    result = await handler.async_step_init()
    assert result["type"] == FlowResultType.FORM
    assert result["description_placeholders"] == {"name": "Living Room"}
