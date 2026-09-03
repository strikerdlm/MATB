"""Cross-platform JSON-lines control channel for a supervised OpenMATB run."""

from __future__ import annotations

import json
import queue
import sys
import threading
from typing import Any, TextIO


class StdioControlBridge:
    """Read commands from stdin and emit machine-readable events on stdout."""

    def __init__(self, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> None:
        self._input = input_stream or sys.stdin
        self._output = output_stream or sys.stdout
        self._commands: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self._write_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_commands, name="openmatb-control", daemon=True)

    def start(self) -> None:
        self._reader.start()

    def _read_commands(self) -> None:
        for raw_line in self._input:
            try:
                payload = json.loads(raw_line)
                if not isinstance(payload, dict) or not isinstance(payload.get("command"), str):
                    raise ValueError("command must be a JSON object with a string command")
                self._commands.put(payload)
            except (json.JSONDecodeError, ValueError) as exc:
                self.emit("protocol_error", message=str(exc))

    def drain(self) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        while True:
            try:
                commands.append(self._commands.get_nowait())
            except queue.Empty:
                return commands

    def emit(self, event: str, **payload: Any) -> None:
        record = {"schema_version": "1.0", "event": event, **payload}
        with self._write_lock:
            self._output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._output.flush()
