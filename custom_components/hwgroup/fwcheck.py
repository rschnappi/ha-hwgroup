"""Look up the newest published firmware on the HW group download page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import html
import logging
import re

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PRODUCT_PAGE = "https://www.hw-group.com/product-version/poseidon2-damocles2"
CHECK_INTERVAL = timedelta(hours=24)

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_FILE = re.compile(r'href="([^"]+\.hwg)"')
_VERSION = re.compile(r"(\d+(?:\.\d+)+)(?:\s*\((\d+)\))?")
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Firmware:
    """One published firmware."""

    version: str
    build: str | None
    released: str
    url: str

    @property
    def key(self) -> tuple[int, ...]:
        """Sortable version."""
        return tuple(int(p) for p in self.version.split("."))


def parse_firmware_page(page: str) -> list[Firmware]:
    """Extract all firmware rows (with a .hwg download link) from the page."""
    found: list[Firmware] = []
    for row in _ROW.findall(page):
        link = _FILE.search(row)
        if not link:
            continue
        cells = [
            re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", c))).strip()
            for c in _CELL.findall(row)
        ]
        match = _VERSION.search(cells[1] if len(cells) > 1 else "")
        if not match:
            continue
        found.append(
            Firmware(
                version=match.group(1),
                build=match.group(2),
                released=cells[2] if len(cells) > 2 else "",
                url=html.unescape(link.group(1)),
            )
        )
    return found


def newest(firmwares: list[Firmware]) -> Firmware | None:
    """Highest version (beta versions are not listed as .hwg rows on that page)."""
    return max(firmwares, key=lambda f: f.key, default=None)


class FirmwareCoordinator(DataUpdateCoordinator[Firmware | None]):
    """Polls the HW group page once a day."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} firmware",
            update_interval=CHECK_INTERVAL,
        )

    async def _async_update_data(self) -> Firmware | None:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                PRODUCT_PAGE, timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    raise UpdateFailed(f"HTTP {response.status}")
                page = await response.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"firmware page unreachable: {err}") from err
        return newest(parse_firmware_page(page))
