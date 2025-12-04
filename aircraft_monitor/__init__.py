"""
UAV & Fighter Aircraft Monitoring System.

A real-time, visually stunning terminal-based monitoring system
for UAV and Fighter Aircraft operations with realistic mission challenges.
"""

__version__ = "1.0.0"
__author__ = "Diego L Malpica"

from aircraft_monitor.models import UAV, FighterAircraft
from aircraft_monitor.visualization.dashboard import MonitoringDashboard

__all__ = ["UAV", "FighterAircraft", "MonitoringDashboard", "__version__"]
