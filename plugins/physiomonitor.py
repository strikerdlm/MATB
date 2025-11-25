# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin

try:  # pragma: no cover - pylsl availability depends on runtime environment
    import pylsl
except ImportError:  # pragma: no cover
    pylsl = None

RRInterval = Tuple[float, float]  # (timestamp, interval_seconds)
HRVMetrics = Dict[str, float]


class Physiomonitor(AbstractPlugin):
    """Displays acute heart-rate-variability metrics sourced from an LSL stream."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Physio Monitor'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'streamname': validation.is_string,
            'windowseconds': validation.is_positive_integer,
            'baselineseconds': validation.is_positive_integer,
            'resampleseconds': validation.is_positive_float,
            'rmssdalertpct': validation.is_positive_float,
            'lfhfalertpct': validation.is_positive_float,
            'sdnnalertpct': validation.is_positive_float,
        }

        self.parameters.update({
            'streamname': 'HRV-RR',
            'windowseconds': 30,
            'baselineseconds': 120,
            'resampleseconds': 0.5,
            'rmssdalertpct': 15.0,
            'lfhfalertpct': 20.0,
            'sdnnalertpct': 15.0,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 500,
        })

        self._metrics_widget: Optional[Simpletext] = None
        self._display_text: str = _('Waiting for HRV data…')
        self._nn_history: Deque[RRInterval] = deque()
        self._baseline_metrics: HRVMetrics = dict()
        self._current_metrics: HRVMetrics = dict()
        self._alert_active: bool = False
        self._last_log_time: float = 0.0
        self._log_interval: float = 5.0
        self._min_samples: int = 5
        self._resolve_cooldown: float = 2.0
        self._next_resolve_time: float = 0.0
        self._inlet: Optional['pylsl.StreamInlet'] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        self._metrics_widget = self.add_widget(
            'metrics',
            Simpletext,
            container=self.task_container,
            text=self._display_text,
            font_size=F['SMALL'],
            x=0.05,
            y=0.8,
            wrap_width=0.9,
            color=C['WHITE'],
            bold=False,
        )

    def compute_next_plugin_state(self) -> bool:
        self._pull_samples()
        should_refresh = super().compute_next_plugin_state()
        if not should_refresh:
            return False
        self._update_metrics()
        return True

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        if self._metrics_widget is not None:
            self._metrics_widget.set_text(self._display_text)
        return True

    def _pull_samples(self) -> None:
        if pylsl is None or self.parameters['streamname'] == '':
            return

        now = self._now()
        if self._inlet is None and now >= self._next_resolve_time:
            self._resolve_inlet(now)

        if self._inlet is None:
            return

        try:
            chunk, timestamps = self._inlet.pull_chunk(timeout=0.0)
        except Exception:
            self._inlet = None
            return

        for sample, ts in zip(chunk, timestamps):
            interval = self._extract_interval(sample)
            if interval is None:
                continue
            timestamp = float(ts) if ts is not None else now
            self._nn_history.append((timestamp, interval))

        self._trim_history()

    def _extract_interval(self, sample: List[float]) -> Optional[float]:
        if not sample:
            return None
        try:
            interval = float(sample[0])
        except (TypeError, ValueError):
            return None
        if interval <= 0:
            return None
        # Streams may emit milliseconds; convert to seconds if needed.
        return interval / 1000.0 if interval > 5 else interval

    def _resolve_inlet(self, now: float) -> None:
        self._next_resolve_time = now + self._resolve_cooldown
        try:
            streams = pylsl.resolve_stream('name', self.parameters['streamname'], timeout=0.0)
        except Exception:
            return
        if not streams:
            return
        try:
            self._inlet = pylsl.StreamInlet(
                streams[0],
                processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter,
            )
        except Exception:
            self._inlet = None

    def _trim_history(self) -> None:
        if not self._nn_history:
            return
        horizon = float(max(self.parameters['windowseconds'], self.parameters['baselineseconds'])) * 2.0
        cutoff = self._nn_history[-1][0] - horizon
        while self._nn_history and self._nn_history[0][0] < cutoff:
            self._nn_history.popleft()

    def _update_metrics(self) -> None:
        if pylsl is None:
            self._display_text = _('pylsl is not available. Install pylsl to enable HRV monitoring.')
            self._current_metrics = dict()
            self._set_alert(False, '')
            return

        window_intervals = self._recent_intervals(float(self.parameters['windowseconds']))
        if len(window_intervals) < self._min_samples:
            needed = self._min_samples - len(window_intervals)
            self._display_text = _('Waiting for HRV window ({} more samples)…').format(max(0, needed))
            self._current_metrics = dict()
            self._set_alert(False, '')
            return

        metrics = self._compute_metrics(window_intervals)
        self._current_metrics = metrics
        self._initialize_baseline_if_needed()
        self._display_text = self._format_metrics(metrics)
        self._log_metrics(metrics)
        self._evaluate_alert(metrics)

    def _recent_intervals(self, seconds: float) -> List[float]:
        if not self._nn_history:
            return []
        cutoff = self._nn_history[-1][0] - seconds
        return [interval for ts, interval in self._nn_history if ts >= cutoff]

    def _initialize_baseline_if_needed(self) -> None:
        if self._baseline_metrics:
            return
        baseline_intervals = self._recent_intervals(float(self.parameters['baselineseconds']))
        if len(baseline_intervals) < self._min_samples * 2:
            return
        self._baseline_metrics = self._compute_metrics(baseline_intervals)

    def _compute_metrics(self, intervals_sec: List[float]) -> HRVMetrics:
        intervals_ms = [value * 1000.0 for value in intervals_sec]
        metrics: HRVMetrics = dict()
        metrics['rmssd'] = self._rmssd(intervals_ms)
        metrics['sdnn'] = self._sdnn(intervals_ms)
        metrics['pnn50'] = self._pnn50(intervals_ms)
        lf, hf = self._frequency_metrics(intervals_sec)
        metrics['lf'] = lf
        metrics['hf'] = hf
        metrics['lf_hf'] = lf / hf if hf > 0 else 0.0
        return metrics

    def _rmssd(self, intervals_ms: List[float]) -> float:
        if len(intervals_ms) < 2:
            return 0.0
        diffs = [(intervals_ms[i + 1] - intervals_ms[i]) for i in range(len(intervals_ms) - 1)]
        squares = [diff ** 2 for diff in diffs]
        mean_square = sum(squares) / len(squares)
        return math.sqrt(mean_square)

    def _sdnn(self, intervals_ms: List[float]) -> float:
        if len(intervals_ms) < 2:
            return 0.0
        return statistics.stdev(intervals_ms)

    def _pnn50(self, intervals_ms: List[float]) -> float:
        if len(intervals_ms) < 2:
            return 0.0
        diffs = [abs(intervals_ms[i + 1] - intervals_ms[i]) for i in range(len(intervals_ms) - 1)]
        exceed = len([diff for diff in diffs if diff > 50.0])
        return (exceed / len(diffs)) * 100.0 if diffs else 0.0

    def _frequency_metrics(self, intervals_sec: List[float]) -> Tuple[float, float]:
        resample_step = max(float(self.parameters['resampleseconds']), 0.2)
        samples = self._resample_intervals(intervals_sec, resample_step)
        if len(samples) < self._min_samples:
            return 0.0, 0.0
        sample_rate = 1.0 / resample_step
        lf = self._band_power(samples, sample_rate, 0.04, 0.15)
        hf = self._band_power(samples, sample_rate, 0.15, 0.4)
        return lf, hf

    def _resample_intervals(self, intervals_sec: List[float], step_seconds: float) -> List[float]:
        if len(intervals_sec) < 2:
            return []
        cumulative: List[float] = []
        total = 0.0
        for value in intervals_sec:
            total += value
            cumulative.append(total)

        start = cumulative[0]
        end = cumulative[-1]
        if end <= start:
            return []

        resampled: List[float] = []
        sample_time = start
        index = 0
        max_samples = 512
        while sample_time <= end and len(resampled) < max_samples:
            while index < len(cumulative) - 1 and cumulative[index + 1] < sample_time:
                index += 1
            if index == len(cumulative) - 1:
                value = intervals_sec[index]
            else:
                span = cumulative[index + 1] - cumulative[index]
                if span <= 0:
                    value = intervals_sec[index]
                else:
                    ratio = (sample_time - cumulative[index]) / span
                    start_val = intervals_sec[index]
                    end_val = intervals_sec[index + 1]
                    value = start_val + ratio * (end_val - start_val)
            resampled.append(value * 1000.0)
            sample_time += step_seconds
        return resampled

    def _band_power(self, samples: List[float], sample_rate: float, low: float, high: float) -> float:
        n = len(samples)
        if n < 2:
            return 0.0
        mean_value = sum(samples) / n
        centered = [value - mean_value for value in samples]
        power = 0.0
        half = n // 2
        if half == 0:
            return 0.0
        for k in range(1, half):
            freq = (k * sample_rate) / n
            if freq < low or freq >= high:
                continue
            real = 0.0
            imag = 0.0
            for t, sample in enumerate(centered):
                angle = 2.0 * math.pi * k * t / n
                real += sample * math.cos(angle)
                imag -= sample * math.sin(angle)
            power += (real ** 2 + imag ** 2) / n
        return power

    def _format_metrics(self, metrics: HRVMetrics) -> str:
        rmssd = metrics.get('rmssd', 0.0)
        sdnn = metrics.get('sdnn', 0.0)
        lf_hf = metrics.get('lf_hf', 0.0)
        lfhf_text = '{:.2f}'.format(lf_hf) if lf_hf > 0 else _('N/A')
        rmssd_str = '{:.1f}'.format(rmssd)
        sdnn_str = '{:.1f}'.format(sdnn)
        deltas = self._delta_summary(metrics)
        status_line = _('Status: {}').format(_('Stable') if not self._alert_active else _('Acute load'))
        return (
            f"RMSSD: {rmssd_str} ms ({deltas.get('rmssd', '')})\n"
            f"SDNN: {sdnn_str} ms ({deltas.get('sdnn', '')})\n"
            f"LF/HF: {lfhf_text} ({deltas.get('lf_hf', '')})\n"
            f"{status_line}"
        )

    def _delta_summary(self, metrics: HRVMetrics) -> Dict[str, str]:
        if not self._baseline_metrics:
            return {}
        summary: Dict[str, str] = {}
        for key in ('rmssd', 'sdnn', 'lf_hf'):
            baseline = self._baseline_metrics.get(key)
            current = metrics.get(key)
            if baseline in (None, 0) or current is None:
                continue
            delta = ((current - baseline) / baseline) * 100.0
            summary[key] = '{:+.0f}%'.format(delta)
        return summary

    def _evaluate_alert(self, metrics: HRVMetrics) -> None:
        if not self._baseline_metrics:
            self._set_alert(False, '')
            return
        rmssd_threshold = float(self.parameters['rmssdalertpct'])
        lfhf_threshold = float(self.parameters['lfhfalertpct'])
        sdnn_threshold = float(self.parameters['sdnnalertpct'])

        alerts: List[str] = []
        if self._delta_below('rmssd', metrics, rmssd_threshold):
            alerts.append(_('RMSSD drop'))
        if self._delta_above('lf_hf', metrics, lfhf_threshold):
            alerts.append(_('LF/HF rise'))
        if self._delta_below('sdnn', metrics, sdnn_threshold):
            alerts.append(_('SDNN drop'))

        self._set_alert(bool(alerts), ', '.join(alerts))

    def _delta_below(self, key: str, metrics: HRVMetrics, threshold: float) -> bool:
        baseline = self._baseline_metrics.get(key)
        current = metrics.get(key)
        if baseline in (None, 0) or current is None:
            return False
        delta = ((current - baseline) / baseline) * 100.0
        return delta <= -abs(threshold)

    def _delta_above(self, key: str, metrics: HRVMetrics, threshold: float) -> bool:
        baseline = self._baseline_metrics.get(key)
        current = metrics.get(key)
        if baseline in (None, 0) or current is None:
            return False
        delta = ((current - baseline) / baseline) * 100.0
        return delta >= abs(threshold)

    def _set_alert(self, active: bool, reason: str) -> None:
        self._alert_active = active
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = active
        if active and reason:
            self.log_performance('hrv_alert', reason)

    def _log_metrics(self, metrics: HRVMetrics) -> None:
        now = self._now()
        if now - self._last_log_time < self._log_interval:
            return
        self._last_log_time = now
        for key, value in metrics.items():
            self.log_performance(f'hrv_{key}', round(value, 4))

    def _now(self) -> float:
        if pylsl is not None:
            try:
                return pylsl.local_clock()
            except Exception:
                pass
        return time.monotonic()

