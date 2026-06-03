from __future__ import annotations

from matb_integration.suhir.hcf import HCFEstimate, resolve, F0_DEFAULT


def test_resolve_defaults_to_f0_when_absent():
    est = resolve("P01", store=None)
    assert isinstance(est, HCFEstimate)
    assert est.source == "F0_default"
    assert est.value == F0_DEFAULT


def test_resolve_uses_store_when_present():
    store = {"P02": HCFEstimate("P02", value=2.5, source="screen", components={"wm": 2.5})}
    est = resolve("P02", store=store)
    assert est.value == 2.5
    assert est.source == "screen"


def test_resolve_missing_id_in_store_falls_back():
    store = {"P02": HCFEstimate("P02", 2.5, "screen", {})}
    est = resolve("P99", store=store)
    assert est.source == "F0_default"
