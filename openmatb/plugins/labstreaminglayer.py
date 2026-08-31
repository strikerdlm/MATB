# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from time import perf_counter_ns
from typing import Any, Callable

from core import validation
from core.recordsink import SinkCloseTimeout
from plugins import Instructions

try:
    import pylsl
except (ImportError, RuntimeError):
    pylsl = None


class Labstreaminglayer(Instructions):
    def __init__(self) -> None:
        super().__init__()

        self.validation_dict: dict[str, Callable[..., Any]] = {
            "marker": validation.is_string,
            "streamsession": validation.is_boolean,
            "pauseatstart": validation.is_boolean,
            "state": validation.is_string,
        }

        self.parameters.update({"marker": "", "streamsession": False, "pauseatstart": False})

        self.stream_info: Any | None = None
        self.stream_outlet: Any | None = None
        self.stop_on_end: bool = False
        self._marker_queue: list[str] = []

        self.lsl_wait_msg: str = _("Please enable the OpenMATB stream into your LabRecorder.")

    def start(self) -> None:
        # If we get there it's because the plugin is used.
        # If pylsl is not available this part should fail.
        # Create a LSL marker outlet.
        super().start()
        self.stream_info = pylsl.StreamInfo(
            "OpenMATB",
            type="Markers",
            channel_count=1,
            nominal_srate=0,
            channel_format="string",
            source_id=f"openmatb-{self.logger.scientific_session_id}",
        )
        self.stream_outlet = pylsl.StreamOutlet(self.stream_info)

        if self.parameters["pauseatstart"] is True:
            self.slides = [self.get_msg_slide_content(self.lsl_wait_msg)]

    def update(self, dt: float) -> None:
        super().update(dt)

        if self.parameters["streamsession"] is True and self.logger.lsl is None:
            self.logger.lsl = self
        elif self.parameters["streamsession"] is False and self.logger.lsl is not None:
            self.logger.lsl = None

        direct_marker = str(self.parameters.get("marker") or "")
        if direct_marker:
            self._marker_queue = getattr(self, "_marker_queue", [])
            self._marker_queue.append(direct_marker)
            self.parameters["marker"] = ""
        self._flush_marker_queue()

    def _flush_marker_queue(self) -> None:
        """Submit every explicit marker before an update or outlet shutdown."""
        direct_marker = str(self.parameters.get("marker") or "")
        if direct_marker:
            self._marker_queue = getattr(self, "_marker_queue", [])
            self._marker_queue.append(direct_marker)
            self.parameters["marker"] = ""
        queued = list(getattr(self, "_marker_queue", []))
        self._marker_queue = []
        for marker in queued:
            # Explicit markers share the same bounded asynchronous path and QC
            # sidecar as automatic runtime records. A queue is essential because
            # the scheduler can dispatch multiple same-tick parameter events.
            self.logger.submit_lsl_marker(self, marker)

    def set_parameter(self, keys_str: str, value: Any) -> dict[str, Any]:
        if keys_str == "marker" and str(value):
            self._marker_queue = getattr(self, "_marker_queue", [])
            self._marker_queue.append(str(value))
            # Keep the legacy scalar empty so update() cannot duplicate a queued
            # marker while preserving AbstractPlugin's parameter return contract.
            return super().set_parameter(keys_str, "")
        return super().set_parameter(keys_str, value)

    def push(self, message: str) -> dict[str, float | int] | None:
        if self.stream_outlet is None:
            return None
        started_ns = perf_counter_ns()
        lsl_time = pylsl.local_clock()
        self.stream_outlet.push_sample([message], lsl_time)
        finished_ns = perf_counter_ns()
        return {
            "lsl_time_s": lsl_time,
            "push_started_monotonic_ns": started_ns,
            "push_finished_monotonic_ns": finished_ns,
        }

    #        print(message)

    def stop(self) -> None:
        # Scheduler dispatches events after plugin updates. A marker immediately
        # followed by stop would otherwise remain queued forever and lose its
        # source-event link. Submit it before asking the logger to drain.
        self._flush_marker_queue()
        if not self.logger.close_async_sinks():
            raise SinkCloseTimeout(
                "async markers did not drain before the LSL outlet could be released"
            )
        if self.logger.lsl is self:
            self.logger.lsl = None
        super().stop()
        self.stream_info = None
        self.stream_outlet = None

    def get_msg_slide_content(self, str_msg: str) -> str:
        return f"<title>Lab streaming layer\n{self.lsl_wait_msg}"
