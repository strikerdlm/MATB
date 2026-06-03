from __future__ import annotations

import json

import pytest

from matb_integration.suhir.calibration import synth_tau
from matb_integration.suhir.pipeline import fit_participant

G0_TRUE, P0_TRUE, TAU0_TRUE = 40.0, 0.99, 12.0


def _block(raw_tlx, failure_times, duration):
    """Build a minimal (record, raw_rows) pair the pipeline consumes."""
    record = {
        "nasatlx": {"raw_tlx": raw_tlx},
        "isa": {"mean": raw_tlx / 20.0, "probes": []},
        "bedford": {"value": raw_tlx / 10.0},
        "scenario_time_max_s": duration,
    }
    rows = [
        {"scenario_time": str(t), "type": "performance",
         "module": "sysmon", "address": "signal_detection", "value": "MISS"}
        for t in failure_times
    ]
    return record, rows


def _failures_for(g, duration):
    """Synthesize SYSMON MISS times whose MTTF matches synth_tau(g)."""
    tau = synth_tau(g, G0_TRUE, P0_TRUE, TAU0_TRUE)
    times, t = [], tau
    while t < duration:
        times.append(round(t, 3))
        t += tau
    return times


def test_fit_participant_recovers_parameters_and_serializes():
    duration = 100000.0  # long block so MTTF ~ tau
    blocks = {
        "LOW":    _block(44.0, _failures_for(44.0, duration), duration),
        "MEDIUM": _block(60.0, _failures_for(60.0, duration), duration),
        "HIGH":   _block(80.0, _failures_for(80.0, duration), duration),
    }
    out = fit_participant("P01", blocks, source="raw_tlx")
    assert out["participant_id"] == "P01"
    assert out["g0"] == pytest.approx(G0_TRUE, rel=2e-2)
    assert out["p0"] == pytest.approx(P0_TRUE, rel=2e-2)
    assert out["hcf_source"] == "F0_default"
    assert out["criteria_version"] == 1
    # Must be JSON-serializable.
    json.dumps(out)
