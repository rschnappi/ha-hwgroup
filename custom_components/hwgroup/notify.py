"""notify entity: send an SMS to the configured default recipient."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HWGroupError
from .const import CONF_DEFAULT_RECIPIENT, DEVICE_TYPE_SMS_GATEWAY
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the notify entity for SMS gateways with a default recipient."""
    coordinator = entry.runtime_data.coordinator
    if (
        coordinator.data.info.device_type == DEVICE_TYPE_SMS_GATEWAY
        and entry.options.get(CONF_DEFAULT_RECIPIENT)
    ):
        async_add_entities([HWGroupSmsNotify(coordinator, entry)])


class HWGroupSmsNotify(HWGroupEntity, NotifyEntity):
    """SMS to the default recipient (notify.send_message)."""

    _attr_translation_key = "sms"

    def __init__(self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_notify_sms"

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send the message (title is prepended if given)."""
        number = self._entry.options[CONF_DEFAULT_RECIPIENT]
        text = f"{title}: {message}" if title else message
        try:
            await self.coordinator.api.async_send_sms(number, text)
        except HWGroupError as err:
            raise HomeAssistantError(f"Sending SMS failed: {err}") from err
