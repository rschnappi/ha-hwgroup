"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DOMAIN
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator


class HWGroupEntity(CoordinatorEntity[HWGroupCoordinator]):
    """Entity bound to one config entry / device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._entry = entry
        info = coordinator.data.info
        connections = (
            {(CONNECTION_NETWORK_MAC, info.mac.lower())} if info.mac else set()
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            connections=connections,
            name=entry.data.get(CONF_DEVICE_NAME) or info.name,
            manufacturer="HW group",
            model=info.model,
            sw_version=info.version,
            serial_number=info.serial,
            configuration_url=f"http://{coordinator.api.host}:{coordinator.api.port}/",
        )
