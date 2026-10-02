# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import os
from collections import deque
from math import isfinite
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from pyglet import app as pyglet_app
from pyglet.app import EventLoop

from core.clock import Clock
from core.constants import REPLAY_MODE, SYSTEM_PSEUDO_PLUGIN, VISUAL_THEME
from core.controlbridge import StdioControlBridge
from core.error import get_errors
from core.event import Event
from core.experimentclock import ExperimentClock
from core.joystick import joystick
from core.logger import get_logger
from core.scenario import Scenario
from core.scenarioprovenance import load_adjacent_scenario_manifest
from core.window import Window


class Scheduler:
    """
    This class manages events execution.
    """

    def __init__(
        self,
        scenario_path: Path | None = None,
        control_bridge: StdioControlBridge | None = None,
        participant_briefing: bool = False,
    ) -> None:
        with open("VERSION", "r") as f:
            self.runtime_version = f.read().strip()

        self.clock: Clock = Clock("main")
        self.scenario_time: float = 0
        self.scenario_path: Path | None = scenario_path
        self.control_bridge = control_bridge
        self.preflight_held = os.environ.get("MATB_PREPARATION_HOLD") == "1" and control_bridge is not None
        self.preflight_snapshot = None

        # Create the event loop
        self.clock.schedule(self.update)
        self.event_loop: EventLoop = EventLoop()
        # Win32 window callbacks address pyglet's global event loop.
        pyglet_app.event_loop = self.event_loop

        self.joystick: Any = joystick
        self.set_scenario()

        if self.control_bridge is not None:
            from core.preflight import snapshot
            self.preflight_snapshot = snapshot(self)
        if self.preflight_held:
            Window.MainWindow.set_visible(False)
        else:
            Window.MainWindow.activate()
        if self.control_bridge is not None:
            self.control_bridge.start()
            self.clock.schedule(self._poll_control_bridge)
            self.control_bridge.emit(
                "ready",
                scenario=str(self.scenario_path) if self.scenario_path is not None else None,
                session_csv=str(get_logger().path),
                preflight=self.preflight_snapshot,
                visual_theme=VISUAL_THEME.name,
                visual_profile_id=VISUAL_THEME.profile_id,
                visual_profile_version=VISUAL_THEME.version,
                visual_profile_schema_version=VISUAL_THEME.schema_version,
                visual_profile_sha256=VISUAL_THEME.sha256,
            )

        if participant_briefing:
            from core.briefing import ParticipantBriefing
            Window.MainWindow.modal_dialog = ParticipantBriefing(Window.MainWindow)
        else:
            Window.MainWindow.display_session_id()
        self.event_loop.run()

    def _poll_control_bridge(self, _dt: float) -> None:
        if self.control_bridge is None or getattr(self, "_exiting", False):
            return
        for message in self.control_bridge.drain():
            command = message["command"].strip().lower()
            if command == "status":
                self.control_bridge.emit(
                    "status",
                    paused=self.is_scenario_time_paused(),
                    scenario_time_seconds=round(self.scenario_time, 3),
                    active_plugins=[plugin.alias for plugin in self.get_active_plugins()],
                )
            elif command == "release_preflight":
                if (not getattr(self, "preflight_held", False) or self.preflight_snapshot is None
                        or self.preflight_snapshot['issues'] or message.get('snapshot_sha256') != self.preflight_snapshot['sha256']):
                    self.control_bridge.emit("command_rejected", command=command, reason="preflight_snapshot_mismatch")
                    continue
                from core.preflight import snapshot
                if snapshot(self)['sha256'] != self.preflight_snapshot['sha256']:
                    self.control_bridge.emit("command_rejected", command=command, reason="preflight_mapping_changed")
                    continue
                get_logger().admit_preflight()
                self.preflight_held = False
                self.pause_scenario_time = False
                Window.MainWindow.set_visible(True)
                Window.MainWindow.activate()
                self.control_bridge.emit("preflight_released", snapshot_sha256=self.preflight_snapshot['sha256'])
            elif command == "pause":
                self._operator_pause()
            elif command == "resume":
                self._operator_resume()
            elif command == "abort":
                self.control_bridge.emit("aborted", scenario_time_seconds=round(self.scenario_time, 3))
                self.exit(completion="aborted")
                return
            else:
                self.control_bridge.emit("command_rejected", command=command, reason="unsupported_command")

    def _operator_pause(self) -> None:
        if self.control_bridge is None:
            return
        self._operator_paused = True
        if not self.is_scenario_time_paused():
            self.pause_scenario()
            self.execute_plugins_methods(self.get_active_non_blocking_plugins(), methods="pause")
        self.control_bridge.emit("paused", scenario_time_seconds=round(self.scenario_time, 3))

    def _operator_resume(self) -> None:
        if getattr(self, "preflight_held", False):
            self.control_bridge.emit("command_rejected", command="resume", reason="preflight_admission_required")
            return
        if self.control_bridge is None:
            return
        if self.get_active_blocking_plugin() is not None or Window.MainWindow.modal_dialog is not None:
            self.control_bridge.emit("command_rejected", command="resume", reason="participant_prompt_active")
            return
        self._operator_paused = False
        if self.paused_plugins:
            self.execute_plugins_methods(self.paused_plugins, methods=["show", "resume"])
            self.paused_plugins = []
        self.execute_plugins_methods(
            self.get_plugins_by_states([("alive", True), ("paused", True)]),
            methods="resume",
        )
        self.resume_scenario()
        self.control_bridge.emit("resumed", scenario_time_seconds=round(self.scenario_time, 3))

    def set_scenario(self, events: list[str] | None = None) -> None:
        # Resolve the module-level clock dynamically so tests and qualification
        # harnesses can inject a clock without changing the production contract.
        self.experiment_clock = ExperimentClock(monotonic_ns=lambda: perf_counter_ns())
        scenario_path: Path | None = self.scenario_path if events is None else None
        source = Scenario.resolve_source(events, scenario_path=scenario_path)
        bound_manifest = load_adjacent_scenario_manifest(
            source.scenario_path,
            scenario_sha256=source.scenario_sha256,
        )
        logger = get_logger()
        logger.configure_scientific_context(
            scenario_sha256=source.scenario_sha256,
            profile_id=os.environ.get("MATB_PROFILE_ID", "openmatb-1.4.5-derived"),
            source_commit=os.environ.get("MATB_SOURCE_COMMIT", "unavailable"),
            component_version=getattr(self, "runtime_version", "unavailable"),
            scenario_manifest_evidence=bound_manifest.evidence,
            source_dirty=self._source_dirty_from_environment(),
            preparation_hold=getattr(self, "preflight_held", False),
        )
        # Bootstrap facts become authoritative records only after the immutable
        # scenario/runtime/source context is installed. This prevents a clean
        # session from beginning with provenance-null JSONL events.
        logger.archive_scenario_manifest(bound_manifest)
        self.scenario = Scenario(source=source)
        logger.log_manual_entry(self.runtime_version, key="version")
        if self.scenario.scenario_path is not None:
            logger.log_manual_entry(self.scenario.scenario_path, key="scenario_path")
        logger.log_manual_entry(VISUAL_THEME.name, key="visual_theme")
        logger.log_manual_entry(VISUAL_THEME.profile_id, key="visual_profile_id")
        logger.log_manual_entry(VISUAL_THEME.version, key="visual_profile_version")
        logger.log_manual_entry(VISUAL_THEME.schema_version, key="visual_profile_schema_version")
        logger.log_manual_entry(VISUAL_THEME.sha256, key="visual_profile_sha256")

        self.events: list[Event] = self.scenario.events
        self.plugins: dict[str, Any] = self.scenario.plugins
        logger.configure_evidence_tasks(list(self.plugins))

        # Attribute window to plugins in use, and push their handles to window
        for p in self.plugins:
            self.plugins[p].win = Window.MainWindow
            self.plugins[p].joystick = self.joystick
            if not REPLAY_MODE:
                Window.MainWindow.push_handlers(self.plugins[p].on_key_press, self.plugins[p].on_key_release)

            self.plugins[p].on_scenario_loaded(self.scenario)

        self.pause_scenario_time: bool = False
        self.scenario_time = 0

        # We store events in a list in case their execution is delayed by a blocking event
        self.events_queue: deque[Event] = deque()
        self.blocking_plugin: Any | None = None

        # Store the plugins that could be paused by a *blocking* event
        self.paused_plugins: list[Any] = list()

        # Track whether plugins have been paused due to a modal dialog (e.g. pause prompt)
        self._dialog_paused: bool = False
        self._operator_paused: bool = False
        self._dispatch_failed: bool = False
        self._dispatch_failure: dict[str, Any] | None = None

    @staticmethod
    def _source_dirty_from_environment() -> bool | None:
        raw = os.environ.get("MATB_SOURCE_DIRTY")
        if raw is None:
            return None
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
        return None

    def update(self, dt: float) -> None:
        if getattr(self, "_exiting", False):
            return
        if Window.MainWindow is not None and Window.MainWindow.alive is False:
            self.check_if_must_exit()
            return
        if getattr(self, "preflight_held", False):
            return
        # A failed scenario command invalidates the complete session. Hosts that
        # catch the propagated exception must not advance clocks/plugins or
        # accidentally retry/continue the experimental timeline.
        if getattr(self, "_dispatch_failed", False):
            return
        failure_phase = "modal_dialog_pause"
        try:
            if Window.MainWindow.modal_dialog is not None:
                if not self._dialog_paused:
                    self.execute_plugins_methods(self.get_active_plugins(), ["pause"])
                    self._dialog_paused = True
                return

            failure_phase = "modal_dialog_resume"
            if self._dialog_paused:
                if not getattr(self, "_operator_paused", False):
                    self.execute_plugins_methods(self.get_active_plugins(), ["resume"])
                self._dialog_paused = False

            failure_phase = "runtime_error_display"
            if not get_errors().is_empty():
                get_errors().show_errors()

            failure_phase = "scenario_clock_update"
            self.update_timers(dt)
            failure_phase = "joystick_update"
            self.update_joystick()
            failure_phase = "plugin_update"
            self.update_active_plugins()
            failure_phase = "event_dispatch"
            self.execute_events()
            failure_phase = "exit_check"
            self.check_if_must_exit()
        except Exception as exc:
            # Command dispatch and clock paths already capture richer evidence.
            # Every other update phase still invalidates the complete session.
            if not getattr(self, "_dispatch_failed", False):
                self._terminalize_runtime_phase_failure(
                    exc,
                    failure_phase=failure_phase,
                )
            raise

    def _terminalize_runtime_phase_failure(
        self,
        exc: Exception,
        *,
        failure_phase: str,
    ) -> None:
        self._dispatch_failed = True
        self._dispatch_failure = {
            "failure_phase": failure_phase,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:4096],
            "failure_evidence_status": "in_memory_and_manual_log_attempted",
        }
        self.pause_scenario_time = True
        if hasattr(self, "events_queue"):
            self.events_queue.clear()
        try:
            get_logger().log_manual_entry(
                f"{failure_phase}: {type(exc).__name__}: {exc}",
                key="runtime_phase_failure",
            )
        except Exception as evidence_exc:  # noqa: BLE001 - preserve origin
            self._dispatch_failure["failure_evidence_status"] = "write_failed"
            self._dispatch_failure["failure_evidence_error"] = (
                f"{type(evidence_exc).__name__}: {evidence_exc}"
            )[:4096]

    def update_timers(self, dt: float) -> None:
        if getattr(self, "preflight_held", False):
            return
        if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not isfinite(dt):
            exc = ValueError("scheduler dt must be a finite non-negative number")
            self._terminalize_scenario_clock_failure(exc)
            raise exc
        if dt < 0:
            exc = ValueError("scheduler dt must be non-negative")
            self._terminalize_scenario_clock_failure(exc)
            raise exc
        if self.is_scenario_time_paused():
            return
        candidate = self.scenario_time + float(dt)
        if not isfinite(candidate) or candidate < self.scenario_time:
            exc = RuntimeError("scenario clock advance is non-finite or regressed")
            self._terminalize_scenario_clock_failure(exc)
            raise exc
        experiment_clock = getattr(self, "experiment_clock", None)
        if experiment_clock is None:
            experiment_clock = ExperimentClock(monotonic_ns=lambda: perf_counter_ns())
            self.experiment_clock = experiment_clock
        try:
            experiment_clock.observe(int(round(candidate * 1_000_000_000)))
            get_logger().set_scenario_time(candidate)
        except Exception as exc:
            self._terminalize_scenario_clock_failure(exc)
            raise
        self.scenario_time = candidate

    def _terminalize_scenario_clock_failure(self, exc: Exception) -> None:
        self._dispatch_failed = True
        self._dispatch_failure = {
            "failure_phase": "scenario_clock_update",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:4096],
        }
        self.pause_scenario_time = True
        if hasattr(self, "events_queue"):
            self.events_queue.clear()
        logger = get_logger()
        try:
            logger.log_manual_entry(
                f"{type(exc).__name__}: {exc}", key="scenario_clock_failure"
            )
        except Exception:  # noqa: BLE001 - preserve the originating clock failure
            pass

    def update_active_plugins(self) -> None:
        for p in self.get_active_plugins():
            p.update(self.scenario_time)

    def update_joystick(self) -> None:
        # Execute the update method of the joystick
        if self.joystick is None:
            return

        self.joystick.update()
        # Check if there are active plugins...
        if len(self.get_active_plugins()) > 0:
            for p in self.get_active_plugins():
                # Send joystick inputs to appropriate plugin (tracking)
                if hasattr(p, "get_joystick_inputs"):
                    p.get_joystick_inputs(self.joystick.x, self.joystick.y)

                # ... if a joystick button has been just pressed/released
                # ... execute the according on_key_press method in active plugins
            if self.joystick.has_any_key_changed():
                for k, v in self.joystick.key_change.items():
                    if v == "press":
                        [p.on_joy_key_press(k) for p in self.get_active_plugins()]
                    elif v == "release":
                        [p.on_joy_key_release(k) for p in self.get_active_plugins()]

                    self.joystick.reset_key_change(k)

    def check_if_must_exit(self) -> None:
        # An empty due-event queue is not an empty scenario: delayed first starts
        # and idle gaps between task blocks legitimately have no active plugin.
        unfinished_events = any(event.done != 1 for event in self.events)
        if (
            len(self.get_active_plugins()) == 0
            and len(self.events_queue) == 0
            and not unfinished_events
        ):
            self.exit()
            return

        # If the windows has been killed, exit the program
        if not Window.MainWindow.alive:
            # Be careful to stop all the plugins in case they're not
            # (so we have a stop time for each plugin, in case we must compute this somewhere)
            for p_name, plugin in self.plugins.items():
                if plugin.alive:
                    stop_event: Event = Event(0, int(self.scenario_time), p_name, "stop")
                    self.execute_one_event(stop_event)
            self.exit(completion="window_closed")

    def execute_events(self) -> None:
        if getattr(self, "preflight_held", False):
            return
        # Operator holds survive the automatic release of participant prompts.
        if getattr(self, "_operator_paused", False):
            return
        if getattr(self, "_dispatch_failed", False):
            return
        # Detect a potential blocking plugin
        active_blocking_plugin: Any | None = self.get_active_blocking_plugin()

        # Execute scenario events in case the scenario timer is running
        if not self.is_scenario_time_paused():
            if active_blocking_plugin is None:
                # Drain due events by scheduled time then source line. Re-check the
                # modal/blocking state after each dispatch: an instruction or pause
                # event owns the UI before any later due event is allowed to run.
                while (event := self.get_event_at_scenario_time(self.scenario_time)) is not None:
                    self.execute_one_event(event)
                    blocker = self.get_active_blocking_plugin()
                    main_window = Window.MainWindow
                    if (main_window is not None and main_window.modal_dialog is not None) or (
                        blocker is not None and blocker.alive
                    ):
                        if blocker is not None and blocker.alive:
                            self._pause_for_blocking_plugin(blocker)
                        break

            # Check if a blocking plugin has started so to pause concurrent plugins
            elif active_blocking_plugin.alive:
                self._pause_for_blocking_plugin(active_blocking_plugin)

        # In Replay mode: IT IS the play/pause button that manages the scenario resuming
        elif active_blocking_plugin is None:
            if len(self.paused_plugins) > 0:
                self.execute_plugins_methods(self.paused_plugins, methods=["show", "resume"])
                self.paused_plugins = list()
            self.resume_scenario()

    def is_scenario_time_paused(self) -> bool:
        return self.pause_scenario_time

    def pause_scenario(self) -> bool:
        self.pause_scenario_time = True
        return self.is_scenario_time_paused()

    def resume_scenario(self) -> bool:
        if getattr(self, "preflight_held", False) or getattr(self, "_operator_paused", False):
            return True
        self.pause_scenario_time = False
        return self.is_scenario_time_paused()

    def toggle_scenario(self) -> bool:
        self.pause_scenario_time = not self.pause_scenario_time
        return self.is_scenario_time_paused()

    def get_active_blocking_plugin(self) -> Any | None:
        p: list[Any] = self.get_plugins_by_states(
            [("alive", True), ("blocking", True), ("paused", False)]
        )
        if len(p) > 0:
            return p[0]

    def get_active_non_blocking_plugins(self) -> list[Any]:
        return self.get_plugins_by_states(
            [("alive", True), ("blocking", False), ("paused", False)]
        )

    def _pause_for_blocking_plugin(self, blocking_plugin: Any) -> None:
        """Freeze experiment time in the same dispatch that starts a blocker."""
        if not blocking_plugin.alive or self.is_scenario_time_paused():
            return
        self.pause_scenario()
        self.paused_plugins = self.get_active_non_blocking_plugins()
        self.execute_plugins_methods(self.paused_plugins, methods=["pause", "hide"])

    def get_active_plugins(self) -> list[Any]:
        return self.get_plugins_by_states([("alive", True)])

    def execute_one_event(self, event: Event) -> None:
        if getattr(self, "preflight_held", False):
            return
        experiment_clock = getattr(self, "experiment_clock", None)
        if experiment_clock is None:
            experiment_clock = ExperimentClock(monotonic_ns=lambda: perf_counter_ns())
            self.experiment_clock = experiment_clock
        dispatch_experiment_time_ns = int(round(
            float(getattr(self, "scenario_time", event.time_sec)) * 1_000_000_000
        ))
        dispatch_start_monotonic_ns = perf_counter_ns()
        failure_phase = "clock_acquisition"
        try:
            dispatch_start_monotonic_ns = experiment_clock.observe(
                dispatch_experiment_time_ns
            ).host_monotonic_ns
            failure_phase = "command_dispatch"
            if event.plugin == SYSTEM_PSEUDO_PLUGIN:
                self._execute_system_command(event)
            else:
                # Set the plugin corresponding to the event
                plugin: Any = self.plugins[event.plugin]
                plugin._scenario_dispatch_context = {
                    "scheduled_time_s": event.time_sec,
                    "dispatch_time_s": getattr(self, "scenario_time", event.time_sec),
                    "source_line": event.line,
                }

                try:
                    # If one argument, assume it is a plugin method to execute
                    if len(event.command) == 1:
                        getattr(plugin, event.command[0])()

                    # If two arguments in the 'command' field, suppose a (parameter, value) to update
                    elif len(event.command) == 2:
                        plugin.set_parameter(event.command[0], event.command[1])
                    else:
                        raise ValueError(
                            "scenario event command must contain one or two fields"
                        )
                finally:
                    del plugin._scenario_dispatch_context
            failure_phase = "clock_acquisition"
            dispatch_end_monotonic_ns = experiment_clock.observe(
                dispatch_experiment_time_ns
            ).host_monotonic_ns
        except Exception as exc:
            try:
                dispatch_end_monotonic_ns = experiment_clock.observe(
                    dispatch_experiment_time_ns
                ).host_monotonic_ns
            except Exception:
                dispatch_end_monotonic_ns = max(
                    dispatch_start_monotonic_ns, perf_counter_ns()
                )
            # A failed command is terminal for this event and invalidates the
            # session. Clear the due batch and freeze state before touching the
            # logger so even a secondary sink failure cannot permit a retry.
            self._terminalize_dispatch_failure(
                event,
                exc,
                failure_phase=failure_phase,
            )
            try:
                get_logger().record_event_failure(
                    event,
                    dispatch_start_monotonic_ns=dispatch_start_monotonic_ns,
                    dispatch_end_monotonic_ns=dispatch_end_monotonic_ns,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    failure_phase=failure_phase,
                )
            except Exception as evidence_exc:  # noqa: BLE001 - preserve origin
                self._dispatch_failure["failure_evidence_status"] = "write_failed"
                self._dispatch_failure["failure_evidence_error"] = (
                    f"{type(evidence_exc).__name__}: {evidence_exc}"
                )[:4096]
            else:
                self._dispatch_failure["failure_evidence_status"] = "persisted"
            raise

        event.done = 1

        # The event can be logged whenever inside the method, since self.durations remain
        # constant all along it
        try:
            get_logger().record_event(
                event,
                dispatch_start_monotonic_ns=dispatch_start_monotonic_ns,
                dispatch_end_monotonic_ns=dispatch_end_monotonic_ns,
            )
        except Exception as exc:
            # The command already mutated runtime state, but no authoritative
            # event record exists. Freeze immediately; attempting another JSONL
            # write would only hit the logger's fail-stop state and could never
            # serve as scientific evidence for this failure.
            self._terminalize_dispatch_failure(
                event,
                exc,
                failure_phase="authoritative_event_logging",
            )
            raise

    def _terminalize_dispatch_failure(
        self,
        event: Event,
        exc: Exception,
        *,
        failure_phase: str,
    ) -> None:
        """Make any dispatch/logging failure an in-memory terminal state."""

        event.done = 1
        self._dispatch_failed = True
        self._dispatch_failure = {
            "scenario_line": event.line,
            "plugin": event.plugin,
            "command": list(event.command),
            "failure_phase": failure_phase,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:4096],
        }
        self.pause_scenario_time = True
        if hasattr(self, "events_queue"):
            self.events_queue.clear()

    def _execute_system_command(self, event: Event) -> None:
        command: str = event.command[0]
        if command == "pause":
            Window.MainWindow.pause_prompt()

    def execute_plugins_methods(self, plugins: list[Any], methods: str | list[str]) -> None:
        if len(plugins) == 0:
            return

        if isinstance(methods, str):
            methods = [methods]

        for m in methods:
            if getattr(self, "preflight_held", False) and m not in {"stop", "hide", "pause"}:
                continue
            for p in plugins:
                # self.execute_one_event(Event(0, 0, p.alias, m)) DO NOT create new events
                getattr(p, m)()

    def get_plugins_by_states(self, attribute_state_list: list[tuple[str, Any]]) -> list[Any]:
        plugins: dict[str, Any] = {k: p for k, p in self.plugins.items()}
        for attribute, state in attribute_state_list:
            plugins = {k: p for k, p in plugins.items() if getattr(p, attribute) == state}
        return [p for _, p in plugins.items()]

    def get_event_at_scenario_time(self, scenario_time: float) -> Event | None:
        # Once a due batch is materialized, drain it without repeatedly
        # rescanning/sorting the entire scenario for every event.
        if self.events_queue:
            return self.unqueue_event()

        # Retrieve (simultaneous) events matching scenario_duration_sec
        # We look to the most precise point in the near future that might matches a set of event time(s)
        events_time: list[Event] = [event for event in self.events if event.time_sec <= scenario_time]

        # Filter events that are either done or already in the queue
        events_time = [event for event in events_time if event.done != 1]

        # Task-oriented scenario files group sections by source line.  After a
        # frame stall, scheduled time must remain the primary ordering key.
        self.events_queue.extend(
            sorted(events_time, key=lambda x: (x.time_sec, x.line))
        )

        return self.unqueue_event()

    def unqueue_event(self) -> Event | None:
        if not isinstance(self.events_queue, deque):
            # Compatibility with external harnesses and older replay fixtures;
            # production queues remain deque-backed for O(1) batch draining.
            self.events_queue = deque(self.events_queue)
        if self.events_queue:
            return self.events_queue.popleft()

        return None

    def exit(self, *, completion: str = "completed") -> None:
        if getattr(self, "_exiting", False):
            return
        self._exiting = True
        Window.MainWindow.alive = False
        get_logger().log_manual_entry("end")
        get_logger().finalize_evidence(completion)
        if self.control_bridge is not None:
            self.control_bridge.emit(
                "finished",
                completion=completion,
                scenario_time_seconds=round(self.scenario_time, 3),
                session_csv=str(get_logger().path),
            )
        self.event_loop.exit()
        Window.MainWindow.close()  # needed for windows clean exit
        # Return through EventLoop.run so its platform stop/on_exit cleanup runs.
        # Raising SystemExit here interrupts that cleanup inside a clock callback.
