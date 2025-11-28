# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Real-Time HRV Monitoring Plugin for Combat Scenario Integration.

Computes and displays acute heart-rate-variability metrics from LSL streams,
with support for baseline calibration, z-score normalization, artifact rejection,
overload detection, and data export per Manual.md Section 18.

Research References:
    - Durantin et al. 2014: LF/HF may decrease at overload (DOI: 10.1016/j.bbr.2013.10.042)
    - Koskelo et al. 2024: Military flight HRV (DOI: 10.1016/j.apergo.2024.104370)
    - Makowski et al. 2021: NeuroKit2 (DOI: 10.3758/s13428-020-01516-y)

Implementation Credit: Dr Diego Malpica, Aerospace Medicine
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin

try:  # pragma: no cover - pylsl availability depends on runtime environment
    import pylsl
except ImportError:  # pragma: no cover
    pylsl = None


# Type aliases
RRInterval = Tuple[float, float]  # (timestamp, interval_seconds)
HRVMetrics = Dict[str, float]

# Artifact rejection thresholds (Kubios-style, per Manual.md Section 18.2.4)
MIN_RR_SEC = 0.300   # 300 ms minimum
MAX_RR_SEC = 2.000   # 2000 ms maximum
MAX_DELTA_PCT = 0.20  # 20% maximum change between successive intervals


@dataclass(frozen=True, slots=True)
class HRVSnapshot:
    """Immutable snapshot of HRV metrics at a point in time.
    
    Attributes:
        timestamp: Monotonic timestamp in seconds.
        hr: Heart rate in BPM.
        rmssd: Root mean square of successive differences (ms).
        sdnn: Standard deviation of NN intervals (ms).
        pnn50: Percentage of successive NN intervals differing >50ms.
        lf: Low-frequency power (0.04-0.15 Hz).
        hf: High-frequency power (0.15-0.40 Hz).
        lf_hf: LF/HF ratio.
        rmssd_zscore: Z-score of RMSSD vs baseline.
        lf_hf_zscore: Z-score of LF/HF vs baseline.
        workload_level: Categorical workload (low/medium/high/overload).
        is_alert: Whether acute alert is active.
        alert_reasons: List of alert trigger reasons.
    """
    timestamp: float
    hr: float
    rmssd: float
    sdnn: float
    pnn50: float
    lf: float
    hf: float
    lf_hf: float
    rmssd_zscore: float
    lf_hf_zscore: float
    workload_level: str
    is_alert: bool
    alert_reasons: Tuple[str, ...]


@dataclass
class BaselineStats:
    """Baseline statistics for z-score normalization.
    
    Attributes:
        rmssd_mean: Mean RMSSD during baseline.
        rmssd_std: Standard deviation of RMSSD during baseline.
        sdnn_mean: Mean SDNN during baseline.
        sdnn_std: Standard deviation of SDNN during baseline.
        lf_hf_mean: Mean LF/HF during baseline.
        lf_hf_std: Standard deviation of LF/HF during baseline.
        hr_mean: Mean heart rate during baseline.
        sample_count: Number of windows used for baseline.
        calibrated: Whether baseline has been calibrated.
    """
    rmssd_mean: float = 0.0
    rmssd_std: float = 1.0
    sdnn_mean: float = 0.0
    sdnn_std: float = 1.0
    lf_hf_mean: float = 1.0
    lf_hf_std: float = 0.5
    hr_mean: float = 70.0
    sample_count: int = 0
    calibrated: bool = False


