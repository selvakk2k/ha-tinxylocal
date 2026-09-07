"""Fan platform for Tinxy Local integration."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    int_states_in_range,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import CONF_MQTT_PASS, DOMAIN
from .coordinator import TinxyUpdateCoordinator
from .hub import QueuedCommand, TinxyLocalHub

_LOGGER = logging.getLogger(__name__)
SPEED_RANGE = (1, 3)  # Speeds 1, 2, 3 mapped to 33%, 66%, 100%


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tinxy fans from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinxyUpdateCoordinator = entry_data["coordinator"]
    hub: TinxyLocalHub = entry_data["hubs"][0]
    mqtt_pass: str = entry.data.get(CONF_MQTT_PASS, "")

    node = coordinator.nodes[0]
    node_id = node["device_id"]

    fans: list[TinxyFan] = []
    for i, sub_dev in enumerate(node.get("devices", [])):
        dev_name = sub_dev.get("name") or f"Fan {i + 1}"
        dev_type = sub_dev.get("type") or "Switch"

        if str(dev_type).lower() == "fan" or "fan" in str(dev_name).lower():
            fans.append(TinxyFan(coordinator, hub, node_id, dev_name, i, mqtt_pass))

    async_add_entities(fans)


class TinxyFan(CoordinatorEntity[TinxyUpdateCoordinator], FanEntity):
    """Representation of a Tinxy fan with 3-speed control."""

    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        hub: TinxyLocalHub,
        node_id: str,
        name: str,
        relay_number: int,
        mqtt_pass: str,
    ) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator)
        self.hub = hub
        self.node_id = node_id
        self._name = name
        self.relay_number = relay_number
        self.mqtt_pass = mqtt_pass

        self._attr_unique_id = f"{node_id}_fan_{relay_number}"
        self._attr_name = name
        self._dev_key = f"{name}_{relay_number}"
        self._last_known_percentage = 66
        self._optimistic_is_on: bool | None = None
        self._optimistic_percentage: int | None = None

    @property
    def speed_count(self) -> int:
        """Return the number of speeds."""
        return int_states_in_range(SPEED_RANGE)

    @property
    def is_on(self) -> bool | None:
        """Return true if fan is on."""
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on

        if not self.coordinator.data:
            return None
        node_data = self.coordinator.data.get(self.node_id, {})
        relay_info = node_data.get(self._dev_key, {})
        return relay_info.get("state")

    @property
    def percentage(self) -> int | None:
        """Return current speed percentage."""
        if self._optimistic_percentage is not None:
            return self._optimistic_percentage

        if not self.coordinator.data:
            return None
        node_data = self.coordinator.data.get(self.node_id, {})
        relay_info = node_data.get(self._dev_key, {})
        brightness = relay_info.get("brightness", 0)

        # Convert brightness (0-100) to 3-step speed percentage
        if brightness <= 0:
            return 0
        speed_step = min(3, max(1, math.ceil(brightness / 33.3)))
        pct = ranged_value_to_percentage(SPEED_RANGE, speed_step)
        self._last_known_percentage = pct
        return pct

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self.node_id)},
            name=self.coordinator.nodes[0]["name"],
            manufacturer="Tinxy",
            model=metadata.get("model", "Tinxy Smart Fan"),
            sw_version=metadata.get("firmware"),
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        target_pct = percentage or self._last_known_percentage or 66
        await self.async_set_percentage(target_pct)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        self._optimistic_is_on = False
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
        finally:
            self._optimistic_is_on = None
            await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return

        self._optimistic_is_on = True
        self._optimistic_percentage = percentage
        self.async_write_ha_state()

        step = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        brightness_val = {1: 33, 2: 66, 3: 100}.get(step, 66)

        command = QueuedCommand(
            command_type="brightness",
            relay_number=self.relay_number,
            action=1,
            brightness=brightness_val,
        )
        try:
            await self.hub.queue_command(
                command, self.mqtt_pass, self.coordinator.web_session
            )
        finally:
            self._optimistic_is_on = None
            self._optimistic_percentage = None
            await self.coordinator.async_request_refresh()
