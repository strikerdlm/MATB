from types import SimpleNamespace
import asyncio
import sys

from matb_integration.physiology import transport


def test_connectability_uses_winrt_advertising_event_and_preserves_false():
    device = SimpleNamespace(details={})
    raw = SimpleNamespace(adv=SimpleNamespace(is_connectable=False), scan=None)
    advertisement = SimpleNamespace(platform_data=(None, raw))
    assert transport._connectability(device, advertisement) is False
    raw.adv.is_connectable = True
    assert transport._connectability(device, advertisement) is True
    assert transport._connectability(device, SimpleNamespace()) is None


def test_windows_apartment_preparation_is_per_call_not_a_global_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(transport.sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'bleak.backends.winrt.util', SimpleNamespace(uninitialize_sta=lambda: calls.append(True)))
    transport._prepare_windows_bleak_thread()
    transport._prepare_windows_bleak_thread()
    assert len(calls) == 2


def test_device_alias_does_not_change_when_scan_order_changes(monkeypatch):
    first = SimpleNamespace(address="private-address-a", name="Polar H10 A")
    second = SimpleNamespace(address="private-address-b", name="Polar H10 B")
    adv = SimpleNamespace(local_name=None, manufacturer_data={}, rssi=-50)
    scans = iter([{"a": (first, adv), "b": (second, adv)}, {"b": (second, adv), "a": (first, adv)}])
    async def discover(**kwargs):
        return next(scans)
    monkeypatch.setitem(sys.modules, "bleak", SimpleNamespace(BleakScanner=SimpleNamespace(discover=discover)))
    monkeypatch.setattr(transport, "_prepare_windows_bleak_thread", lambda: None)
    async def exercise():
        adapter = transport.PolarBleakTransport()
        initial = await adapter.scan(1)
        repeated = await adapter.scan(1)
        assert [row.alias for row in initial] == ["Polar H10 1", "Polar H10 2"]
        assert [row.alias for row in repeated] == ["Polar H10 2", "Polar H10 1"]
        assert all("private-address" not in row.alias for row in initial + repeated)
    asyncio.run(exercise())
