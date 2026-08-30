# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import json
import platform
from collections import namedtuple
from csv import DictWriter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, perf_counter_ns
from typing import IO, Any

from core.constants import PATHS, REPLAY_MODE
from core.utils import find_the_first_available_session_number

_logger: Logger | None = None
EVENT_SCHEMA_VERSION = "1.0"
TIMING_QC_SCHEMA_VERSION = "1.0"


def get_logger() -> Logger:
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger


def set_logger(lg: Logger | None) -> None:
    global _logger
    _logger = lg


class Logger:
    def __init__(self) -> None:
        self.datetime: datetime = datetime.now()
        self.fields_list: list[str] = ["logtime", "scenario_time", "type", "module", "address", "value"]
        self.slot: type = namedtuple("Row", self.fields_list)
        self.maxfloats: int = 6  # Time logged at microsecond precision
        self.session_id: int | None = None
        self.lsl: Any = None

        self.session_id = find_the_first_available_session_number()
        self.mode: str = "w"

        self.scenario_time: float = 0  # Updated by the scheduler class

        self.file: IO[str] | None = None
        self.events_file: IO[str] | None = None
        self.writer: DictWriter | None = None
        self.queue: list[Any] = list()
        self.metadata_queue: list[dict[str, Any]] = list()
        self.event_sequence: int = 0
        self._last_update_monotonic_ns: int | None = None
        self._last_scenario_time: float | None = None
        self._update_intervals_ms: list[float] = []
        self._scenario_deltas_ms: list[float] = []
        self._event_lateness_ms: list[float] = []
        self._logger_write_latency_ms: list[float] = []
        self._lsl_write_latency_ms: list[float] = []
        self._started_monotonic_ns: int = perf_counter_ns()

        if not REPLAY_MODE:
            self.path: Path = PATHS["SESSIONS"].joinpath(
                self.datetime.strftime("%Y-%m-%d"), f"{self.session_id}_{self.datetime.strftime('%y%m%d_%H%M%S')}.csv"
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.events_path: Path = self.path.with_suffix(".events.jsonl")
            self.timing_qc_path: Path = self.path.with_suffix(".timing_qc.json")
            self.open()

    # TODO: see if we can/should merge record_* methods into one
    def record_event(self, event: Any) -> None:
        if len(event.command) == 1:
            adress: str = "self"
            value: str = event.command[0]
        elif len(event.command) == 2:
            adress = event.command[0]
            value = event.command[1]
        slot: list[Any] = [perf_counter(), self.scenario_time, "event", event.plugin, adress, value]
        self.write_single_slot(slot, metadata={
            "scheduled_scenario_time_s": event.time_sec,
            "scenario_line": event.line,
        })

    def record_input(self, module: str, key: str, state: str) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "input", module, key, state]
        self.write_single_slot(slot)

    def record_aoi(self, container: Any, name: str) -> None:
        plugin: str = name.split("_")[0]
        widget: str = "_".join(name.split("_")[1:])
        slot: list[Any] = [perf_counter(), self.scenario_time, "aoi", plugin, widget, container.get_x1y1x2y2()]
        self.write_single_slot(slot)

    def record_state(self, graph_name: str, attribute: str, value: Any) -> None:
        module: str = graph_name.split("_")[0]
        graph_name = "_".join(graph_name.split("_")[1:])
        address: str = f"{graph_name}, {attribute}"
        slot: list[Any] = [perf_counter(), self.scenario_time, "state", module, address, value]
        self.write_single_slot(slot)

    def record_parameter(self, plugin: str, address: str, value: Any) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "parameter", plugin, address, value]
        self.write_single_slot(slot)

    def log_performance(self, module: str, metric: str, value: Any) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "performance", module, metric, value]
        self.write_single_slot(slot)

    def record_a_pseudorandom_value(self, module: str, seed: int, output: Any) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "seed_value", module, "", seed]
        self.write_single_slot(slot)
        slot = [perf_counter(), self.scenario_time, "seed_output", module, "", output]
        self.write_single_slot(slot)

    def log_manual_entry(self, entry: str, key: str = "manual") -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, key, "", "", entry]
        self.write_single_slot(slot)
        # The scheduler emits this terminal marker before the process exits.  Write
        # (but do not close) the QC sidecar here so an ordinary completed session
        # always has timing evidence even when GUI teardown bypasses __exit__.
        if entry == "end":
            self.write_timing_qc()
            if self.file is not None and not self.file.closed:
                self.file.flush()
            events_file = getattr(self, "events_file", None)
            if events_file is not None and not events_file.closed:
                events_file.flush()

    def __enter__(self) -> Logger:
        self.open()
        return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        self.close()

    def open(self) -> None:
        create_header: bool = not (self.path.exists() and self.mode == "a")
        self.file = open(str(self.path), self.mode, newline="", encoding="utf-8")
        self.writer = DictWriter(self.file, fieldnames=self.fields_list)
        if create_header:
            self.writer.writeheader()
        events_path = getattr(self, "events_path", None)
        if events_path is not None and (self.events_file is None or self.events_file.closed):
            events_mode = "a" if self.mode == "a" else "w"
            self.events_file = open(str(events_path), events_mode, encoding="utf-8")

    def close(self) -> None:
        self.write_timing_qc()
        if self.file is not None and not self.file.closed:
            self.file.flush()
            self.file.close()
        if self.events_file is not None and not self.events_file.closed:
            self.events_file.flush()
            self.events_file.close()

    def add_row_to_queue(self, row: Any) -> None:
        self.queue.append(row)

    def empty_queue(self) -> None:
        self.queue = list()
        self.metadata_queue = list()

    def round_row(self, row: Any) -> Any:
        new_list: list[Any] = list()
        for col in row:
            new_value: Any = round(col, self.maxfloats) if isinstance(col, (float, int)) else col
            new_list.append(new_value)
        return self.slot(*new_list)

    def write_row_queue(self, change_dict: dict[str, Any] | None = None) -> None:
        if not REPLAY_MODE:
            if len(self.queue) == 0:
                print(_("Warning, queue is empty"))
            else:
                for index, this_row in enumerate(self.queue):
                    row_dict: dict[str, Any] = self.round_row(this_row)._asdict()
                    if change_dict is not None:
                        for k, v in change_dict.items():
                            row_dict[k] = v
                    self.writer.writerow(row_dict)
                    metadata_queue = getattr(self, "metadata_queue", [])
                    metadata = metadata_queue[index] if index < len(metadata_queue) else {}
                    if self.lsl is not None:
                        lsl_started = perf_counter_ns()
                        lsl_result = self.lsl.push(";".join([str(r) for r in row_dict.values()]))
                        lsl_finished = perf_counter_ns()
                        self._lsl_write_latency_ms = getattr(self, "_lsl_write_latency_ms", [])
                        self._lsl_write_latency_ms.append((lsl_finished - lsl_started) / 1_000_000)
                        if isinstance(lsl_result, dict):
                            metadata["lsl_time_s"] = lsl_result.get("lsl_time_s")
                    self.write_jsonl_row(row_dict, metadata)
                self.empty_queue()

    def write_single_slot(self, values: list[Any], metadata: dict[str, Any] | None = None) -> None:
        row: Any = self.slot(*values)
        self.add_row_to_queue(row)
        if not hasattr(self, "metadata_queue"):
            self.metadata_queue = []
        self.metadata_queue.append(dict(metadata or {}))
        self.write_row_queue()

    def write_jsonl_row(self, row_dict: dict[str, Any], metadata: dict[str, Any] | None = None) -> None:
        """Write an additive, versioned event record without changing legacy CSV."""
        events_file = getattr(self, "events_file", None)
        if events_file is None:
            return
        write_ns = perf_counter_ns()
        recorded_ns = int(float(row_dict["logtime"]) * 1_000_000_000)
        latency_ms = max(0.0, (write_ns - recorded_ns) / 1_000_000)
        self._logger_write_latency_ms = getattr(self, "_logger_write_latency_ms", [])
        self._logger_write_latency_ms.append(latency_ms)
        self.event_sequence = getattr(self, "event_sequence", 0) + 1
        payload: dict[str, Any] = {
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "sequence": self.event_sequence,
            "session_id": self.session_id,
            "recorded_monotonic_ns": recorded_ns,
            "logger_write_monotonic_ns": write_ns,
            "clock_domain": "python.perf_counter",
            "scenario_time_s": row_dict["scenario_time"],
            "record_type": row_dict["type"],
            "module": row_dict["module"],
            "address": row_dict["address"],
            "value": row_dict["value"],
        }
        payload.update(metadata or {})
        scheduled = payload.get("scheduled_scenario_time_s")
        if isinstance(scheduled, (int, float)):
            lateness = max(0.0, (float(row_dict["scenario_time"]) - float(scheduled)) * 1000)
            payload["dispatch_lateness_ms"] = round(lateness, 6)
            self._event_lateness_ms = getattr(self, "_event_lateness_ms", [])
            self._event_lateness_ms.append(lateness)
        events_file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        events_file.flush()

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = round((len(ordered) - 1) * percentile)
        return round(ordered[index], 6)

    def timing_qc_summary(self) -> dict[str, Any]:
        intervals = getattr(self, "_update_intervals_ms", [])
        scenario_deltas = getattr(self, "_scenario_deltas_ms", [])
        lateness = getattr(self, "_event_lateness_ms", [])
        logger_latency = getattr(self, "_logger_write_latency_ms", [])
        lsl_latency = getattr(self, "_lsl_write_latency_ms", [])

        def stats(values: list[float]) -> dict[str, Any]:
            return {
                "n": len(values),
                "median_ms": self._percentile(values, 0.50),
                "p95_ms": self._percentile(values, 0.95),
                "p99_ms": self._percentile(values, 0.99),
                "max_ms": round(max(values), 6) if values else None,
            }

        return {
            "timing_qc_schema_version": TIMING_QC_SCHEMA_VERSION,
            "session_id": self.session_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "software_clock": "python.perf_counter_ns",
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "update_interval": stats(intervals),
            "scenario_delta": stats(scenario_deltas),
            "long_update_stalls_over_100ms": sum(1 for value in intervals if value > 100),
            "event_dispatch_lateness": stats(lateness),
            "logger_write_latency": stats(logger_latency),
            "lsl_push_call_latency": stats(lsl_latency),
            "physical_onset": {
                "available": False,
                "reason": "requires session-specific photodiode or audio-loopback measurement",
            },
            "interpretation": "software timing QC only; not evidence of physical stimulus-onset latency",
        }

    def write_timing_qc(self) -> None:
        path = getattr(self, "timing_qc_path", None)
        if path is None:
            return
        path.write_text(
            json.dumps(self.timing_qc_summary(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def set_totaltime(self, totaltime: float) -> None:
        self.totaltime: float = totaltime

    def set_scenario_time(self, scenario_time: float) -> None:
        now_ns = perf_counter_ns()
        last_ns = getattr(self, "_last_update_monotonic_ns", None)
        last_scenario_time = getattr(self, "_last_scenario_time", None)
        if last_ns is not None:
            self._update_intervals_ms = getattr(self, "_update_intervals_ms", [])
            self._update_intervals_ms.append((now_ns - last_ns) / 1_000_000)
        if last_scenario_time is not None:
            self._scenario_deltas_ms = getattr(self, "_scenario_deltas_ms", [])
            self._scenario_deltas_ms.append(max(0.0, (scenario_time - last_scenario_time) * 1000))
        self._last_update_monotonic_ns = now_ns
        self._last_scenario_time = scenario_time
        self.scenario_time = scenario_time
