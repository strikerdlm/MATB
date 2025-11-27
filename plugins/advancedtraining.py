# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from plugins.abstractplugin import AbstractPlugin


@dataclass
class PhaseState:
    """Holds state for the active training phase."""

    name: str
    mode: str
    difficulty: str
    started_at: float
    sequence_label: str
    metrics: List[float] = field(default_factory=list)


class Advancedtraining(AbstractPlugin):
    """Guides multi-phase training blocks and logs performance variability."""

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'invisible',
        taskupdatetime: int = 1000,
    ) -> None:
        super().__init__(label or _('Advanced Training'), taskplacement, taskupdatetime)
        self.parameters.update({
            'phaseorder': 'single_easy,dual_easy,single_hard,dual_hard',
            'transferthreshold': 0.1,
        })
        self.sequence_index: int = 0
        self.sequence_label: str = 'default'
        self.current_phase: Optional[PhaseState] = None
        self.sequence: Sequence[Tuple[str, str]] = self._parse_phase_order()

    # Scenario commands --------------------------------------------------
    def start(self, payload: str) -> None:
        """Begin the default Easy→Hard sequence."""
        self._close_current_phase(note='auto-reset')
        self.sequence_index = 0
        self.sequence_label = payload.strip() or 'sequence'
        self.log_performance('training_sequence_start', self.sequence_label)
        self.sequence = self._parse_phase_order()
        self._start_next_phase()

    def next(self, payload: str) -> None:
        """Advance to the next configured phase."""
        self._close_current_phase(note='auto-advance')
        self._start_next_phase()

    def phase(self, payload: str) -> None:
        """
        payload: name,mode,difficulty
        Example: advancedtraining;phase;Easy Single,single,easy
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        self._close_current_phase()
        self._start_phase(parts[0], parts[1], parts[2])

    def metric(self, payload: str) -> None:
        """payload: numeric value representing performance score for current phase."""
        if self.current_phase is None:
            return
        try:
            value = float(payload)
        except (TypeError, ValueError):
            return
        self.current_phase.metrics.append(value)
        self.log_performance('training_metric', f'{self.current_phase.name}:{value:.3f}')

    def complete(self, payload: str) -> None:
        """payload: optional note/outcome string."""
        note = self._extract_note(payload)
        self._close_current_phase(note=note)

    def transfer(self, payload: str) -> None:
        """
        payload: numeric delta or keyword (positive|negative)
        Example: advancedtraining;transfer;0.12
        """
        token = (payload or '').strip()
        if not token:
            return
        threshold = float(self.parameters.get('transferthreshold', 0.1))
        verdict: Optional[str] = None
        try:
            delta = float(token)
            verdict = 'positive' if delta >= threshold else 'negative'
            detail = f'{delta:.3f}'
        except ValueError:
            verdict = token.lower()
            if verdict not in {'positive', 'negative'}:
                return
            detail = verdict
        self.log_performance('skill_transfer_detected', f'{verdict}:{detail}')

    # Helpers ------------------------------------------------------------
    def _start_next_phase(self) -> None:
        if not self.sequence:
            return
        desc = self.sequence[self.sequence_index % len(self.sequence)]
        mode, difficulty = desc
        phase_name = f'{mode.upper()}_{difficulty.upper()}'
        self.sequence_index += 1
        self._start_phase(phase_name, mode, difficulty)

    def _start_phase(self, name: str, mode: str, difficulty: str) -> None:
        self.current_phase = PhaseState(
            name=name,
            mode=mode,
            difficulty=difficulty,
            started_at=self.scenario_time,
            sequence_label=self.sequence_label,
        )
        self.log_performance(
            'training_phase_start',
            f'{name}:{mode}:{difficulty}:{self.sequence_label}',
        )

    def _close_current_phase(self, note: Optional[str] = None) -> None:
        if self.current_phase is None:
            return
        stats = self._compute_stats(self.current_phase.metrics)
        summary = (
            f'{self.current_phase.name}:{self.current_phase.mode}:{self.current_phase.difficulty};'
            f'mean={stats["mean"]:.3f};sd={stats["sd"]:.3f};rmssd={stats["rmssd"]:.3f};'
            f'n={stats["count"]};note={note or ""}'
        )
        self.log_performance('training_phase_complete', summary)
        self.current_phase = None

    def _compute_stats(self, values: Sequence[float]) -> dict[str, float]:
        if not values:
            return {'mean': 0.0, 'sd': 0.0, 'rmssd': 0.0, 'count': 0}
        count = float(len(values))
        mean = sum(values) / count
        variance = sum((v - mean) ** 2 for v in values) / count if count > 1 else 0.0
        sd = variance ** 0.5
        if len(values) > 1:
            diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
            rmssd = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
        else:
            rmssd = 0.0
        return {'mean': mean, 'sd': sd, 'rmssd': rmssd, 'count': len(values)}

    def _parse_phase_order(self) -> List[Tuple[str, str]]:
        order_str = str(self.parameters.get('phaseorder', 'single_easy,dual_easy,single_hard,dual_hard'))
        entries: List[Tuple[str, str]] = []
        for token in order_str.split(','):
            token = token.strip()
            if not token or '_' not in token:
                continue
            mode, difficulty = token.split('_', 1)
            entries.append((mode.strip(), difficulty.strip()))
        return entries or [('single', 'easy'), ('dual', 'easy'), ('single', 'hard'), ('dual', 'hard')]

    def _split(self, payload: str, expected: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    @staticmethod
    def _extract_note(payload: Optional[str]) -> Optional[str]:
        if payload is None:
            return None
        text = payload.strip()
        if not text:
            return None
        if '=' in text:
            key, value = text.split('=', 1)
            if key.strip().lower() == 'note':
                return value.strip()
        return text

