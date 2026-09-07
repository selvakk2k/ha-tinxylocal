"""Unit tests for coordinator behavior and deprecation fixes."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from custom_components.tinxylocal.coordinator import TinxyUpdateCoordinator


@pytest.mark.asyncio
async def test_sw_version_int_coercion():
    """Verify that integer firmware values are coerced to strings."""
    mock_hass = MagicMock()
    mock_session = MagicMock()
    mock_entry = MagicMock()

    nodes = [
        {
            "ip_address": "192.168.0.163",
            "device_id": "test_node_1",
            "name": "Living Room",
            "model": "Tinxy 2-Node Switch",
            "devices": [{"name": "Relay 1", "type": "Switch"}],
        }
    ]

    coordinator = TinxyUpdateCoordinator(
        mock_hass,
        nodes,
        mock_session,
        polling_interval=15,
        request_timeout=8,
        config_entry=mock_entry,
    )

    # Mock hub returning integer firmware (e.g., 2)
    coordinator.hubs[0].fetch_device_data = AsyncMock(
        return_value={
            "rssi": -65,
            "firmware": 2,  # Integer from hardware
            "state": "10",
            "model": "Tinxy 2-Node Switch",
        }
    )

    data = await coordinator._async_update_data()
    assert "test_node_1" in data

    # Verify sw_version is coerced to str '2', NOT int 2
    metadata = coordinator.device_metadata["test_node_1"]
    assert metadata["firmware"] == "2"
    assert isinstance(metadata["firmware"], str)


def test_request_timeout_propagation():
    """Verify request_timeout overrides default 5s in all child hubs."""
    mock_hass = MagicMock()
    mock_session = MagicMock()
    mock_entry = MagicMock()

    nodes = [{"ip_address": "192.168.0.10", "device_id": "node_10"}]
    coordinator = TinxyUpdateCoordinator(
        mock_hass,
        nodes,
        mock_session,
        polling_interval=20,
        request_timeout=12,
        config_entry=mock_entry,
    )

    assert coordinator.request_timeout == 12
    assert coordinator.hubs[0].request_timeout == 12


@pytest.mark.asyncio
async def test_null_device_types_handling():
    """Verify that null/None elements in deviceTypes do not crash decoding."""
    from custom_components.tinxylocal.hub import TinxyLocalHub

    node = {
        "device_id": "test_node_null",
        "name": "Living Room",
        "devices": [
            {"name": "LED Bulb", "type": "LED Bulb"},
            {"name": "Relay 2", "type": "Switch"},
        ],
    }

    raw_data = {
        "state": "00",
        "bright": "",
        "status": 1,
        "rssi": -65,
    }

    decoded = TinxyLocalHub._decode_device_data(raw_data, node)
    assert "LED Bulb_0" in decoded
    assert "Relay 2_1" in decoded
    assert decoded["LED Bulb_0"]["state"] is False
    assert decoded["Relay 2_1"]["state"] is False


@pytest.mark.asyncio
async def test_migration_v1_to_v2_strips_api_key():
    """Verify that migration from v1 to v2 strips legacy api_key and upgrades version to 2."""
    from custom_components.tinxylocal import async_migrate_entry
    from unittest.mock import MagicMock

    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.version = 1
    mock_entry.title = "Living Room"
    mock_entry.data = {
        "api_key": "legacy_master_account_token",
        "host": "192.168.0.163",
        "mqtt_pass": "secret123",
        "device_id": "tinxy_dev_1",
    }

    result = await async_migrate_entry(mock_hass, mock_entry)
    assert result is True

    # Verify async_update_entry was called with version=2 and data without api_key
    mock_hass.config_entries.async_update_entry.assert_called_once()
    call_args = mock_hass.config_entries.async_update_entry.call_args
    updated_data = call_args.kwargs["data"]
    updated_version = call_args.kwargs["version"]

    assert "api_key" not in updated_data
    assert updated_data["host"] == "192.168.0.163"
    assert updated_version == 2


@pytest.mark.asyncio
async def test_switch_unique_id_and_hardware_feature_check():
    """Verify switches use 1-indexed unique IDs and pure-switch hardware does not spawn fans."""
    from custom_components.tinxylocal.switch import async_setup_entry as switch_setup_entry
    from custom_components.tinxylocal.fan import async_setup_entry as fan_setup_entry
    from custom_components.tinxylocal.const import DOMAIN

    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.data = {
        "device": {
            "typeId": {
                "name": "WIFI_2SWITCH_V3",
                "features": ["SWITCH|RECIEVER", "SWITCH"],  # Pure switch, no FAN feature
            }
        },
        "mqtt_pass": "pass123",
    }

    mock_coordinator = MagicMock()
    mock_coordinator.nodes = [
        {
            "device_id": "test_node_1",
            "name": "Living Room",
            "features": ["SWITCH|RECIEVER", "SWITCH"],
            "devices": [
                {"name": "Foyer Light", "type": "Switch"},
                {"name": "Relay 2", "type": "Fan"},  # User labeled Fan, but hardware is Switch
            ],
        }
    ]

    mock_hub = MagicMock()
    mock_hass.data = {
        DOMAIN: {
            "test_entry": {
                "coordinator": mock_coordinator,
                "hubs": [mock_hub],
            }
        }
    }

    added_switches = []
    added_fans = []

    await switch_setup_entry(mock_hass, mock_entry, lambda ents: added_switches.extend(ents))
    await fan_setup_entry(mock_hass, mock_entry, lambda ents: added_fans.extend(ents))

    # Since hardware features don't have FAN, both relays should be switches
    assert len(added_switches) == 2
    assert len(added_fans) == 0

    # Verify 1-indexed unique IDs matching upstream arevindh/tinxylocal
    assert added_switches[0].unique_id == "test_node_1_1"
    assert added_switches[1].unique_id == "test_node_1_2"


@pytest.mark.asyncio
async def test_sensor_setup_multi_node(hass):
    """Test diagnostic sensors setup registers entities for each node in coordinator."""
    from custom_components.tinxylocal.sensor import async_setup_entry as sensor_setup_entry
    from custom_components.tinxylocal.const import DOMAIN

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"

    mock_coordinator = MagicMock()
    mock_coordinator.nodes = [
        {"device_id": "node_1", "name": "Living Room"},
        {"device_id": "node_2", "name": "Bedroom"},
    ]
    mock_coordinator.device_metadata = {
        "node_1": {"rssi": -65, "ip": "192.168.0.101", "ssid": "HomeWiFi", "model": "2-Node", "firmware": "83"},
        "node_2": {"rssi": -72, "ip": "192.168.0.102", "ssid": "HomeWiFi", "model": "4-Node", "firmware": "84"},
    }

    hass.data = {
        DOMAIN: {
            "test_entry": {
                "coordinator": mock_coordinator,
            }
        }
    }

    added_sensors = []
    await sensor_setup_entry(hass, mock_entry, lambda ents: added_sensors.extend(ents))

    # 3 sensors per node (RSSI, IP, SSID) * 2 nodes = 6 sensors
    assert len(added_sensors) == 6
    unique_ids = [s.unique_id for s in added_sensors]
    assert "node_1_rssi" in unique_ids
    assert "node_1_ip" in unique_ids
    assert "node_1_ssid" in unique_ids
    assert "node_2_rssi" in unique_ids
    assert "node_2_ip" in unique_ids
    assert "node_2_ssid" in unique_ids

    # For multi-node, names include node_name
    rssi_1 = next(s for s in added_sensors if s.unique_id == "node_1_rssi")
    assert rssi_1.name == "Living Room Wi-Fi Signal"
    assert rssi_1.native_value == -65
