"""Switches (relay outputs). Created only for devices that report outputs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HWGroupError
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity
from .parser import Channel


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches; outputs that show up later are added on the fly."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [
            HWGroupSwitch(coordinator, entry, channel)
            for channel_id, channel in coordinator.data.outputs.items()
            if channel_id not in known
        ]
        known.update(switch.channel_id for switch in new)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class HWGroupSwitch(HWGroupEntity, SwitchEntity):
    """A relay output."""

    def __init__(
        self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry, channel: Channel
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self.channel_id = channel.id
        self._attr_name = channel.name
        self._attr_unique_id = f"{entry.entry_id}_switch_{channel.id}"

    @property
    def _channel(self) -> Channel | None:
        return self.coordinator.data.outputs.get(self.channel_id)

    @property
    def available(self) -> bool:
        """Unavailable when the device is unreachable or the output vanished."""
        return super().available and self._channel is not None

    @property
    def is_on(self) -> bool | None:
        """Return the output state."""
        channel = self._channel
        return channel.is_on if channel else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show whether the device controls the output itself."""
        channel = self._channel
        return {"manual_mode": channel.mode == 0} if channel and channel.mode is not None else {}

    async def _set(self, on: bool) -> None:
        channel = self._channel
        if channel is not None and channel.mode not in (None, 0):
            raise HomeAssistantError(
                f"{self.name} is controlled by the device itself (mode {channel.mode}); "
                "set it to manual control in the device's web interface first"
            )
        try:
            await self.coordinator.api.async_set_output(self.channel_id, on)
        except HWGroupError as err:
            raise HomeAssistantError(f"Switching {self.name} failed: {err}") from err
        await self.coordinator.async_refresh()
        if self.is_on is not on:
            raise HomeAssistantError(
                f"{self.name}: the device did not accept the new state"
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the output on."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the output off."""
        await self._set(False)
