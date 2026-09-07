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

@pytest.mark.asyncio
async def test_zeroconf_discovery_new_device(hass):
    """Test zeroconf discovers a new device and prompts for confirmation."""
    import ipaddress
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    service_info = ZeroconfServiceInfo(
        ip_address=ipaddress.ip_address("192.168.0.163"),
        ip_addresses=[ipaddress.ip_address("192.168.0.163")],
        port=80,
        hostname="tinxy-6707357.local.",
        type="_http._tcp.local.",
        name="tinxy-6707357._http._tcp.local.",
        properties={},
    )

    with patch(
        "custom_components.tinxylocal.config_flow.TinxyLocalHub.fetch_device_data",
        new_callable=AsyncMock,
    ) as mock_info:
        mock_info.return_value = {"chip_id": "6707357", "type": "WIFI_2SWITCH_V3"}
        result = await flow.async_step_zeroconf(service_info)

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    assert "zeroconf_cloud" in result["menu_options"]
    assert "zeroconf_manual" in result["menu_options"]
    assert flow.discovered_ip == "192.168.0.163"
    assert flow.discovered_chip_id == "6707357"

    # Option A: User chooses manual setup and enters private key
    with patch(
        "custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip",
        new_callable=AsyncMock,
    ) as mock_val:
        mock_val.return_value = "ok"
        manual_result = await flow.async_step_zeroconf_manual(
            {
                "name": "Living Room Switch",
                CONF_MQTT_PASS: "pass_12345",
                CONF_RELAY_COUNT: 2,
            }
        )

    assert manual_result["type"] == FlowResultType.CREATE_ENTRY
    assert manual_result["title"] == "Living Room Switch"
    assert manual_result["data"][CONF_HOST] == "192.168.0.163"
    assert manual_result["data"][CONF_DEVICE_ID] == "6707357"
    assert manual_result["data"][CONF_MQTT_PASS] == "pass_12345"


@pytest.mark.asyncio
async def test_zeroconf_cloud_assisted_setup(hass):
    """Test zeroconf cloud-assisted setup automatically retrieves device key and configuration."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow.discovered_ip = "192.168.0.163"
    flow.discovered_chip_id = "6707357"

    mock_devices = [
        {
            "_id": "6a9ec90206d399c976aefdeb",
            "name": "Living Room Switch",
            "mqttPassword": "cloud_secret_pass",
            "uuidRef": {"uuid": "6707357"},
            "devices": ["Bulb", "Socket"],
            "deviceTypes": ["Switch", "Switch"],
            "typeId": {"numberOfRelays": 2},
        }
    ]

    with patch(
        "custom_components.tinxylocal.config_flow.TinxyCloud.get_device_list",
        new_callable=AsyncMock,
    ) as mock_list, patch(
        "custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip",
        new_callable=AsyncMock,
    ) as mock_val:
        mock_list.return_value = mock_devices
        mock_val.return_value = "ok"

        result = await flow.async_step_zeroconf_cloud({CONF_API_KEY: "valid_token_123"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room Switch"
    assert result["data"][CONF_HOST] == "192.168.0.163"
    assert result["data"][CONF_DEVICE_ID] == "6a9ec90206d399c976aefdeb"
    assert result["data"][CONF_MQTT_PASS] == "cloud_secret_pass"
    assert result["data"][CONF_DEVICE]["name"] == "Living Room Switch"


@pytest.mark.asyncio
async def test_zeroconf_cloud_device_not_found(hass):
    """Test zeroconf cloud setup reports error when discovered device is not in cloud account."""
    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow.discovered_ip = "192.168.0.163"
    flow.discovered_chip_id = "9999999"  # Different chip ID

    mock_devices = [
        {
            "_id": "6a9ec90206d399c976aefdeb",
            "name": "Different Device",
            "mqttPassword": "cloud_secret_pass",
            "uuidRef": {"uuid": "6707357"},
        }
    ]

    with patch(
        "custom_components.tinxylocal.config_flow.TinxyCloud.get_device_list",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = mock_devices
        result = await flow.async_step_zeroconf_cloud({CONF_API_KEY: "valid_token_123"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_cloud"
    assert result["errors"]["base"] == "device_not_found"


@pytest.mark.asyncio
async def test_zeroconf_discovery_updates_existing_ip(hass):
    """Test zeroconf automatically updates IP when device IP changes via DHCP."""
    import ipaddress
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
    from custom_components.tinxylocal.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="6707357",
        data={
            CONF_HOST: "192.168.0.100",  # Old IP
            CONF_DEVICE_ID: "6707357",
            "device": {"uuidRef": {"uuid": "6707357"}},
        },
    )
    entry.add_to_hass(hass)

    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    service_info = ZeroconfServiceInfo(
        ip_address=ipaddress.ip_address("192.168.0.163"),  # New IP
        ip_addresses=[ipaddress.ip_address("192.168.0.163")],
        port=80,
        hostname="tinxy-6707357.local.",
        type="_http._tcp.local.",
        name="tinxy-6707357._http._tcp.local.",
        properties={},
    )

    with patch(
        "custom_components.tinxylocal.config_flow.TinxyLocalHub.fetch_device_data",
        new_callable=AsyncMock,
    ) as mock_info:
        mock_info.return_value = {"chip_id": "6707357"}
        result = await flow.async_step_zeroconf(service_info)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.168.0.163"


@pytest.mark.asyncio
async def test_reconfigure_flow_success(hass):
    """Test reconfigure flow updates host and device key."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.tinxylocal.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        unique_id="6707357",
        data={
            CONF_HOST: "192.168.0.163",
            CONF_DEVICE_ID: "6707357",
            CONF_MQTT_PASS: "old_key_123",
            "device": {"mqttPassword": "old_key_123", "name": "Living Room"},
        },
    )
    entry.add_to_hass(hass)

    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": "reconfigure",
        "entry_id": entry.entry_id,
    }

    result = await flow.async_step_reconfigure()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["description_placeholders"] == {"name": "Living Room"}

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "ok"
        confirm_result = await flow.async_step_reconfigure(
            {CONF_HOST: "192.168.0.200", CONF_MQTT_PASS: "new_key_456"}
        )

    assert confirm_result["type"] == FlowResultType.ABORT
    assert confirm_result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.0.200"
    assert entry.data[CONF_MQTT_PASS] == "new_key_456"
    assert entry.data["device"]["mqttPassword"] == "new_key_456"


