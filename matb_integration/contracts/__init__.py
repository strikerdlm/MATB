"""Versioned scientific contracts shared by MATB product components.

The public imports in this module are the stable Python boundary. Optional
runtime, console, physiology, and simulation components may consume these
records without importing one another.
"""

from .components import ComponentManifestV1, ComponentRegistry
from .events import ScientificEventV3, TimingObservationV1
from .experiments import (
    MAX_EXPERIMENT_BODY_BYTES,
    MAX_EXPERIMENT_COMPONENTS,
    MAX_EXPERIMENT_DURATION_NS,
    MAX_EXPERIMENT_TIMELINE_EVENTS,
    ExperimentSpecV1,
    TimelineEventV1,
)

__all__ = [
    "ComponentManifestV1",
    "ComponentRegistry",
    "ExperimentSpecV1",
    "MAX_EXPERIMENT_BODY_BYTES",
    "MAX_EXPERIMENT_COMPONENTS",
    "MAX_EXPERIMENT_DURATION_NS",
    "MAX_EXPERIMENT_TIMELINE_EVENTS",
    "ScientificEventV3",
    "TimelineEventV1",
    "TimingObservationV1",
]
