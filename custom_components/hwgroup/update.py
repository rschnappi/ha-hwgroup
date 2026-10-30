"""Firmware availability (read-only: nothing is installed from Home Assistant)."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_SMS_GATEWAY
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity
from .fwcheck import PRODUCT_PAGE, FirmwareCoordinator

DESCRIPTION = UpdateEntityDescription(
    key="firmware",
    translation_key="firmware",
    entity_category=EntityCategory.DIAGNOSTIC,
)


def _short(version: str) -> str:
    """'1.4.1.2958' (version.build) -> '1.4.1'."""
    parts = version.split(".")
    return ".".join(parts[:3]) if len(parts) > 3 else version


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """SMS gateways report a pending firmware themselves; Poseidon2 units are checked online."""
    coordinator = entry.runtime_data.coordinator
    info = coordinator.data.info
    if info.device_type == DEVICE_TYPE_SMS_GATEWAY:
        async_add_entities([HWGroupGatewayUpdate(coordinator, entry)])
    elif "poseidon2" in info.model.lower():
        firmware = FirmwareCoordinator(hass, entry)
        await firmware.async_refresh()  # a failed lookup must not block setup
        async_add_entities([HWGroupPoseidonUpdate(coordinator, entry, firmware)])


class HWGroupGatewayUpdate(HWGroupEntity, UpdateEntity):
    """Firmware the gateway has found or already downloaded (nuv/nus in status.xml)."""

    entity_description = DESCRIPTION

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
        """Pending firmware, otherwise the installed one."""
        pending = self.coordinator.data.status.get("update_version")
        return _short(str(pending)) if pending else self.installed_version

    @property
    def release_summary(self) -> str | None:
        """What the gateway says (e.g. 'Download done. Please restart.')."""
        state = self.coordinator.data.status.get("update_state")
        return str(state) if state else None


class HWGroupPoseidonUpdate(HWGroupEntity, UpdateEntity):
    """Compares the device firmware with the newest one HW group publishes."""

    entity_description = DESCRIPTION

    def __init__(
        self,
        coordinator: HWGroupCoordinator,
        entry: HWGroupConfigEntry,
        firmware: FirmwareCoordinator,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self._firmware = firmware
        self._attr_unique_id = f"{entry.entry_id}_firmware_update"
        self._attr_release_url = PRODUCT_PAGE

    async def async_added_to_hass(self) -> None:
        """Also follow the firmware lookup."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._firmware.async_add_listener(self.async_write_ha_state)
        )

    @property
    def installed_version(self) -> str | None:
        """Firmware running now."""
        return self.coordinator.data.info.version

    @property
    def latest_version(self) -> str | None:
        """Newest published firmware; unknown while the lookup has failed."""
        latest = self._firmware.data
        return latest.version if latest else None

    @property
    def release_summary(self) -> str | None:
        """Date and build of the newest firmware."""
        latest = self._firmware.data
        if not latest:
            return None
        build = f", Build {latest.build}" if latest.build else ""
        return f"Veröffentlicht {latest.released}{build}"
