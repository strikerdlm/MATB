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


def envelope(command_id: str, *, expected: int, command):
    """Build a public typed command envelope for runtime tests."""

    from matb_integration.suas.domain.commands import CommandEnvelope

    return CommandEnvelope(command_id, expected, command)


def place_pair(world, separation_mm: int) -> None:
    """Position the first two lexical aircraft on a horizontal exact separation."""

    first, second = sorted(world.aircraft)[:2]
    world.aircraft[first].position = PointMM(0, 0)
    world.aircraft[second].position = PointMM(separation_mm, 0)


def event_kinds(events) -> list[str]:
    return [event.kind.value for event in events]
