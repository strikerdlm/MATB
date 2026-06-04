from __future__ import annotations

from matb_integration.analysis.stats.engine import ENGINE_VERSION, Q3_PAIRS, run_analysis


def test_full_artifact_on_simulated_study(sim_study, sim_fits):
    art = run_analysis(sim_study, sim_fits, created_utc="2026-06-03T00:00:00+00:00")
    assert art["engine_version"] == ENGINE_VERSION
    prov = art["provenance"]
    assert len(prov["fingerprint"]) == 64
    assert prov["n_metric_rows"] == 12 * 6 * 3 * 3 and prov["n_fit_rows"] == 36
    assert set(prov["libraries"]) == {"pandas", "statsmodels", "scipy", "numpy"}
    # confirmatory family: 3 metrics x {Q1 omnibus, Q2 slope} = 6, all estimable here
    fam = art["confirmatory"]
    assert fam["family_size_planned"] == 6 and fam["family_size_actual"] == 6
    assert len(fam["tests"]) == 6
    assert all(t["reject"] in (True, False) and 0 <= t["p_fdr"] <= 1 for t in fam["tests"])
    # strong simulated effects -> Q1 omnibus tests all survive -> Holm contrasts attached
    q1_dprime = art["q1"]["sysmon_d_prime"]
    assert q1_dprime["status"] == "ok"
    assert q1_dprime["contrasts"] is not None
    assert all("p_holm" in c for c in q1_dprime["contrasts"])
    # exploratory metrics carry no contrasts and are flagged
    assert art["q1"]["isa_mean"]["exploratory"] is True
    assert art["q1"]["isa_mean"].get("contrasts") is None
    # Q3: one entry per pre-specified pair, each with canonical + sensitivity
    assert len(art["q3"]) == len(Q3_PAIRS)
    ok_pairs = [e for e in art["q3"] if e["canonical"]["status"] == "ok"]
    assert all("sensitivity" in e for e in ok_pairs)
    # Q4 over the three DEPDF params
    assert set(art["q4"]) == {"g0", "p0", "tau0"}
    assert art["q4"]["g0"]["status"] == "ok"
    # rmANOVA sensitivity for the three confirmatory metrics
    assert set(art["rmanova"]) == {"sysmon_d_prime", "nasatlx_raw_tlx", "bedford"}
    assert isinstance(art["caveats"], list) and art["caveats"]


def test_empty_inputs_never_crash():
    art = run_analysis([], [])
    assert art["confirmatory"]["family_size_actual"] == 0
    assert all(v["status"] == "insufficient_data" for v in art["q1"].values())
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())
    assert all(e["canonical"]["status"] == "insufficient_data" for e in art["q3"])


def test_artifact_is_json_serializable(sim_study, sim_fits):
    import json
    json.dumps(run_analysis(sim_study, sim_fits))
