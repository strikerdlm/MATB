from __future__ import annotations

import json

from matb_integration.analysis.stats.cli import main


def test_cli_run_writes_artifact(tmp_path, sim_study, sim_fits):
    m = tmp_path / "metrics.json"
    f = tmp_path / "fits.json"
    out = tmp_path / "artifact.json"
    m.write_text(json.dumps(sim_study))
    f.write_text(json.dumps(sim_fits))
    rc = main(["run", "--metrics-json", str(m), "--fits-json", str(f), "-o", str(out)])
    assert rc == 0
    art = json.loads(out.read_text())
    assert art["engine_version"]
    assert art["provenance"]["created_utc"]  # CLI stamps the timestamp
    assert art["confirmatory"]["family_size_actual"] == 6


def test_cli_bayes_writes_artifact(tmp_path, sim_study, sim_fits):
    m = tmp_path / "metrics.json"
    f = tmp_path / "fits.json"
    out = tmp_path / "bayes.json"
    # one confirmatory metric only -> a single sampled model keeps this fast
    rows = [r for r in sim_study if r["metric"] == "sysmon_d_prime"]
    m.write_text(json.dumps(rows))
    f.write_text(json.dumps([]))
    rc = main(["bayes", "--metrics-json", str(m), "--fits-json", str(f),
               "-o", str(out), "--draws", "200", "--tune", "200", "--chains", "2"])
    assert rc == 0
    art = json.loads(out.read_text())
    assert art["bayes_version"]
    assert art["sampler"]["draws"] == 200
    assert art["q2"]["sysmon_d_prime"]["status"] == "ok"
