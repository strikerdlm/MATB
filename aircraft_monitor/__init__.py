"""
UAV & Fighter Aircraft Monitoring System.

A real-time, visually stunning terminal-based monitoring system
for UAV and Fighter Aircraft operations with realistic mission challenges.
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "Diego L Malpica"

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aircraft_monitor.models import FighterAircraft, UAV
    from aircraft_monitor.visualization.dashboard import MonitoringDashboard


def __getattr__(name: str) -> object:
    """Lazy attribute access to keep imports lightweight and avoid cycles."""
    if name in {"UAV", "FighterAircraft"}:
        from aircraft_monitor import models as _models

        return getattr(_models, name)
    if name == "MonitoringDashboard":
        from aircraft_monitor.visualization.dashboard import MonitoringDashboard as _MonitoringDashboard

        return _MonitoringDashboard
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["UAV", "FighterAircraft", "MonitoringDashboard", "__version__"]
