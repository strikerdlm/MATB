"""Synchronous fail-stop scientific capture owned by the native logger."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid5

from matb_integration.contracts import ScientificEventV3, TimingObservationV1
from .contracts import (ArtifactV1, CaptureManifestV1, RuntimePayloadV1, TASKS,
                        canonical_bytes, event_type, opportunity_uuid, strict_json,
                        MAX_STREAM_BYTES, MAX_STREAM_RECORDS, MAX_JSONL_LINE_BYTES)


class EvidenceWriter:
    def __init__(self, stem: Path, session_id: str, context: dict, identity: dict):
        self.paths = {"events": stem.with_suffix(".scientific.events.jsonl"),
                      "timing": stem.with_suffix(".timing.observations.jsonl")}
        self.manifest_path = stem.with_suffix(".capture.manifest.json")
        self.session_id = session_id
        self.block_id = identity.get("block_instance_id") or str(uuid5(UUID(session_id), "block"))
        source = context.get("source_commit", "unavailable")
        dirty = context.get("source_dirty")
        if source in {"unknown", "unavailable"}:
            dirty = None
        self.manifest = CaptureManifestV1(
            capture_id=str(uuid5(UUID(session_id), "classic-capture-1")), session_id=session_id,
            block_instance_id=self.block_id, parent_session_id=identity.get("parent_session_id"),
            participant_id=identity.get("participant_id"), visit_ordinal=identity.get("visit_ordinal"),
            condition=identity.get("condition", "UNSPECIFIED"),
            execution_purpose=identity.get("execution_purpose", "exploration"),
            scenario_sha256=context["scenario_sha256"], profile_id=context["profile_id"],
            component_version=context["component_version"], source_commit=source, source_dirty=dirty,
            scenario_manifest_status=context["scenario_manifest_status"], tasks=[],
            completion="recording", artifacts={},
            clocks={"python.perf_counter": "host monotonic software observation; no physical onset",
                    "openmatb.scenario": "scenario time; pauses excluded"})
        self.sequence = 0
        self.counts = {"events": 0, "timing": 0}
        self.digests = {key: sha256() for key in self.paths}
        self.sizes = {key: 0 for key in self.paths}
        self.handles = {}
        try:
            for key, path in self.paths.items():
                self.handles[key] = path.open("xb")
        except Exception:
            for handle in self.handles.values():
                handle.close()
            raise
        self.parameters: dict[str, dict] = {}
        self.failed: str | None = None
        self.sealed = False
        self._save_manifest()

    def _save_manifest(self) -> None:
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_bytes(canonical_bytes(self.manifest.model_dump(mode="json")))
        temp.replace(self.manifest_path)

    def _write(self, role: str, record: dict) -> None:
        content = canonical_bytes(record)
        if (len(content) > MAX_JSONL_LINE_BYTES or self.sizes[role] + len(content) > MAX_STREAM_BYTES
                or self.counts[role] >= MAX_STREAM_RECORDS):
            raise RuntimeError("scientific_capture_capacity_exceeded")
        self.handles[role].write(content)
        self.handles[role].flush()
        self.counts[role] += 1
        self.digests[role].update(content)
        self.sizes[role] += len(content)

    def record(self, row: dict, metadata: dict, *, runtime_event_id: str | None = None) -> None:
        if self.failed or self.sealed:
            raise RuntimeError("scientific capture is failed or sealed")
        try:
            module = str(row.get("module", ""))
            address = str(row.get("address", ""))
            kind = str(row["type"])
            value = row.get("value")
            if isinstance(value, Path):
                value = str(value)
            params = self.parameters.setdefault(module, {})
            if kind in {"parameter", "event"} and address in {"automaticsolver", "taskupdatetime"}:
                params[address] = value
            automation = metadata.get("automation_active", params.get("automaticsolver"))
            if type(automation) is not bool:
                automation = None
            interval = metadata.get("sample_interval_ms", params.get("taskupdatetime"))
            if type(interval) not in (int, float):
                interval = None
            opportunity = None
            if kind == "performance" and (module, address) in {
                ("sysmon", "opportunity"), ("communications", "comm_opportunity_v1")}:
                opportunity = strict_json(value)
            payload = RuntimePayloadV1(
                block_instance_id=self.block_id, record_type=kind, module=module, address=address,
                value=value, opportunity=opportunity,
                native_opportunity_id=opportunity.get("opportunity_id") if opportunity else None,
                automation_active=automation, sample_interval_ms=interval,
                runtime_event_id=runtime_event_id, completion=metadata.get("completion"),
                compatibility_row=metadata.get("compatibility_row"))
            native_id = payload.native_opportunity_id
            event = ScientificEventV3.create(
                session_id=self.session_id, sequence=self.sequence, component_id="matb-runtime",
                component_version=self.manifest.component_version, task=module if module in TASKS else None,
                event_type=event_type(payload), scenario_time_ns=int(round(float(row["scenario_time"]) * 1e9)),
                scenario_sha256=self.manifest.scenario_sha256, profile_id=self.manifest.profile_id,
                source_commit=self.manifest.source_commit, source_dirty=self.manifest.source_dirty,
                correlation_id=self.block_id,
                opportunity_id=opportunity_uuid(self.session_id, module, native_id) if native_id else None,
                payload=payload.model_dump(mode="json"))
            self._write("events", event.to_record())
            observations = [("software_receipt", "python.perf_counter", metadata["recorded_monotonic_ns"])]
            for key, observation_kind in (("dispatch_start_monotonic_ns", "dispatch_start"),
                                           ("dispatch_end_monotonic_ns", "dispatch_end")):
                if key in metadata:
                    observations.append((observation_kind, "python.perf_counter", metadata[key]))
            if "scheduled_scenario_time_s" in metadata:
                observations.append(("scheduled", "openmatb.scenario", int(round(metadata["scheduled_scenario_time_s"] * 1e9))))
            for index, (observation_kind, clock, value_ns) in enumerate(observations):
                self._write("timing", TimingObservationV1.create(
                    session_id=self.session_id, event_id=event.event_id, observation_index=index,
                    kind=observation_kind, clock_id=clock, value=int(value_ns), unit="ns",
                    evidence_source="software", method="experiment_clock" if observation_kind == "scheduled" else "software_clock",
                    details={"boundary": "native_logger_receipt"} if observation_kind == "software_receipt" else {},
                ).to_record())
            self.sequence += 1
        except Exception as exc:
            self.failed = type(exc).__name__
            # Persist failure state even if a stream is now unusable. Do not
            # rewrite/truncate the partial original or pretend it is complete.
            self.manifest.completion = "failed"
            self.manifest.failure_reason = self.failed
            self.manifest.artifacts = {
                key: ArtifactV1(sha256=self.digests[key].hexdigest(), size_bytes=self.sizes[key], records=self.counts[key])
                for key in self.paths}
            try:
                self._save_manifest()
            except OSError:
                pass  # Caller enters fail-stop even when the manifest sink fails.
            raise

    def lifecycle(self, phase: str, scenario_time: float, observed_ns: int, completion: str | None = None) -> None:
        self.record({"type": "capture_lifecycle", "module": "", "address": "", "value": phase,
                     "scenario_time": scenario_time}, {"recorded_monotonic_ns": observed_ns, "completion": completion})

    def set_tasks(self, tasks: list[str]) -> None:
        self.manifest.tasks = sorted(set(tasks) & set(TASKS))
        self._save_manifest()

    def seal(self, *, completion: str, artifacts: dict[str, Path]) -> None:
        if self.sealed:
            return
        for handle in self.handles.values():
            handle.close()
        self.manifest.artifacts = {
            key: ArtifactV1(sha256=self.digests[key].hexdigest(), size_bytes=self.sizes[key], records=self.counts[key])
            for key in self.paths}
        for key, path in artifacts.items():
            if path.is_file():
                content = path.read_bytes()
                self.manifest.artifacts[key] = ArtifactV1(sha256=sha256(content).hexdigest(), size_bytes=len(content))
        self.manifest.completion = "failed" if self.failed else completion
        self.manifest.failure_reason = self.failed
        self._save_manifest()
        self.sealed = True
