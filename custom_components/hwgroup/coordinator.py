"""DataUpdateCoordinator for HW group devices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HWGroupApi, HWGroupAuthError, HWGroupError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .parser import DeviceData

_LOGGER = logging.getLogger(__name__)


@dataclass
class HWGroupRuntimeData:
    """Per-entry runtime objects."""

    api: HWGroupApi
    coordinator: HWGroupCoordinator


type HWGroupConfigEntry = ConfigEntry[HWGroupRuntimeData]


class HWGroupCoordinator(DataUpdateCoordinator[DeviceData]):
    """Polls one device."""

    config_entry: HWGroupConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: HWGroupConfigEntry, api: HWGroupApi
    ) -> None:
        """Initialize."""
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {api.host}",
            update_interval=timedelta(seconds=int(interval)),
        )
        self.api = api

    async def _async_update_data(self) -> DeviceData:
        try:
            return await self.api.async_get_data()
        except HWGroupAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HWGroupError as err:
            raise UpdateFailed(f"{self.api.host}: {err}") from err
