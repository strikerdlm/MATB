# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from plugins.abstractplugin import AbstractPlugin
from core import validation

try:  # pragma: no cover - optional dependency
    from bleak import BleakClient  # type: ignore
except ImportError:  # pragma: no cover
    BleakClient = None

try:  # pragma: no cover - optional dependency
    import pylsl
except ImportError:  # pragma: no cover
    pylsl = None


HR_CHAR_UUID = '00002a37-0000-1000-8000-00805f9b34fb'


class Polarrlink(AbstractPlugin):
    """Streams RR intervals from a Polar H10 belt into LSL for downstream plugins."""

    def __init__(self, label: str = '', taskplacement: str = 'invisible', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Polar RR Link'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'deviceid': validation.is_string,
            'lslstreamname': validation.is_string,
        }

        self.parameters.update({
            'deviceid': '',
            'lslstreamname': 'POLAR_H10_RR',
        })

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stream_info = None
        self._stream_outlet = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self) -> None:
        super().start()
        if BleakClient is None or pylsl is None:
            print(_('Polar RR link requires both bleak and pylsl packages.'))
            return
        if not self.parameters['deviceid']:
            print(_('Polar RR link requires a deviceid (MAC address or UUID).'))
            return
        self._stop_event.clear()
        self._stream_info = pylsl.StreamInfo(
            name=self.parameters['lslstreamname'],
            type='RR',
            channel_count=1,
            nominal_srate=0.0,
            channel_format='float32',
            source_id='polar-h10'
        )
        self._stream_outlet = pylsl.StreamOutlet(self._stream_info)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._stream_outlet = None
        self._stream_info = None
        super().stop()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._client_loop())
        except Exception as exc:  # pragma: no cover
            print(_('Polar RR link stopped: {}').format(exc))
        finally:
            self._loop.close()

    async def _client_loop(self) -> None:
        device_id = self.parameters['deviceid']
        async with BleakClient(device_id) as client:
            await client.start_notify(HR_CHAR_UUID, self._handle_hr_measurement)
            while not self._stop_event.is_set():
                await asyncio.sleep(0.25)
            await client.stop_notify(HR_CHAR_UUID)

    def _handle_hr_measurement(self, _sender: int, data: bytearray) -> None:
        if self._stream_outlet is None:
            return
        if not data:
            return
        flags = data[0]
        offset = 1
        if flags & 0x01:
            hr = int.from_bytes(data[offset:offset + 2], byteorder='little')
            offset += 2
        else:
            hr = data[offset]
            offset += 1
        # RR intervals follow; each is little endian 1/1024 s units
        while offset + 1 < len(data):
            rr_raw = int.from_bytes(data[offset:offset + 2], byteorder='little')
            offset += 2
            rr_seconds = rr_raw / 1024.0
            if rr_seconds > 0:
                self._stream_outlet.push_sample([rr_seconds])


