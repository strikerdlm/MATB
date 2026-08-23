"""On-demand visit summaries across preserved classic OpenMATB retakes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import csv
import io
import json
from typing import Any


def _safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe(item) for item in value]
    return value


def visit_summary_json(summary: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _safe(summary),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _flatten(value: Any, prefix: tuple[str, ...] = ()):
    if isinstance(value, Mapping):
        for key in sorted(value):
            yield from _flatten(value[key], (*prefix, str(key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            yield from _flatten(item, (*prefix, str(index)))
    else:
        yield prefix, value


def visit_summary_csv(summary: Mapping[str, Any]) -> bytes:
    fields = (
        "participant_id",
        "visit_ordinal",
        "workload_level",
        "attempt_id",
        "attempt_number",
        "selected",
        "scope",
        "domain",
        "metric",
        "value",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    workloads = summary.get("workloads", {})
    if isinstance(workloads, Mapping):
        for workload, group in sorted(workloads.items()):
            if not isinstance(group, Mapping):
                continue
            selected_id = group.get("selected_attempt_id")
            attempts = group.get("attempts", [])
            if not isinstance(attempts, Sequence):
                continue
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                session = attempt.get("session", {})
                if not isinstance(session, Mapping):
                    session = {}
                base = {
                    "participant_id": summary.get("participant_id"),
                    "visit_ordinal": summary.get("visit_ordinal"),
                    "workload_level": workload,
                    "attempt_id": session.get("id"),
                    "attempt_number": session.get("attempt_number"),
                    "selected": str(session.get("id") == selected_id).lower(),
                }
                for scope in ("session", "matb_metrics", "hrv"):
                    for path, value in _flatten(attempt.get(scope, {})):
                        if not path:
                            continue
                        domain = "" if scope == "session" else path[0]
                        metric_path = path if scope == "session" else path[1:]
                        writer.writerow(
                            {
                                **base,
                                "scope": scope,
                                "domain": domain,
                                "metric": ".".join(metric_path) or path[0],
                                "value": "" if value is None else value,
                            }
                        )
    audits = summary.get("selection_audit", [])
    if isinstance(audits, Sequence) and not isinstance(audits, (str, bytes, bytearray)):
        for audit in audits:
            if not isinstance(audit, Mapping):
                continue
            base = {
                "participant_id": summary.get("participant_id"),
                "visit_ordinal": summary.get("visit_ordinal"),
                "workload_level": audit.get("workload_level"),
                "attempt_id": audit.get("new_attempt_id"),
                "attempt_number": "",
                "selected": "",
                "scope": "selection_audit",
                "domain": "audit",
            }
            for path, value in _flatten(audit):
                if path:
                    writer.writerow(
                        {
                            **base,
                            "metric": ".".join(path),
                            "value": "" if value is None else value,
                        }
                    )
    return stream.getvalue().encode("utf-8")


def visit_summary_markdown(summary: Mapping[str, Any]) -> bytes:
    participant = summary.get("participant_id", "—")
    visit = summary.get("visit_ordinal", "—")
    lines = [
        f"# Classic MATB visit summary — {participant}, visit {visit}",
        "",
        "> **Research use only. Descriptive results are not a diagnosis or medical advice.**",
        "",
        "| Workload | Attempt | Selected | Status | Task validity | RR signal quality | Failure reason |",
        "|---|---:|---|---|---|---|---|",
    ]
    workloads = summary.get("workloads", {})
    if isinstance(workloads, Mapping):
        for workload, group in sorted(workloads.items()):
            if not isinstance(group, Mapping):
                continue
            attempts = group.get("attempts", [])
            selected_id = group.get("selected_attempt_id")
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                session = attempt.get("session", {})
                if not isinstance(session, Mapping):
                    continue
                lines.append(
                    f"| {workload} | Attempt {session.get('attempt_number', '—')} | "
                    f"{'yes' if session.get('id') == selected_id else 'no'} | "
                    f"{session.get('status', '—')} | {session.get('task_validity', '—')} | "
                    f"{session.get('physiology_quality', '—')} | "
                    f"{session.get('failure_reason_code') or '—'} |"
                )
    lines.extend(["", "## Complete attempt data", ""])
    if isinstance(workloads, Mapping):
        for workload, group in sorted(workloads.items()):
            if not isinstance(group, Mapping):
                continue
            attempts = group.get("attempts", [])
            if not isinstance(attempts, Sequence):
                continue
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                session = attempt.get("session", {})
                if not isinstance(session, Mapping):
                    session = {}
                lines.extend(
                    [
                        f"### {workload} — Attempt {session.get('attempt_number', '—')}",
                        "",
                        "| Scope | Metric | Value |",
                        "|---|---|---|",
                    ]
                )
                for scope in ("session", "matb_metrics", "hrv"):
                    for path, value in _flatten(attempt.get(scope, {})):
                        if path:
                            escaped = str(value).replace("|", "\\|").replace("\n", " ")
                            lines.append(f"| {scope} | {'.'.join(path)} | {escaped} |")
                lines.append("")
    lines.extend(
        [
            "## Selection audit",
            "",
            "| Workload | Previous attempt | New attempt | Reason | Actor | Changed at |",
            "|---|---|---|---|---|---|",
        ]
    )
    audits = summary.get("selection_audit", [])
    if isinstance(audits, Sequence) and not isinstance(audits, (str, bytes, bytearray)):
        for audit in audits:
            if isinstance(audit, Mapping):
                lines.append(
                    f"| {audit.get('workload_level', '—')} | "
                    f"{audit.get('previous_attempt_id') or '—'} | "
                    f"{audit.get('new_attempt_id', '—')} | "
                    f"{audit.get('reason_code', '—')} | {audit.get('actor', '—')} | "
                    f"{audit.get('changed_at', '—')} |"
                )
    lines.extend(
        [
            "",
            "All retakes and selection changes are included; selected attempts feed the canonical visit analysis.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


__all__ = ["visit_summary_csv", "visit_summary_json", "visit_summary_markdown"]
