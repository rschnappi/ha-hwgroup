"""Firmware updates: gateway shows a pending firmware, Poseidon2 units can be flashed from HA."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import aiohttp

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HWGroupError
from .const import DEVICE_TYPE_SMS_GATEWAY
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity
from .fwcheck import PRODUCT_PAGE, FirmwareCoordinator

_LOGGER = logging.getLogger(__name__)

# Nie zwei Geraete gleichzeitig flashen (Ueberwachung faellt sonst flaechendeckend aus).
INSTALL_LOCK = asyncio.Lock()
MIN_FIRMWARE_BYTES = 500_000
MAX_FIRMWARE_BYTES = 3_000_000
RESTART_DELAY = 30  # s: so lange braucht das Geraet mindestens fuer Flash + Neustart
RESTART_TIMEOUT = 300  # s
POLL_INTERVAL = 5

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
        self._attr_supported_features = (
            UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
        )

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

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Download the published firmware and flash it, one device at a time.

        The device restarts (about a minute offline). Success means the device reports
        the new version afterwards; otherwise an error is raised and nothing is retried.
        """
        latest = self._firmware.data
        if latest is None:
            raise HomeAssistantError("Keine Firmware-Information von HW group verfügbar")
        if version not in (None, latest.version):
            raise HomeAssistantError(f"Nur die aktuelle Version {latest.version} kann installiert werden")
        if latest.version == self.installed_version:
            return

        async with INSTALL_LOCK:
            self._attr_in_progress = True
            self.async_write_ha_state()
            try:
                payload = await self._download(latest.url)
                _LOGGER.warning(
                    "Flashing %s on %s: %s bytes, sha256 %s",
                    latest.version,
                    self.coordinator.api.host,
                    len(payload),
                    hashlib.sha256(payload).hexdigest(),
                )
                try:
                    await self.coordinator.api.async_upload_firmware(
                        payload, latest.url.rsplit("/", 1)[-1]
                    )
                except HWGroupError as err:
                    raise HomeAssistantError(f"Firmware-Upload fehlgeschlagen: {err}") from err
                await self._wait_for(latest.version)
            finally:
                self._attr_in_progress = False
                self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _download(self, url: str) -> bytes:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    raise HomeAssistantError(f"Firmware-Download fehlgeschlagen (HTTP {response.status})")
                payload = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Firmware-Download fehlgeschlagen: {err}") from err
        if not MIN_FIRMWARE_BYTES <= len(payload) <= MAX_FIRMWARE_BYTES:
            raise HomeAssistantError(
                f"Firmware-Datei hat eine unplausible Größe ({len(payload)} Bytes), Abbruch"
            )
        return payload

    async def _wait_for(self, version: str) -> None:
        """Wait until the restarted device reports the new version."""
        await asyncio.sleep(RESTART_DELAY)
        deadline = asyncio.get_running_loop().time() + RESTART_TIMEOUT
        while True:
            try:
                if await self.coordinator.api.async_read_version() == version:
                    return
            except HWGroupError:
                pass  # noch im Neustart
            if asyncio.get_running_loop().time() > deadline:
                raise HomeAssistantError(
                    f"{self.coordinator.api.host} meldet nach {RESTART_TIMEOUT} s nicht Version {version}"
                )
            await asyncio.sleep(POLL_INTERVAL)
