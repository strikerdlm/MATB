"""Deterministic sUAS test builders; never imported by product code."""

from matb_integration.suas.domain.geometry import PointMM, PolygonMM


def rectangle(minimum_x_mm: int, minimum_y_mm: int, maximum_x_mm: int, maximum_y_mm: int) -> PolygonMM:
    """Return an axis-aligned polygon with integer millimetre vertices."""

    return PolygonMM((
        PointMM(minimum_x_mm, minimum_y_mm),
        PointMM(maximum_x_mm, minimum_y_mm),
        PointMM(maximum_x_mm, maximum_y_mm),
        PointMM(minimum_x_mm, maximum_y_mm),
    ))
