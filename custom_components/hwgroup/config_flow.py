"""Config flow for the HW group integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HWGroupApi, HWGroupAuthError, HWGroupError
from .const import (
    CONF_DEFAULT_RECIPIENT,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_INVERT_BINARY_SENSORS,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE_SMS_GATEWAY,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import HWGroupConfigEntry
from .parser import DeviceData

_LOGGER = logging.getLogger(__name__)


async def _probe(hass: HomeAssistant, data: Mapping[str, Any]) -> DeviceData:
    """Connect with the given data and return what the device reports."""
    api = HWGroupApi(
        data[CONF_HOST],
        async_get_clientsession(hass),
        data.get(CONF_USERNAME),
        data.get(CONF_PASSWORD),
        data.get(CONF_PORT, DEFAULT_PORT),
    )
    return await api.async_get_data()


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Optional(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, "")): str,
        }
    )


class HWGroupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: HWGroupConfigEntry) -> HWGroupOptionsFlow:
        """Return the options flow."""
        return HWGroupOptionsFlow()

    async def _validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> DeviceData | None:
        try:
            return await _probe(self.hass, user_input)
        except HWGroupAuthError:
            errors["base"] = "invalid_auth"
        except HWGroupError:
            errors["base"] = "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error while connecting to %s", user_input[CONF_HOST])
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (data := await self._validate(user_input, errors)) is not None:
                # Gleiches Schema wie die Vorgaengerversion (host_seriennummer).
                serial = data.info.serial
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{serial}" if serial else user_input[CONF_HOST]
                )
                self._abort_if_unique_id_configured()
                name = user_input.get(CONF_DEVICE_NAME) or data.info.name
                return self.async_create_entry(
                    title=name,
                    data={
                        **user_input,
                        CONF_DEVICE_NAME: name,
                        CONF_DEVICE_TYPE: data.info.device_type,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema({}), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            candidate = {**entry.data, **user_input}
            if await self._validate(candidate, errors) is not None:
                return self.async_update_reload_and_abort(entry, data=candidate)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, port or credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            candidate = {**entry.data, **user_input}
            if await self._validate(candidate, errors) is not None:
                return self.async_update_reload_and_abort(
                    entry, data=candidate, title=candidate.get(CONF_DEVICE_NAME) or entry.title
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(entry.data), user_input or entry.data
            ),
            errors=errors,
        )


class HWGroupOptionsFlow(OptionsFlowWithReload):
    """Options: polling interval, SMS default recipient, input inversion."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry: HWGroupConfigEntry = self.config_entry
        options = entry.options
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=3600,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
        runtime = getattr(entry, "runtime_data", None)
        data = runtime.coordinator.data if runtime else None
        if data is not None and data.binary_sensors:
            current = options.get(
                CONF_INVERT_BINARY_SENSORS, entry.data.get(CONF_INVERT_BINARY_SENSORS, [])
            )
            schema[vol.Optional(CONF_INVERT_BINARY_SENSORS, default=current)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=cid, label=ch.name)
                            for cid, ch in data.binary_sensors.items()
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        if data is not None and data.info.device_type == DEVICE_TYPE_SMS_GATEWAY:
            schema[
                vol.Optional(
                    CONF_DEFAULT_RECIPIENT,
                    description={"suggested_value": options.get(CONF_DEFAULT_RECIPIENT, "")},
                )
            ] = str
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
