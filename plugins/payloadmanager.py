# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class SensorState:
    name: str
    target: str = ''
    bandwidth: float = 0.0  # Mbps
    energy: float = 100.0  # %
    status: str = 'IDLE'  # IDLE, ACTIVE, DEPLETED


class Payloadmanager(AbstractPlugin):
    """Manages sensor payload energy/bandwidth budgets."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomleft', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Payload Manager'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'sensors': validation.is_string,
            'capacitymbps': validation.is_positive_float,
            'consumptionpersec': validation.is_positive_float,
            'rechargepersec': validation.is_positive_float,
        }

        self.parameters.update({
            'sensors': 'CamA,CamB,IRST,Lidar',
            'capacitymbps': 40.0,
            'consumptionpersec': 2.5,
            'rechargepersec': 1.0,
        })

        self.sensors: Dict[str, SensorState] = {}
        self._widget: Optional[Simpletext] = None
        self._last_update_time: float = 0.0

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 450,
        })

    # Lifecycle --------------------------------------------------------
    def start(self) -> None:
        self._initialise_sensors()
        self._last_update_time = self.scenario_time
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        # Instructions at top
        self.add_widget(
            'help',
            Simpletext,
            container=self.task_container,
            text=_('SOLO MONITOREO - Estado de sensores'),
            font_size=F['TINY'],
            y=0.95,
            color=C['GREY'],
            wrap_width=0.95,
        )
        self._widget = self.add_widget(
            'summary',
            Simpletext,
            container=self.task_container,
            text=_('Sin sensores activos'),
            font_size=F['SMALL'],
            y=0.55,
            wrap_width=0.95,
            color=C['BLACK'],
        )

    def compute_next_plugin_state(self) -> bool:
        self._tick_energy_budget()
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        self._update_overdue()
        return True

    # Scenario commands ------------------------------------------------
    def activate(self, payload: str) -> None:
        """
        payload: sensor,target,bandwidth
        """
        parts = self._split(payload, 3)
        if not parts:
            return
        sensor = self._canonical_sensor(parts[0])
        if sensor not in self.sensors:
            return
        try:
            bandwidth = max(0.0, float(parts[2]))
        except ValueError:
            return
        state = self.sensors[sensor]
        state.status = 'ACTIVE' if state.energy > 0 else 'DEPLETED'
        state.target = parts[1]
        state.bandwidth = bandwidth
        self.log_performance('payload_activate', f'{sensor}:{state.target}:{state.bandwidth}')

    def standby(self, payload: str) -> None:
        sensor = self._canonical_sensor(payload)
        if sensor not in self.sensors:
            return
        state = self.sensors[sensor]
        state.status = 'IDLE' if state.energy > 0 else 'DEPLETED'
        state.target = ''
        state.bandwidth = 0.0
        self.log_performance('payload_standby', sensor)

    def priority(self, payload: str) -> None:
        """
        payload: sensor,bandwidth
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        sensor = self._canonical_sensor(parts[0])
        if sensor not in self.sensors:
            return
        try:
            bandwidth = max(0.0, float(parts[1]))
        except ValueError:
            return
        self.sensors[sensor].bandwidth = bandwidth
        self.log_performance('payload_priority', f'{sensor}:{bandwidth}')

    def recharge(self, payload: str) -> None:
        sensor = self._canonical_sensor(payload)
        if sensor not in self.sensors:
            return
        state = self.sensors[sensor]
        state.energy = 100.0
        if state.status == 'DEPLETED':
            state.status = 'IDLE'
        self.log_performance('payload_recharge', sensor)

    def capacity(self, payload: str) -> None:
        try:
            capacity = max(1.0, float(payload))
        except (TypeError, ValueError):
            return
        self.parameters['capacitymbps'] = capacity
        self.log_performance('payload_capacity', capacity)

    def apply_platform_profile(self, platform_name: str, config: Mapping[str, object]) -> None:
        """Allow other plugins to push platform-specific constraints."""
        sensors = config.get('sensors')
        capacity = config.get('datalink_mbps')
        updated = False
        if sensors:
            sensor_labels = self._normalise_sensor_list(sensors)
            if sensor_labels:
                self.parameters['sensors'] = ','.join(sensor_labels)
                self.sensors = {label: SensorState(label) for label in sensor_labels}
                updated = True
        if capacity is not None:
            try:
                numeric = max(1.0, float(capacity))
            except (TypeError, ValueError):
                numeric = None
            if numeric is not None:
                self.parameters['capacitymbps'] = numeric
                updated = True
        if updated and self._widget is not None:
            self._update_widget()
        if updated:
            self.log_performance('payload_platform_profile', platform_name)

    # Helpers -----------------------------------------------------------
    def _initialise_sensors(self) -> None:
        labels = [name.strip() for name in self.parameters['sensors'].split(',') if name.strip()]
        self.sensors = {label: SensorState(label) for label in labels}

    def _canonical_sensor(self, name: str) -> str:
        name = name.strip()
        for key in self.sensors.keys():
            if key.lower() == name.lower():
                return key
        return name

    def _split(self, payload: str, expected: int) -> Optional[list]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    def _normalise_sensor_list(self, sensors: object) -> Sequence[str]:
        if isinstance(sensors, str):
            tokens = [token.strip() for token in sensors.replace('/', ',').split(',')]
        elif isinstance(sensors, Sequence):
            tokens = [str(token).strip() for token in sensors]
        else:
            tokens = []
        return [token for token in tokens if token]

    def _tick_energy_budget(self) -> None:
        now = self.scenario_time
        dt = max(0.0, now - self._last_update_time)
        self._last_update_time = now
        consumption = float(self.parameters['consumptionpersec'])
        recharge = float(self.parameters['rechargepersec'])

        for sensor in self.sensors.values():
            if sensor.status == 'ACTIVE':
                sensor.energy = max(0.0, sensor.energy - consumption * dt)
                if sensor.energy == 0.0:
                    sensor.status = 'DEPLETED'
                    sensor.target = ''
                    sensor.bandwidth = 0.0
                    self.log_performance('payload_depleted', sensor.name)
            else:
                sensor.energy = min(100.0, sensor.energy + recharge * dt)
                if sensor.status == 'DEPLETED' and sensor.energy >= 5.0:
                    sensor.status = 'IDLE'

    def _total_bandwidth(self) -> float:
        return sum(sensor.bandwidth for sensor in self.sensors.values())

    def _update_widget(self) -> None:
        if self._widget is None:
            return

        if not self.sensors:
            self._widget.set_text(_('Sin sensores activos'))
            return

        total_bw = self._total_bandwidth()
        capacity = float(self.parameters['capacitymbps'])

        lines = []
        for sensor in self.sensors.values():
            target = sensor.target if sensor.target else 'Sin objetivo'
            status_es = {'IDLE': 'ESPERA', 'ACTIVE': 'ACTIVO', 'DEPLETED': 'AGOTADO'}.get(sensor.status, sensor.status)
            line = f"{sensor.name}: {target} - Energía: {sensor.energy:.0f}% - {status_es}"
            lines.append(line)

        lines.append(f"Ancho banda: {total_bw:.0f}/{capacity:.0f} Mbps")
        self._widget.set_text('\n'.join(lines))

    def _update_overdue(self) -> None:
        capacity = float(self.parameters['capacitymbps'])
        over_capacity = self._total_bandwidth() > capacity + 1e-6
        depleted_active = any(sensor.status == 'DEPLETED' for sensor in self.sensors.values())
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = over_capacity or depleted_active

        if over_capacity:
            self.log_performance('payload_overbandwidth', self._total_bandwidth())
        if depleted_active:
            depleted = ','.join(sensor.name for sensor in self.sensors.values() if sensor.status == 'DEPLETED')
            self.log_performance('payload_overdue', depleted)

