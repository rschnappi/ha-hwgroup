"""Constants for the HW group integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hwgroup"

CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_INVERT_BINARY_SENSORS: Final = "invert_binary_sensors"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_DEFAULT_RECIPIENT: Final = "default_recipient"

DEVICE_TYPE_SENSOR_UNIT: Final = "sensor_unit"
DEVICE_TYPE_SMS_GATEWAY: Final = "sms_gateway"

DEFAULT_PORT: Final = 80
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
REQUEST_TIMEOUT: Final = 10

# Werte unterhalb dieser Grenze meldet Poseidon fuer "kein Fuehler gesteckt".
NO_SENSOR_VALUE: Final = -999.0

SERVICE_SEND_SMS: Final = "send_sms"
SERVICE_CALL_NUMBER: Final = "call_number"
ATTR_PHONE_NUMBER: Final = "phone_number"
ATTR_MESSAGE: Final = "message"
ATTR_DEVICE_ID: Final = "device_id"
