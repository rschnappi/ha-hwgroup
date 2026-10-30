"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hwgroup.const import DOMAIN

from .conftest import HOST, fixture_bytes

BASE = f"http://{HOST}:80"


def mock_gateway(aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", content=fixture_bytes("sms_values.xml"))
    aioclient_mock.get(f"{BASE}/status.xml", content=fixture_bytes("sms_status.xml"))


async def start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_entry(hass, aioclient_mock):
    mock_gateway(aioclient_mock)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["device_type"] == "sms_gateway"
    assert result["result"].unique_id == f"{HOST}_0000000001"


async def test_user_flow_errors(hass, aioclient_mock):
    aioclient_mock.get(f"{BASE}/values.xml", status=401)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/values.xml", content=b"kein xml")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(hass, aioclient_mock, sms_entry):
    mock_gateway(aioclient_mock)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
