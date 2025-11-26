# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Automated training module for standardised familiarisation.

This plugin implements a ~7 minute training procedure based on USAARL MATB
protocols. It walks subjects through each subtask, input device, and scoring
rule before culminating in a short combined run.

Scenario commands:
    autotraining;start
    autotraining;phase;tracking|sysmon|communications|resman|combined
    autotraining;stop

Performance metrics emitted:
    training_phase_start, training_phase_complete, training_comprehension
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class TrainingPhase:
    """Represents a single training phase."""

    name: str
    description: str
    duration_seconds: float
    plugin_to_start: str
    instructions: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def is_active(self) -> bool:
        return self.started_at is not None and self.completed_at is None

    def is_complete(self) -> bool:
        return self.completed_at is not None

    def remaining(self, now: float) -> float:
        if not self.is_active() or self.started_at is None:
            return self.duration_seconds
        elapsed = now - self.started_at
        return max(0.0, self.duration_seconds - elapsed)


class Autotraining(AbstractPlugin):
    """Automated training procedure for MATB familiarisation."""

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'fullscreen',
        taskupdatetime: int = 500,
    ) -> None:
        super().__init__(label or _('Training'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'phaseduration': validation.is_positive_integer,
            'combinedduration': validation.is_positive_integer,
            'showscoring': validation.is_boolean,
        }

        self.parameters.update({
            'phaseduration': 60,      # seconds per single-task phase
            'combinedduration': 120,  # seconds for combined phase
            'showscoring': True,
        })

        self.phases: List[TrainingPhase] = []
        self.current_phase_index: int = -1
        self._widget: Optional[Simpletext] = None
        self._instruction_widget: Optional[Simpletext] = None
        self._timer_widget: Optional[Simpletext] = None
        self._comprehension_scores: Dict[str, bool] = {}

    def start(self) -> None:
        self._initialise_phases()
        super().start()
        self._start_next_phase()

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'title',
            Simpletext,
            container=self.task_container,
            text=_('MATB Training'),
            font_size=F['LARGE'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._instruction_widget = self.add_widget(
            'instructions',
            Simpletext,
            container=self.task_container,
            text=_('Preparing training sequence…'),
            font_size=F['MEDIUM'],
            y=0.6,
            wrap_width=0.9,
            color=C['WHITE'],
        )
        self._timer_widget = self.add_widget(
            'timer',
            Simpletext,
            container=self.task_container,
            text='',
            font_size=F['MEDIUM'],
            y=0.2,
            color=C['GREEN'],
        )

    def compute_next_plugin_state(self) -> bool:
        self._advance_phases()
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_display()
        return True

    # Scenario commands -------------------------------------------------
    def phase(self, payload: str) -> None:
        """Force start a specific phase by name."""
        phase_name = payload.strip().lower()
        for idx, phase in enumerate(self.phases):
            if phase.name.lower() == phase_name and not phase.is_complete():
                self.current_phase_index = idx - 1
                self._start_next_phase()
                break

    def comprehension(self, payload: str) -> None:
        """Record comprehension check result: phase_name,passed (1/0)."""
        parts = [p.strip() for p in payload.split(',')]
        if len(parts) >= 2:
            phase_name = parts[0]
            passed = parts[1] in ('1', 'true', 'True')
            self._comprehension_scores[phase_name] = passed
            self.log_performance('training_comprehension', f'{phase_name}:{int(passed)}')

    # Internal methods --------------------------------------------------
    def _initialise_phases(self) -> None:
        base_duration = float(self.parameters['phaseduration'])
        combined_duration = float(self.parameters['combinedduration'])

        self.phases = [
            TrainingPhase(
                name='tracking',
                description=_('Tracking Task: Use the joystick to keep the cursor centred.'),
                duration_seconds=base_duration,
                plugin_to_start='track',
                instructions=[
                    _('The tracking task simulates manual aircraft control.'),
                    _('Use the joystick to keep the circular cursor inside the target area.'),
                    _('The cursor will drift automatically; your job is to compensate.'),
                ],
            ),
            TrainingPhase(
                name='sysmon',
                description=_('System Monitoring: Respond to light and gauge anomalies.'),
                duration_seconds=base_duration,
                plugin_to_start='sysmon',
                instructions=[
                    _('Monitor the lights and gauges at the top-left.'),
                    _('Press F5 if the green light turns off.'),
                    _('Press F6 if the red light turns on.'),
                    _('Press F1–F4 if a gauge pointer moves outside the centre zone.'),
                ],
            ),
            TrainingPhase(
                name='communications',
                description=_('Communications: Tune radios to the requested frequencies.'),
                duration_seconds=base_duration,
                plugin_to_start='communications',
                instructions=[
                    _('Listen for audio messages addressed to your call sign.'),
                    _('Use UP/DOWN arrows to select the radio channel.'),
                    _('Use LEFT/RIGHT arrows to adjust the frequency.'),
                    _('Press ENTER to confirm your selection.'),
                ],
            ),
            TrainingPhase(
                name='resman',
                description=_('Resource Management: Maintain fuel levels in tanks A and B.'),
                duration_seconds=base_duration,
                plugin_to_start='resman',
                instructions=[
                    _('Keep tanks A and B near 2500 units each.'),
                    _('Use number keys 1–8 to toggle pumps on or off.'),
                    _('Pumps shown in red have failed and cannot be used.'),
                    _('Plan ahead: some tanks have limited capacity.'),
                ],
            ),
            TrainingPhase(
                name='combined',
                description=_('Combined Run: Perform all tasks simultaneously.'),
                duration_seconds=combined_duration,
                plugin_to_start='all',
                instructions=[
                    _('Now you will perform all four tasks at once.'),
                    _('Prioritise based on urgency and task demands.'),
                    _('This simulates the multitasking required in real operations.'),
                ],
            ),
        ]
        self.current_phase_index = -1

    def _start_next_phase(self) -> None:
        # Complete current phase if active
        if 0 <= self.current_phase_index < len(self.phases):
            current = self.phases[self.current_phase_index]
            if current.is_active():
                current.completed_at = self.scenario_time
                self.log_performance('training_phase_complete', current.name)

        # Move to next phase
        self.current_phase_index += 1
        if self.current_phase_index >= len(self.phases):
            self.log_performance('training_complete', 'all')
            self.stop()
            return

        next_phase = self.phases[self.current_phase_index]
        next_phase.started_at = self.scenario_time
        self.log_performance('training_phase_start', next_phase.name)

    def _advance_phases(self) -> None:
        if self.current_phase_index < 0 or self.current_phase_index >= len(self.phases):
            return
        current = self.phases[self.current_phase_index]
        if current.is_active() and current.remaining(self.scenario_time) <= 0:
            self._start_next_phase()

    def _update_display(self) -> None:
        if self._widget is None or self._instruction_widget is None or self._timer_widget is None:
            return

        if self.current_phase_index < 0 or self.current_phase_index >= len(self.phases):
            self._widget.set_text(_('Training Complete'))
            self._instruction_widget.set_text(_('You may now proceed to the experiment.'))
            self._timer_widget.set_text('')
            return

        current = self.phases[self.current_phase_index]
        self._widget.set_text(current.description)

        instructions_text = '\n'.join(f'• {instr}' for instr in current.instructions)
        self._instruction_widget.set_text(instructions_text)

        remaining = current.remaining(self.scenario_time)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        self._timer_widget.set_text(f'{minutes:02d}:{seconds:02d}')

    def get_response_timers(self) -> Optional[List[int]]:
        """No overdue feedback for training."""
        return None

