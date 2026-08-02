from __future__ import annotations

from dataclasses import dataclass

import pytest

from matb_integration.suas.domain.enums import AircraftMode, WorkloadProfile
from matb_integration.suas.domain.geometry import PointMM, PolygonMM, distance_mm, heading_mdeg
from matb_integration.suas.domain.serialization import canonical_data, canonical_json, canonical_sha256


def test_geometry_uses_integer_millimetres_and_inclusive_boundary() -> None:
    square = PolygonMM((PointMM(0, 0), PointMM(10_000, 0),
                        PointMM(10_000, 10_000), PointMM(0, 10_000)))
    assert square.contains(PointMM(5_000, 5_000))
    assert square.contains(PointMM(0, 5_000))
    assert not square.contains(PointMM(10_001, 5_000))
    assert distance_mm(PointMM(0, 0), PointMM(3_000, 4_000)) == 5_000
    assert [heading_mdeg(dx, dy) for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0))] == [
        0, 90_000, 180_000, 270_000,
    ]


def test_polygon_rejects_self_intersection() -> None:
    bow_tie = (PointMM(0, 0), PointMM(10_000, 10_000),
               PointMM(0, 10_000), PointMM(10_000, 0))
    with pytest.raises(ValueError, match="self-intersects"):
        PolygonMM(bow_tie)


def test_heading_rejects_zero_vector() -> None:
    with pytest.raises(ValueError, match="zero vector"):
        heading_mdeg(0, 0)


def test_canonical_hash_is_independent_of_mapping_insertion_order() -> None:
    left = {"mode": AircraftMode.SEARCH, "profile": WorkloadProfile.LOW, "xy": [1, 2]}
    right = {"xy": [1, 2], "profile": WorkloadProfile.LOW, "mode": AircraftMode.SEARCH}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_sha256(left) == canonical_sha256(right)


def test_canonical_data_sorts_sets_and_converts_dataclasses() -> None:
    @dataclass(frozen=True)
    class Payload:
        point: PointMM
        values: set[str]

    assert canonical_data(Payload(PointMM(2, 3), {"z", "a"})) == {
        "point": {"x_mm": 2, "y_mm": 3},
        "values": ["a", "z"],
    }


def test_canonical_data_rejects_unsupported_values() -> None:
    with pytest.raises(TypeError, match="unsupported"):
        canonical_data(object())
