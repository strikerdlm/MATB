"""Concurrent ISA-10 workload prompt with structured scientific output."""

from __future__ import annotations

from typing import Any

from core import validation
from core.constants import FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


class Instantaneousworkload(AbstractPlugin):
    """A nonblocking 1--10 Instantaneous Self-Assessment prompt.

    Number keys 1--9 select their corresponding value and 0 selects 10.  The
    prompt occupies the otherwise unused bottom-right task region, so the four
    MATB subtasks continue to run while workload is reported.
    """

    blocking = False

    def __init__(
        self,
        label: str = "",
        taskplacement: str = "bottomright",
        taskupdatetime: int = 50,
    ) -> None:
        super().__init__(_("Instantaneous workload"), taskplacement, taskupdatetime)
        self.validation_dict = {
            "minimum": validation.is_positive_integer,
            "maximum": validation.is_positive_integer,
            "timeoutms": validation.is_positive_integer,
            "prompt": validation.is_string,
        }
        self.parameters.update(
            minimum=1,
            maximum=10,
            timeoutms=10_000,
            prompt=_("Current workload? Press 1 (very low) to 0 (10, very high)."),
        )
        digits = {str(value) for value in range(10)}
        self.keys.update(digits | {f"_{value}" for value in range(10)})
        self._research_trial_counter = 0
        self._prompt_id: str | None = None
        self._onset_s: float | None = None
        self._deadline_s: float | None = None
        self._event_sequence_start: int | None = None

    def create_widgets(self) -> None:
        super().create_widgets()
        self.add_widget(
            "prompt",
            Simpletext,
            container=self.task_container,
            text=self.parameters["prompt"],
            wrap_width=0.85,
            font_size=F["MEDIUM"],
        )

    def start(self) -> None:
        if self.alive:
            self._finish(value=None, timeout=True)
        self.alive = True
        self._research_trial_counter = getattr(self, "_research_trial_counter", 0) + 1
        self._prompt_id = f"workload-{self._research_trial_counter:06d}"
        self._onset_s = float(self.scenario_time)
        self._deadline_s = self._onset_s + float(self.parameters["timeoutms"]) / 1000.0
        self._event_sequence_start = int(getattr(self.logger, "event_sequence", 0))
        if not self.widgets:
            self.create_widgets()
        self.show()
        self.resume()

    def stop(self) -> None:
        self.alive = False
        self.pause()
        self.hide()

    def get_research_state(self) -> dict[str, Any]:
        return {
            "workload_alive": bool(self.alive),
            "load_workload": bool(self.alive and self._prompt_id),
            "workload_prompt_id": self._prompt_id if self.alive else None,
        }

    def compute_next_plugin_state(self) -> None:
        if self.alive and self._deadline_s is not None and self.scenario_time >= self._deadline_s:
            self._finish(value=None, timeout=True)

    def do_on_key(self, keystr: str, state: str, emulate: bool = False) -> str | None:
        keystr = super().do_on_key(keystr, state, emulate)
        if keystr is None or state != "press" or not self.alive:
            return keystr
        digit = keystr.removeprefix("_")
        if digit not in {str(value) for value in range(10)}:
            return keystr
        value = 10 if digit == "0" else int(digit)
        if self.parameters["minimum"] <= value <= self.parameters["maximum"]:
            self._finish(value=value, timeout=False, actor="automation" if emulate else "manual")
        return keystr

    def _finish(self, *, value: int | None, timeout: bool, actor: str = "manual") -> None:
        if not self.alive or self._prompt_id is None or self._onset_s is None:
            return
        response_s = None if timeout else float(self.scenario_time)
        rt_ms = None if response_s is None else round((response_s - self._onset_s) * 1000.0, 6)
        if value is not None:
            self.log_performance("workload", value)
            self.log_performance("response_time", rt_ms)
        self.logger.record_research_trial(
            {
                "trial_id": self._prompt_id,
                "task": "workload",
                "trial_type": "ISA-10",
                "stimulus_id": self._prompt_id,
                "onset_s": self._onset_s,
                "deadline_s": self._deadline_s,
                "response_s": response_s,
                "rt_ms": rt_ms,
                "outcome": "timeout" if timeout else "response",
                "correct": None,
                "timeout": timeout,
                "actor": actor,
                "automation_active": actor == "automation",
                "target_json": {"minimum": 1, "maximum": 10},
                "response_json": {"value": value},
                "elements_available": 1,
                "elements_correct": None,
                "raw_value": None if value is None else float(value),
                "raw_unit": "ISA_1_to_10",
                "event_sequence_start": self._event_sequence_start,
                "event_sequence_end": int(getattr(self.logger, "event_sequence", 0)),
            }
        )
        self.stop()
        self._prompt_id = None
        self._onset_s = None
        self._deadline_s = None
        self._event_sequence_start = None


__all__ = ["Instantaneousworkload"]
