"""Integration tests against a mocked device."""

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.hwgroup.const import DOMAIN

from .conftest import HOST, fixture_bytes

BASE = f"http://{HOST}:80"


def mock_sms(aioclient_mock, status="sms_status.xml"):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("sms_values.xml"))
    aioclient_mock.get(f"{BASE}/status.xml", content=fixture_bytes(status))


async def setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity(hass, platform, entry, suffix):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{suffix}")


async def test_sms_gateway_text_sensors_load_without_errors(hass, sms_entry, aioclient_mock):
    mock_sms(aioclient_mock)
    await setup(hass, sms_entry)
    assert sms_entry.state is ConfigEntryState.LOADED

    eid = entity(hass, "sensor", sms_entry, "network_operator")
    assert eid
    state = hass.states.get(eid)
    assert state.state == "A1"
    assert "state_class" not in state.attributes
    sent = hass.states.get(entity(hass, "sensor", sms_entry, "sms_sent"))
    assert sent.state == "10619"
    assert sent.attributes["state_class"] == "total_increasing"


async def test_poseidon_entities_and_inversion(hass, poseidon_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("poseidon_values.xml"))
    await setup(hass, poseidon_entry)

    temp = hass.states.get(entity(hass, "sensor", poseidon_entry, "1"))
    assert temp.state == "25.3"
    assert temp.attributes["device_class"] == "temperature"
    assert hass.states.get(entity(hass, "sensor", poseidon_entry, "3")).state == "unknown"
    text = hass.states.get(entity(hass, "sensor", poseidon_entry, "5"))
    assert text.state == "OK" and "state_class" not in text.attributes
    # Wert 1, Eingang invertiert -> off
    door = hass.states.get(entity(hass, "binary_sensor", poseidon_entry, "binary_101"))
    assert door.state == "off" and door.attributes["device_class"] == "door"
    assert entity(hass, "switch", poseidon_entry, "switch_201")


async def test_gateway_failure_is_unavailable_not_exception(hass, sms_entry, aioclient_mock):
    mock_sms(aioclient_mock)
    await setup(hass, sms_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/values.xml", status=500)
    await sms_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    eid = entity(hass, "sensor", sms_entry, "sms_sent")
    assert hass.states.get(eid).state == STATE_UNAVAILABLE


async def test_status_xml_failure_only_makes_status_unavailable(hass, sms_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("sms_values.xml"))
    aioclient_mock.get(f"{BASE}/status.xml", status=500)
    await setup(hass, sms_entry)
    assert sms_entry.state is ConfigEntryState.LOADED
    eid = entity(hass, "sensor", sms_entry, "sms_sent")
    assert hass.states.get(eid).state == STATE_UNAVAILABLE


async def test_setup_retry_when_unreachable(hass, sms_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", exc=TimeoutError)
    await setup(hass, sms_entry)
    assert sms_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failure_triggers_reauth(hass, sms_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", status=401)
    await setup(hass, sms_entry)
    assert sms_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_send_sms_service_url_matches_previous_version(hass, sms_entry, aioclient_mock):
    mock_sms(aioclient_mock)
    await setup(hass, sms_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/values.xml", content=b"<Root><Rslt>1</Rslt></Root>")
    await hass.services.async_call(
        DOMAIN, "send_sms", {"phone_number": "+43676123456", "message": "Hallo Welt"}, blocking=True
    )
    url = str(aioclient_mock.mock_calls[-1][1])
    assert "Cmd=SMS" in url and "Nmr=+43676123456" in url and "Text=Hallo%20Welt" in url


async def test_send_sms_failure_raises(hass, sms_entry, aioclient_mock):
    mock_sms(aioclient_mock)
    await setup(hass, sms_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/values.xml", content=b"<Root><Rslt>0</Rslt></Root>")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "send_sms", {"phone_number": "+43676123456", "message": "x"}, blocking=True
        )


async def test_service_without_gateway_is_validation_error(hass, poseidon_entry, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("poseidon_values.xml"))
    await setup(hass, poseidon_entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "send_sms", {"phone_number": "+43676123456", "message": "x"}, blocking=True
        )
