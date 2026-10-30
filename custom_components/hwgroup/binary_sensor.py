"""Binary sensors (digital inputs)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_INVERT_BINARY_SENSORS
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity
from .parser import Channel

# Reihenfolge wie in der Vorgaengerversion: erster Treffer im Namen gewinnt.
_NAME_CLASSES: tuple[tuple[tuple[str, ...], BinarySensorDeviceClass], ...] = (
    (("door", "tür", "türe", "tur"), BinarySensorDeviceClass.DOOR),
    (("window", "fenster"), BinarySensorDeviceClass.WINDOW),
    (("motion", "bewegung", "pir"), BinarySensorDeviceClass.MOTION),
    (("smoke", "rauch", "fire", "feuer"), BinarySensorDeviceClass.SMOKE),
    (("water", "wasser", "leak", "leck"), BinarySensorDeviceClass.MOISTURE),
    (("hum", "feucht", "moisture"), BinarySensorDeviceClass.MOISTURE),
    (("temp", "heat", "cold"), BinarySensorDeviceClass.HEAT),
    (("vibr", "shock"), BinarySensorDeviceClass.VIBRATION),
    (("sound", "noise", "geräusch", "laut"), BinarySensorDeviceClass.SOUND),
    (("power", "strom", "electricity"), BinarySensorDeviceClass.POWER),
    (("gas",), BinarySensorDeviceClass.GAS),
    (("light", "licht", "brightness"), BinarySensorDeviceClass.LIGHT),
    (("presence", "anwesenheit", "occupancy"), BinarySensorDeviceClass.OCCUPANCY),
    (("comm", "connection", "verbindung", "network"), BinarySensorDeviceClass.CONNECTIVITY),
    (("alarm", "alert"), BinarySensorDeviceClass.PROBLEM),
    (("battery", "batterie", "akku"), BinarySensorDeviceClass.BATTERY),
)


def guess_device_class(name: str) -> BinarySensorDeviceClass:
    """Guess a device class from the channel name (fallback: opening)."""
    lowered = name.lower()
    for keywords, device_class in _NAME_CLASSES:
        if any(keyword in lowered for keyword in keywords):
            return device_class
    return BinarySensorDeviceClass.OPENING


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors; channels that show up later are added on the fly."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [
            HWGroupBinarySensor(coordinator, entry, channel)
            for channel_id, channel in coordinator.data.binary_sensors.items()
            if channel_id not in known
        ]
        known.update(sensor.channel_id for sensor in new)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class HWGroupBinarySensor(HWGroupEntity, BinarySensorEntity):
    """A digital input."""

    def __init__(
        self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry, channel: Channel
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self.channel_id = channel.id
        self._attr_name = channel.name
        self._attr_unique_id = f"{entry.entry_id}_binary_{channel.id}"
        self._attr_device_class = guess_device_class(channel.name)

    @property
    def _channel(self) -> Channel | None:
        return self.coordinator.data.binary_sensors.get(self.channel_id)

    @property
    def _inverted(self) -> bool:
        # Optionen haben Vorrang; "data" bleibt fuer Eintraege der Vorgaengerversion.
        entry = self._entry
        configured = entry.options.get(
            CONF_INVERT_BINARY_SENSORS, entry.data.get(CONF_INVERT_BINARY_SENSORS, [])
        )
        return self.channel_id in configured

    @property
    def available(self) -> bool:
        """Unavailable when the device is unreachable or the channel vanished."""
        return super().available and self._channel is not None

    @property
    def is_on(self) -> bool | None:
        """Return the (optionally inverted) input state."""
        channel = self._channel
        if channel is None or (state := channel.is_on) is None:
            return None
        return not state if self._inverted else state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose inversion and the device's alarm state."""
        attrs: dict[str, Any] = {"inverted": self._inverted}
        if (channel := self._channel) and channel.alarm:
            attrs["alarm_state"] = channel.alarm
        return attrs
