# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class Intruder:
    """Represents an individual conflict to resolve."""

    identifier: str
    bearing: str
    range_nm: float
    altitude_ft: float
    time_to_conflict: float
    created_at: float
    status: str = field(default='ACTIVE')
    action: Optional[str] = field(default=None)
    resolved_at: Optional[float] = field(default=None)

    def remaining(self, now: float) -> float:
        return max(0.0, self.time_to_conflict - (now - self.created_at))


GRID_SIZE = 12


class Senseandavoid(AbstractPlugin):
    """Provides intruder tracking and sense-and-avoid prompts."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Sense & Avoid'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'horizontalthresholdnm': validation.is_positive_float,
            'verticalthresholdft': validation.is_positive_integer,
        }

        self.parameters.update({
            'horizontalthresholdnm': 1.5,
            'verticalthresholdft': 500,
        })

        self.intruders: Dict[str, Intruder] = {}
        self._intruder_widget: Optional[Simpletext] = None
        self._geofence_widget: Optional[Simpletext] = None
        self.geofence_polygon: List[Tuple[float, float]] = []
        self.uav_positions: Dict[str, Tuple[float, float]] = {}
        self._breach_flags: Set[str] = set()

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 400,
        })

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('ID | Brg | RNG (nm) | ALT (ft) | TTI (s) | Status')
        self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._intruder_widget = self.add_widget(
            'intruders',
            Simpletext,
            container=self.task_container,
            text=_('Waiting for intruders…'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )
        self._geofence_widget = self.add_widget(
            'geofence_overlay',
            Simpletext,
            container=self.task_container,
            text=_('Geofence overlay inactive.'),
            font_size=F['SMALL'],
            y=0.3,
            wrap_width=0.95,
            color=C['GREEN'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_intruder_widget()
        self._update_overdue_state()
        self._update_geofence_widget()
        return True

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _update_intruder_widget(self) -> None:
        if self._intruder_widget is None:
            return
        if not self.intruders:
            self._intruder_widget.set_text(_('Waiting for intruders…'))
            return
        now = self.scenario_time
        # Sort by increasing time-to-impact for faster scan
        rows = []
        for intr in sorted(self.intruders.values(), key=lambda i: i.remaining(now)):
            remaining = intr.remaining(now)
            # 0–1 fraction based on original time_to_conflict (avoid altering logic)
            denom = max(1.0, float(intr.time_to_conflict))
            frac = remaining / denom
            bar = self.format_progress_bar(frac, length=10)
            row = (
                f"{intr.identifier:4} | {intr.bearing:>3} | "
                f"{intr.range_nm:4.1f} | {intr.altitude_ft:6.0f} | "
                f"{remaining:5.1f}s {bar} | {intr.status}"
            )
            rows.append(row)
        self._intruder_widget.set_text('\n'.join(rows))

    # Scenario commands -------------------------------------------------
    def spawn(self, payload: str) -> None:
        """
        Expect payload: id,bearing,range_nm,altitude_ft,time_to_conflict
        Example: senseandavoid;spawn;INTR1,090,2.1,300,-20
        """
        parts = self._split_payload(payload, min_parts=5)
        if not parts:
            return
        identifier = parts[0].upper()
        try:
            intruder = Intruder(
                identifier=identifier,
                bearing=parts[1],
                range_nm=float(parts[2]),
                altitude_ft=float(parts[3]),
                time_to_conflict=float(parts[4]),
                created_at=self.scenario_time,
            )
        except ValueError:
            return
        self.intruders[identifier] = intruder
        self.log_performance('saa_spawn', f'{identifier}:{intruder.range_nm}:{intruder.altitude_ft}')

    def resolve(self, payload: str) -> None:
        """
        Expect payload: id,action
        """
        parts = self._split_payload(payload, min_parts=2)
        if not parts:
            return
        identifier = parts[0].upper()
        if identifier not in self.intruders:
            return
        action = parts[1]
        intruder = self.intruders[identifier]
        intruder.status = 'RESOLVED'
        intruder.action = action
        intruder.resolved_at = self.scenario_time
        self.log_performance('saa_resolve', f'{identifier}:{action}:{self._resolution_time(intruder):.1f}')

    def clear(self, payload: str) -> None:
        identifier = payload.upper().strip()
        if identifier in self.intruders:
            del self.intruders[identifier]
            self.log_performance('saa_clear', identifier)

    def thresholds(self, payload: str) -> None:
        """
        Expect payload: horizontal_nm,vertical_ft
        """
        parts = self._split_payload(payload, min_parts=2)
        if not parts:
            return
        try:
            self.parameters['horizontalthresholdnm'] = float(parts[0])
            self.parameters['verticalthresholdft'] = int(float(parts[1]))
        except ValueError:
            return
        self.log_performance('saa_thresholds', f"{self.parameters['horizontalthresholdnm']}:{self.parameters['verticalthresholdft']}")

    def geofence(self, payload: str) -> None:
        """
        Define or clear the geofence polygon.
        Payload: list of x|y coordinate pairs in [0,1] (e.g., 0.1|0.1,0.9|0.1,...)
        Pass 'clear' to remove the geofence.
        """
        if not payload:
            return
        if payload.strip().lower() == 'clear':
            self.geofence_polygon = []
            if self._breach_flags:
                for label in list(self._breach_flags):
                    self.log_performance('geofence_recover', f'{label}:clear')
                self._breach_flags.clear()
            self.log_performance('geofence_config', 'cleared')
            return
        vertices = self._parse_geofence_vertices(payload)
        if len(vertices) < 3:
            return
        self.geofence_polygon = vertices
        self._breach_flags.clear()
        summary = ';'.join(f'{x:.2f}|{y:.2f}' for x, y in vertices)
        self.log_performance('geofence_config', summary)

    def position(self, payload: str) -> None:
        """
        Update a UAV position relative to the geofence overlay.
        Payload: label,x,y with coordinates normalized to [0,1].
        """
        parts = self._split_payload(payload, min_parts=3)
        if not parts:
            return
        label = parts[0].strip()
        try:
            x = self._clamp_unit(float(parts[1]))
            y = self._clamp_unit(float(parts[2]))
        except ValueError:
            return
        self.uav_positions[label] = (x, y)
        self._evaluate_geofence_state(label, (x, y))

    # Helpers -----------------------------------------------------------
    def _split_payload(self, payload: str, min_parts: int) -> Optional[list]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < min_parts:
            return None
        return parts

    def _parse_geofence_vertices(self, payload: str) -> List[Tuple[float, float]]:
        vertices: List[Tuple[float, float]] = []
        for token in payload.split(','):
            token = token.strip()
            if not token or '|' not in token:
                continue
            x_str, y_str = token.split('|', 1)
            try:
                x = float(x_str)
                y = float(y_str)
            except ValueError:
                continue
            vertices.append((self._clamp_unit(x), self._clamp_unit(y)))
        return vertices

    @staticmethod
    def _clamp_unit(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return max(0.0, min(1.0, value))

    def _update_intruder_widget(self) -> None:
        if self._intruder_widget is None:
            return
        if not self.intruders:
            self._intruder_widget.set_text(_('No intruders.'))
            return
        lines = []
        now = self.scenario_time
        for intruder in sorted(self.intruders.values(), key=lambda x: x.remaining(now)):
            remaining = intruder.remaining(now)
            status = _('ACTIVE') if intruder.status == 'ACTIVE' else _('RESOLVED')
            if intruder.action:
                status = f"{status}:{intruder.action}"
            line = (
                f"{intruder.identifier} | {intruder.bearing} | "
                f"{intruder.range_nm:.1f} | {intruder.altitude_ft:.0f} | "
                f"{remaining:5.1f} | {status}"
            )
            lines.append(line)
        self._intruder_widget.set_text('\n'.join(lines))

    def _evaluate_geofence_state(self, label: str, point: Tuple[float, float]) -> None:
        if not self.geofence_polygon:
            if label in self._breach_flags:
                self._breach_flags.discard(label)
                self.log_performance('geofence_recover', f'{label}:{point[0]:.3f}:{point[1]:.3f}')
            return
        inside = self._point_in_polygon(point)
        if inside:
            if label in self._breach_flags:
                self._breach_flags.discard(label)
                self.log_performance('geofence_recover', f'{label}:{point[0]:.3f}:{point[1]:.3f}')
        else:
            if label not in self._breach_flags:
                self._breach_flags.add(label)
                self.log_performance('geofence_breach', f'{label}:{point[0]:.3f}:{point[1]:.3f}')

    def _point_in_polygon(self, point: Tuple[float, float]) -> bool:
        if not self.geofence_polygon:
            return False
        x, y = point
        inside = False
        j = len(self.geofence_polygon) - 1
        for i, (xi, yi) in enumerate(self.geofence_polygon):
            xj, yj = self.geofence_polygon[j]
            intersects = (yi > y) != (yj > y)
            if intersects:
                denom = yj - yi
                if denom == 0:
                    denom = 1e-9
                x_intersect = (xj - xi) * (y - yi) / denom + xi
                if x < x_intersect:
                    inside = not inside
            j = i
        return inside

    def _update_geofence_widget(self) -> None:
        if self._geofence_widget is None:
            return
        if not self.geofence_polygon:
            self._geofence_widget.set_text(_('Geofence overlay inactive.'))
            return
        grid = self._build_geofence_grid()
        legend = self._build_uav_legend()
        if legend:
            self._geofence_widget.set_text(f'{grid}\n{legend}')
        else:
            self._geofence_widget.set_text(grid)

    def _build_geofence_grid(self) -> str:
        rows = [[' ' for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        if self.geofence_polygon:
            for gy in range(GRID_SIZE):
                for gx in range(GRID_SIZE):
                    px = (gx + 0.5) / GRID_SIZE
                    py = 1.0 - ((gy + 0.5) / GRID_SIZE)
                    if self._point_in_polygon((px, py)):
                        rows[gy][gx] = '.'
        for idx, (label, (x, y)) in enumerate(sorted(self.uav_positions.items())):
            symbol = str(idx % 10)
            col = min(GRID_SIZE - 1, max(0, int(x * GRID_SIZE)))
            row = min(GRID_SIZE - 1, max(0, int((1.0 - y) * GRID_SIZE)))
            rows[row][col] = symbol
        return '\n'.join(''.join(row) for row in rows)

    def _build_uav_legend(self) -> str:
        if not self.uav_positions:
            return ''
        entries: List[str] = []
        for idx, (label, (x, y)) in enumerate(sorted(self.uav_positions.items())):
            symbol = str(idx % 10)
            status = 'BRCH' if label in self._breach_flags else 'OK'
            entries.append(f"{symbol}={label}({x:.2f},{y:.2f})[{status}]")
        return ' '.join(entries)

    def _update_overdue_state(self) -> None:
        now = self.scenario_time
        conflict_overdue = any(
            intr.status == 'ACTIVE' and intr.remaining(now) <= 0 for intr in self.intruders.values()
        )
        overdue_active = conflict_overdue or bool(self._breach_flags)
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active
        if conflict_overdue:
            for intr in self.intruders.values():
                if intr.status == 'ACTIVE' and intr.remaining(now) <= 0:
                    self.log_performance('saa_overdue', intr.identifier)

    def _resolution_time(self, intruder: Intruder) -> float:
        if intruder.resolved_at is None:
            return 0.0
        return max(0.0, intruder.resolved_at - intruder.created_at)

