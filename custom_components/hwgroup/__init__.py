"""The HW group integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HWGroupApi, HWGroupError
from .const import (
    ATTR_DEVICE_ID,
    ATTR_MESSAGE,
    ATTR_PHONE_NUMBER,
    DEFAULT_PORT,
    DEVICE_TYPE_SMS_GATEWAY,
    DOMAIN,
    SERVICE_CALL_NUMBER,
    SERVICE_SEND_SMS,
)
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator, HWGroupRuntimeData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NOTIFY,
]

SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PHONE_NUMBER): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)
CALL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PHONE_NUMBER): cv.string,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)


def _resolve_gateway(hass: HomeAssistant, device_id: str | None) -> HWGroupConfigEntry:
    """Find the SMS gateway entry for a service call.

    ``device_id`` may be a config entry id (as in the previous version) or a
    device registry id. Without it the first loaded SMS gateway is used.
    """
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and entry.runtime_data.coordinator.data.info.device_type == DEVICE_TYPE_SMS_GATEWAY
    ]
    if device_id:
        wanted = {device_id}
        if (device := dr.async_get(hass).async_get(device_id)) is not None:
            wanted |= set(device.config_entries)
        entries = [entry for entry in entries if entry.entry_id in wanted]
    if not entries:
        raise ServiceValidationError(
            "No loaded HW group SMS gateway found", translation_domain=DOMAIN,
            translation_key="no_gateway",
        )
    return entries[0]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide actions once."""

    async def _send_sms(call: ServiceCall) -> None:
        entry = _resolve_gateway(hass, call.data.get(ATTR_DEVICE_ID))
        try:
            await entry.runtime_data.api.async_send_sms(
                call.data[ATTR_PHONE_NUMBER], call.data[ATTR_MESSAGE]
            )
        except HWGroupError as err:
            raise HomeAssistantError(f"Sending SMS failed: {err}") from err

    async def _call_number(call: ServiceCall) -> None:
        entry = _resolve_gateway(hass, call.data.get(ATTR_DEVICE_ID))
        try:
            await entry.runtime_data.api.async_call_number(call.data[ATTR_PHONE_NUMBER])
        except HWGroupError as err:
            raise HomeAssistantError(f"Ringing the number failed: {err}") from err

    hass.services.async_register(DOMAIN, SERVICE_SEND_SMS, _send_sms, schema=SEND_SMS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CALL_NUMBER, _call_number, schema=CALL_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HWGroupConfigEntry) -> bool:
    """Set up one device."""
    api = HWGroupApi(
        entry.data[CONF_HOST],
        async_get_clientsession(hass),
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = HWGroupCoordinator(hass, entry, api)
    # UpdateFailed -> ConfigEntryNotReady (Wiederholung), Auth -> Re-Auth-Flow
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = HWGroupRuntimeData(api=api, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HWGroupConfigEntry) -> bool:
    """Unload a device."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
