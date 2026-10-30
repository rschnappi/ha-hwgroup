"""Firmware update availability (read-only; the device installs it itself)."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_SMS_GATEWAY
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity


def _short(version: str) -> str:
    """'1.4.1.2958' (version.build) -> '1.4.1'."""
    parts = version.split(".")
    return ".".join(parts[:3]) if len(parts) > 3 else version


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Only SMS gateways report a pending firmware (nuv/nus in status.xml)."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.data.info.device_type == DEVICE_TYPE_SMS_GATEWAY:
        async_add_entities([HWGroupFirmwareUpdate(coordinator, entry)])


class HWGroupFirmwareUpdate(HWGroupEntity, UpdateEntity):
    """Shows the firmware the gateway has found or already downloaded."""

    entity_description = UpdateEntityDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_firmware_update"

    @property
    def installed_version(self) -> str | None:
        """Firmware running now."""
        return self.coordinator.data.info.version

    @property
    def latest_version(self) -> str | None:
        """Newest known firmware; equals the installed one when nothing is pending."""
        pending = self.coordinator.data.status.get("update_version")
        if not pending:
            return self.installed_version
        return _short(str(pending))

    @property
    def release_summary(self) -> str | None:
        """What the gateway says about the update (e.g. 'Download done. Please restart.')."""
        state = self.coordinator.data.status.get("update_state")
        return str(state) if state else None
