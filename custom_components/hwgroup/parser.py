"""Tolerant decoding and parsing of HW group XML documents.

Pure functions without Home Assistant dependencies so they can be unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from xml.etree import ElementTree

from .const import DEVICE_TYPE_SENSOR_UNIT, DEVICE_TYPE_SMS_GATEWAY, NO_SENSOR_VALUE

_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
# Zeichen, die in XML 1.0 nicht vorkommen duerfen (Steuerzeichen ausser Tab/LF/CR).
_INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_SIGNAL = re.compile(r"(-?\d+)\s*dBm(?:\s*\(\s*(\d+)\s*%\s*\))?", re.IGNORECASE)
_RESULT_OK = re.compile(r"<Rslt>\s*1\s*</Rslt>")

# Namensmuster der <...Set>-Gruppen in values.xml
_SET_KIND = (
    ("output", re.compile(r"out|relay|rele", re.IGNORECASE)),
    ("binary", re.compile(r"bin|input|contact", re.IGNORECASE)),
    ("sensor", re.compile(r"sen", re.IGNORECASE)),
)


class HWGroupParseError(Exception):
    """Raised when a document cannot be parsed at all."""


def decode_body(raw: bytes) -> str:
    """Decode a gateway response without ever raising.

    UTF-8 first (so SMS texts with umlauts stay intact); on failure fall back
    to Windows-1252 and finally to replacement characters.
    """
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_xml(raw: bytes | str) -> ElementTree.Element:
    """Parse a document: tolerant decoding, no namespaces, sanitised."""
    text = decode_body(raw) if isinstance(raw, bytes) else raw
    text = _XML_DECLARATION.sub("", text, count=1)
    text = _INVALID_XML_CHARS.sub("", text).strip()
    if not text:
        raise HWGroupParseError("empty response")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as err:
        raise HWGroupParseError(f"invalid XML: {err}") from err
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]
    return root


def _text(parent: ElementTree.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    child = parent.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def parse_number(value: str | None) -> float | None:
    """Return a float for numeric text (comma allowed), else None."""
    if value is None:
        return None
    try:
        number = float(value.replace(",", "."))
    except ValueError:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


@dataclass(slots=True)
class DeviceInfoData:
    """Static information of a device."""

    name: str = "HW group device"
    model: str = "Unknown"
    version: str | None = None
    serial: str | None = None
    mac: str | None = None
    device_type: str = DEVICE_TYPE_SENSOR_UNIT


@dataclass(slots=True)
class Channel:
    """One sensor, binary input or output of a device."""

    id: str
    name: str
    value: float | str | None
    unit: str = ""
    alarm: str | None = None

    @property
    def is_on(self) -> bool | None:
        """Interpret the value as 0/1."""
        number = parse_number(self.value) if isinstance(self.value, str) else self.value
        if number is None:
            return None
        return number >= 1


@dataclass(slots=True)
class DeviceData:
    """Everything one poll returns."""

    info: DeviceInfoData
    sensors: dict[str, Channel] = field(default_factory=dict)
    binary_sensors: dict[str, Channel] = field(default_factory=dict)
    outputs: dict[str, Channel] = field(default_factory=dict)
    status: dict[str, float | int | str] = field(default_factory=dict)


def detect_device_type(model: str) -> str:
    """Classify a device by its model text."""
    return (
        DEVICE_TYPE_SMS_GATEWAY
        if "sms" in model.lower()
        else DEVICE_TYPE_SENSOR_UNIT
    )


def _parse_info(root: ElementTree.Element) -> DeviceInfoData:
    agent = root.find(".//Agent")
    if agent is None:
        return DeviceInfoData()
    model = (
        _text(agent, "Title")
        or _text(agent, "ProductName")
        or _text(agent, "Model")
        or "Unknown"
    )
    return DeviceInfoData(
        name=_text(agent, "DeviceName") or model,
        model=model,
        version=_text(agent, "Version"),
        serial=_text(agent, "SerialNumber"),
        mac=_text(agent, "MAC"),
        device_type=detect_device_type(model),
    )


def _parse_channel(entry: ElementTree.Element, default_prefix: str) -> Channel | None:
    channel_id = _text(entry, "ID")
    if channel_id is None or entry.find("Value") is None:
        return None
    raw = _text(entry, "Value")
    number = parse_number(raw)
    value: float | str | None
    if number is not None:
        value = None if number <= NO_SENSOR_VALUE else number
    else:
        value = raw
    return Channel(
        id=channel_id,
        name=_text(entry, "Name") or f"{default_prefix} {channel_id}",
        value=value,
        unit=_text(entry, "Units") or _text(entry, "Unit") or "",
        alarm=_text(entry, "State"),
    )


def parse_values(raw: bytes | str) -> DeviceData:
    """Parse values.xml."""
    root = parse_xml(raw)
    data = DeviceData(info=_parse_info(root))
    targets = {
        "sensor": (data.sensors, "Sensor"),
        "binary": (data.binary_sensors, "Input"),
        "output": (data.outputs, "Output"),
    }
    for group in root.iter():
        if not isinstance(group.tag, str) or not group.tag.endswith("Set"):
            continue
        prefix = group.tag[: -len("Set")]
        kind = next((k for k, pattern in _SET_KIND if pattern.search(prefix)), None)
        if kind is None:
            continue
        bucket, label = targets[kind]
        for entry in group.findall("Entry"):
            channel = _parse_channel(entry, label)
            if channel is not None:
                bucket[channel.id] = channel
    return data


def parse_status(raw: bytes | str) -> dict[str, float | int | str]:
    """Parse the SMS gateway status.xml into a flat dict.

    Inbound SMS (<GsmIn>) are deliberately ignored.
    """
    root = parse_xml(raw)
    status: dict[str, float | int | str] = {}

    signal = _text(root, "ModemSigQ")
    if signal and (match := _SIGNAL.search(signal)):
        status["signal_strength"] = float(match.group(1))
        if match.group(2) is not None:
            status["signal_quality"] = float(match.group(2))

    for key, tag in (("network_operator", "ModemNetOp"), ("network_status", "ModemNetReg")):
        if (text := _text(root, tag)) is not None:
            status[key] = text

    for key, tag in (
        ("sms_sent", "CntSmsOK"),
        ("sms_errors", "CntSmsError"),
        ("calls_ok", "CntRingOK"),
        ("call_errors", "CntRingError"),
    ):
        if (number := parse_number(_text(root, tag))) is not None:
            status[key] = int(number)

    if (text := _text(root, "pin_tstatus")) is not None:
        status["sim_status"] = text
    return status


def result_ok(raw: bytes | str) -> bool:
    """True if a command response reports <Rslt>1</Rslt>."""
    text = decode_body(raw) if isinstance(raw, bytes) else raw
    return bool(_RESULT_OK.search(text))


def redact(data: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    """Return a copy with the given keys replaced (used by diagnostics)."""
    return {k: ("**REDACTED**" if k in keys else v) for k, v in data.items()}
