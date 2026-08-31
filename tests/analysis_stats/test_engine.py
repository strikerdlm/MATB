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
    q1_sysmon = art["q1"]["sysmon_hit_rate"]
    assert q1_sysmon["status"] == "ok"
    assert q1_sysmon["contrasts"] is not None
    assert all("p_holm" in c for c in q1_sysmon["contrasts"])
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
    assert set(art["rmanova"]) == {"sysmon_hit_rate", "nasatlx_rtlx_mean_0_100", "bedford"}
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


def test_confirmatory_models_exclude_ineligible_rows_fail_closed(sim_study):
    rows = [dict(row, confirmatory_eligible=False) for row in sim_study]

    art = run_analysis(rows, [])

    assert art["confirmatory"]["family_size_actual"] == 0
    assert art["confirmatory"]["eligibility"]["rows_excluded"] == len(rows)
    assert art["confirmatory"]["eligibility"]["rows_eligible"] == 0
    assert all(
        art["q1"][metric]["status"] == "insufficient_data"
        for metric in ("sysmon_hit_rate", "nasatlx_rtlx_mean_0_100", "bedford")
    )
    assert all(result["status"] == "insufficient_data" for result in art["rmanova"].values())


def test_exploratory_outputs_may_retain_ineligible_rows(sim_study):
    rows = [dict(row, confirmatory_eligible=False) for row in sim_study]
    art = run_analysis(rows, [])

    assert any(entry["canonical"]["status"] == "ok" for entry in art["q3"])
