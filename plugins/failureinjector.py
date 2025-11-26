# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core import validation
from plugins.abstractplugin import AbstractPlugin


@dataclass
class FailureEvent:
    target: str
    method: str
    argument: Optional[str]
    fire_at: float
    jitter: float = 0.0
    executed: bool = False


class Failureinjector(AbstractPlugin):
    """Automatically injects failures or automation commands into other plugins."""

    def __init__(self, label: str = '', taskplacement: str = 'invisible', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('Failure Injector'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'enablelogging': validation.is_boolean,
        }

        self.parameters.update({
            'enablelogging': True,
        })

        self.events: list[FailureEvent] = []

    def start(self) -> None:
        self.events = []
        super().start()

    def update(self, scenario_time: float) -> None:
        super().update(scenario_time)
        for event in self.events:
            if event.executed:
                continue
            if scenario_time >= event.fire_at:
                self._execute_event(event)

    # Scenario commands -------------------------------------------------
    def schedule(self, payload: str) -> None:
        """
        payload: target_plugin,method,arg_payload,delay_seconds[,jitter]
        Example: failureinjector;schedule;emergencystack,trigger,HYD1|HYD PRESS LOW|Switch pumps|Check breakers,15
        """
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < 4:
            return
        target, method, args_str = parts[0], parts[1], parts[2]
        try:
            delay = float(parts[3])
        except ValueError:
            return
        jitter = 0.0
        if len(parts) > 4:
            try:
                jitter = float(parts[4])
            except ValueError:
                jitter = 0.0
        argument = args_str.replace('|', ',') if args_str else None
        fire_at = self.scenario_time + delay
        self.events.append(FailureEvent(target, method, argument, fire_at, jitter))
        self.log_performance('failure_schedule', f'{target}:{method}:{delay}')

    def clear(self, payload: str) -> None:
        self.events = []
        self.log_performance('failure_clear', payload or 'all')

    # Internal ----------------------------------------------------------
    def _execute_event(self, event: FailureEvent) -> None:
        if self.scheduler is None:
            return
        plugin = self.scheduler.plugins.get(event.target)
        if plugin is None:
            return
        try:
            method = getattr(plugin, event.method)
        except AttributeError:
            return
        try:
            if event.argument:
                method(event.argument)
            else:
                method()
            event.executed = True
            if self.parameters['enablelogging']:
                self.log_performance('failure_execute', f'{event.target}:{event.method}')
        except Exception as exc:  # pragma: no cover
            if self.parameters['enablelogging']:
                self.log_performance('failure_error', str(exc))

