"""Reproducible software measurements using synthetic workloads only.

Run recorder mode on an otherwise idle rig. Capacity mode includes the existing
in-memory upload/service path and should run in a separate process per size.
Neither mode measures a physical input or display onset.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

from .contracts import canonical_bytes, MAX_STREAM_BYTES
from .provenance import collect_analysis_execution
from .writer import EvidenceWriter


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    def percentile(p):
        at = (len(ordered) - 1) * p
        low = int(at)
        return ordered[low] + (ordered[min(low + 1, len(ordered)-1)] - ordered[low]) * (at-low)
    return {"n": len(values), "p50": percentile(.5), "p95": percentile(.95), "p99": percentile(.99), "max": ordered[-1]}


def peak_rss_bytes() -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess
        handle.restype = wintypes.HANDLE
        memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        memory_info.restype = wintypes.BOOL
        if not memory_info(handle(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return counters.PeakWorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def writer_at(root: Path) -> EvidenceWriter:
    root.mkdir(parents=True, exist_ok=False)
    return EvidenceWriter(root / "synthetic.csv", str(uuid4()), {
        "scenario_sha256": "a" * 64, "profile_id": "synthetic-benchmark", "source_commit": "b" * 40,
        "source_dirty": False, "component_version": "benchmark-1", "scenario_manifest_status": "verified",
    }, {"condition": "BENCHMARK", "execution_purpose": "exploration"})


def recorder(root: Path, samples: int, interval_ms: float, repeats: int) -> dict:
    rows, runs = [], []
    for repeat in range(repeats):
        for enabled in ([False, True] if repeat % 2 == 0 else [True, False]):
            writer = writer_at(root / f"capture-{repeat}") if enabled else None
            start = time.perf_counter_ns()
            previous = start
            checksum = 0
            costs, lateness, gaps = [], [], []
            for index in range(samples):
                due = start + int(index * interval_ms * 1e6)
                remaining = (due - time.perf_counter_ns()) / 1e9
                if remaining > 0:
                    time.sleep(remaining)
                dispatched = time.perf_counter_ns()
                checksum += (index % 17) ** 2
                row = {"type": "performance", "module": "track", "address": "center_deviation",
                       "value": float(index % 17), "scenario_time": index * interval_ms / 1000}
                before = time.perf_counter_ns()
                if writer:
                    writer.record(row, {"recorded_monotonic_ns": before, "dispatch_start_monotonic_ns": dispatched,
                        "dispatch_end_monotonic_ns": before, "scheduled_scenario_time_s": row["scenario_time"]})
                after = time.perf_counter_ns()
                cost, late, gap = (after-before)/1e6, max(0, dispatched-due)/1e6, (dispatched-previous)/1e6
                costs.append(cost); lateness.append(late)
                if index: gaps.append(gap)
                rows.append([repeat, enabled, index, cost, late, gap])
                previous = dispatched
            if writer:
                writer.seal(completion="completed", artifacts={})
            runs.append({"repeat": repeat, "recording": enabled, "workload_checksum": checksum,
                "recorder_call_ms": distribution(costs), "synthetic_dispatch_lateness_ms": distribution(lateness),
                "sample_gap_ms": distribution(gaps), "gaps_over_two_intervals": sum(g > interval_ms*2 for g in gaps)})
    with (root / "recorder-observations.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["repeat", "recording", "sample", "call_ms", "dispatch_lateness_ms", "gap_ms"], *rows])
    assert len({r["workload_checksum"] for r in runs}) == 1
    return {"runs": runs, "interval_ms": interval_ms, "samples_per_run": samples,
            "physical_input_latency_ms": None, "physical_onset_latency_ms": None,
            "acceptance": "not_assessed_without_prespecified_rig_and_protocol_limits"}


def capacity_source(root: Path, samples: int, payload_bytes: int = 0) -> dict[str, bytes]:
    writer = writer_at(root)
    writer.set_tasks(["track"])
    manifest = {"manifest_version": 3, "scenario": {"sha256": "a" * 64}, "synthetic_reference_only": True}
    path = root / "scenario.json"
    path.write_bytes(canonical_bytes(manifest))
    writer.lifecycle("started", 0, time.perf_counter_ns())
    def emit(kind, address, value, at):
        writer.record({"type": kind, "module": "track", "address": address, "value": value, "scenario_time": at},
                      {"recorded_monotonic_ns": time.perf_counter_ns()})
    emit("scenario_manifest_evidence", "", canonical_bytes({"status": "verified", "scenario_manifest_sha256": sha256(path.read_bytes()).hexdigest()}).decode().strip(), 0)
    emit("parameter", "automaticsolver", False, 0)
    emit("parameter", "taskupdatetime", 100, 0)
    emit("task_lifecycle", "self", "resumed", 0)
    for index in range(samples):
        at = (index + 1) / 10
        emit("performance", "cursor_in_target", bool(index % 4), at)
        emit("performance", "center_deviation", float(index % 11), at)
        if payload_bytes:
            emit("benchmark_padding", "capacity_only", "x" * payload_bytes, at)
    emit("task_lifecycle", "self", "stopped", (samples+1) / 10)
    writer.lifecycle("completed", (samples+1) / 10, time.perf_counter_ns())
    writer.seal(completion="completed", artifacts={"scenario_manifest": path})
    return {"capture_manifest": writer.manifest_path.read_bytes(), "scenario_manifest": path.read_bytes(),
            **{role: p.read_bytes() for role, p in writer.paths.items()}}


def capacity(root: Path, samples: int, payload_bytes: int, reuse_source: Path | None = None) -> dict:
    # The benchmark uses exactly the production service; no alternate importer.
    from sqlmodel import Session, SQLModel, create_engine
    from app import main  # noqa: F401 - register the production table inventory
    from app.evidence_service import ingest_evidence, write_bundle, capture_summary, recover_evidence_runs
    from app.evidence_models import EvidenceRun
    source = capacity_source(root / "source", samples, payload_bytes) if reuse_source is None else {
        role: (reuse_source / name).read_bytes() for role, name in {
            "capture_manifest": "synthetic.capture.manifest.json", "scenario_manifest": "scenario.json",
            "events": "synthetic.scientific.events.jsonl", "timing": "synthetic.timing.observations.jsonl"}.items()}
    engine = create_engine(f"sqlite:///{(root/'capacity.sqlite').as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        start = time.perf_counter()
        cid, created = ingest_evidence(db, source)
        imported = time.perf_counter() - start
        start = time.perf_counter()
        with (root / "bundle.zip").open("w+b") as sink:
            write_bundle(db, cid, sink)
            zip_bytes = sink.tell()
        exported = time.perf_counter() - start
        before = capture_summary(db, cid)
        db.add(EvidenceRun(id="synthetic-interrupted-run", capture_id=cid, version="benchmark"))
        db.commit()
    recover_evidence_runs(engine)
    with Session(engine) as db:
        recovery = db.get(EvidenceRun, "synthetic-interrupted-run").reason
        start = time.perf_counter()
        duplicate = ingest_evidence(db, source)
        duplicate_seconds = time.perf_counter()-start
    # Fresh sessions on concurrent requests, matching the API's transaction ownership.
    from concurrent.futures import ThreadPoolExecutor
    def same_upload(_):
        with Session(engine) as db:
            begin = time.perf_counter()
            result = ingest_evidence(db, source)
            return {"seconds": time.perf_counter()-begin, "capture_id": result[0], "created": result[1]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(same_upload, range(2)))
    return {"samples": samples, "scenario_duration_seconds": (samples+1)/10, "created": created,
        "source_bytes": {k: len(v) for k, v in source.items()}, "stream_limit_bytes": MAX_STREAM_BYTES,
        "import_seconds": imported, "export_seconds": exported, "duplicate_seconds": duplicate_seconds,
        "duplicate_created": duplicate[1], "concurrent_duplicate_requests": concurrent,
        "zip_bytes": zip_bytes, "database_bytes": (root/'capacity.sqlite').stat().st_size,
        "source_sha256": {role: sha256(content).hexdigest() for role, content in source.items()},
        "payload_bytes_per_padding_record": payload_bytes, "reused_source": reuse_source is not None,
        "process_lifetime_peak_rss_bytes": peak_rss_bytes(), "recovery_reason": recovery,
        "reconciliation_status": before["reconciliation"]["status"],
        "acceptance": "not_assessed_without_prespecified_capacity_limits"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["recorder", "capacity"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--interval-ms", type=float, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--payload-bytes", type=int, default=0)
    parser.add_argument("--reuse-source", type=Path)
    args = parser.parse_args()
    if not 1 <= args.samples <= 150000 or not 0 < args.interval_ms <= 1000 or not 1 <= args.repeats <= 20 or not 0 <= args.payload_bytes <= 240000:
        parser.error("benchmark parameter outside bounded range")
    args.output.mkdir(parents=True, exist_ok=False)
    result = recorder(args.output, args.samples, args.interval_ms, args.repeats) if args.mode == "recorder" else capacity(args.output, args.samples, args.payload_bytes, args.reuse_source)
    report = {"schema_version": "1.0", "synthetic_only": True, "mode": args.mode,
              "execution": collect_analysis_execution(), "result": result,
              "benchmark_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "writer_sha256": sha256(Path(__file__).with_name("writer.py").read_bytes()).hexdigest()}
    (args.output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
