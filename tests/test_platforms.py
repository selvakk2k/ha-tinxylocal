"""Unit tests verifying platform entity availability and behavior."""

from unittest.mock import MagicMock
import pytest
from custom_components.tinxylocal.fan import TinxyFan
from custom_components.tinxylocal.lock import TinxyLock
from custom_components.tinxylocal.sensor import TinxyRssiSensor
from custom_components.tinxylocal.switch import TinxySwitch


@pytest.fixture
def mock_node():
    return {
        "device_id": "test_node_1",
        "name": "Living Room Fan & Light",
        "model": "Tinxy Fan & Light",
        "devices": [
            {"name": "Fan", "type": "Fan"},
            {"name": "Light", "type": "Switch"},
            {"name": "Door", "type": "Lock"},
        ],
    }


def test_platform_availability_parity(mock_node):
    """Verify that all platform entities return available=False when node_id is missing from coordinator data."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {}
    mock_coordinator.device_metadata = {}
    mock_hub = MagicMock()

    node_id = mock_node["device_id"]
    node_name = mock_node["name"]

    fan = TinxyFan(mock_coordinator, mock_hub, node_id, "Fan", 0, "pass123")
    switch = TinxySwitch(mock_coordinator, mock_hub, node_id, "Light", "Switch", 1, "pass123")
    lock = TinxyLock(mock_coordinator, mock_hub, node_id, "Door", "pass123")
    sensor = TinxyRssiSensor(mock_coordinator, node_id, node_name)

    # 1. When coordinator.data is empty
    assert fan.available is False
    assert switch.available is False
    assert lock.available is False
    assert sensor.available is False

    # 2. When coordinator.data has another node, but test_node_1 is offline
    mock_coordinator.data = {
        "other_node": {"device_1": {"state": True}}
    }
    assert fan.available is False
    assert switch.available is False
    assert lock.available is False
    assert sensor.available is False

    # 3. When test_node_1 is online
    mock_coordinator.data = {
        "test_node_1": {
            "device_1": {"state": True, "brightness": 66},
            "device_2": {"state": False},
            "device_3": {"state": False},
        }
    }
    assert fan.available is True
    assert switch.available is True
    assert lock.available is True
    assert sensor.available is True
