"""Integer-only planar geometry for authoritative simulation state."""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt


@dataclass(frozen=True, slots=True)
class PointMM:
    """A Cartesian point expressed in integer millimetres."""

    x_mm: int
    y_mm: int

    def __post_init__(self) -> None:
        if isinstance(self.x_mm, bool) or isinstance(self.y_mm, bool):
            raise TypeError("PointMM coordinates must be integers")
        if not isinstance(self.x_mm, int) or not isinstance(self.y_mm, int):
            raise TypeError("PointMM coordinates must be integers")


@dataclass(frozen=True, slots=True)
class PolygonMM:
    """A simple non-degenerate polygon with inclusive containment."""

    vertices: tuple[PointMM, ...]

    def __post_init__(self) -> None:
        vertices = tuple(self.vertices)
        object.__setattr__(self, "vertices", vertices)
        if len(vertices) < 3:
            raise ValueError("polygon requires at least three vertices")
        if any(not isinstance(vertex, PointMM) for vertex in vertices):
            raise TypeError("polygon vertices must be PointMM instances")
        if _self_intersects(vertices):
            raise ValueError("polygon self-intersects")
        if _signed_area2(vertices) == 0:
            raise ValueError("polygon has zero signed area")

    @property
    def signed_area2(self) -> int:
        """Twice the signed area, preserving exact integer geometry."""

        return _signed_area2(self.vertices)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Return ``(minimum_x, minimum_y, maximum_x, maximum_y)``."""

        return (
            min(point.x_mm for point in self.vertices),
            min(point.y_mm for point in self.vertices),
            max(point.x_mm for point in self.vertices),
            max(point.y_mm for point in self.vertices),
        )

    def contains(self, point: PointMM) -> bool:
        """Return whether *point* lies inside or on this polygon's boundary."""

        if not isinstance(point, PointMM):
            raise TypeError("point must be a PointMM")
        inside = False
        vertices = self.vertices
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if _point_on_segment(point, start, end):
                return True
            if (start.y_mm > point.y_mm) != (end.y_mm > point.y_mm):
                cross_x = ((end.x_mm - start.x_mm) * (point.y_mm - start.y_mm)
                           - (point.x_mm - start.x_mm) * (end.y_mm - start.y_mm))
                if (end.y_mm > start.y_mm and cross_x > 0) or (
                    end.y_mm < start.y_mm and cross_x < 0
                ):
                    inside = not inside
        return inside


def distance_mm(start: PointMM, end: PointMM) -> int:
    """Return the integer-floor Euclidean distance in millimetres."""

    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    return isqrt(dx * dx + dy * dy)


# atan(2**-i), in microdegrees, rounded once at source-generation time.
# Keeping the table in source avoids platform trigonometry and float variance.
_CORDIC_ATAN_UDEG = (
    45_000_000, 26_565_051, 14_036_243, 7_125_016, 3_576_334, 1_789_911,
    895_174, 447_614, 223_811, 111_906, 55_953, 27_976, 13_988, 6_994,
    3_497, 1_749, 874, 437, 219, 109, 55, 27, 14, 7, 3, 2, 1,
)
_FULL_TURN_UDEG = 360_000_000
_HALF_TURN_UDEG = 180_000_000
_QUARTER_TURN_UDEG = 90_000_000


def heading_mdeg(dx: int, dy: int) -> int:
    """Return the north-clockwise heading, rounded half-even to millidegrees.

    This intentionally uses CORDIC integer vectoring rather than ``atan2`` so
    replay results do not depend on a platform math library.
    """

    if isinstance(dx, bool) or isinstance(dy, bool) or not isinstance(dx, int) or not isinstance(dy, int):
        raise TypeError("heading vector components must be integers")
    if dx == 0 and dy == 0:
        raise ValueError("heading is undefined for a zero vector")
    if dx == 0:
        angle_udeg = _QUARTER_TURN_UDEG if dy > 0 else -_QUARTER_TURN_UDEG
    elif dx > 0:
        angle_udeg = _cordic_angle_udeq(dx, dy)
    else:
        angle_udeg = _cordic_angle_udeq(-dx, -dy)
        angle_udeg += _HALF_TURN_UDEG if dy >= 0 else -_HALF_TURN_UDEG
    return _round_half_even(((_QUARTER_TURN_UDEG - angle_udeg) % _FULL_TURN_UDEG), 1_000) % 360_000


def _cordic_angle_udeq(x: int, y: int) -> int:
    """Return the x-axis counter-clockwise angle for a vector whose x is > 0."""

    scaled_x = x << 40
    scaled_y = y << 40
    angle_udeq = 0
    for shift, atan_udeq in enumerate(_CORDIC_ATAN_UDEG):
        if scaled_y > 0:
            scaled_x, scaled_y = scaled_x + (scaled_y >> shift), scaled_y - (scaled_x >> shift)
            angle_udeq += atan_udeq
        elif scaled_y < 0:
            scaled_x, scaled_y = scaled_x - (scaled_y >> shift), scaled_y + (scaled_x >> shift)
            angle_udeq -= atan_udeq
    return angle_udeq


def _round_half_even(value: int, divisor: int) -> int:
    quotient, remainder = divmod(value, divisor)
    if remainder > divisor // 2 or (remainder == divisor // 2 and quotient % 2):
        return quotient + 1
    return quotient


def _cross(origin: PointMM, first: PointMM, second: PointMM) -> int:
    return ((first.x_mm - origin.x_mm) * (second.y_mm - origin.y_mm)
            - (first.y_mm - origin.y_mm) * (second.x_mm - origin.x_mm))


def _point_on_segment(point: PointMM, start: PointMM, end: PointMM) -> bool:
    return (
        _cross(start, end, point) == 0
        and min(start.x_mm, end.x_mm) <= point.x_mm <= max(start.x_mm, end.x_mm)
        and min(start.y_mm, end.y_mm) <= point.y_mm <= max(start.y_mm, end.y_mm)
    )


def _segments_intersect(first_start: PointMM, first_end: PointMM, second_start: PointMM, second_end: PointMM) -> bool:
    first_a = _cross(first_start, first_end, second_start)
    first_b = _cross(first_start, first_end, second_end)
    second_a = _cross(second_start, second_end, first_start)
    second_b = _cross(second_start, second_end, first_end)
    if first_a == 0 and _point_on_segment(second_start, first_start, first_end):
        return True
    if first_b == 0 and _point_on_segment(second_end, first_start, first_end):
        return True
    if second_a == 0 and _point_on_segment(first_start, second_start, second_end):
        return True
    if second_b == 0 and _point_on_segment(first_end, second_start, second_end):
        return True
    return (first_a > 0) != (first_b > 0) and (second_a > 0) != (second_b > 0)


def _self_intersects(vertices: tuple[PointMM, ...]) -> bool:
    count = len(vertices)
    for first in range(count):
        first_end = (first + 1) % count
        for second in range(first + 1, count):
            second_end = (second + 1) % count
            if first == second or first_end == second or second_end == first:
                continue
            if _segments_intersect(vertices[first], vertices[first_end], vertices[second], vertices[second_end]):
                return True
    return False


def _signed_area2(vertices: tuple[PointMM, ...]) -> int:
    return sum(
        point.x_mm * vertices[(index + 1) % len(vertices)].y_mm
        - point.y_mm * vertices[(index + 1) % len(vertices)].x_mm
        for index, point in enumerate(vertices)
    )
