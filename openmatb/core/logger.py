# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from collections import namedtuple
from csv import DictWriter
from datetime import datetime
import json
import math
import os
from pathlib import Path
from time import perf_counter, perf_counter_ns, time_ns
from typing import IO, Any

from core.constants import PATHS, REPLAY_MODE
from core.utils import find_the_first_available_session_number

_logger: Logger | None = None
OPENMATB_EVENT_SCHEMA_VERSION = "openmatb-synchronized-event-v2"


def _sync_directory(path: Path) -> None:
    """Persist a newly created capture-file directory entry on POSIX."""

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(Path(path)), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json_safe(value: Any) -> Any:
    """Normalize non-finite measurements while preserving raw CSV values."""

    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


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
        self.research_recorder: Any = None
        self.event_sequence: int = 0

        self.session_id = find_the_first_available_session_number()
        self.mode: str = "w"

        self.scenario_time: float = 0  # Updated by the scheduler class

        self.file: IO[str] | None = None
        self.writer: DictWriter | None = None
        self.events_file: IO[str] | None = None
        self.events_sequence: int = 0
        self.external_session_id: str | None = os.getenv("OPENMATB_SESSION_ID")
        self.queue: list[Any] = list()

        if not REPLAY_MODE:
            configured_output = os.getenv("OPENMATB_OUTPUT_CSV")
            self.path: Path = (
                Path(configured_output)
                if configured_output
                else PATHS["SESSIONS"].joinpath(
                    self.datetime.strftime("%Y-%m-%d"),
                    f"{self.session_id}_{self.datetime.strftime('%y%m%d_%H%M%S')}.csv",
                )
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
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
        self.write_single_slot(slot)

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

    def record_research_trial(self, trial: dict[str, Any]) -> None:
        """Forward one structured trial without altering the legacy CSV."""
        if self.research_recorder is not None:
            self.research_recorder.record_trial(trial)

    def record_boundary(self, event: str) -> None:
        self._write_synchronized_event(
            {"event": event, "scenario_time": float(self.scenario_time)},
            durable=True,
        )

    def __enter__(self) -> Logger:
        self.open()
        return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        self.close()

    def open(self) -> None:
        path_existed = self.path.exists()
        create_header: bool = not (path_existed and self.mode == "a")
        mode = "x" if os.getenv("OPENMATB_OUTPUT_CSV") and self.mode == "w" else self.mode
        self.file = open(str(self.path), mode, newline="", encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        if not path_existed:
            _sync_directory(self.path.parent)
        self.writer = DictWriter(self.file, fieldnames=self.fields_list)
        if create_header:
            self.writer.writeheader()
            self.file.flush()
        events_path = os.getenv("OPENMATB_EVENTS_JSONL")
        if events_path and self.events_file is None:
            event_destination = Path(events_path)
            event_destination.parent.mkdir(parents=True, exist_ok=True)
            self.events_file = event_destination.open("x", encoding="utf-8", newline="")
            if os.name != "nt":
                os.chmod(event_destination, 0o600)
            _sync_directory(event_destination.parent)

    def close(self) -> None:
        if self.file is not None and not self.file.closed:
            try:
                self._sync_stream(self.file)
            finally:
                self.file.close()
        if self.events_file is not None and not self.events_file.closed:
            try:
                self._sync_stream(self.events_file)
            finally:
                self.events_file.close()

    def add_row_to_queue(self, row: Any) -> None:
        self.queue.append(row)

    def empty_queue(self) -> None:
        self.queue = list()

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
                for this_row in self.queue:
                    row_dict: dict[str, Any] = self.round_row(this_row)._asdict()
                    if change_dict is not None:
                        for k, v in change_dict.items():
                            row_dict[k] = v
                    self.writer.writerow(row_dict)
                    # Unit/replay adapters may provide a writer without an
                    # underlying file object.  Flush eagerly for the native
                    # research logger, while preserving that long-standing
                    # writer-only contract.
                    if self.file is not None:
                        self.file.flush()
                    self._write_synchronized_event({"row": row_dict})
                    if self.lsl is not None:
                        self.lsl.push(";".join([str(r) for r in row_dict.values()]))
                self.empty_queue()

    def write_single_slot(self, values: list[Any]) -> None:
        row: Any = self.slot(*values)
        self.add_row_to_queue(row)
        self.write_row_queue()
        self.event_sequence = getattr(self, "event_sequence", 0) + 1

    @staticmethod
    def _sync_stream(stream: IO[str]) -> None:
        stream.flush()
        os.fsync(stream.fileno())

    def _write_synchronized_event(
        self,
        payload: dict[str, Any],
        *,
        durable: bool = False,
    ) -> None:
        # Some integrations construct lightweight logger adapters with
        # ``__new__``.  Synchronized sidecar output is opt-in and must not
        # alter those legacy adapters.
        if getattr(self, "events_file", None) is None:
            return
        self.events_sequence += 1
        record = {
            "schema_version": OPENMATB_EVENT_SCHEMA_VERSION,
            "session_id": self.external_session_id,
            "sequence": self.events_sequence,
            "received_monotonic_ns": str(perf_counter_ns()),
            "received_utc_ns": str(time_ns()),
            **payload,
        }
        self.events_file.write(
            json.dumps(
                _json_safe(record),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
                allow_nan=False,
            )
            + "\n"
        )
        self.events_file.flush()
        if durable:
            # Boundary events drive physiology phase transitions in a separate
            # process. Persist both logs at that boundary without imposing an
            # fsync on every high-rate performance row.
            if self.file is not None:
                self._sync_stream(self.file)
            self._sync_stream(self.events_file)

    def set_totaltime(self, totaltime: float) -> None:
        self.totaltime: float = totaltime

    def set_scenario_time(self, scenario_time: float) -> None:
        self.scenario_time = scenario_time
