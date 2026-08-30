"""CLI for MATB compatibility, timing, and release qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from matb_integration.recording.artifacts import write_json_artifact

from .contracts import (
    canonical_json,
    evaluate_conformance,
    evaluate_release_eligibility,
    list_profiles,
    load_profile,
)
from .timing import analyze_timing_csv
from .reference import build_reference_session, export_bids_events
from .study import build_calibration_study_manifest
from .golden import run_scenario_builder_golden


def _json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_or_print(payload: Any, output: str | None) -> None:
    if output:
        write_json_artifact(Path(output), payload)
    else:
        print(canonical_json(payload))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="matb-qualify")
    sub = root.add_subparsers(dest="command", required=True)

    profiles = sub.add_parser("profiles", help="List or inspect compatibility profiles")
    profiles.add_argument("profile_id", nargs="?")

    conformance = sub.add_parser("conformance", help="Evaluate explicit golden checks")
    conformance.add_argument("profile_id")
    conformance.add_argument("checks_json")
    conformance.add_argument("--source-commit", required=True)
    conformance.add_argument("--output")

    timing = sub.add_parser("timing", help="Analyze matched physical timing CSV")
    timing.add_argument("timing_csv")
    timing.add_argument("--rig-json", required=True)
    timing.add_argument("--limits-json", required=True)
    timing.add_argument("--use-tier", default="block_plus_physiology")
    timing.add_argument("--source-commit", required=True)
    timing.add_argument("--representative-full-block", action="store_true")
    timing.add_argument("--output")

    release = sub.add_parser("release-status", help="Evaluate v1 release gates")
    release.add_argument("qualification_json")
    release.add_argument("--output")

    bids = sub.add_parser("bids-events", help="Export native JSONL events to BIDS-compatible TSV")
    bids.add_argument("events_jsonl")
    bids.add_argument("events_tsv")
    bids.add_argument("sidecar_json")
    bids.add_argument("--profile-id", required=True)
    bids.add_argument("--scenario-sha256", required=True)
    bids.add_argument("--source-commit", required=True)
    bids.add_argument("--timing-status", default="NOT_MEASURED")

    reference = sub.add_parser("reference-session", help="Build a deidentified reference-session manifest")
    reference.add_argument("metadata_json")
    reference.add_argument("session_root")
    reference.add_argument("artifacts", nargs="+")
    reference.add_argument("--output", required=True)

    study = sub.add_parser("calibration-manifest", help="Build the frozen calibration-study manifest")
    study.add_argument("scenario_hashes_json")
    study.add_argument("--source-commit", required=True)
    study.add_argument("--profile-id", default="MATB-EXTENDED-2.0")
    study.add_argument("--locale", default="es-CO")
    study.add_argument("--output", required=True)

    golden = sub.add_parser("golden", help="Run the frozen deterministic scenario golden suite")
    golden.add_argument("--source-commit", required=True)
    golden.add_argument("--output")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "profiles":
        payload = load_profile(args.profile_id) if args.profile_id else {"profiles": list_profiles()}
        _write_or_print(payload, None)
        return 0
    if args.command == "conformance":
        checks = _json_file(args.checks_json)
        if not isinstance(checks, list):
            raise ValueError("checks JSON must contain a list")
        result = evaluate_conformance(
            load_profile(args.profile_id), checks, source_commit=args.source_commit
        )
        _write_or_print(result, args.output)
        return 0 if result["status"] == "PASS" else 2
    if args.command == "timing":
        result = analyze_timing_csv(
            Path(args.timing_csv),
            rig=_json_file(args.rig_json),
            use_tier=args.use_tier,
            preregistered_limits=_json_file(args.limits_json),
            representative_full_block_recorded=args.representative_full_block,
            source_commit=args.source_commit,
        )
        _write_or_print(result, args.output)
        return 0 if result["status"] == "PASS" else 2
    if args.command == "bids-events":
        export_bids_events(
            Path(args.events_jsonl),
            Path(args.events_tsv),
            Path(args.sidecar_json),
            profile_id=args.profile_id,
            scenario_sha256=args.scenario_sha256,
            source_commit=args.source_commit,
            timing_qualification_status=args.timing_status,
        )
        return 0
    if args.command == "reference-session":
        result = build_reference_session(
            _json_file(args.metadata_json),
            artifact_paths=[Path(path) for path in args.artifacts],
            session_root=Path(args.session_root),
        )
        _write_or_print(result, args.output)
        return 0
    if args.command == "calibration-manifest":
        result = build_calibration_study_manifest(
            source_commit=args.source_commit,
            compatibility_profile_id=args.profile_id,
            scenario_hashes=_json_file(args.scenario_hashes_json),
            locale=args.locale,
        )
        _write_or_print(result, args.output)
        return 0
    if args.command == "golden":
        result = run_scenario_builder_golden(source_commit=args.source_commit)
        _write_or_print(result, args.output)
        return 0 if result["status"] == "PASS" else 2
    result = evaluate_release_eligibility(_json_file(args.qualification_json))
    _write_or_print(result, args.output)
    return 0 if result["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
