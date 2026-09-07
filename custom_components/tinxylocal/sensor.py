"""Diagnostic sensor platform for Tinxy Local integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TinxyUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tinxy diagnostic sensors."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinxyUpdateCoordinator = entry_data["coordinator"]

    sensors: list[TinxyDiagnosticSensorBase] = []
    is_multi_node = len(coordinator.nodes) > 1

    for node in coordinator.nodes:
        node_id = node["device_id"]
        node_name = node.get("name") or "Tinxy Device"
        sensors.extend(
            [
                TinxyRssiSensor(coordinator, node_id, node_name, is_multi_node),
                TinxyIpSensor(coordinator, node_id, node_name, is_multi_node),
                TinxySsidSensor(coordinator, node_id, node_name, is_multi_node),
            ]
        )

    async_add_entities(sensors)


class TinxyDiagnosticSensorBase(CoordinatorEntity[TinxyUpdateCoordinator], SensorEntity):
    """Base class for Tinxy diagnostic sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        node_id: str,
        node_name: str,
        is_multi_node: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self.node_id = node_id
        self.node_name = node_name
        self.is_multi_node = is_multi_node

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self.node_id)},
            name=self.node_name,
            manufacturer="Tinxy",
            model=metadata.get("model", "Tinxy Smart Device"),
            sw_version=metadata.get("firmware"),
        )


class TinxyRssiSensor(TinxyDiagnosticSensorBase):
    """Wi-Fi RSSI Signal Strength sensor in dBm."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        node_id: str,
        node_name: str,
        is_multi_node: bool = False,
    ) -> None:
        super().__init__(coordinator, node_id, node_name, is_multi_node)
        self._attr_unique_id = f"{node_id}_rssi"
        self._attr_name = f"{node_name} Wi-Fi Signal" if is_multi_node else "Wi-Fi Signal"

    @property
    def native_value(self) -> int | None:
        """Return current RSSI."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return metadata.get("rssi")


class TinxyIpSensor(TinxyDiagnosticSensorBase):
    """IP Address sensor."""

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        node_id: str,
        node_name: str,
        is_multi_node: bool = False,
    ) -> None:
        super().__init__(coordinator, node_id, node_name, is_multi_node)
        self._attr_unique_id = f"{node_id}_ip"
        self._attr_name = f"{node_name} IP Address" if is_multi_node else "IP Address"

    @property
    def native_value(self) -> str | None:
        """Return current local IP."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return metadata.get("ip")


class TinxySsidSensor(TinxyDiagnosticSensorBase):
    """Connected Wi-Fi SSID sensor."""

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        node_id: str,
        node_name: str,
        is_multi_node: bool = False,
    ) -> None:
        super().__init__(coordinator, node_id, node_name, is_multi_node)
        self._attr_unique_id = f"{node_id}_ssid"
        self._attr_name = f"{node_name} Wi-Fi SSID" if is_multi_node else "Wi-Fi SSID"

    @property
    def native_value(self) -> str | None:
        """Return current SSID."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        return metadata.get("ssid")
