from __future__ import annotations

import pytest

from matb_integration.physiology.broadcast import parse_polar_hr_manufacturer_data
from matb_integration.physiology.hrs import parse_heart_rate_measurement
from matb_integration.physiology.transport import PolarBleakTransport, validate_pmd_frame


def test_hrs_golden_vector_preserves_ticks_units_and_optional_fields() -> None:
    # flags: 16-bit HR, contact supported/detected, energy, two RR intervals
    payload = bytes.fromhex("1f 2c 01 34 12 00 04 80 03")
    measurement = parse_heart_rate_measurement(payload)

    assert measurement.heart_rate_bpm == 300
    assert measurement.energy_expended_kj == 0x1234
    assert measurement.sensor_contact_supported is True
    assert measurement.sensor_contact_detected is True
    assert measurement.rr_ticks_1024 == (1024, 896)
    assert measurement.rr_ms == (1000.0, 875.0)


def test_hrs_8_bit_without_contact_or_rr() -> None:
    measurement = parse_heart_rate_measurement(bytes.fromhex("00 3c"))
    assert measurement.heart_rate_bpm == 60
    assert measurement.sensor_contact_detected is None
    assert measurement.rr_ticks_1024 == ()


@pytest.mark.parametrize("payload", [b"", b"\x01", bytes.fromhex("10 3c 01")])
def test_hrs_rejects_truncated_frames(payload: bytes) -> None:
    with pytest.raises(ValueError, match="truncated"):
        parse_heart_rate_measurement(payload)


def test_polar_broadcast_golden_vectors() -> None:
    direct = parse_polar_hr_manufacturer_data(bytes.fromhex("2b 0b b6 ac"))
    assert direct is not None
    assert direct.heart_rate_bpm == 172
    assert direct.fast_average_hr_bpm == 182
    assert direct.frame_counter == 2
    assert direct.sensor_contact is True
    assert direct.battery_ok is False

    # GPB length=8 followed by the official SAGRFC23 HR example.
    after_gpb = parse_polar_hr_manufacturer_data(
        bytes.fromhex("72 08 97 c9 c3 00 00 00 00 00 7a 01 03 33 00 00")
    )
    assert after_gpb is not None
    # The upstream fixture only asserts presence; its trailing HR payload is 0.
    assert after_gpb.fast_average_hr_bpm == 0
    assert after_gpb.heart_rate_bpm == 0


def test_polar_broadcast_rejects_truncated_gpb() -> None:
    with pytest.raises(ValueError, match="truncated"):
        parse_polar_hr_manufacturer_data(bytes.fromhex("40"))


@pytest.mark.parametrize(
    "payload, message",
    [
        (bytes.fromhex("00 00"), "header"),
        (bytes.fromhex("00 0000000000000000 00 0102"), "ECG"),
        (bytes.fromhex("02 0000000000000000 01 0102030405"), "ACC"),
        (bytes.fromhex("07 0000000000000000 00 010203"), "measurement type"),
        (bytes.fromhex("02 0000000000000000 7f 010203"), "frame type"),
    ],
)
def test_pmd_rejects_truncated_and_unknown_frames(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_pmd_frame(payload)


def test_pmd_golden_vectors_decode_signed_units_and_endianness() -> None:
    transport = PolarBleakTransport()
    ecg_packets = []
    acc_packets = []
    transport._ecg_callback = ecg_packets.append
    transport._acc_callback = acc_packets.append
    transport._on_pmd_data(None, bytearray.fromhex(
        "00 0100000000000000 00 ffffff 000000 010000"
    ))
    transport._on_pmd_data(None, bytearray.fromhex(
        "02 0200000000000000 01 fffffeff 00000100 0080ff7f"
    ))
    assert ecg_packets[0].samples_uv == (-1, 0, 1)
    assert acc_packets[0].samples_mg == ((-1, -2, 0), (1, -32768, 32767))
