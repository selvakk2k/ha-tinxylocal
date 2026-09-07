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
