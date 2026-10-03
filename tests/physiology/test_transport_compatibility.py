from types import SimpleNamespace
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
