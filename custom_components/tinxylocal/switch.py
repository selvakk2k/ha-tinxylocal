"""Switch platform for Tinxy Local integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Tinxy switches from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinxyUpdateCoordinator = entry_data["coordinator"]
    hub: TinxyLocalHub = entry_data["hubs"][0]
    mqtt_pass: str = entry.data.get(CONF_MQTT_PASS, "")

    device_data = entry.data.get("device", {})
    if device_data.get("typeId", {}).get("gtype") == "action.devices.types.LOCK":
        return

    node = coordinator.nodes[0]
    node_id = node["device_id"]

    switches: list[TinxySwitch] = []
    for i, sub_dev in enumerate(node.get("devices", [])):
        dev_name = sub_dev.get("name", f"Relay {i}")
        dev_type = sub_dev.get("type", "Switch")

        # Fans and locks have dedicated platforms
        if dev_type.lower() == "fan" or "fan" in dev_name.lower():
            continue

        switches.append(
            TinxySwitch(coordinator, hub, node_id, dev_name, dev_type, i, mqtt_pass)
        )

    async_add_entities(switches)


class TinxySwitch(CoordinatorEntity[TinxyUpdateCoordinator], SwitchEntity):
    """Representation of a Tinxy switch relay."""

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        hub: TinxyLocalHub,
        node_id: str,
        name: str,
        device_type: str,
        relay_number: int,
        mqtt_pass: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.hub = hub
        self.node_id = node_id
        self._name = name
        self._device_type = device_type
        self.relay_number = relay_number
        self.mqtt_pass = mqtt_pass

        self._attr_unique_id = f"{node_id}_relay_{relay_number}"
        self._attr_name = name
        self._dev_key = f"{name}_{relay_number}"

        # Optimistic local state
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        if self._optimistic_state is not None:
            return self._optimistic_state

        if not self.coordinator.data:
            return None

        node_data = self.coordinator.data.get(self.node_id, {})
        relay_info = node_data.get(self._dev_key, {})
        return relay_info.get("state")

    @property
    def available(self) -> bool:
        """Return true if device status is available."""
        if not self.coordinator.data:
            return False
        return self.node_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self.node_id)},
            name=self.coordinator.nodes[0]["name"],
            manufacturer="Tinxy",
            model=metadata.get("model", "Tinxy Smart Device"),
            sw_version=metadata.get("firmware"),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on optimistically."""
        self._optimistic_state = True
        self.async_write_ha_state()

        command = QueuedCommand(
            command_type="toggle",
            relay_number=self.relay_number,
            action=1,
        )
        try:
            await self.hub.queue_command(
                command, self.mqtt_pass, self.coordinator.web_session
            )
        except Exception as err:
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed turning on switch %s: %s", self._attr_name, err)
        finally:
            self._optimistic_state = None
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off optimistically."""
        self._optimistic_state = False
        self.async_write_ha_state()

        command = QueuedCommand(
            command_type="toggle",
            relay_number=self.relay_number,
            action=0,
        )
        try:
            await self.hub.queue_command(
                command, self.mqtt_pass, self.coordinator.web_session
            )
        except Exception as err:
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.error("Failed turning off switch %s: %s", self._attr_name, err)
        finally:
            self._optimistic_state = None
            await self.coordinator.async_request_refresh()
