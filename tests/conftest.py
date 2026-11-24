"""Pytest configuration and Home Assistant stubs for Tinxy Local."""

import sys
from pathlib import Path

# Add project root and custom_components to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set up Home Assistant mock stubs for standalone testing
from tests.ha_stub import setup_ha_stubs  # noqa: E402

setup_ha_stubs()

import homeassistant.const  # noqa: E402

homeassistant.const.CONF_API_KEY = "api_key"
homeassistant.const.CONF_HOST = "host"
homeassistant.const.CONF_IP_ADDRESS = "ip_address"
homeassistant.const.CONF_PORT = "port"
homeassistant.const.CONF_USERNAME = "username"
homeassistant.const.CONF_PASSWORD = "password"
homeassistant.const.CONF_DEVICE = "device"
homeassistant.const.CONF_DEVICES = "devices"

