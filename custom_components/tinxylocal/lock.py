"""Lock platform for Tinxy Local integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MQTT_PASS, DOMAIN
from .coordinator import TinxyUpdateCoordinator
from .hub import QueuedCommand, TinxyLocalHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tinxy locks from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinxyUpdateCoordinator = entry_data["coordinator"]
    hub: TinxyLocalHub = entry_data["hubs"][0]
    mqtt_pass: str = entry.data.get(CONF_MQTT_PASS, "")

    device_data = entry.data.get("device", {})
    if device_data.get("typeId", {}).get("gtype") != "action.devices.types.LOCK":
        return

    node = coordinator.nodes[0]
    async_add_entities([TinxyLock(coordinator, hub, node["device_id"], node["name"], mqtt_pass)])


class TinxyLock(CoordinatorEntity[TinxyUpdateCoordinator], LockEntity):
    """Representation of a Tinxy pulse-relay door lock."""

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        hub: TinxyLocalHub,
        node_id: str,
        name: str,
        mqtt_pass: str,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(coordinator)
        self.hub = hub
        self.node_id = node_id
        self._name = name
        self.mqtt_pass = mqtt_pass
        self._attr_unique_id = f"{node_id}_lock"
        self._attr_name = name
        self._attr_is_locked = True

    @property
    def is_locked(self) -> bool:
        """Return true if locked."""
        return self._attr_is_locked

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self.node_id)},
            name=self._name,
            manufacturer="Tinxy",
            model=metadata.get("model", "Tinxy Smart Lock"),
            sw_version=metadata.get("firmware"),
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Pulse the relay to unlock the door."""
        self._attr_is_locked = False
        self.async_write_ha_state()

        command = QueuedCommand(command_type="toggle", relay_number=0, action=1)
        try:
            await self.hub.queue_command(
                command, self.mqtt_pass, self.coordinator.web_session
            )
        finally:
            self._attr_is_locked = True
            self.async_write_ha_state()
            self.coordinator.async_request_refresh()

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door (pulse locks lock automatically)."""
        self._attr_is_locked = True
        self.async_write_ha_state()
