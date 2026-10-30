"""Firmware lookup tests."""

from pathlib import Path

from homeassistant.helpers import entity_registry as er

from custom_components.hwgroup.const import DOMAIN
from custom_components.hwgroup.fwcheck import PRODUCT_PAGE, newest, parse_firmware_page

from .conftest import HOST, fixture_bytes

PAGE = (Path(__file__).parent / "fixtures" / "hw_firmware_page.html").read_text()
BASE = f"http://{HOST}:80"


def test_parse_and_newest_compares_numerically():
    firmwares = parse_firmware_page(PAGE)
    assert [f.version for f in firmwares] == ["3.9.1", "3.8.7", "3.10.0"]  # PDF-Zeile ignoriert
    top = newest(firmwares)
    assert top.version == "3.10.0"  # nicht "3.9.1" (Textvergleich waere falsch)
    assert newest([]) is None
    assert firmwares[0].build == "7215" and firmwares[0].url.endswith(".hwg")


async def test_poseidon_update_entity(hass, poseidon_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("poseidon_values.xml"))
    aioclient_mock.get(PRODUCT_PAGE, text=PAGE)
    await hass.config_entries.async_setup(poseidon_entry.entry_id)
    await hass.async_block_till_done()
    eid = er.async_get(hass).async_get_entity_id(
        "update", DOMAIN, f"{poseidon_entry.entry_id}_firmware_update"
    )
    state = hass.states.get(eid)
    assert state.attributes["latest_version"] == "3.10.0"
    assert state.attributes["installed_version"] == "3.0.6"
    assert state.state == "on"


async def test_firmware_lookup_failure_does_not_break_setup(hass, poseidon_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("poseidon_values.xml"))
    aioclient_mock.get(PRODUCT_PAGE, status=503)
    await hass.config_entries.async_setup(poseidon_entry.entry_id)
    await hass.async_block_till_done()
    from homeassistant.config_entries import ConfigEntryState

    assert poseidon_entry.state is ConfigEntryState.LOADED
    eid = er.async_get(hass).async_get_entity_id(
        "update", DOMAIN, f"{poseidon_entry.entry_id}_firmware_update"
    )
    assert hass.states.get(eid).state == "unknown"
