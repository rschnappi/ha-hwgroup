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
    aioclient_mock.clear_requests()  # autouse-Mock der Seite entfernen, sonst gewinnt er
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


def _install_mocks(aioclient_mock, *, version="3.10.0", size=600_000, upload_ok=True):
    aioclient_mock.clear_requests()
    values = fixture_bytes("poseidon_values.xml").replace(b"<Version>3.0.6</Version>", f"<Version>{version}</Version>".encode())
    aioclient_mock.get(f"{BASE}/values.xml", content=values)
    aioclient_mock.get(
        "https://www.hw-group.com/files/download/fw/version/posdam2_3-10-0.hwg",
        content=b"x" * size,
    )
    aioclient_mock.post(
        f"{BASE}/upload",
        text="Successfully uploaded, wait a while" if upload_ok else "error",
    )


async def _setup_update(hass, poseidon_entry, aioclient_mock, monkeypatch):
    for name, value in (("RESTART_DELAY", 0), ("POLL_INTERVAL", 0), ("RESTART_TIMEOUT", 1)):
        monkeypatch.setattr(f"custom_components.hwgroup.update.{name}", value)
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("poseidon_values.xml"))
    await hass.config_entries.async_setup(poseidon_entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass).async_get_entity_id(
        "update", DOMAIN, f"{poseidon_entry.entry_id}_firmware_update"
    )


async def test_install_downloads_uploads_and_verifies(hass, poseidon_entry, aioclient_mock, monkeypatch):
    eid = await _setup_update(hass, poseidon_entry, aioclient_mock, monkeypatch)
    _install_mocks(aioclient_mock)
    await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert len(posts) == 1 and str(posts[0][1]).endswith("/upload")
    body = posts[0][2]
    # Teile-Reihenfolge wie curl: Content-Disposition zuerst, kein Content-Type beim Submit-Feld
    assert b'Content-Disposition: form-data; name="filename"; filename="posdam2_3-10-0.hwg"
Content-Type: application/octet-stream

' in body
    assert b'Content-Disposition: form-data; name="Submit"

Upload
' in body


async def test_install_fails_when_device_keeps_old_version(hass, poseidon_entry, aioclient_mock, monkeypatch):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    eid = await _setup_update(hass, poseidon_entry, aioclient_mock, monkeypatch)
    _install_mocks(aioclient_mock, version="3.0.6")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)
    assert hass.states.get(eid).attributes["in_progress"] is False


async def test_install_refuses_implausible_download_and_rejected_upload(hass, poseidon_entry, aioclient_mock, monkeypatch):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    eid = await _setup_update(hass, poseidon_entry, aioclient_mock, monkeypatch)
    _install_mocks(aioclient_mock, size=1000)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)
    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]

    _install_mocks(aioclient_mock, upload_ok=False)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)


async def _setup_gateway(hass, sms_entry, aioclient_mock, monkeypatch, status="sms_status.xml"):
    for name, value in (("RESTART_DELAY", 0), ("POLL_INTERVAL", 0), ("RESTART_TIMEOUT", 1)):
        monkeypatch.setattr(f"custom_components.hwgroup.update.{name}", value)
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("sms_values.xml"))
    aioclient_mock.get(f"{BASE}/status.xml", content=fixture_bytes(status))
    await hass.config_entries.async_setup(sms_entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass).async_get_entity_id(
        "update", DOMAIN, f"{sms_entry.entry_id}_firmware_update"
    )


async def test_gateway_install_restarts_and_verifies(hass, sms_entry, aioclient_mock, monkeypatch):
    eid = await _setup_gateway(hass, sms_entry, aioclient_mock, monkeypatch)
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/values.xml",
        content=fixture_bytes("sms_values.xml").replace(b"<Version>1.3.5</Version>", b"<Version>1.4.1</Version>"),
    )
    aioclient_mock.post(f"{BASE}/sysinfo.xml", text="ok")
    await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert len(posts) == 1 and str(posts[0][1]).endswith("/sysinfo.xml")


async def test_gateway_install_refuses_when_not_downloaded(hass, sms_entry, aioclient_mock, monkeypatch):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    eid = await _setup_gateway(hass, sms_entry, aioclient_mock, monkeypatch)
    # Status "noch nichts geladen": Entity aus dem Zustand neu aufbauen
    status = sms_entry.runtime_data.coordinator.data.status
    status["update_state"] = "New version available"
    aioclient_mock.post(f"{BASE}/sysinfo.xml", text="ok")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {"entity_id": eid}, blocking=True)
    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
