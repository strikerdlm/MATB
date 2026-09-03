"""Optional Polar H10 acquisition and conservative HRV descriptors.

The package has no import-time Bluetooth or Arrow dependency so the MATB core
remains usable when the optional physiology component is not installed.
"""

from .analysis import HRV_ALGORITHM_VERSIONS, analyze_rr_window, workload_response
from .contracts import (
    PolarArtifactManifestV1,
    PolarCaptureEventV1,
    PolarCaptureV1,
    PolarDeviceCapabilitiesV1,
)
from .hrs import HeartRateMeasurement, parse_heart_rate_measurement

__all__ = [
    "HRV_ALGORITHM_VERSIONS",
    "HeartRateMeasurement",
    "PolarArtifactManifestV1",
    "PolarCaptureEventV1",
    "PolarCaptureV1",
    "PolarDeviceCapabilitiesV1",
    "analyze_rr_window",
    "parse_heart_rate_measurement",
    "workload_response",
]
