from __future__ import annotations

import pytest

from matb_integration.physiology.hrs import (
    HeartRatePacketError,
    parse_heart_rate_measurement,
)


def test_parser_decodes_uint8_hr_and_native_rr_ticks() -> None:
    packet = parse_heart_rate_measurement(bytes([0x10, 60, 0x00, 0x04]))

    assert packet.heart_rate_bpm == 60
    assert len(packet.rr_values) == 1
    assert packet.rr_values[0].ticks_1024 == 1024
    assert packet.rr_values[0].milliseconds == pytest.approx(1000.0)


def test_parser_decodes_uint16_contact_energy_and_every_rr_value() -> None:
    # uint16 HR, contact supported/detected, energy present, RR present.
    payload = bytes(
        [
            0x1F,
            0x2C,
            0x01,  # 300 bpm
            0x34,
            0x12,  # 4660 kJ
            0x00,
            0x02,  # 512 ticks
            0x00,
            0x04,  # 1024 ticks
        ]
    )

    packet = parse_heart_rate_measurement(payload)

    assert packet.heart_rate_bpm == 300
    assert packet.sensor_contact_supported is True
    assert packet.sensor_contact_detected is True
    assert packet.energy_expended_kj == 0x1234
    assert [rr.ticks_1024 for rr in packet.rr_values] == [512, 1024]


def test_parser_reports_supported_contact_without_skin_contact() -> None:
    packet = parse_heart_rate_measurement(bytes([0x04, 72]))

    assert packet.sensor_contact_supported is True
    assert packet.sensor_contact_detected is False
    assert packet.rr_values == ()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "empty_heart_rate_packet"),
        (bytes([0x00]), "truncated_heart_rate"),
        (bytes([0x01, 0x2C]), "truncated_heart_rate"),
        (bytes([0x08, 70, 0x01]), "truncated_energy_expended"),
        (bytes([0x10, 70, 0x01]), "truncated_rr_value"),
    ],
)
def test_parser_rejects_truncated_payloads(payload: bytes, code: str) -> None:
    with pytest.raises(HeartRatePacketError) as exc_info:
        parse_heart_rate_measurement(payload)

    assert exc_info.value.code == code
