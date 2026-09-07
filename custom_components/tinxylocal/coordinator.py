"""DataUpdateCoordinator for Tinxy Local devices."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_POLLING_INTERVAL, DEFAULT_REQUEST_TIMEOUT
from .hub import TinxyConnectionException, TinxyLocalException, TinxyLocalHub

_LOGGER = logging.getLogger(__name__)


class TinxyUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll data directly from Tinxy nodes over LAN."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        nodes: list[dict[str, Any]],
        web_session: Any,
        polling_interval: int = DEFAULT_POLLING_INTERVAL,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
        config_entry: ConfigEntry | None = None,
        hubs: list[TinxyLocalHub] | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Tinxy Nodes",
            update_interval=timedelta(seconds=polling_interval),
            config_entry=config_entry,
        )
        self.hass = hass
        self.nodes = nodes
        self.web_session = web_session
        self.request_timeout = request_timeout

        # Use shared hub instances if provided, or instantiate fallback hubs
        if hubs is not None:
            self.hubs = hubs
        else:
            self.hubs = [
                TinxyLocalHub(hass, node["ip_address"], request_timeout)
                for node in nodes
            ]
        self.device_metadata: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from each configured Tinxy node over LAN."""
        status_list: dict[str, Any] = {}

        for hub, node in zip(self.hubs, self.nodes, strict=False):
            node_id = node["device_id"]
            try:
                device_data = await hub.fetch_device_data(node, self.web_session)
                if device_data:
                    status_list[node_id] = device_data

                    # Coerce sw_version/firmware to string to prevent HA 2026 deprecation warnings
                    raw_fw = device_data.get("firmware") or device_data.get("version")
                    fw_str = str(raw_fw) if raw_fw is not None else "Unknown"

                    self.device_metadata[node_id] = {
                        "firmware": fw_str,
                        "model": device_data.get("model", node.get("model", "Tinxy Smart Device")),
                        "rssi": device_data.get("rssi"),
                        "ssid": device_data.get("ssid"),
                        "ip": device_data.get("ip", node.get("ip_address")),
                        "door": device_data.get("door"),
                    }
            except (TinxyConnectionException, TinxyLocalException) as err:
                _LOGGER.debug("Failed updating node %s: %s", node.get("name"), err)
                continue
            except Exception as err:
                _LOGGER.warning("Unexpected error updating node %s: %s", node.get("name"), err)
                continue

        # Device registry is managed once during entity creation via DeviceInfo;
        # no recurring _register_devices() churn in the polling loop.
        return status_list
