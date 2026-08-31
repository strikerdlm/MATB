# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import json
from typing import Any, Callable

from core import validation
from core.constants import COLORS as C
from core.container import Container
from core.pseudorandom import choice, sample
from core.widgets import Light, Scale
from plugins.abstractplugin import AbstractPlugin


class Sysmon(AbstractPlugin):
    def __init__(self, label: str = "", taskplacement: str = "topleft", taskupdatetime: int = 200) -> None:
        super().__init__(_("System monitoring"), taskplacement, taskupdatetime)

        self.validation_dict: dict[str, Callable[..., Any] | tuple[Callable[..., Any], list[str]]] = {
            "alerttimeout": validation.is_positive_integer,
            "nontargetduration": validation.is_positive_integer,
            "automaticsolverdelay": validation.is_positive_integer,
            "allowanykey": validation.is_boolean,
            "lights-1-name": validation.is_string,
            "lights-1-failure": validation.is_boolean,
            "lights-1-on": validation.is_boolean,
            "lights-1-default": (validation.is_in_list, ["on", "off"]),
            "lights-1-oncolor": validation.is_color,
            "lights-1-key": validation.is_key,
            "lights-1-onfailure": validation.is_boolean,
            "lights-2-name": validation.is_string,
            "lights-2-failure": validation.is_boolean,
            "lights-2-on": validation.is_boolean,
            "lights-2-default": (validation.is_in_list, ["on", "off"]),
            "lights-2-oncolor": validation.is_color,
            "lights-2-key": validation.is_key,
            "lights-2-onfailure": validation.is_boolean,
            "scales-1-name": validation.is_string,
            "scales-1-failure": validation.is_boolean,
            "scales-1-side": (validation.is_in_list, ["-1", "0", "1"]),
            "scales-1-key": validation.is_key,
            "scales-1-onfailure": validation.is_boolean,
            "scales-2-name": validation.is_string,
            "scales-2-failure": validation.is_boolean,
            "scales-2-side": (validation.is_in_list, ["-1", "0", "1"]),
            "scales-2-key": validation.is_key,
            "scales-2-onfailure": validation.is_boolean,
            "scales-3-name": validation.is_string,
            "scales-3-failure": validation.is_boolean,
            "scales-3-side": (validation.is_in_list, ["-1", "0", "1"]),
            "scales-3-key": validation.is_key,
            "scales-3-onfailure": validation.is_boolean,
            "scales-4-name": validation.is_string,
            "scales-4-failure": validation.is_boolean,
            "scales-4-side": (validation.is_in_list, ["-1", "0", "1"]),
            "scales-4-key": validation.is_key,
            "scales-4-onfailure": validation.is_boolean,
        }

        self.keys: set[str] = {"F1", "F2", "F3", "F4", "F5", "F6"}
        self.moving_seed: int = 1  # Useful for pseudorandom generation of
        # multiple values at once (arrows move)

        new_par: dict[str, Any] = dict(
            alerttimeout=10000,
            nontargetduration=2000,
            automaticsolver=False,
            automaticsolverdelay=1000,
            displayautomationstate=True,
            allowanykey=False,
            feedbackduration=1500,
            feedbacks=dict(positive=dict(active=True, color=C["GREEN"]), negative=dict(active=True, color=C["RED"])),
            lights=dict(
                [
                    ("1", dict(name="F5", failure=False, default="on", oncolor=C["GREEN"], key="F5", on=True)),
                    ("2", dict(name="F6", failure=False, default="off", oncolor=C["RED"], key="F6", on=False)),
                ]
            ),
            scales=dict(
                [
                    ("1", dict(name="F1", failure=False, side=0, key="F1")),
                    ("2", dict(name="F2", failure=False, side=0, key="F2")),
                    ("3", dict(name="F3", failure=False, side=0, key="F3")),
                    ("4", dict(name="F4", failure=False, side=0, key="F4")),
                ]
            ),
        )

        self.parameters.update(new_par)

        # Add private parameters
        # to any gauge
        self._opportunity_counter: int = 0
        self._nontarget_opportunity_id: str | None = None
        self._nontarget_opened_scenario_time: float | None = None
        self._nontarget_remaining_ms: int | None = None
        self._nontarget_deadline_s: float | None = None
        for gauge in self.get_all_gauges():
            gauge.update({
                "_failuretimer": None,
                "_failure_deadline_s": None,
                "_onfailure": False,
                "_milliresponsetime": 0,
                "_freezetimer": None,
                "_opportunity_id": None,
                "_opportunity_opened_scenario_time": None,
            })

        # and to scale only
        for gauge in self.get_scale_gauges():
            gauge.update({"_pos": 5, "_zone": 0, "_feedbacktimer": None, "_feedbacktype": None})

        self.automode_position: tuple[float, float] = (0.5, 0.05)
        self.scale_zones: dict[int, list[int]] = {1: list(range(3)), 0: list(range(3, 8)), -1: list(range(8, 11))}

    def get_response_timers(self) -> list[int]:
        return [g["_milliresponsetime"] for g in self.get_all_gauges()]

    def create_widgets(self) -> None:
        super().create_widgets()
        # Widgets coordinates (the left l coordinate is variable)
        scale_w: float = self.task_container.w * 0.1
        scale_b: float = self.task_container.b + self.task_container.h * 0.15
        scale_h: float = self.task_container.h * 0.5

        light_w: float = self.task_container.w * 0.4
        light_b: float = self.task_container.b + self.task_container.h * 0.75
        light_h: float = self.task_container.h * 0.15

        for scale_n, scale in self.parameters["scales"].items():
            scale_l: float = (
                self.task_container.l
                + (self.task_container.w / 4) * (int(scale_n) - 1)
                + self.task_container.w / 8
                - scale_w / 2
            )
            scale_container: Container = Container(f"scale_{scale_n}", scale_l, scale_b, scale_w, scale_h)

            scale["widget"] = self.add_widget(
                f"scale{scale_n!s}",
                Scale,
                container=scale_container,
                label=scale["name"],
                arrow_position=scale["_pos"],
            )

        for light_n, light in self.parameters["lights"].items():
            light_l: float = (
                self.task_container.l
                + (self.task_container.w / 2) * (int(light_n) - 1)
                + self.task_container.w / 4
                - light_w / 2
            )
            light_container: Container = Container(f"light_{light_n}", light_l, light_b, light_w, light_h)

            light["widget"] = self.add_widget(
                f"light{light_n!s}",
                Light,
                container=light_container,
                label=light["name"],
                color=self.determine_light_color(light),
            )

    def compute_next_plugin_state(self) -> None:
        if not super().compute_next_plugin_state():
            return

        nontarget_remaining_ms = getattr(self, "_nontarget_remaining_ms", None)
        if nontarget_remaining_ms is not None:
            deadline = getattr(self, "_nontarget_deadline_s", None)
            if deadline is None:
                deadline = self.scenario_time + nontarget_remaining_ms / 1000.0
                self._nontarget_deadline_s = deadline
            self._nontarget_remaining_ms = max(0, round((deadline - self.scenario_time) * 1000))
            if self.scenario_time >= deadline:
                lateness_ms = max(0, round((self.scenario_time - deadline) * 1000))
                tolerance_ms = int(self.parameters["taskupdatetime"])
                self.close_nontarget_opportunity(
                    false_alarm=False,
                    invalid_reason=(
                        "window_closed_after_update_stall"
                        if lateness_ms > tolerance_ms
                        else None
                    ),
                )

        # For the gauges that are on failure
        for gauge in self.get_gauges_on_failure():
            deadline = gauge.get("_failure_deadline_s")
            if deadline is None:
                deadline = self.scenario_time + gauge["_failuretimer"] / 1000.0
                gauge["_failure_deadline_s"] = deadline
            opened = gauge.get("_opportunity_opened_scenario_time")
            if opened is not None:
                gauge["_milliresponsetime"] = max(
                    0,
                    round((self.scenario_time - opened) * 1000),
                )
            gauge["_failuretimer"] = max(0, round((deadline - self.scenario_time) * 1000))

            # If the failure timer has ended by itself, stop failure and trigger a negative feedback
            # if possible (scale gauges)
            if self.scenario_time >= deadline:
                lateness_ms = max(0, round((self.scenario_time - deadline) * 1000))
                self.stop_failure(
                    gauge,
                    success=False,
                    invalid_reason=(
                        "window_closed_after_update_stall"
                        if lateness_ms > int(self.parameters["taskupdatetime"])
                        else None
                    ),
                )

        for gauge in self.get_scale_gauges():
            if gauge["_feedbacktimer"] is not None:
                gauge["_feedbacktimer"] -= self.parameters["taskupdatetime"]
                if gauge["_feedbacktimer"] <= 0:
                    gauge["_feedbacktimer"] = None
                    gauge["_feedbacktype"] = None

        # Compute arrows next position
        for _scale_n, scale in self.parameters["scales"].items():
            self.moving_seed += 1
            # Manage the case where the arrow must change its zone
            if scale["_pos"] not in self.scale_zones[scale["_zone"]]:
                scale["_pos"] = sample(
                    self.scale_zones[scale["_zone"]], self.alias, self.scenario_time, self.moving_seed
                )
            else:  # Move into a delimited zone
                direction: int = sample([-1, 1], self.alias, self.scenario_time, self.moving_seed)
                if scale["_pos"] + direction in self.scale_zones[scale["_zone"]]:
                    scale["_pos"] += direction
                else:
                    scale["_pos"] -= direction

            # If the gauge freeze timer is not null, freeze its arrow (pos = )
            if scale["_freezetimer"] is not None and isinstance(scale["_freezetimer"], int):
                scale["_freezetimer"] -= self.parameters["taskupdatetime"]
                if scale["_freezetimer"] > 0:
                    # Here, freeze position
                    scale["_pos"] = 5  # TODO: Check central scale value
                else:
                    scale["_freezetimer"] = None

        # Check for failure
        for gauge in self.get_gauges_key_value("failure", True):
            self.start_failure(gauge)

    def refresh_widgets(self) -> None:
        if not super().refresh_widgets():
            return
        for _scale_n, scale in self.parameters["scales"].items():
            scale["widget"].set_arrow_position(scale["_pos"])

            if scale["_feedbacktimer"] is not None:
                color: tuple[int, ...] = self.parameters["feedbacks"][scale["_feedbacktype"]]["color"]
                scale["widget"].set_feedback_color(color)
                scale["widget"].set_feedback_visibility(True)

            # Feedback timer is over and the feedback is yet visible
            # Hide the feedback
            else:
                scale["widget"].set_feedback_visibility(False)

        for _light_n, light in self.parameters["lights"].items():
            light["widget"].set_color(self.determine_light_color(light))

        for gauge in self.get_all_gauges():
            gauge["widget"].set_label(gauge["name"])

    def determine_light_color(self, light: dict[str, Any]) -> tuple[int, ...]:
        color: tuple[int, ...] = light["oncolor"] if light["on"] else C["BACKGROUND"]
        return color

    def _dispatch_context(self) -> dict[str, Any]:
        context = getattr(self, "_scenario_dispatch_context", None)
        return dict(context) if isinstance(context, dict) else {}

    def _log_rejected_opportunity(
        self,
        *,
        target: bool,
        outcome: str,
        reason: str,
        indicator: str | None = None,
        planned_duration_ms: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._opportunity_counter = getattr(self, "_opportunity_counter", 0) + 1
        payload = {
            "dispatch_scenario_time_s": self.scenario_time,
            "indicator": indicator,
            "opportunity_id": f"sysmon-{self._opportunity_counter:06d}",
            "outcome": outcome,
            "phase": "rejected",
            "planned_duration_ms": planned_duration_ms,
            "reason": reason,
            "target": target,
        }
        dispatch_context = context or self._dispatch_context()
        if dispatch_context:
            payload["scheduled_scenario_time_s"] = dispatch_context.get("scheduled_time_s")
            payload["source_line"] = dispatch_context.get("source_line")
        self.log_performance("opportunity", json.dumps(payload, sort_keys=True))

    def _reject_pending_targets(self, *, reason: str) -> bool:
        rejected = False
        for pending_gauge in self.get_all_gauges():
            if pending_gauge.get("failure") is not True:
                continue
            context = pending_gauge.pop("_pending_dispatch_context", None)
            planned_duration_ms = pending_gauge.pop("_pending_alerttimeout_ms", None)
            pending_gauge.pop("_pending_automation_active", None)
            pending_gauge["failure"] = False
            self._log_rejected_opportunity(
                target=True,
                outcome="INVALID_COLLAPSED_BATCH",
                reason=reason,
                indicator=str(pending_gauge.get("name", "unknown")),
                planned_duration_ms=planned_duration_ms,
                context=context,
            )
            rejected = True
        return rejected

    def _dispatch_is_late(self, context: dict[str, Any]) -> bool:
        scheduled = context.get("scheduled_time_s")
        if not isinstance(scheduled, (int, float)) or isinstance(scheduled, bool):
            return False
        lateness_ms = max(0.0, (self.scenario_time - float(scheduled)) * 1000.0)
        return lateness_ms > int(self.parameters["taskupdatetime"])

    def set_parameter(self, keys_str: str, value: Any) -> dict[str, Any]:
        """Queue target commands only when their evidence window is observable."""
        if not (keys_str.endswith("-failure") and value is True):
            return super().set_parameter(keys_str, value)

        context = self._dispatch_context()
        keys = keys_str.split("-")
        gauge = self.parameters[keys[0]][keys[1]]
        automation_active = bool(self.parameters["automaticsolver"])
        duration_ms = int(
            self.parameters["automaticsolverdelay"]
            if automation_active
            else self.parameters["alerttimeout"]
        )
        rejected_reason: str | None = None
        if self._dispatch_is_late(context):
            rejected_reason = "target_command_dispatched_after_observable_onset"
        elif getattr(self, "_nontarget_opportunity_id", None) is not None:
            self.close_nontarget_opportunity(
                invalid_reason="collapsed_due_batch_collision"
            )
            rejected_reason = "collapsed_due_batch_collision"
        elif self._reject_pending_targets(reason="collapsed_due_batch_collision"):
            rejected_reason = "collapsed_due_batch_collision"
        elif self.get_gauges_on_failure():
            rejected_reason = "target_window_already_active"

        if rejected_reason is not None:
            result = super().set_parameter(keys_str, False)
            self._log_rejected_opportunity(
                target=True,
                outcome=(
                    "INVALID_LATE_DISPATCH"
                    if rejected_reason == "target_command_dispatched_after_observable_onset"
                    else "INVALID_COLLAPSED_BATCH"
                ),
                reason=rejected_reason,
                indicator=str(gauge.get("name", "unknown")),
                planned_duration_ms=duration_ms,
                context=context,
            )
            return result

        gauge["_pending_alerttimeout_ms"] = duration_ms
        gauge["_pending_automation_active"] = automation_active
        gauge["_pending_dispatch_context"] = context
        return super().set_parameter(keys_str, value)

    def start_failure(self, gauge: dict[str, Any]) -> None:
        if getattr(self, "_nontarget_opportunity_id", None) is not None:
            raise RuntimeError("cannot open a target opportunity during an active non-target opportunity")
        if gauge["_onfailure"]:
            gauge["failure"] = False
            return
        else:
            dispatch_context = gauge.get("_pending_dispatch_context") or {}
            scheduled = dispatch_context.get("scheduled_time_s")
            if (
                isinstance(scheduled, (int, float))
                and not isinstance(scheduled, bool)
                and max(0.0, (self.scenario_time - float(scheduled)) * 1000.0)
                > int(self.parameters["taskupdatetime"])
            ):
                planned_duration_ms = int(
                    gauge.pop("_pending_alerttimeout_ms", self.parameters["alerttimeout"])
                )
                gauge["failure"] = False
                gauge.pop("_pending_dispatch_context", None)
                gauge.pop("_pending_automation_active", None)
                self._log_rejected_opportunity(
                    target=True,
                    outcome="INVALID_STALLED_WINDOW",
                    reason="target_window_opened_after_update_stall",
                    indicator=str(gauge.get("name", "unknown")),
                    planned_duration_ms=planned_duration_ms,
                    context=dispatch_context,
                )
                return
            self._opportunity_counter = getattr(self, "_opportunity_counter", 0) + 1
            opportunity_id = f"sysmon-{self._opportunity_counter:06d}"
            gauge["_opportunity_id"] = opportunity_id
            gauge["_opportunity_opened_scenario_time"] = self.scenario_time
            planned_duration_ms = int(
                gauge.get("_pending_alerttimeout_ms")
                or (
                    self.parameters["automaticsolverdelay"]
                    if self.parameters["automaticsolver"]
                    else self.parameters["alerttimeout"]
                )
            )
            automation_active = bool(
                gauge.pop(
                    "_pending_automation_active",
                    self.parameters["automaticsolver"],
                )
            )
            allocation_actor = "automation" if automation_active else "participant"
            gauge["_opportunity_automation_active"] = automation_active
            gauge["_opportunity_duration_ms"] = planned_duration_ms
            self.log_performance("opportunity", json.dumps({
                "allocation_actor": allocation_actor,
                "automation_active": automation_active,
                "close_lateness_tolerance_ms": int(self.parameters["taskupdatetime"]),
                "deadline_s": self.scenario_time + planned_duration_ms / 1000.0,
                "duration_ms": planned_duration_ms,
                "opportunity_id": opportunity_id,
                "phase": "opened",
                "target": True,
                "indicator": gauge["name"],
                "opened_scenario_time_s": self.scenario_time,
                "scheduled_scenario_time_s": dispatch_context.get("scheduled_time_s"),
            }, sort_keys=True))
            gauge["_onfailure"] = True
            if "default" in gauge:  # Light case
                gauge["on"] = gauge["default"] != "on"
            else:  # Scale case
                if gauge["side"] not in [-1, 1]:
                    add: str | None = self.get_gauge_key(gauge)  # Specify a gauge integer to generate
                    # a unique seed
                    gauge["side"] = choice([-1, 1], self.alias, self.scenario_time, int(add))
                gauge["_zone"] = gauge["side"]
        gauge["failure"] = False

        # Schedule failure timing
        delay = int(gauge.pop("_pending_alerttimeout_ms", planned_duration_ms))
        gauge.pop("_pending_dispatch_context", None)
        gauge["_failuretimer"] = delay
        gauge["_failure_deadline_s"] = self.scenario_time + delay / 1000.0

    def stop_failure(
        self,
        gauge: dict[str, Any],
        success: bool = False,
        invalid_reason: str | None = None,
        response_actor: str | None = None,
    ) -> None:
        opportunity_id = gauge.get("_opportunity_id")
        opened_scenario_time = gauge.get("_opportunity_opened_scenario_time")
        automation_active = bool(gauge.get("_opportunity_automation_active", False))
        response_actor = str(
            response_actor
            or ("automation" if automation_active else "participant")
        )
        if response_actor not in {"participant", "automation"}:
            raise ValueError("SYSMON response actor must be participant or automation")
        response_time_ms = gauge["_milliresponsetime"]
        if opened_scenario_time is not None:
            response_time_ms = max(
                0,
                round((self.scenario_time - opened_scenario_time) * 1000),
            )
        deadline = gauge.get("_failure_deadline_s")
        lateness_ms = (
            max(0, round((self.scenario_time - deadline) * 1000))
            if isinstance(deadline, (int, float))
            else None
        )
        # Reset the gauge failure timer
        gauge["_onfailure"] = False
        gauge["_failuretimer"] = None
        gauge["_failure_deadline_s"] = None

        # Set the (potential) feedback type (ft)
        ft: str = "positive" if automation_active or success else "negative"

        # Does this feedback type (positive or negative) is currently active ?
        # If so, set the feedback type and duration, if the gauge has got one
        # (the feedback widget is refreshed by the refresh_widget method)
        if self.parameters["feedbacks"][ft]["active"] and "_feedbacktimer" in gauge:
            self.set_scale_feedback(gauge, ft)

        # Feed the freeze timer with feedback duration (1.5 by default) if the response is good
        if success:
            gauge["_freezetimer"] = self.parameters["feedbackduration"]

        # IDEA: do we need to distinguish manual detection (hit) from automatic detection ?
        # Evaluate performance in terms of signal detection and response time
        if ft == "positive":
            sdt_string: str
            rt: int | float
            sdt_string, rt = "HIT", response_time_ms
        else:
            sdt_string, rt = "MISS", float("nan")
        sdt_string = "HIT" if ft == "positive" else "MISS"

        if invalid_reason is None:
            self.log_performance("name", gauge["name"])
            self.log_performance("signal_detection", sdt_string)
            self.log_performance("response_time", rt)
        if opportunity_id is not None:
            self.log_performance("opportunity", json.dumps({
                "automation_active": automation_active,
                "opportunity_id": opportunity_id,
                "phase": "closed",
                "target": True,
                "indicator": gauge["name"],
                "lateness_ms": lateness_ms,
                "opened_scenario_time_s": opened_scenario_time,
                "closed_scenario_time_s": self.scenario_time,
                "response_time_ms": response_time_ms if success else None,
                "outcome": (
                    "INVALID_COLLAPSED_BATCH"
                    if invalid_reason == "collapsed_due_batch_collision"
                    else ("INVALID_STALLED_WINDOW" if invalid_reason else sdt_string)
                ),
                "reason": invalid_reason,
                "response_actor": response_actor,
                "scheduled_deadline_s": deadline,
            }, sort_keys=True))

        # Reset gauge to its nominal (default) state
        if "default" in gauge:  # Light case
            gauge["on"] = gauge["default"] == "on"
        else:  # Scale case
            gauge["_zone"] = 0
        gauge["_milliresponsetime"] = 0
        gauge["_opportunity_id"] = None
        gauge["_opportunity_opened_scenario_time"] = None
        gauge["_opportunity_automation_active"] = None
        gauge["_opportunity_duration_ms"] = None

    def open_nontarget_opportunity(self) -> None:
        """Open one explicit target-absent observation window.

        Only protocol-defined windows contribute non-target opportunities to signal
        detection metrics. Ordinary idle duration is intentionally never inferred as
        a denominator.
        """
        context = self._dispatch_context()
        if self._dispatch_is_late(context):
            self._log_rejected_opportunity(
                target=False,
                outcome="INVALID_LATE_DISPATCH",
                reason="nontarget_command_dispatched_after_observable_onset",
                planned_duration_ms=int(self.parameters["nontargetduration"]),
                context=context,
            )
            return
        if getattr(self, "_nontarget_opportunity_id", None) is not None:
            raise RuntimeError("a non-target opportunity is already active")
        if len(self.get_gauges_on_failure()) > 0:
            if context:
                self._log_rejected_opportunity(
                    target=False,
                    outcome="INVALID_COLLAPSED_BATCH",
                    reason="target_window_already_active",
                    planned_duration_ms=int(self.parameters["nontargetduration"]),
                    context=context,
                )
                return
            raise RuntimeError("cannot open a non-target opportunity during an active target opportunity")
        pending_targets = [
            gauge for gauge in self.get_all_gauges() if gauge.get("failure") is True
        ]
        if pending_targets:
            # A long frame stall can dispatch a target command and a later
            # non-target command before the next plugin update consumes the
            # target flag. Refuse to reclassify that interval as target-absent,
            # preserve explicit invalid evidence, and let the next update open
            # the pending target normally.
            pending_indicators = sorted(
                str(gauge.get("name", "unknown")) for gauge in pending_targets
            )
            self._reject_pending_targets(reason="collapsed_due_batch_collision")
            self._log_rejected_opportunity(
                target=False,
                outcome="INVALID_COLLAPSED_BATCH",
                reason="collapsed_due_batch_collision_with_pending_target",
                indicator=",".join(pending_indicators),
                planned_duration_ms=int(self.parameters["nontargetduration"]),
                context=context,
            )
            return

        duration_ms = int(self.parameters["nontargetduration"])
        self._opportunity_counter = getattr(self, "_opportunity_counter", 0) + 1
        opportunity_id = f"sysmon-{self._opportunity_counter:06d}"
        self._nontarget_opportunity_id = opportunity_id
        self._nontarget_opened_scenario_time = self.scenario_time
        self._nontarget_remaining_ms = duration_ms
        self._nontarget_deadline_s = self.scenario_time + duration_ms / 1000.0
        self._nontarget_automation_active = bool(self.parameters["automaticsolver"])
        self.log_performance("opportunity", json.dumps({
            "allocation_actor": (
                "automation"
                if self._nontarget_automation_active
                else "participant"
            ),
            "automation_active": self._nontarget_automation_active,
            "close_lateness_tolerance_ms": int(self.parameters["taskupdatetime"]),
            "deadline_s": self._nontarget_deadline_s,
            "duration_ms": duration_ms,
            "opened_scenario_time_s": self.scenario_time,
            "opportunity_id": opportunity_id,
            "phase": "opened",
            "target": False,
        }, sort_keys=True))

    def close_nontarget_opportunity(
        self,
        false_alarm: bool = False,
        indicator: str | None = None,
        invalid_reason: str | None = None,
        response_actor: str | None = None,
    ) -> None:
        """Close the active target-absent window as a CR or linked FA."""
        opportunity_id = getattr(self, "_nontarget_opportunity_id", None)
        if opportunity_id is None:
            raise RuntimeError("no non-target opportunity is active")

        opened_scenario_time = getattr(self, "_nontarget_opened_scenario_time", None)
        response_time_ms: float | None = None
        if false_alarm and opened_scenario_time is not None:
            response_time_ms = max(0.0, (self.scenario_time - opened_scenario_time) * 1000.0)
        deadline = getattr(self, "_nontarget_deadline_s", None)
        lateness_ms = (
            max(0, round((self.scenario_time - deadline) * 1000))
            if deadline is not None
            else None
        )
        automation_active = bool(
            getattr(self, "_nontarget_automation_active", False)
        )
        response_actor = response_actor or (
            "automation" if automation_active else "participant"
        )
        if response_actor not in {"participant", "automation"}:
            raise ValueError("SYSMON response actor must be participant or automation")

        self.log_performance("opportunity", json.dumps({
            "automation_active": automation_active,
            "closed_scenario_time_s": self.scenario_time,
            "indicator": indicator,
            "opened_scenario_time_s": opened_scenario_time,
            "opportunity_id": opportunity_id,
            "lateness_ms": lateness_ms,
            "outcome": (
                "INVALID_COLLAPSED_BATCH"
                if invalid_reason == "collapsed_due_batch_collision"
                else (
                    "INVALID_STALLED_WINDOW"
                    if invalid_reason is not None
                    else ("FA" if false_alarm else "CR")
                )
            ),
            "phase": "closed",
            "reason": invalid_reason,
            "response_time_ms": response_time_ms,
            "response_actor": response_actor,
            "scheduled_deadline_s": deadline,
            "target": False,
        }, sort_keys=True))
        self._nontarget_opportunity_id = None
        self._nontarget_opened_scenario_time = None
        self._nontarget_remaining_ms = None
        self._nontarget_deadline_s = None
        self._nontarget_automation_active = None

    def get_gauges_key_value(self, key: str, value: Any) -> list[dict[str, Any]]:
        gauge_list: list[dict[str, Any]] = list()
        for gauge in self.get_all_gauges():
            if gauge[key] == value:
                gauge_list.append(gauge)
        return gauge_list

    def stop(self) -> None:
        """Close every observable or queued opportunity before task teardown."""

        self._reject_pending_targets(reason="task_stopped_before_outcome")
        for gauge in list(self.get_gauges_on_failure()):
            self.stop_failure(
                gauge,
                success=False,
                invalid_reason="task_stopped_before_outcome",
            )
        if getattr(self, "_nontarget_opportunity_id", None) is not None:
            self.close_nontarget_opportunity(
                invalid_reason="task_stopped_before_outcome"
            )
        super().stop()

    def get_gauge_by_key(self, key: str) -> dict[str, Any]:
        return self.get_gauges_key_value("key", key)[0]

    def get_gauge_key(self, gauge: dict[str, Any]) -> str | None:
        for key in ["lights", "scales"]:
            for k, v in self.parameters[key].items():
                if gauge == v:
                    return k

    def get_gauges_on_failure(self) -> list[dict[str, Any]]:
        return self.get_gauges_key_value("_onfailure", True)

    def get_scale_gauges(self) -> list[dict[str, Any]]:
        return [g for _, g in self.parameters["scales"].items()]

    def get_light_gauges(self) -> list[dict[str, Any]]:
        return [g for _, g in self.parameters["lights"].items()]

    def get_all_gauges(self) -> list[dict[str, Any]]:
        return [g for g in self.get_scale_gauges() + self.get_light_gauges()]

    def set_scale_feedback(self, gauge: dict[str, Any], feedback_type: str) -> None:
        # Set the feedback type and duration, if the gauge has got one
        # (the feedback widget is refreshed by the refresh_widget method)
        gauge["_feedbacktype"] = feedback_type
        gauge["_feedbacktimer"] = self.parameters["feedbackduration"]

    def do_on_key(self, key: str, state: str, emulate: bool) -> None:
        key = super().do_on_key(key, state, emulate)
        if key is None:
            return

        if state == "press":
            gauge: dict[str, Any] = self.get_gauge_by_key(key)
            if key in [g["key"] for g in self.get_gauges_on_failure()]:
                self.stop_failure(
                    gauge=gauge,
                    success=True,
                    response_actor="automation" if emulate else "participant",
                )
            else:
                self.log_performance("name", gauge["name"])
                self.log_performance("signal_detection", "FA")
                self.log_performance("response_time", float("nan"))
                if getattr(self, "_nontarget_opportunity_id", None) is not None:
                    self.close_nontarget_opportunity(
                        false_alarm=True,
                        indicator=gauge["name"],
                        response_actor="automation" if emulate else "participant",
                    )
                else:
                    self.log_performance("opportunity_unlinked_response", json.dumps({
                        "indicator": gauge["name"],
                        "outcome": "FA",
                        "scenario_time_s": self.scenario_time,
                        "reason": "no_protocol_defined_nontarget_opportunity",
                    }, sort_keys=True))

                # Set a negative feedback if relevant
                if self.parameters["feedbacks"]["negative"]["active"]:
                    self.set_scale_feedback(gauge, "negative")
