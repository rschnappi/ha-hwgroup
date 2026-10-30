"""Shared fixtures."""

from pathlib import Path

import pytest

from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hwgroup.const import DOMAIN

FIX = Path(__file__).parent / "fixtures"
HOST = "192.0.2.9"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in tests."""


def fixture_bytes(name: str) -> bytes:
    return (FIX / name).read_bytes()


@pytest.fixture
def sms_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SMS-GW",
        data={CONF_HOST: HOST},
        unique_id=f"{HOST}_0000000001",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def poseidon_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="REM",
        data={CONF_HOST: HOST},
        options={"invert_binary_sensors": ["101"]},
        unique_id=f"{HOST}_0000000002",
    )
    entry.add_to_hass(hass)
    return entry
