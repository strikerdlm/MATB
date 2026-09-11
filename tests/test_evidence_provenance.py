from copy import deepcopy

import pytest

from matb_integration.evidence.provenance import collect_analysis_execution
from matb_integration.evidence.reconcile import reconcile
from matb_integration.evidence.reference import synthetic_capture


def test_analysis_identity_is_independent_of_acquisition(monkeypatch, tmp_path):
    monkeypatch.setenv("MATB_SOURCE_COMMIT", "a" * 40)
    bundle = synthetic_capture(tmp_path)
    execution = collect_analysis_execution()
    assert execution["source_commit"] != "a" * 40
    assert execution["dependency_lock_sha256"]
    result = reconcile(bundle, execution=execution)
    assert result["analysis_execution"] == execution
    changed = deepcopy(execution)
    changed["source_commit"] = "c" * 40
    other = reconcile(bundle, execution=changed)
    assert result["fingerprint"] != other["fingerprint"]
    assert result["metrics"] == other["metrics"]
    assert result["source_hashes"] == other["source_hashes"]


def test_old_derivation_reader_preserves_old_fingerprint(tmp_path):
    bundle = synthetic_capture(tmp_path)
    legacy = reconcile(bundle, derivation_version="classic-evidence-1.0")
    assert "analysis_execution" not in legacy
    assert legacy["fingerprint"] == reconcile(bundle, derivation_version="classic-evidence-1.0")["fingerprint"]
    assert legacy["metrics"] == reconcile(bundle)["metrics"]
    with pytest.raises(ValueError, match="unsupported derivation"):
        reconcile(bundle, derivation_version="future")


def test_configuration_cannot_claim_unexecuted_interpolation(tmp_path):
    execution = collect_analysis_execution()
    execution["analysis_configuration"]["missing_sample_interpolation"] = True
    with pytest.raises(ValueError, match="unsupported analysis configuration"):
        reconcile(synthetic_capture(tmp_path), execution=execution)


def test_frozen_previous_derivation_version_stays_replayable(tmp_path):
    bundle = synthetic_capture(tmp_path)
    old = reconcile(bundle, derivation_version='classic-evidence-1.1')
    replay = reconcile(bundle, derivation_version='classic-evidence-1.1', execution=old['analysis_execution'])
    assert replay['fingerprint'] == old['fingerprint']
    assert replay['derivation_version'] == 'classic-evidence-1.1'
    assert replay['metrics'] == old['metrics']
