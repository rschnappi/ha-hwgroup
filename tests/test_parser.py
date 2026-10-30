"""Parser tests (no Home Assistant needed)."""

from pathlib import Path

import pytest

from custom_components.hwgroup.parser import (
    HWGroupParseError,
    decode_body,
    parse_status,
    parse_values,
    result_ok,
)

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_sms_gateway_values():
    data = parse_values(read("sms_values.xml"))
    assert data.info.model == "HWg-SMS-GW3"
    assert data.info.device_type == "sms_gateway"
    assert data.info.serial == "0000000001"
    assert not data.sensors and not data.binary_sensors and not data.outputs


def test_sms_gateway_status_text_values_stay_text():
    status = parse_status(read("sms_status.xml"))
    assert status["network_operator"] == "A1"
    assert status["network_status"] == "Registered, roaming"
    assert status["signal_strength"] == -69.0
    assert status["signal_quality"] == 70.0
    assert status["sms_sent"] == 10619
    assert status["sms_errors"] == 0
    assert status["calls_ok"] == 8
    assert status["sim_status"] == "PIN not required"
    # eingehende SMS werden nicht uebernommen
    assert not any("gut" in str(v) for v in status.values())


def test_poseidon_values_with_namespace_and_latin1_declaration():
    data = parse_values(read("poseidon_values.xml"))
    assert data.info.device_type == "sensor_unit"
    assert data.info.name == "MON-REM"
    assert data.info.model == "Poseidon2 3268"
    assert data.sensors["1"].value == 25.3
    assert data.sensors["2"].value == 41.5  # Komma
    assert data.sensors["3"].value is None  # -999.9 = kein Fuehler
    assert data.sensors["5"].value == "OK"
    assert data.binary_sensors["101"].is_on is True
    assert data.binary_sensors["102"].alarm == "1"
    assert data.outputs["201"].is_on is False


def test_invalid_bytes_and_control_chars_do_not_raise():
    status = parse_status(read("status_latin1.xml"))
    assert status["network_operator"] == "Telekörn".replace("rn", "m")  # cp1252-Fallback
    assert status["network_status"] == "Registered"  # NUL entfernt
    assert status["sms_sent"] == 5


def test_decode_body_never_raises():
    assert decode_body(b"\xff\xfe\x00abc")  # Muell, aber kein Fehler
    assert decode_body("ä".encode()) == "ä"


@pytest.mark.parametrize("raw", [b"", b"   ", b"<a><b></a>", b"kein xml"])
def test_garbage_raises_parse_error_only(raw):
    with pytest.raises(HWGroupParseError):
        parse_values(raw)


def test_result_ok():
    assert result_ok(b"<Root><Rslt>1</Rslt></Root>")
    assert result_ok("<Rslt> 1 </Rslt>")
    assert not result_ok(b"<Rslt>0</Rslt>")
