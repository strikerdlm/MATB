"""Small physics helpers for unit-consistent simulation values.

This module intentionally uses lightweight approximations (ISA-like) to keep
speed conversions self-contained, deterministic, and dependency-free.
"""

from __future__ import annotations

import math


def _isa_temperature_k(altitude_m: float) -> float:
    """Return ISA temperature (K) at altitude.

    Uses a simple 2-layer model:
    - Troposphere (0..11km): linear lapse rate -6.5 K/km
    - Lower stratosphere (11km..20km): isothermal

    Args:
        altitude_m: Geopotential altitude in meters (must be finite).

    Returns:
        Temperature in kelvin.

    Raises:
        ValueError: If altitude_m is not finite.
    """
    if not math.isfinite(altitude_m):
        raise ValueError(f"altitude_m must be finite, got {altitude_m!r}")

    if altitude_m < 0.0:
        altitude_m = 0.0

    # ISA constants
    t0_k = 288.15
    lapse_k_per_m = -0.0065
    tropopause_m = 11_000.0

    if altitude_m <= tropopause_m:
        return t0_k + (lapse_k_per_m * altitude_m)

    # Isothermal layer (11-20 km) at tropopause temperature
    return t0_k + (lapse_k_per_m * tropopause_m)


def speed_of_sound_knots(altitude_ft: float) -> float:
    """Compute speed of sound at altitude, in knots.

    Args:
        altitude_ft: Altitude in feet.

    Returns:
        Speed of sound in knots.

    Raises:
        ValueError: If altitude_ft is not finite.
    """
    if not math.isfinite(altitude_ft):
        raise ValueError(f"altitude_ft must be finite, got {altitude_ft!r}")

    altitude_m = max(0.0, altitude_ft) * 0.3048
    temp_k = _isa_temperature_k(altitude_m)

    # a = sqrt(gamma * R * T)
    gamma = 1.4
    r_specific = 287.05287  # J/(kg·K)
    a_m_s = math.sqrt(gamma * r_specific * temp_k)

    # m/s -> knots (1 knot = 0.514444 m/s)
    return a_m_s / 0.514444


def mach_to_knots(mach: float, altitude_ft: float) -> int:
    """Convert Mach number to approximate true airspeed in knots.

    Args:
        mach: Mach number (>= 0).
        altitude_ft: Altitude in feet.

    Returns:
        Speed in knots (rounded to nearest int).

    Raises:
        ValueError: If mach or altitude_ft are not finite, or mach is negative.
    """
    if not math.isfinite(mach):
        raise ValueError(f"mach must be finite, got {mach!r}")
    if mach < 0.0:
        raise ValueError(f"mach must be non-negative, got {mach!r}")

    a_knots = speed_of_sound_knots(altitude_ft)
    knots = mach * a_knots

    # Bound to non-negative integer.
    if knots <= 0.0:
        return 0
    return int(round(knots))

