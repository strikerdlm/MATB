# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Polar H10 RR Interval Streaming Plugin.

Streams RR intervals from a Polar H10 chest strap via BLE into LSL for
downstream HRV analysis. Implements auto-reconnect, battery monitoring,
signal quality tracking, and monotonic timestamps per Manual.md Section 18.2.

Research Reference:
    - Polar H10 validated for HRV research (Villani et al. 2020, DOI: 10.1109/ACCESS.2020.3001355)
    - BLE SDK: https://github.com/polarofficial/polar-ble-sdk
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from plugins.abstractplugin import AbstractPlugin
from core import validation

try:  # pragma: no cover - optional dependency
    from bleak import BleakClient, BleakScanner  # type: ignore
    from bleak.exc import BleakError  # type: ignore
except ImportError:  # pragma: no cover
    BleakClient = None
    BleakScanner = None
    BleakError = Exception

try:  # pragma: no cover - optional dependency
    import pylsl
except ImportError:  # pragma: no cover
    pylsl = None


# Polar H10 BLE UUIDs
HR_MEASUREMENT_UUID = '00002a37-0000-1000-8000-00805f9b34fb'
BATTERY_LEVEL_UUID = '00002a19-0000-1000-8000-00805f9b34fb'

# Artifact rejection thresholds (Kubios-style, per Manual.md Section 18.2.4)
MIN_RR_MS = 300   # Minimum physiologically plausible RR interval
MAX_RR_MS = 2000  # Maximum physiologically plausible RR interval
MAX_DELTA_PCT = 0.20  # Maximum change between successive intervals (20%)

# Reconnection parameters
MAX_RECONNECT_ATTEMPTS = 10
INITIAL_BACKOFF_SEC = 1.0
MAX_BACKOFF_SEC = 30.0


@dataclass(frozen=True, slots=True)
class RRPacket:
    """Immutable RR interval data packet per Manual.md specification.
    
    Attributes:
        timestamp_ms: Monotonic timestamp in milliseconds.
        rr_ms: RR interval in milliseconds.
        quality: Signal quality score (0.0-1.0).
    """
    timestamp_ms: int
    rr_ms: int
    quality: float


