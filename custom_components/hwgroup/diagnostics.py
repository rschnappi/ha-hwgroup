"""Diagnostics."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_DEFAULT_RECIPIENT
from .coordinator import HWGroupConfigEntry

TO_REDACT = {
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEFAULT_RECIPIENT,
    "serial",
    "mac",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HWGroupConfigEntry
) -> dict[str, Any]:
    """Return diagnostics (no credentials, no inbound SMS)."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "last_update_success": coordinator.last_update_success,
        "device": async_redact_data(asdict(coordinator.data.info), TO_REDACT),
        "sensors": {k: asdict(v) for k, v in coordinator.data.sensors.items()},
        "binary_sensors": {k: asdict(v) for k, v in coordinator.data.binary_sensors.items()},
        "outputs": {k: asdict(v) for k, v in coordinator.data.outputs.items()},
        "status": dict(coordinator.data.status),
    }
