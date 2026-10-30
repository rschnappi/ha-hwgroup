"""Sensors: Poseidon-style measurements and SMS gateway status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_SMS_GATEWAY
from .coordinator import HWGroupConfigEntry, HWGroupCoordinator
from .entity import HWGroupEntity
from .parser import Channel, parse_number

# unit text (lower case) -> (device class, native unit)
_UNIT_MAP: dict[str, tuple[SensorDeviceClass, str]] = {
    "c": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "°c": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "f": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.FAHRENHEIT),
    "°f": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.FAHRENHEIT),
    "%": (SensorDeviceClass.HUMIDITY, PERCENTAGE),
    "%rh": (SensorDeviceClass.HUMIDITY, PERCENTAGE),
    "v": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
    "a": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
    "ma": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.MILLIAMPERE),
    "hpa": (SensorDeviceClass.PRESSURE, UnitOfPressure.HPA),
    "mbar": (SensorDeviceClass.PRESSURE, UnitOfPressure.MBAR),
    "pa": (SensorDeviceClass.PRESSURE, UnitOfPressure.PA),
}


def describe_channel(channel: Channel) -> SensorEntityDescription:
    """Build the entity description for a measurement channel.

    Text values never get a state class (that was the old 'A1' crash).
    """
    unit = channel.unit.strip()
    mapped = _UNIT_MAP.get(unit.lower())
    if mapped:
        return SensorEntityDescription(
            key=channel.id,
            device_class=mapped[0],
            native_unit_of_measurement=mapped[1],
            state_class=SensorStateClass.MEASUREMENT,
        )
    is_text = isinstance(channel.value, str)
    return SensorEntityDescription(
        key=channel.id,
        native_unit_of_measurement=unit or None,
        state_class=None if is_text else SensorStateClass.MEASUREMENT,
    )


@dataclass(frozen=True, kw_only=True)
class StatusDescription(SensorEntityDescription):
    """Description of an SMS gateway status sensor."""

    enabled_by_default: bool = True


STATUS_SENSORS: tuple[StatusDescription, ...] = (
    StatusDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StatusDescription(
        key="signal_quality",
        translation_key="signal_quality",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Reiner Text (z. B. "A1"): bewusst ohne state_class und Einheit.
    StatusDescription(
        key="network_operator",
        translation_key="network_operator",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StatusDescription(
        key="network_status",
        translation_key="network_status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StatusDescription(
        key="sms_sent",
        translation_key="sms_sent",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    StatusDescription(
        key="sms_errors",
        translation_key="sms_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StatusDescription(
        key="calls_ok",
        translation_key="calls_ok",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_by_default=False,
    ),
    StatusDescription(
        key="call_errors",
        translation_key="call_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_by_default=False,
    ),
    StatusDescription(
        key="sim_status",
        translation_key="sim_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_by_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HWGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors; channels that show up later are added on the fly."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = [
            HWGroupSensor(coordinator, entry, channel)
            for channel_id, channel in coordinator.data.sensors.items()
            if channel_id not in known
        ]
        known.update(sensor.channel_id for sensor in new)  # type: ignore[attr-defined]
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))

    if coordinator.data.info.device_type == DEVICE_TYPE_SMS_GATEWAY:
        async_add_entities(
            HWGroupStatusSensor(coordinator, entry, description)
            for description in STATUS_SENSORS
        )


class HWGroupSensor(HWGroupEntity, SensorEntity):
    """A measurement channel of a sensor unit."""

    def __init__(
        self, coordinator: HWGroupCoordinator, entry: HWGroupConfigEntry, channel: Channel
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self.channel_id = channel.id
        self.entity_description = describe_channel(channel)
        self._attr_name = channel.name
        # Gleiches Schema wie die Vorgaengerversion -> Entitaeten und Statistik bleiben.
        self._attr_unique_id = f"{entry.entry_id}_{channel.id}"

    @property
    def _channel(self) -> Channel | None:
        return self.coordinator.data.sensors.get(self.channel_id)

    @property
    def available(self) -> bool:
        """Unavailable when the device is unreachable or the channel vanished."""
        return super().available and self._channel is not None

    @property
    def native_value(self) -> float | str | None:
        """Return the value; non-numeric text for numeric sensors becomes None."""
        channel = self._channel
        if channel is None or channel.value is None:
            return None
        if self.entity_description.state_class is not None:
            return channel.value if isinstance(channel.value, float) else parse_number(
                channel.value
            )
        return channel.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the device's own alarm state."""
        channel = self._channel
        return {"alarm_state": channel.alarm} if channel and channel.alarm else {}


class HWGroupStatusSensor(HWGroupEntity, SensorEntity):
    """Status value of the SMS gateway (from status.xml)."""

    entity_description: StatusDescription

    def __init__(
        self,
        coordinator: HWGroupCoordinator,
        entry: HWGroupConfigEntry,
        description: StatusDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_entity_registry_enabled_default = description.enabled_by_default

    @property
    def available(self) -> bool:
        """status.xml may fail while values.xml works."""
        return super().available and self.entity_description.key in self.coordinator.data.status

    @property
    def native_value(self) -> float | int | str | None:
        """Return the value."""
        return self.coordinator.data.status.get(self.entity_description.key)