class Physiomonitor(AbstractPlugin):
    """Real-time HRV monitoring with combat scenario integration.
    
    Features:
        - Rolling window HRV computation (RMSSD, SDNN, pNN50, LF, HF, LF/HF)
        - Baseline calibration with z-score normalization
        - Kubios-style artifact rejection
        - Durantin overload detection (quadratic LF/HF model)
        - Acute workload alerts with configurable thresholds
        - Data export to CSV/JSON for offline analysis
        - API for automation hooks integration
    
    Scenario Commands:
        - physiomonitor;start
        - physiomonitor;stop
        - physiomonitor;baseline;start (begin baseline collection)
        - physiomonitor;baseline;stop (finalize baseline)
        - physiomonitor;baseline;reset (clear baseline)
        - physiomonitor;threshold;rmssd,15 (set RMSSD alert threshold %)
        - physiomonitor;export;path (export current data)
    """

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'topright',
        taskupdatetime: int = 1000
    ) -> None:
        """Initialize Physio Monitor plugin.
        
        Args:
            label: Display label for the plugin.
            taskplacement: Widget placement location.
            taskupdatetime: Update interval in milliseconds.
        """
        super().__init__(label or _('Physio Monitor'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'streamname': validation.is_string,
            'windowseconds': validation.is_positive_integer,
            'baselineseconds': validation.is_positive_integer,
            'resampleseconds': validation.is_positive_float,
            'rmssdalertpct': validation.is_positive_float,
            'lfhfalertpct': validation.is_positive_float,
            'sdnnalertpct': validation.is_positive_float,
            'artifactrejection': validation.is_boolean,
            'overloaddetection': validation.is_boolean,
            'exportpath': validation.is_string,
        }

        self.parameters.update({
            'streamname': 'POLAR_H10_RR',
            'windowseconds': 30,
            'baselineseconds': 120,
            'resampleseconds': 0.5,
            'rmssdalertpct': 15.0,
            'lfhfalertpct': 20.0,
            'sdnnalertpct': 15.0,
            'artifactrejection': True,
            'overloaddetection': True,
            'exportpath': '',
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 500,
        })

        # Display widgets
        self._metrics_widget: Optional[Simpletext] = None
        self._status_widget: Optional[Simpletext] = None
        self._display_text: str = _('Waiting for HRV data…')
        self._status_text: str = ''
        
        # RR interval history with timestamps
        self._nn_history: Deque[RRInterval] = deque()
        self._last_valid_rr: Optional[float] = None
        
        # Baseline and metrics
        self._baseline: BaselineStats = BaselineStats()
        self._baseline_collecting: bool = False
        self._baseline_windows: List[HRVMetrics] = []
        self._current_metrics: HRVMetrics = {}
        self._current_snapshot: Optional[HRVSnapshot] = None
        
        # Overload detection state (Durantin model)
        self._lf_hf_history: Deque[float] = deque(maxlen=10)
        self._hr_history: Deque[float] = deque(maxlen=10)
        self._overload_detected: bool = False
        
        # Alert state
        self._alert_active: bool = False
        self._alert_reasons: List[str] = []
        
        # Timing and logging
        self._last_log_time: float = 0.0
        self._log_interval: float = 5.0
        self._min_samples: int = 5
        self._resolve_cooldown: float = 2.0
        self._next_resolve_time: float = 0.0
        
        # LSL inlet
        self._inlet: Optional['pylsl.StreamInlet'] = None
        
        # Data export
        self._export_rr: List[Dict] = []
        self._export_windows: List[Dict] = []
        self._export_alerts: List[Dict] = []
        self._artifact_count: int = 0
        self._total_count: int = 0

    def create_widgets(self) -> None:
        """Create display widgets for HRV metrics."""
        super().create_widgets()
        
        self._metrics_widget = self.add_widget(
            'metrics',
            Simpletext,
            container=self.task_container,
            text=self._display_text,
            font_size=F['SMALL'],
            x=0.05,
            y=0.75,
            wrap_width=0.9,
            color=C['WHITE'],
            bold=False,
        )
        
        self._status_widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=self._status_text,
            font_size=F['TINY'],
            x=0.05,
            y=0.15,
            wrap_width=0.9,
            color=C['GREY'],
            bold=False,
        )

    def do_on_command(self, command: str, value: str) -> None:
        """Handle scenario commands.
        
        Args:
            command: Command name.
            value: Command parameters.
        """
        if command == 'baseline':
            self._handle_baseline_command(value)
        elif command == 'threshold':
            self._handle_threshold_command(value)
        elif command == 'export':
            self._export_data(value if value else None)
        elif command == 'start':
            if not self.alive:
                self.start()
        elif command == 'stop':
            if self.alive:
                self.stop()

    def _handle_baseline_command(self, value: str) -> None:
        """Handle baseline collection commands.
        
        Args:
            value: 'start', 'stop', or 'reset'.
        """
        if value == 'start':
            self._baseline_collecting = True
            self._baseline_windows.clear()
            self.log_performance('baseline_start', 'collecting')
        elif value == 'stop':
            self._baseline_collecting = False
            self._finalize_baseline()
        elif value == 'reset':
            self._baseline = BaselineStats()
            self._baseline_windows.clear()
            self._baseline_collecting = False
            self.log_performance('baseline_reset', 'cleared')

    def _handle_threshold_command(self, value: str) -> None:
        """Handle threshold configuration commands.
        
        Args:
            value: 'metric,value' format (e.g., 'rmssd,15').
        """
        parts = value.split(',')
        if len(parts) != 2:
            return
            
        metric, threshold = parts[0].strip().lower(), parts[1].strip()
        
        try:
            threshold_val = float(threshold)
        except ValueError:
            return
            
        if metric == 'rmssd':
            self.parameters['rmssdalertpct'] = threshold_val
        elif metric == 'lfhf':
            self.parameters['lfhfalertpct'] = threshold_val
        elif metric == 'sdnn':
            self.parameters['sdnnalertpct'] = threshold_val
            
        self.log_performance('threshold_set', f'{metric}={threshold_val}')

    def compute_next_plugin_state(self) -> bool:
        """Update HRV metrics from LSL stream."""
        self._pull_samples()
        should_refresh = super().compute_next_plugin_state()
        if not should_refresh:
            return False
        self._update_metrics()
        return True

    def refresh_widgets(self) -> bool:
        """Update display widgets with current metrics."""
        if not super().refresh_widgets():
            return False
        if self._metrics_widget is not None:
            self._metrics_widget.set_text(self._display_text)
        if self._status_widget is not None:
            self._status_widget.set_text(self._status_text)
        return True

    def _pull_samples(self) -> None:
        """Pull RR interval samples from LSL stream."""
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
            quality = float(sample[1]) if len(sample) > 1 else 1.0
            
            self._total_count += 1
            
            # Apply artifact rejection if enabled
            if self.parameters['artifactrejection']:
                if self._is_artifact(interval):
                    self._artifact_count += 1
                    # Log artifact but don't add to history
                    self._export_rr.append({
                        'timestamp': timestamp,
                        'rr_sec': interval,
                        'quality': 0.0,
                        'artifact': True
                    })
                    continue
                    
            self._last_valid_rr = interval
            self._nn_history.append((timestamp, interval))
            
            # Store for export
            self._export_rr.append({
                'timestamp': timestamp,
                'rr_sec': interval,
                'quality': quality,
                'artifact': False
            })

        self._trim_history()

    def _extract_interval(self, sample: List[float]) -> Optional[float]:
        """Extract RR interval from LSL sample.
        
        Args:
            sample: LSL sample data.
            
        Returns:
            RR interval in seconds, or None if invalid.
        """
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

    def _is_artifact(self, interval_sec: float) -> bool:
        """Check if RR interval is an artifact using Kubios-style thresholds.
        
        Args:
            interval_sec: RR interval in seconds.
            
        Returns:
            True if the interval should be rejected.
        """
        # Physiological bounds check
        if interval_sec < MIN_RR_SEC or interval_sec > MAX_RR_SEC:
            return True
            
        # Successive difference check
        if self._last_valid_rr is not None:
            delta_ratio = abs(interval_sec - self._last_valid_rr) / self._last_valid_rr
            if delta_ratio > MAX_DELTA_PCT:
                return True
                
        return False

    def _resolve_inlet(self, now: float) -> None:
        """Resolve LSL stream inlet.
        
        Args:
            now: Current timestamp.
        """
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
        """Trim RR history to keep only relevant window."""
        if not self._nn_history:
            return
        horizon = float(max(self.parameters['windowseconds'], self.parameters['baselineseconds'])) * 2.0
        cutoff = self._nn_history[-1][0] - horizon
        while self._nn_history and self._nn_history[0][0] < cutoff:
            self._nn_history.popleft()

    def _update_metrics(self) -> None:
        """Compute and update HRV metrics."""
        if pylsl is None:
            self._display_text = _('pylsl is not available. Install pylsl to enable HRV monitoring.')
            self._current_metrics = {}
            self._set_alert(False, [])
            return

        window_intervals = self._recent_intervals(float(self.parameters['windowseconds']))
        if len(window_intervals) < self._min_samples:
            needed = self._min_samples - len(window_intervals)
            self._display_text = _('Waiting for HRV window ({} more samples)…').format(max(0, needed))
            self._status_text = self._format_status()
            self._current_metrics = {}
            self._set_alert(False, [])
            return

        metrics = self._compute_metrics(window_intervals)
        self._current_metrics = metrics
        
        # Collect baseline if in collection mode
        if self._baseline_collecting:
            self._baseline_windows.append(metrics.copy())
            
        # Compute z-scores and create snapshot
        snapshot = self._create_snapshot(metrics)
        self._current_snapshot = snapshot
        
        # Update displays
        self._display_text = self._format_metrics(metrics, snapshot)
        self._status_text = self._format_status()
        
        # Log metrics
        self._log_metrics(metrics, snapshot)
        
        # Evaluate alerts
        self._evaluate_alert(metrics, snapshot)
        
        # Store for export
        self._export_windows.append({
            'timestamp': snapshot.timestamp,
            **{k: round(v, 4) for k, v in metrics.items()},
            'rmssd_zscore': round(snapshot.rmssd_zscore, 4),
            'lf_hf_zscore': round(snapshot.lf_hf_zscore, 4),
            'workload_level': snapshot.workload_level,
            'is_alert': snapshot.is_alert,
            'overload_detected': self._overload_detected,
        })

    def _recent_intervals(self, seconds: float) -> List[float]:
        """Get recent RR intervals within time window.
        
        Args:
            seconds: Window duration in seconds.
            
        Returns:
            List of RR intervals in seconds.
        """
        if not self._nn_history:
            return []
        cutoff = self._nn_history[-1][0] - seconds
        return [interval for ts, interval in self._nn_history if ts >= cutoff]

    def _compute_metrics(self, intervals_sec: List[float]) -> HRVMetrics:
        """Compute HRV metrics from RR intervals.
        
        Args:
            intervals_sec: List of RR intervals in seconds.
            
        Returns:
            Dictionary of HRV metrics.
        """
        intervals_ms = [value * 1000.0 for value in intervals_sec]
        metrics: HRVMetrics = {}
        
        # Heart rate
        if intervals_sec:
            hr_values = [60.0 / rr for rr in intervals_sec if rr > 0]
            metrics['hr'] = statistics.mean(hr_values) if hr_values else 0.0
        else:
            metrics['hr'] = 0.0
            
        # Time-domain metrics
        metrics['rmssd'] = self._rmssd(intervals_ms)
        metrics['sdnn'] = self._sdnn(intervals_ms)
        metrics['pnn50'] = self._pnn50(intervals_ms)
        
        # Frequency-domain metrics
        lf, hf = self._frequency_metrics(intervals_sec)
        metrics['lf'] = lf
        metrics['hf'] = hf
        metrics['lf_hf'] = lf / hf if hf > 0 else 0.0
        
        return metrics

    def _rmssd(self, intervals_ms: List[float]) -> float:
        """Compute RMSSD (Root Mean Square of Successive Differences).
        
        Args:
            intervals_ms: RR intervals in milliseconds.
            
        Returns:
            RMSSD value in milliseconds.
        """
        if len(intervals_ms) < 2:
            return 0.0
        diffs = [(intervals_ms[i + 1] - intervals_ms[i]) for i in range(len(intervals_ms) - 1)]
        squares = [diff ** 2 for diff in diffs]
        mean_square = sum(squares) / len(squares)
        return math.sqrt(mean_square)

    def _sdnn(self, intervals_ms: List[float]) -> float:
        """Compute SDNN (Standard Deviation of NN intervals).
        
        Args:
            intervals_ms: RR intervals in milliseconds.
            
        Returns:
            SDNN value in milliseconds.
        """
        if len(intervals_ms) < 2:
            return 0.0
        return statistics.stdev(intervals_ms)

    def _pnn50(self, intervals_ms: List[float]) -> float:
        """Compute pNN50 (percentage of successive intervals differing >50ms).
        
        Args:
            intervals_ms: RR intervals in milliseconds.
            
        Returns:
            pNN50 as percentage.
        """
        if len(intervals_ms) < 2:
            return 0.0
        diffs = [abs(intervals_ms[i + 1] - intervals_ms[i]) for i in range(len(intervals_ms) - 1)]
        exceed = len([diff for diff in diffs if diff > 50.0])
        return (exceed / len(diffs)) * 100.0 if diffs else 0.0

    def _frequency_metrics(self, intervals_sec: List[float]) -> Tuple[float, float]:
        """Compute LF and HF power using DFT.
        
        Args:
            intervals_sec: RR intervals in seconds.
            
        Returns:
            Tuple of (LF power, HF power).
        """
        resample_step = max(float(self.parameters['resampleseconds']), 0.2)
        samples = self._resample_intervals(intervals_sec, resample_step)
        if len(samples) < self._min_samples:
            return 0.0, 0.0
        sample_rate = 1.0 / resample_step
        lf = self._band_power(samples, sample_rate, 0.04, 0.15)
        hf = self._band_power(samples, sample_rate, 0.15, 0.4)
        return lf, hf

    def _resample_intervals(self, intervals_sec: List[float], step_seconds: float) -> List[float]:
        """Resample RR intervals to uniform time grid for spectral analysis.
        
        Args:
            intervals_sec: RR intervals in seconds.
            step_seconds: Resampling step size.
            
        Returns:
            Resampled RR values in milliseconds.
        """
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
        """Compute power in frequency band using DFT.
        
        Args:
            samples: Resampled RR values.
            sample_rate: Sampling rate in Hz.
            low: Lower frequency bound.
            high: Upper frequency bound.
            
        Returns:
            Power in the specified band.
        """
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

    def _finalize_baseline(self) -> None:
        """Finalize baseline statistics from collected windows.
        
        Calibration only succeeds if at least one metric type (RMSSD, SDNN, 
        LF/HF, or HR) has ≥3 valid samples. This prevents marking baseline 
        as calibrated when using uncalibrated default values.
        """
        if len(self._baseline_windows) < 3:
            self.log_performance('baseline_error', f'insufficient_windows={len(self._baseline_windows)}')
            return
            
        rmssd_values = [w['rmssd'] for w in self._baseline_windows if w.get('rmssd', 0) > 0]
        sdnn_values = [w['sdnn'] for w in self._baseline_windows if w.get('sdnn', 0) > 0]
        lf_hf_values = [w['lf_hf'] for w in self._baseline_windows if w.get('lf_hf', 0) > 0]
        hr_values = [w['hr'] for w in self._baseline_windows if w.get('hr', 0) > 0]
        
        # Track which metrics were successfully calibrated
        metrics_calibrated = 0
        
        if len(rmssd_values) >= 3:
            self._baseline.rmssd_mean = statistics.mean(rmssd_values)
            self._baseline.rmssd_std = statistics.stdev(rmssd_values) if len(rmssd_values) > 1 else 1.0
            metrics_calibrated += 1
            
        if len(sdnn_values) >= 3:
            self._baseline.sdnn_mean = statistics.mean(sdnn_values)
            self._baseline.sdnn_std = statistics.stdev(sdnn_values) if len(sdnn_values) > 1 else 1.0
            metrics_calibrated += 1
            
        if len(lf_hf_values) >= 3:
            self._baseline.lf_hf_mean = statistics.mean(lf_hf_values)
            self._baseline.lf_hf_std = statistics.stdev(lf_hf_values) if len(lf_hf_values) > 1 else 0.5
            metrics_calibrated += 1
            
        if len(hr_values) >= 3:
            self._baseline.hr_mean = statistics.mean(hr_values)
            metrics_calibrated += 1
        
        # Only mark calibrated if at least one metric type met the minimum
        if metrics_calibrated == 0:
            self.log_performance('baseline_error', 
                f'no_valid_metrics,rmssd={len(rmssd_values)},sdnn={len(sdnn_values)},'
                f'lf_hf={len(lf_hf_values)},hr={len(hr_values)}')
            return
            
        self._baseline.sample_count = len(self._baseline_windows)
        self._baseline.calibrated = True
        
        self.log_performance('baseline_complete', 
            f'rmssd={self._baseline.rmssd_mean:.1f}±{self._baseline.rmssd_std:.1f},'
            f'lf_hf={self._baseline.lf_hf_mean:.2f}±{self._baseline.lf_hf_std:.2f},'
            f'samples={self._baseline.sample_count},metrics_calibrated={metrics_calibrated}')

    def _create_snapshot(self, metrics: HRVMetrics) -> HRVSnapshot:
        """Create immutable HRV snapshot with z-scores and workload classification.
        
        Args:
            metrics: Current HRV metrics.
            
        Returns:
            HRVSnapshot with computed z-scores and workload level.
        """
        now = self._now()
        
        # Compute z-scores
        rmssd_z = self._compute_zscore(
            metrics.get('rmssd', 0),
            self._baseline.rmssd_mean,
            self._baseline.rmssd_std
        )
        lf_hf_z = self._compute_zscore(
            metrics.get('lf_hf', 0),
            self._baseline.lf_hf_mean,
            self._baseline.lf_hf_std
        )
        
        # Track for overload detection
        hr = metrics.get('hr', 0)
        lf_hf = metrics.get('lf_hf', 0)
        if hr > 0:
            self._hr_history.append(hr)
        if lf_hf > 0:
            self._lf_hf_history.append(lf_hf)
            
        # Detect overload (Durantin model)
        self._detect_overload()
        
        # Classify workload level
        workload_level = self._classify_workload(rmssd_z, lf_hf_z)
        
        return HRVSnapshot(
            timestamp=now,
            hr=metrics.get('hr', 0),
            rmssd=metrics.get('rmssd', 0),
            sdnn=metrics.get('sdnn', 0),
            pnn50=metrics.get('pnn50', 0),
            lf=metrics.get('lf', 0),
            hf=metrics.get('hf', 0),
            lf_hf=lf_hf,
            rmssd_zscore=rmssd_z,
            lf_hf_zscore=lf_hf_z,
            workload_level=workload_level,
            is_alert=self._alert_active,
            alert_reasons=tuple(self._alert_reasons)
        )

    def _compute_zscore(self, value: float, mean: float, std: float) -> float:
        """Compute z-score with safe division.
        
        Args:
            value: Current value.
            mean: Baseline mean.
            std: Baseline standard deviation.
            
        Returns:
            Z-score (clamped to ±5).
        """
        if std <= 0 or not self._baseline.calibrated:
            return 0.0
        z = (value - mean) / std
        return max(-5.0, min(5.0, z))

    def _detect_overload(self) -> None:
        """Detect mental overload using Durantin's quadratic model.
        
        Key insight: LF/HF may DECREASE at extreme overload despite high HR,
        indicating parasympathetic withdrawal has reached its limit.
        """
        if not self.parameters['overloaddetection']:
            self._overload_detected = False
            return
            
        if len(self._hr_history) < 5 or len(self._lf_hf_history) < 5:
            self._overload_detected = False
            return
            
        # Check for pattern: HR increasing but LF/HF decreasing
        recent_hr = list(self._hr_history)[-5:]
        recent_lf_hf = list(self._lf_hf_history)[-5:]
        
        hr_trend = self._compute_trend(recent_hr)
        lf_hf_trend = self._compute_trend(recent_lf_hf)
        
        # Overload pattern: HR rising (>0.5 bpm/window) AND LF/HF falling (<-0.1/window)
        # while HR is elevated (>baseline + 10 bpm)
        current_hr = recent_hr[-1]
        hr_elevated = current_hr > (self._baseline.hr_mean + 10) if self._baseline.calibrated else current_hr > 85
        
        if hr_trend > 0.5 and lf_hf_trend < -0.1 and hr_elevated:
            if not self._overload_detected:
                self._overload_detected = True
                self.log_performance('hrv_overload', 
                    f'hr_trend={hr_trend:.2f},lf_hf_trend={lf_hf_trend:.2f},hr={current_hr:.0f}')
        else:
            if self._overload_detected:
                self.log_performance('hrv_overload_resolved', '')
            self._overload_detected = False

    def _compute_trend(self, values: List[float]) -> float:
        """Compute linear trend (slope) of values.
        
        Args:
            values: List of values.
            
        Returns:
            Slope (change per sample).
        """
        if len(values) < 2:
            return 0.0
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        return numerator / denominator if denominator > 0 else 0.0

    def _classify_workload(self, rmssd_z: float, lf_hf_z: float) -> str:
        """Classify workload level based on z-scores.
        
        Args:
            rmssd_z: RMSSD z-score (negative = higher workload).
            lf_hf_z: LF/HF z-score (positive = higher workload).
            
        Returns:
            Workload category: 'low', 'medium', 'high', or 'overload'.
        """
        if self._overload_detected:
            return 'overload'
            
        # Combined score: lower RMSSD and higher LF/HF = higher workload
        combined = -rmssd_z + lf_hf_z
        
        if combined < 0.5:
            return 'low'
        elif combined < 1.5:
            return 'medium'
        else:
            return 'high'

    def _evaluate_alert(self, metrics: HRVMetrics, snapshot: HRVSnapshot) -> None:
        """Evaluate alert conditions and update alert state.
        
        Args:
            metrics: Current HRV metrics.
            snapshot: Current HRV snapshot.
        """
        if not self._baseline.calibrated:
            self._set_alert(False, [])
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
        if self._overload_detected:
            alerts.append(_('Overload'))

        self._set_alert(bool(alerts), alerts)
        
        # Log alerts
        if alerts:
            alert_data = {
                'timestamp': snapshot.timestamp,
                'reasons': alerts,
                'rmssd': metrics.get('rmssd', 0),
                'lf_hf': metrics.get('lf_hf', 0),
                'rmssd_zscore': snapshot.rmssd_zscore,
                'workload_level': snapshot.workload_level,
            }
            self._export_alerts.append(alert_data)

    def _delta_below(self, key: str, metrics: HRVMetrics, threshold: float) -> bool:
        """Check if metric dropped below threshold vs baseline.
        
        Args:
            key: Metric name.
            metrics: Current metrics.
            threshold: Threshold percentage.
            
        Returns:
            True if metric dropped more than threshold.
        """
        baseline_val = getattr(self._baseline, f'{key}_mean', None)
        current = metrics.get(key)
        if baseline_val in (None, 0) or current is None:
            return False
        delta = ((current - baseline_val) / baseline_val) * 100.0
        return delta <= -abs(threshold)

    def _delta_above(self, key: str, metrics: HRVMetrics, threshold: float) -> bool:
        """Check if metric rose above threshold vs baseline.
        
        Args:
            key: Metric name.
            metrics: Current metrics.
            threshold: Threshold percentage.
            
        Returns:
            True if metric rose more than threshold.
        """
        baseline_val = getattr(self._baseline, f'{key}_mean', None)
        current = metrics.get(key)
        if baseline_val in (None, 0) or current is None:
            return False
        delta = ((current - baseline_val) / baseline_val) * 100.0
        return delta >= abs(threshold)

    def _set_alert(self, active: bool, reasons: List[str]) -> None:
        """Update alert state and visual feedback.
        
        Args:
            active: Whether alert is active.
            reasons: List of alert reasons.
        """
        self._alert_active = active
        self._alert_reasons = reasons
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = active
        if active and reasons:
            self.log_performance('hrv_alert', ','.join(reasons))

    def _format_metrics(self, metrics: HRVMetrics, snapshot: HRVSnapshot) -> str:
        """Format metrics for display.
        
        Args:
            metrics: Current HRV metrics.
            snapshot: Current HRV snapshot.
            
        Returns:
            Formatted display string.
        """
        rmssd = metrics.get('rmssd', 0.0)
        sdnn = metrics.get('sdnn', 0.0)
        lf_hf = metrics.get('lf_hf', 0.0)
        hr = metrics.get('hr', 0.0)
        
        # Format with z-scores if baseline available
        if self._baseline.calibrated:
            rmssd_str = f'{rmssd:.1f} (z={snapshot.rmssd_zscore:+.1f})'
            lf_hf_str = f'{lf_hf:.2f} (z={snapshot.lf_hf_zscore:+.1f})'
        else:
            rmssd_str = f'{rmssd:.1f}'
            lf_hf_str = f'{lf_hf:.2f}' if lf_hf > 0 else _('N/A')
            
        # Workload indicator
        workload_icons = {
            'low': '●○○○',
            'medium': '●●○○',
            'high': '●●●○',
            'overload': '●●●●'
        }
        workload_icon = workload_icons.get(snapshot.workload_level, '○○○○')
        
        status = _('ALERT: {}').format(', '.join(self._alert_reasons)) if self._alert_active else _('Stable')
        
        return (
            f"HR: {hr:.0f} bpm\n"
            f"RMSSD: {rmssd_str} ms\n"
            f"SDNN: {sdnn:.1f} ms\n"
            f"LF/HF: {lf_hf_str}\n"
            f"Load: {workload_icon} {snapshot.workload_level.upper()}\n"
            f"{status}"
        )

    def _format_status(self) -> str:
        """Format status line for display.
        
        Returns:
            Status string with baseline and artifact info.
        """
        parts = []
        
        if self._baseline_collecting:
            parts.append(_('Baseline: collecting ({} windows)').format(len(self._baseline_windows)))
        elif self._baseline.calibrated:
            parts.append(_('Baseline: calibrated'))
        else:
            parts.append(_('Baseline: not set'))
            
        if self._total_count > 0:
            artifact_pct = (self._artifact_count / self._total_count) * 100.0
            parts.append(_('Artifacts: {:.1f}%').format(artifact_pct))
            
        return ' | '.join(parts)

    def _log_metrics(self, metrics: HRVMetrics, snapshot: HRVSnapshot) -> None:
        """Log HRV metrics periodically.
        
        Args:
            metrics: Current HRV metrics.
            snapshot: Current HRV snapshot.
        """
        now = self._now()
        if now - self._last_log_time < self._log_interval:
            return
        self._last_log_time = now
        
        for key, value in metrics.items():
            self.log_performance(f'hrv_{key}', round(value, 4))
            
        self.log_performance('hrv_rmssd_zscore', round(snapshot.rmssd_zscore, 4))
        self.log_performance('hrv_lf_hf_zscore', round(snapshot.lf_hf_zscore, 4))
        self.log_performance('hrv_workload', snapshot.workload_level)

    def _export_data(self, path: Optional[str]) -> None:
        """Export HRV data to files.
        
        Args:
            path: Export directory path, or None to use default.
        """
        if path:
            export_dir = Path(path)
        elif self.parameters['exportpath']:
            export_dir = Path(self.parameters['exportpath'])
        else:
            export_dir = Path('sessions') / 'hrv_export'
            
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Export RR intervals
        rr_path = export_dir / f'rr_intervals_{timestamp}.csv'
        if self._export_rr:
            with open(rr_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'rr_sec', 'quality', 'artifact'])
                writer.writeheader()
                writer.writerows(self._export_rr)
            self.log_performance('hrv_export', f'rr_intervals={rr_path}')
            
        # Export HRV windows
        windows_path = export_dir / f'hrv_windows_{timestamp}.csv'
        if self._export_windows:
            fieldnames = list(self._export_windows[0].keys())
            with open(windows_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self._export_windows)
            self.log_performance('hrv_export', f'hrv_windows={windows_path}')
            
        # Export alerts
        alerts_path = export_dir / f'hrv_alerts_{timestamp}.json'
        if self._export_alerts:
            with open(alerts_path, 'w', encoding='utf-8') as f:
                json.dump(self._export_alerts, f, indent=2)
            self.log_performance('hrv_export', f'hrv_alerts={alerts_path}')
            
        # Export baseline
        baseline_path = export_dir / f'hrv_baseline_{timestamp}.json'
        if self._baseline.calibrated:
            baseline_data = {
                'rmssd_mean': self._baseline.rmssd_mean,
                'rmssd_std': self._baseline.rmssd_std,
                'sdnn_mean': self._baseline.sdnn_mean,
                'sdnn_std': self._baseline.sdnn_std,
                'lf_hf_mean': self._baseline.lf_hf_mean,
                'lf_hf_std': self._baseline.lf_hf_std,
                'hr_mean': self._baseline.hr_mean,
                'sample_count': self._baseline.sample_count,
            }
            with open(baseline_path, 'w', encoding='utf-8') as f:
                json.dump(baseline_data, f, indent=2)
            self.log_performance('hrv_export', f'hrv_baseline={baseline_path}')

    def _now(self) -> float:
        """Get current timestamp.
        
        Returns:
            Current time from LSL clock or monotonic clock.
        """
        if pylsl is not None:
            try:
                return pylsl.local_clock()
            except Exception:
                pass
        return time.monotonic()

    # Public API for automation hooks integration
    
    def get_latest_snapshot(self) -> Optional[HRVSnapshot]:
        """Get the most recent HRV snapshot for external queries.
        
        Returns:
            Current HRVSnapshot or None if not available.
        """
        return self._current_snapshot
    
    def get_baseline(self) -> BaselineStats:
        """Get current baseline statistics.
        
        Returns:
            BaselineStats object.
        """
        return self._baseline
    
    def is_overload_detected(self) -> bool:
        """Check if overload condition is currently detected.
        
        Returns:
            True if overload pattern detected.
        """
        return self._overload_detected
    
    def get_workload_level(self) -> str:
        """Get current workload level classification.
        
        Returns:
            Workload level string ('low', 'medium', 'high', 'overload').
        """
        if self._current_snapshot:
            return self._current_snapshot.workload_level
        return 'unknown'
