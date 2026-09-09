"""Recompute exported evidence offline; ZIP members are never extracted."""
import argparse
import hashlib
import json
import re
import zipfile

from .contracts import MAX_STREAM_BYTES, strict_json, canonical_bytes
from .qualification import QualificationBindingV1
from .reconcile import reconcile


def verify_bundle(path: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 268:
            raise ValueError("duplicate or excessive bundle members")
        if any(info.file_size > MAX_STREAM_BYTES for info in archive.infolist()):
            raise ValueError("bundle member too large")
        if sum(info.file_size for info in archive.infolist()) > 6 * MAX_STREAM_BYTES:
            raise ValueError("bundle aggregate capacity exceeded")
        source_names = {f"sources/{role}.{suffix}" for role, suffix in (
            ("capture_manifest", "json"), ("scenario_manifest", "json"), ("events", "jsonl"),
            ("timing", "jsonl"), ("legacy_csv", "csv"), ("runtime_envelope", "jsonl"))}
        for info in archive.infolist():
            if info.filename in {"checksums.json", "README.txt"}:
                limit = 2 * 1024 * 1024
            elif info.filename in source_names or info.filename == "report.json":
                limit = MAX_STREAM_BYTES
            elif re.fullmatch(r"qualification/[a-f0-9]{64}/[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", info.filename):
                limit = 8 * 1024 * 1024
            else:
                raise ValueError("unsupported bundle member")
            if info.file_size > limit:
                raise ValueError("bundle member capacity exceeded")
        checksums = strict_json(archive.read("checksums.json"))
        if set(names) != {*checksums, "checksums.json"}:
            raise ValueError("bundle member inventory mismatch")
        files = {name: archive.read(name) for name in checksums}
        for name, content in files.items():
            if hashlib.sha256(content).hexdigest() != checksums[name]:
                raise ValueError(f"bundle checksum mismatch: {name}")
    sources = {}
    for role in ("capture_manifest", "scenario_manifest", "events", "timing", "legacy_csv", "runtime_envelope"):
        suffix = "jsonl" if role in {"events", "timing", "runtime_envelope"} else "csv" if role == "legacy_csv" else "json"
        name = f"sources/{role}.{suffix}"
        if name in files:
            sources[role] = files[name]
    original = strict_json(files["report.json"])
    previous = original.get("reconciliation")
    if previous is None:
        raise ValueError("export has no completed reconciliation")
    manifest = strict_json(sources["capture_manifest"])
    for item in original.get("qualification", {}).get("items", []):
        record = item["record"]
        content = {k: v for k, v in record.items() if k not in {"id", "revocations"}}
        if hashlib.sha256(canonical_bytes(content)).hexdigest() != record["id"]:
            raise ValueError("qualification record digest mismatch")
        binding = item["binding"]
        QualificationBindingV1.model_validate({k: v for k, v in binding.items() if k != "capture_id"})
        if (hashlib.sha256(canonical_bytes(binding)).hexdigest() != item["id"]
                or binding["record_id"] != record["id"] or binding["capture_id"] != manifest["capture_id"]
                or record["context_sha256"] != hashlib.sha256(canonical_bytes(record["context"])).hexdigest()
                or record["context"]["software_versions"]["acquisition_commit"] != manifest["source_commit"]
                or record["context"]["presentation"]["profile_id"] != manifest["profile_id"]):
            raise ValueError("qualification identity or acquisition binding mismatch")
        for revocation in record["revocations"]:
            expected_id = hashlib.sha256(canonical_bytes([record["id"], revocation["reviewer"], revocation["reason"]])).hexdigest()
            if revocation["qualification_id"] != record["id"] or revocation["id"] != expected_id:
                raise ValueError("qualification revocation mismatch")
        status = "invalidated" if record["revocations"] else "linked_report"
        if item["status"] != status or item["result"] != record["assessment"]["status"]:
            raise ValueError("qualification status mismatch")
        for name, expected in record["evidence"].items():
            artifact = files.get(f"qualification/{record['id']}/{name}", b"")
            if hashlib.sha256(artifact).hexdigest() != expected["sha256"] or len(artifact) != expected["size_bytes"]:
                raise ValueError("qualification evidence integrity mismatch")
        if binding["capture_manifest_sha256"] != hashlib.sha256(sources["capture_manifest"]).hexdigest() or binding["context"] != record["context"]:
            raise ValueError("qualification binding mismatch")
    result = reconcile(sources, derivation_version=previous["derivation_version"],
                       execution=previous.get("analysis_execution"))
    if previous is None or previous["fingerprint"] != result["fingerprint"]:
        raise ValueError("recomputed evidence fingerprint differs from export")
    for actual, expected in zip(sorted(result["metrics"], key=lambda m: m["metric"]), sorted(original["metrics"], key=lambda m: m["metric"])):
        for key in ("metric", "value", "descriptive_value", "status", "confirmatory_eligible", "exclusion_reasons", "metric_version", "definition", "timing_basis", "physical_timing_qualification", "human_calibration"):
            if actual[key] != expected[key]:
                raise ValueError(f"recomputed metric differs: {actual['metric']}.{key}")
        sources = [{"stream": stream, "record_id": rid}
                   for stream, key in (("events", "source_event_ids"), ("timing", "source_observation_ids"))
                   for rid in dict.fromkeys(actual[key])]
        if sources != expected.get("sources"):
            raise ValueError(f"recomputed metric source links differ: {actual['metric']}")
    if len(result["metrics"]) != len(original["metrics"]):
        raise ValueError("metric inventory differs")
    from .provenance import collect_analysis_execution
    verifier = collect_analysis_execution()
    recorded = previous.get("analysis_execution")
    result["offline_verification"] = {
        "recalculated_values_and_links_match": True,
        "recorded_analysis_execution": recorded,
        "verifier_execution": verifier,
        "implementation_matches": verifier["implementation_sha256"] == recorded["implementation_sha256"] if recorded else None,
        "environment_matches": verifier["environment"] == recorded["environment"] and verifier["dependencies"] == recorded["dependencies"] if recorded else None,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    args = parser.parse_args()
    result = verify_bundle(args.bundle)
    print(json.dumps({"verified": True, "fingerprint": result["fingerprint"],
                      "metrics": len(result["metrics"]), "status": result["status"],
                      "offline_verification": result["offline_verification"]}))


if __name__ == "__main__":
    main()
