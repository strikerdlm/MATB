"""Integer-only scanline search-route generation."""

from __future__ import annotations

from fractions import Fraction

from matb_integration.suas.domain.geometry import PointMM, PolygonMM
from matb_integration.suas.domain.models import Route


def lawnmower_route(sector: PolygonMM, spacing_mm: int) -> Route:
    """Return alternating horizontal scan lines wholly represented by sector points.

    Rows start at the lower bound and intentionally exclude the upper bound;
    that convention avoids duplicating a polygon boundary row and gives the
    reference 4-by-2 route for a 2,000 m-high rectangle at 500 m spacing.
    """

    if not isinstance(sector, PolygonMM):
        raise TypeError("sector must be a PolygonMM")
    if isinstance(spacing_mm, bool) or not isinstance(spacing_mm, int) or spacing_mm <= 0:
        raise ValueError("spacing_mm must be a positive integer")
    _, minimum_y, _, maximum_y = sector.bounds
    waypoints: list[PointMM] = []
    left_to_right = True
    for y_mm in range(minimum_y, maximum_y, spacing_mm):
        intersections = _scanline_intersections(sector, y_mm)
        for left, right in zip(intersections[::2], intersections[1::2]):
            start_x = _ceil_fraction(left)
            end_x = right.numerator // right.denominator
            if start_x > end_x:
                continue
            endpoints = (PointMM(start_x, y_mm), PointMM(end_x, y_mm))
            if not all(sector.contains(point) for point in endpoints):
                continue
            ordered = endpoints if left_to_right else endpoints[::-1]
            for point in ordered:
                if not waypoints or point != waypoints[-1]:
                    waypoints.append(point)
            left_to_right = not left_to_right
    if len(waypoints) < 2:
        raise ValueError("spacing_mm yields fewer than two route points")
    return Route(tuple(waypoints))


def _scanline_intersections(polygon: PolygonMM, y_mm: int) -> list[Fraction]:
    """Return exact x crossings using a half-open edge rule."""

    crossings: list[Fraction] = []
    vertices = polygon.vertices
    for index, start in enumerate(vertices):
        end = vertices[(index + 1) % len(vertices)]
        if start.y_mm == end.y_mm:
            continue
        lower, upper = sorted((start.y_mm, end.y_mm))
        if not lower <= y_mm < upper:
            continue
        crossings.append(Fraction(
            start.x_mm * (end.y_mm - start.y_mm) + (y_mm - start.y_mm) * (end.x_mm - start.x_mm),
            end.y_mm - start.y_mm,
        ))
    return sorted(crossings)


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)
