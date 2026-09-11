"""Offline recomputation of a frozen descriptive export, without database or network."""

import hashlib
import json
import sys
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    checks = json.loads((root / "checksums.json").read_text())
    for name, digest in checks.items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Artifact checksum mismatch: " + name)
    sys.path.insert(0, str(root / "source"))
    from matb_integration.analysis.study_calculators import calculate
    from matb_integration.screen.hcf_mapping import compute_cohort_hcf
    from replay_rules import aggregate, render_figure, analysis_unit

    source = json.loads((root / "input.json").read_text())
    expected = json.loads((root / "result.json").read_text())

    def fingerprint(value):
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()

    execution = json.loads((root / "execution.json").read_text())
    selection = json.loads((root / "selection.json").read_text())
    if fingerprint(source) != execution["data_sha256"]:
        raise ValueError("Data fingerprint mismatch.")
    if (
        fingerprint(source["plan"]) != execution["plan_sha256"]
        or fingerprint(source["plan"]) != source["version"]["analysis_sha256"]
    ):
        raise ValueError("Plan fingerprint mismatch.")
    if fingerprint(source["study"]) != source["version"]["study_sha256"]:
        raise ValueError("Study fingerprint mismatch.")
    if fingerprint(source["implementation"]) != execution["implementation_sha256"]:
        raise ValueError("Implementation fingerprint mismatch.")
    if (
        fingerprint(
            dict(
                snapshot=json.loads(selection["snapshot_json"]),
                request=json.loads(selection["request_json"]),
            )
        )
        != selection["id"]
        or selection["id"] != source["frozen_input_id"]
    ):
        raise ValueError("Frozen selection fingerprint mismatch.")
    for name, digest in source["implementation"]["files"].items():
        if checks.get(name) != digest:
            raise ValueError("Pinned implementation artifact mismatch: " + name)
    import importlib.metadata

    for package, version in source["implementation"]["dependencies"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("Dependency version mismatch: " + package)
    plan = source["plan"]
    policy = plan["eligibility_policy"]
    outcomes = {outcome["key"]: outcome for outcome in plan["outcomes"]}
    fresh_rows = []
    for row in source["rows"]:
        fresh = dict(row, values={})
        fresh_rows.append(fresh)
        if row["source"] is None:
            continue
        selected_specs = [
            outcome
            for outcome in outcomes.values()
            if row["occasion_key"] in outcome["occasion_keys"]
            and outcome["metric"] != "screen.hcf"
        ]
        if (
            row["instrument"] == "screen"
            and row["occasion_key"] in policy["hcf_screen_keys"]
            and not selected_specs
        ):
            selected_specs = [dict(key="__hcf_screen", metric="screen.simple_rt")]
        calculations = {
            spec["key"]: calculate(row["source"], spec) for spec in selected_specs
        }
        # Frozen artifacts use JSON semantics (e.g. registered tuple ranges become lists).
        # Canonicalize fresh structured results before exact comparison; no numeric tolerance.
        calculations = json.loads(
            json.dumps(calculations, sort_keys=True, allow_nan=False)
        )
        if calculations != row["calculations"]:
            raise ValueError("Raw calculator mismatch: " + row["attempt_id"])
        if not row["eligible"]:
            continue
        for key, actual in calculations.items():
            if key == "__hcf_screen" or actual.get("value") is None:
                continue
            if row["instrument"] == "openmatb" and not actual.get("source_eligible"):
                continue
            # Frozen pooling exclusions remain exclusions; copied observation values
            # never decide whether a fresh raw observation is included.
            comparison = source["comparisons"][key]["groups"][analysis_unit(plan, row)]
            if comparison["passed"]:
                fresh["values"][key] = actual["value"]

    if source["hcf"]:
        from matb_integration.screen.scoring import score_screen
        from dataclasses import asdict

        hcf_snapshot = source["hcf"]["snapshot"]
        references = hcf_snapshot["references"]
        selected_rows = {row["attempt_id"]: row for row in source["rows"]}
        rescored = {
            reference["participant_id"]: score_screen(
                selected_rows[reference["attempt_id"]]["source"]["raw"]
            )
            for reference in references
        }
        estimates = {
            participant: asdict(estimate)
            for participant, estimate in compute_cohort_hcf(rescored).items()
        }
        if estimates != hcf_snapshot["values"]:
            raise ValueError("HCF recomputation mismatch.")
        if (
            fingerprint(hcf_snapshot) != source["hcf"]["id"]
            or fingerprint(references) != hcf_snapshot["cohort_sha256"]
        ):
            raise ValueError("HCF identity mismatch.")
        for row in fresh_rows:
            estimate = estimates.get(row["participant_id"])
            if not row["eligible"] or estimate is None:
                continue
            for outcome in outcomes.values():
                if (
                    outcome["metric"] == "screen.hcf"
                    and row["occasion_key"] in outcome["occasion_keys"]
                    and source["comparisons"][outcome["key"]]["passed"]
                ):
                    row["values"][outcome["key"]] = estimate["value"]

    for saved, fresh in zip(source["rows"], fresh_rows):
        if saved["values"] != fresh["values"]:
            raise ValueError(
                "Selected observation mismatch: " + str(saved["attempt_id"])
            )
    result = aggregate(plan, fresh_rows, policy["missing_handling"])
    for contrast in source["plan"]["contrasts"]:
        item = result["contrasts"][contrast["key"]]
        failed = {
            group.rsplit(":", 1)[0]
            for group, report in source["comparisons"]["contrast:" + contrast["key"]][
                "groups"
            ].items()
            if not report["passed"]
        }
        for unit in failed:
            item["values"].pop(unit, None)
        item["observed"] = len(item["values"])
        if failed:
            item["excluded_configuration_units"] = sorted(failed)
            item["missing"] = sorted(set(item["missing"]) | failed)
    result["figure"] = render_figure(result)
    if result != expected:
        raise ValueError("Descriptive aggregation/figure mismatch.")
    return dict(
        status="reproduced",
        raw_attempts=sum(r["source"] is not None for r in source["rows"]),
        automatic_model=None,
    )


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1] if len(sys.argv) > 1 else ".")))