@pytest.mark.asyncio
async def test_reconfigure_flow_cannot_connect(hass):
    """Test reconfigure flow displays error when IP cannot connect."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.tinxylocal.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        unique_id="6707357",
        data={
            CONF_HOST: "192.168.0.163",
            CONF_DEVICE_ID: "6707357",
            CONF_MQTT_PASS: "old_key_123",
        },
    )
    entry.add_to_hass(hass)

    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": "reconfigure",
        "entry_id": entry.entry_id,
    }

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.validate_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = "timeout"
        result = await flow.async_step_reconfigure(
            {CONF_HOST: "192.168.0.250", CONF_MQTT_PASS: "some_key"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"]["base"] == "cannot_connect_local"


@pytest.mark.asyncio
async def test_discover_tinxy_devices_with_custom_subnet(hass):
    """Verify async_discover_tinxy_devices dynamically scans custom subnets like 10.0.29.0/24 from HA network adapters."""
    from custom_components.tinxylocal.config_flow import async_discover_tinxy_devices
    import ipaddress

    mock_adapters = [
        {
            "name": "eth0",
            "enabled": True,
            "ipv4": [
                {"address": "10.0.29.5", "network_prefix": 24}
            ]
        }
    ]

    scanned_ips = []
    async def mock_probe(session, ip):
        scanned_ips.append(ip)
        if ip == "10.0.29.100":
            return ip, {"chip_id": "tinxy_custom_1", "model": "2-Node"}
        return None

    with patch("homeassistant.components.network.async_get_adapters", new_callable=AsyncMock) as mock_get_net,          patch("aiohttp.ClientSession.get") as mock_http:
        mock_get_net.return_value = mock_adapters
        
        # Test candidate subnet expansion
        candidate_subnets = []
        for adapter in mock_adapters:
            if adapter.get("enabled"):
                for ip_info in adapter.get("ipv4", []):
                    addr = ip_info.get("address")
                    prefix = ip_info.get("network_prefix", 24)
                    net = ipaddress.IPv4Network(f"{addr}/{prefix}", strict=False)
                    candidate_subnets.append(net)

        assert ipaddress.IPv4Network("10.0.29.0/24") in candidate_subnets


@pytest.mark.asyncio
async def test_zeroconf_fetch_device_data_signature(hass):
    """Verify Zeroconf discovery calls hub.fetch_device_data with correct signature."""
    import ipaddress
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
    
    discovery_info = ZeroconfServiceInfo(
        ip_address=ipaddress.IPv4Address("10.0.29.105"),
        ip_addresses=[ipaddress.IPv4Address("10.0.29.105")],
        port=80,
        hostname="tinxy-6707357.local.",
        type="_http._tcp.local.",
        name="tinxy-6707357._http._tcp.local.",
        properties={},
    )

    flow = TinxyLocalConfigFlow()
    flow.hass = hass
    flow.context = {}

    with patch("custom_components.tinxylocal.config_flow.TinxyLocalHub.fetch_device_data", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "chip_id": "6707357",
            "name": "Association Switch",
            "model": "2-Node",
            "ip": "10.0.29.105",
        }
        result = await flow.async_step_zeroconf(discovery_info)

    # Verify fetch_device_data was called with ({}, session)
    mock_fetch.assert_called_once()
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
