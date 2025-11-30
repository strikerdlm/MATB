# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class SensorState:
    """Represents a single sensor workload."""

    uav: str
    sensor: str
    target: str
    bandwidth: float
    priority: str
    status: str  # ACTIVE | IDLE | FUSION
    components: Tuple[str, ...] = tuple()


class Sensorresource(AbstractPlugin):
    """Manages multi-sensor payload bandwidth and priorities."""

    def __init__(self, label: str = '', taskplacement: str = 'bottommid', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('Sensor Resource Manager'), taskplacement, taskupdatetime)
        self.parameters.update({
            'linkcapacity': 60.0,
        })
        self.default_bandwidth = {
            'eo': 10.0,
            'ir': 15.0,
            'radar': 20.0,
            'lidar': 12.0,
        }
        self.pods: Dict[Tuple[str, str], SensorState] = {}
        self._widget: Optional[Simpletext] = None
        self._over_bandwidth_logged = False

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No sensors active.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def activate(self, payload: str) -> None:
        """
        payload: uav,sensor[,target][,bandwidth]
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        uav = parts[0]
        sensor = parts[1].lower()
        target = parts[2] if len(parts) > 2 else ''
        bandwidth = self._parse_bandwidth(parts[3]) if len(parts) > 3 else self.default_bandwidth.get(sensor, 10.0)
        key = (uav, sensor)
        self.pods[key] = SensorState(
            uav=uav,
            sensor=sensor,
            target=target,
            bandwidth=bandwidth,
            priority='normal',
            status='ACTIVE',
        )
        self.log_performance('sensor_activate', f'{uav}:{sensor}:{bandwidth}')
        self._check_capacity()
        self._update_widget()

    def standby(self, payload: str) -> None:
        """payload: uav,sensor"""
        parts = self._split(payload, 2)
        if parts is None:
            return
        key = (parts[0], parts[1].lower())
        state = self.pods.get(key)
        if state is None:
            return
        self.pods[key] = replace(state, status='IDLE', bandwidth=0.0)
        self.log_performance('sensor_standby', f'{key[0]}:{key[1]}')
        self._check_capacity()
        self._update_widget()

    def priority(self, payload: str) -> None:
        """payload: uav,sensor,level"""
        parts = self._split(payload, 3)
        if parts is None:
            return
        key = (parts[0], parts[1].lower())
        state = self.pods.get(key)
        if state is None:
            return
        self.pods[key] = replace(state, priority=parts[2])
        self.log_performance('sensor_priority', f'{key[0]}:{key[1]}:{parts[2]}')
        self._update_widget()

    def switch(self, payload: str) -> None:
        """payload: uav,source_to_dest"""
        parts = self._split(payload, 2)
        if parts is None:
            return
        uav = parts[0]
        switch_parts = [p.strip() for p in parts[1].split('_to_')]
        if len(switch_parts) != 2:
            return
        src, dest = switch_parts[0], switch_parts[1]
        state = self.pods.pop((uav, src), None)
        if state is None:
            return
        new_bandwidth = self.default_bandwidth.get(dest, state.bandwidth)
        new_state = SensorState(
            uav=uav,
            sensor=dest,
            target=state.target,
            bandwidth=new_bandwidth,
            priority=state.priority,
            status=state.status,
        )
        self.pods[(uav, dest)] = new_state
        self.log_performance('sensor_switch', f'{uav}:{src}->{dest}')
        self._check_capacity()
        self._update_widget()

    def fusion(self, payload: str) -> None:
        """
        payload: uav,sensors_combo[,target]
        sensors_combo example: eo_ir
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        uav = parts[0]
        components = tuple(comp.strip().lower() for comp in parts[1].split('_') if comp.strip())
        if not components:
            return
        target = parts[2] if len(parts) > 2 else ''
        bandwidth = sum(self.default_bandwidth.get(comp, 10.0) for comp in components)
        key = (uav, '+'.join(components))
        self.pods[key] = SensorState(
            uav=uav,
            sensor='+'.join(components),
            target=target,
            bandwidth=bandwidth,
            priority='high',
            status='FUSION',
            components=components,
        )
        self.log_performance('sensor_fusion_enable', f'{uav}:{self.pods[key].sensor}:{bandwidth}')
        self._check_capacity()
        self._update_widget()

    def capacity(self, payload: str) -> None:
        """payload: value"""
        try:
            capacity = float(payload)
        except (TypeError, ValueError):
            return
        self.parameters['linkcapacity'] = max(10.0, capacity)
        self.log_performance('sensor_capacity', self.parameters['linkcapacity'])
        self._check_capacity()
        self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.pods:
            self._widget.set_text(_('No sensors active.'))
            return

        load = self._current_load()
        capacity = float(self.parameters['linkcapacity'])
        if capacity > 0.0:
            link_fraction = max(0.0, min(1.0, load / capacity))
        else:
            link_fraction = 0.0
        link_bar = self.format_progress_bar(link_fraction, length=10)

        lines = [
            _('Capacity {0:.1f} Mbps | Load {1:.1f} Mbps {2}').format(
                capacity,
                load,
                link_bar,
            )
        ]
        for state in self.pods.values():
            if capacity > 0.0 and state.status != 'IDLE' and state.bandwidth > 0.0:
                bw_fraction = max(0.0, min(1.0, state.bandwidth / capacity))
                bw_bar = self.format_progress_bar(bw_fraction, length=8)
                bar_suffix = f' {bw_bar}'
            else:
                bar_suffix = ''
            lines.append(
                f'{state.uav}:{state.sensor} [{state.status}] '
                f'{state.bandwidth:.1f} Mbps {state.priority}{bar_suffix}'
            )
        self._widget.set_text('\\n'.join(lines))

    def _current_load(self) -> float:
        return sum(state.bandwidth for state in self.pods.values() if state.status != 'IDLE')

    def _check_capacity(self) -> None:
        load = self._current_load()
        capacity = float(self.parameters['linkcapacity'])
        if load > capacity:
            if not self._over_bandwidth_logged:
                self._over_bandwidth_logged = True
                self.log_performance('sensor_bandwidth_exceeded', f'{load:.1f}/{capacity:.1f}')
        else:
            self._over_bandwidth_logged = False

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    @staticmethod
    def _parse_bandwidth(value: str) -> float:
        try:
            return max(0.0, float(value))
        except ValueError:
            return 0.0