class Polarrlink(AbstractPlugin):
    """Streams RR intervals from a Polar H10 belt into LSL for downstream plugins.
    
    Features:
        - Auto-reconnect with exponential backoff on BLE disconnection
        - Battery level monitoring and logging
        - Signal quality estimation based on artifact rate
        - Monotonic timestamps for reproducibility
        - Artifact rejection using Kubios-style thresholds
    
    Scenario Commands:
        - polarrlink;set;deviceid,XX:XX:XX:XX:XX:XX
        - polarrlink;start
        - polarrlink;stop
        - polarrlink;scan (logs discovered Polar devices)
    """

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'invisible',
        taskupdatetime: int = 1000
    ) -> None:
        """Initialize Polar RR Link plugin.
        
        Args:
            label: Display label for the plugin.
            taskplacement: Widget placement (default invisible).
            taskupdatetime: Update interval in milliseconds.
        """
        super().__init__(label or _('Polar RR Link'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'deviceid': validation.is_string,
            'lslstreamname': validation.is_string,
            'autoreconnect': validation.is_boolean,
            'maxreconnectattempts': validation.is_positive_integer,
            'artifactrejection': validation.is_boolean,
        }

        self.parameters.update({
            'deviceid': '',
            'lslstreamname': 'POLAR_H10_RR',
            'autoreconnect': True,
            'maxreconnectattempts': MAX_RECONNECT_ATTEMPTS,
            'artifactrejection': True,
        })

        # Threading and async loop
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # LSL streaming
        self._stream_info: Optional['pylsl.StreamInfo'] = None
        self._stream_outlet: Optional['pylsl.StreamOutlet'] = None
        
        # Connection state
        self._connected: bool = False
        self._reconnect_count: int = 0
        self._battery_level: int = -1
        self._last_battery_check: float = 0.0
        self._battery_check_interval: float = 60.0  # Check every 60 seconds
        self._battery_history: List[Dict[str, Any]] = []
        
        # Signal quality tracking
        self._recent_rr: Deque[RRPacket] = deque(maxlen=100)
        self._artifact_count: int = 0
        self._total_count: int = 0
        self._last_valid_rr: Optional[int] = None
        
        # Timing
        self._start_time_mono: float = 0.0
        self._last_log_time: float = 0.0
        self._log_interval: float = 30.0  # Log status every 30 seconds
        self._start_time_epoch: Optional[float] = None
        self._stop_time_epoch: Optional[float] = None

    def start(self) -> None:
        """Start the Polar H10 connection and LSL streaming."""
        if BleakClient is None:
            self.log_performance('polar_error', 'bleak_not_installed')
            print(_('Polar RR link requires the bleak package. Install with: pip install bleak'))
            return
            
        if pylsl is None:
            self.log_performance('polar_error', 'pylsl_not_installed')
            print(_('Polar RR link requires the pylsl package. Install with: pip install pylsl'))
            return
            
        if not self.parameters['deviceid']:
            self.log_performance('polar_error', 'no_device_id')
            print(_('Polar RR link requires a deviceid (MAC address or UUID). Use scan command to find devices.'))
            return
        
        super().start()
        self._stop_event.clear()
        self._start_time_mono = time.monotonic()
        self._reconnect_count = 0
        self._artifact_count = 0
        self._total_count = 0
        self._last_valid_rr = None
        self._recent_rr.clear()
        self._battery_history.clear()
        current_time = time.monotonic()
        self._last_battery_check = current_time - self._battery_check_interval
        self._last_log_time = current_time - self._log_interval
        self._start_time_epoch = time.time()
        self._stop_time_epoch = None
        
        # Create LSL stream
        self._create_lsl_stream()
        
        # Start BLE thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='PolarBLEThread')
        self._thread.start()
        
        self.log_performance('polar_start', self.parameters['deviceid'])

    def stop(self) -> None:
        """Stop the Polar H10 connection and LSL streaming."""
        self._stop_event.set()
        
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:
                pass  # Loop already stopped
                
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            
        self._thread = None
        self._loop = None
        self._stream_outlet = None
        self._stream_info = None
        self._connected = False
        self._stop_time_epoch = time.time()
        try:
            self._write_metadata(self._default_export_dir())
        except OSError as exc:  # pragma: no cover - filesystem errors
            self.log_performance('polar_error', f'metadata_error={type(exc).__name__}')
        
        # Log final statistics
        if self._total_count > 0:
            artifact_rate = (self._artifact_count / self._total_count) * 100.0
            self.log_performance('polar_stop', f'artifacts={artifact_rate:.1f}%,total={self._total_count}')
        else:
            self.log_performance('polar_stop', 'no_data_received')
            
        super().stop()

    def do_on_command(self, command: str, value: str) -> None:
        """Handle scenario commands.
        
        Args:
            command: Command name (set, start, stop, scan).
            value: Command parameters.
        """
        if command == 'scan':
            self._start_scan()
        elif command == 'set':
            parts = value.split(',', 1)
            if len(parts) == 2:
                param_name, param_value = parts[0].strip(), parts[1].strip()
                if param_name in self.parameters:
                    self.set_parameter(param_name, param_value)
        elif command == 'start':
            if not self.alive:
                self.start()
        elif command == 'stop':
            if self.alive:
                self.stop()

    def _create_lsl_stream(self) -> None:
        """Create the LSL outlet for RR interval streaming."""
        if pylsl is None:
            return
            
        self._stream_info = pylsl.StreamInfo(
            name=self.parameters['lslstreamname'],
            type='RR',
            channel_count=2,  # [rr_ms, quality]
            nominal_srate=0.0,  # Irregular rate
            channel_format='float32',
            source_id=f'polar-h10-{self.parameters["deviceid"]}'
        )
        
        # Add metadata
        channels = self._stream_info.desc().append_child('channels')
        ch1 = channels.append_child('channel')
        ch1.append_child_value('label', 'RR_ms')
        ch1.append_child_value('unit', 'milliseconds')
        ch2 = channels.append_child('channel')
        ch2.append_child_value('label', 'Quality')
        ch2.append_child_value('unit', 'ratio')
        
        self._stream_outlet = pylsl.StreamOutlet(self._stream_info)

    def _run_loop(self) -> None:
        """Main BLE event loop running in separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._connection_manager())
        except Exception as exc:  # pragma: no cover
            self.log_performance('polar_error', f'loop_exception={type(exc).__name__}')
            print(_('Polar RR link stopped: {}').format(exc))
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _connection_manager(self) -> None:
        """Manage BLE connection with auto-reconnect."""
        backoff = INITIAL_BACKOFF_SEC
        
        while not self._stop_event.is_set():
            try:
                await self._connect_and_stream()
                backoff = INITIAL_BACKOFF_SEC  # Reset backoff on successful connection
                
            except BleakError as exc:
                self._connected = False
                self.log_performance('polar_disconnect', f'reason={type(exc).__name__}')
                
                if not self.parameters['autoreconnect']:
                    break
                    
                self._reconnect_count += 1
                max_attempts = int(self.parameters['maxreconnectattempts'])
                
                if self._reconnect_count > max_attempts:
                    self.log_performance('polar_error', f'max_reconnects_exceeded={max_attempts}')
                    break
                
                self.log_performance('polar_reconnect', f'attempt={self._reconnect_count},backoff={backoff:.1f}s')
                
                # Wait with exponential backoff
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SEC)
                
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log_performance('polar_error', f'unexpected={type(exc).__name__}')
                break

    async def _connect_and_stream(self) -> None:
        """Connect to Polar H10 and stream RR intervals."""
        device_id = self.parameters['deviceid']
        
        async with BleakClient(device_id, timeout=20.0) as client:
            self._connected = True
            self.log_performance('polar_connect', device_id)
            
            # Read initial battery level
            await self._check_battery(client)
            
            # Subscribe to heart rate measurement
            await client.start_notify(HR_MEASUREMENT_UUID, self._handle_hr_measurement)
            
            try:
                while not self._stop_event.is_set() and client.is_connected:
                    await asyncio.sleep(0.25)
                    
                    # Periodic battery check
                    now = time.monotonic()
                    if now - self._last_battery_check >= self._battery_check_interval:
                        await self._check_battery(client)
                        
                    # Periodic status log
                    if now - self._last_log_time >= self._log_interval:
                        self._log_status()
                        self._last_log_time = now
                        
            finally:
                try:
                    await client.stop_notify(HR_MEASUREMENT_UUID)
                except Exception:
                    pass

    async def _check_battery(self, client: 'BleakClient') -> None:
        """Read and log battery level from Polar H10.
        
        Args:
            client: Connected BleakClient instance.
        """
        try:
            battery_data = await asyncio.wait_for(
                client.read_gatt_char(BATTERY_LEVEL_UUID),
                timeout=5.0
            )
            if battery_data:
                self._battery_level = int(battery_data[0])
                self.log_performance('polar_battery', self._battery_level)
                self._last_battery_check = time.monotonic()
                self._battery_history.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'battery_percent': self._battery_level,
                })
        except asyncio.TimeoutError:
            self.log_performance('polar_warning', 'battery_read_timeout')
        except Exception as exc:
            self.log_performance('polar_warning', f'battery_read_failed={type(exc).__name__}')

    def _handle_hr_measurement(self, _sender: int, data: bytearray) -> None:
        """Handle incoming heart rate measurement BLE notification.
        
        Parses the HR measurement characteristic per Bluetooth SIG spec,
        extracts RR intervals, applies artifact rejection, and streams to LSL.
        
        Args:
            _sender: BLE characteristic handle (unused).
            data: Raw BLE data packet.
        """
        if self._stream_outlet is None or not data:
            return
            
        timestamp_mono = time.monotonic()
        timestamp_ms = int((timestamp_mono - self._start_time_mono) * 1000)
        
        # Parse flags byte
        flags = data[0]
        offset = 1
        
        # HR value format (bit 0): 0 = uint8, 1 = uint16
        if flags & 0x01:
            offset += 2  # Skip 16-bit HR
        else:
            offset += 1  # Skip 8-bit HR
            
        # Sensor contact status (bits 1-2) - used for quality estimation
        sensor_contact_supported = bool(flags & 0x04)
        sensor_contact_detected = bool(flags & 0x02) if sensor_contact_supported else True
        
        # Energy expended (bit 3) - skip if present
        if flags & 0x08:
            offset += 2
            
        # RR intervals present (bit 4)
        if not (flags & 0x10):
            return  # No RR intervals in this packet
            
        # Extract RR intervals (each is 16-bit little-endian, units of 1/1024 sec)
        while offset + 1 < len(data):
            rr_raw = int.from_bytes(data[offset:offset + 2], byteorder='little')
            offset += 2
            
            # Convert to milliseconds (raw is in 1/1024 second units)
            rr_ms = int((rr_raw / 1024.0) * 1000.0)
            
            if rr_ms <= 0:
                continue
                
            self._total_count += 1
            
            # Apply artifact rejection if enabled
            quality = 1.0 if sensor_contact_detected else 0.5
            is_artifact = False
            
            if self.parameters['artifactrejection']:
                is_artifact = self._is_artifact(rr_ms)
                if is_artifact:
                    self._artifact_count += 1
                    quality = 0.0
                else:
                    self._last_valid_rr = rr_ms
            else:
                self._last_valid_rr = rr_ms
                
            # Create packet and store
            packet = RRPacket(
                timestamp_ms=timestamp_ms,
                rr_ms=rr_ms,
                quality=quality
            )
            self._recent_rr.append(packet)
            
            # Stream to LSL (even artifacts, but with quality=0)
            if self._stream_outlet is not None:
                self._stream_outlet.push_sample([float(rr_ms), quality])

    def _is_artifact(self, rr_ms: int) -> bool:
        """Check if RR interval is an artifact using Kubios-style thresholds.
        
        Args:
            rr_ms: RR interval in milliseconds.
            
        Returns:
            True if the interval should be rejected as an artifact.
        """
        # Physiological bounds check
        if rr_ms < MIN_RR_MS or rr_ms > MAX_RR_MS:
            return True
            
        # Successive difference check
        if self._last_valid_rr is not None:
            delta_ratio = abs(rr_ms - self._last_valid_rr) / self._last_valid_rr
            if delta_ratio > MAX_DELTA_PCT:
                return True
                
        return False

    def _log_status(self) -> None:
        """Log periodic status update."""
        if self._total_count == 0:
            return
            
        artifact_rate = (self._artifact_count / self._total_count) * 100.0
        quality = self._compute_signal_quality()
        
        self.log_performance(
            'polar_status',
            f'connected={self._connected},battery={self._battery_level},'
            f'quality={quality:.2f},artifacts={artifact_rate:.1f}%,'
            f'count={self._total_count}'
        )

    def _compute_signal_quality(self) -> float:
        """Compute overall signal quality score (0.0-1.0).
        
        Returns:
            Signal quality as ratio of valid intervals in recent window.
        """
        if not self._recent_rr:
            return 0.0
            
        valid_count = sum(1 for p in self._recent_rr if p.quality > 0)
        return valid_count / len(self._recent_rr)

    def _default_export_dir(self) -> Path:
        """Resolve default HRV export directory."""
        path_param = self.parameters.get('exportpath')
        if path_param:
            return Path(path_param).expanduser()
        session_dir = getattr(self.logger, 'session_dir', None)
        if session_dir:
            return Path(session_dir) / 'hrv'
        return Path('sessions') / 'hrv_export'

    def _write_metadata(self, export_dir: Path) -> None:
        """Persist Polar device metadata for the session."""
        export_dir.mkdir(parents=True, exist_ok=True)
        start_iso = (
            datetime.fromtimestamp(self._start_time_epoch, tz=timezone.utc).isoformat()
            if self._start_time_epoch
            else None
        )
        stop_iso = (
            datetime.fromtimestamp(self._stop_time_epoch, tz=timezone.utc).isoformat()
            if self._stop_time_epoch
            else None
        )
        duration = None
        if self._start_time_epoch and self._stop_time_epoch:
            duration = max(0.0, self._stop_time_epoch - self._start_time_epoch)

        artifact_rate = None
        if self._total_count > 0:
            artifact_rate = (self._artifact_count / self._total_count) * 100.0

        provenance, _ = self.logger.get_provenance_snapshot()
        metadata = {
            'device_id': self.parameters.get('deviceid'),
            'lsl_stream': self.parameters.get('lslstreamname'),
            'start_time': start_iso,
            'stop_time': stop_iso,
            'duration_seconds': duration,
            'total_rr_samples': self._total_count,
            'artifact_rate_percent': artifact_rate,
            'mean_quality': round(self._compute_signal_quality(), 4),
            'reconnect_attempts': self._reconnect_count,
            'battery_samples': self._battery_history,
            'last_battery_percent': self._battery_level,
            'provenance': {
                'user_id': provenance.get('user_id'),
                'session_dir': provenance.get('session_dir'),
                'scenario_hash': provenance.get('scenario_hash'),
            },
            'exported_at': datetime.now(timezone.utc).isoformat(),
        }
        metadata_path = export_dir / 'polar_metadata.json'
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        self.log_performance('polar_metadata', str(metadata_path))

    def _start_scan(self) -> None:
        """Start a BLE scan for Polar devices (runs in background)."""
        if BleakScanner is None:
            print(_('BLE scanning requires the bleak package.'))
            return
            
        thread = threading.Thread(target=self._run_scan, daemon=True)
        thread.start()

    def _run_scan(self) -> None:
        """Run BLE device scan in separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._scan_devices())
        except Exception as exc:
            print(_('Scan error: {}').format(exc))
        finally:
            loop.close()

    async def _scan_devices(self) -> None:
        """Scan for Polar devices and log results."""
        print(_('Scanning for Polar devices (10 seconds)...'))
        
        devices = await BleakScanner.discover(timeout=10.0)
        polar_devices = [d for d in devices if d.name and 'Polar' in d.name]
        
        if polar_devices:
            print(_('Found {} Polar device(s):').format(len(polar_devices)))
            for device in polar_devices:
                print(f'  - {device.name}: {device.address}')
                self.log_performance('polar_scan', f'name={device.name},address={device.address}')
        else:
            print(_('No Polar devices found. Ensure device is worn and awake.'))
            self.log_performance('polar_scan', 'no_devices_found')

    def get_latest_packet(self) -> Optional[RRPacket]:
        """Get the most recent RR packet for external queries.
        
        Returns:
            Most recent RRPacket or None if no data available.
        """
        return self._recent_rr[-1] if self._recent_rr else None

    def get_signal_quality(self) -> float:
        """Get current signal quality for external queries.
        
        Returns:
            Signal quality score (0.0-1.0).
        """
        return self._compute_signal_quality()

    def is_connected(self) -> bool:
        """Check if currently connected to Polar H10.
        
        Returns:
            True if BLE connection is active.
        """
        return self._connected

    def get_battery_level(self) -> int:
        """Get last known battery level.
        
        Returns:
            Battery percentage (0-100) or -1 if unknown.
        """
        return self._battery_level
