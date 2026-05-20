"""SAGAT probe-bank parser, validator, and writer.

Pyglet-free. Used both at runtime (by the Sagat plugin) and at
scenario-generation time (by scenario_builder_ext.py).

File format: header line(s) prefixed with '#'. Then one stanza per probe,
fields in fixed order separated by newlines, stanzas separated by blank lines.
See docs/superpowers/specs/2026-05-20-sagat-freeze-probe-design.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROBE_BANK_FORMAT_VERSION: Final[str] = "1.0"

_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "PROBE_ID",
    "SA_LEVEL",
    "DOMAIN",
    "QUESTION",
    "OPTIONS",
    "CORRECT",
    "TIMEOUT_SEC",
)

_VALID_DOMAINS: Final[dict[int, str]] = {
    1: "perception",
    2: "comprehension",
    3: "projection",
}

_UNKNOWN_ANCHOR_EN: Final[str] = "Unknown"
_UNKNOWN_ANCHOR_ES: Final[str] = "No sé"


class ProbeBankError(ValueError):
    """Raised when a probe-bank file fails parsing or validation."""


@dataclass(frozen=True)
class Probe:
    probe_id: str
    sa_level: int
    domain: str
    question: str
    options: tuple[str, ...]
    correct: str
    timeout_sec: int


def _is_es_bank(path: Path) -> bool:
    return path.name.endswith("_es.txt")


def load_probes(path: Path) -> list[Probe]:
    """Parse a probe-bank file and return validated Probe objects.

    Raises ProbeBankError on any validation failure.
    """
    if not path.exists():
        raise ProbeBankError(f"Probe bank file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    stanzas = _split_into_stanzas(raw)
    probes: list[Probe] = []
    anchor = _UNKNOWN_ANCHOR_ES if _is_es_bank(path) else _UNKNOWN_ANCHOR_EN

    seen_ids: set[str] = set()
    for stanza_lines in stanzas:
        probe = _parse_stanza(stanza_lines, anchor)
        if probe.probe_id in seen_ids:
            raise ProbeBankError(f"Duplicate probe_id: {probe.probe_id}")
        seen_ids.add(probe.probe_id)
        probes.append(probe)

    if not probes:
        raise ProbeBankError(f"Probe bank file is empty (no probes found): {path}")

    return probes


def _split_into_stanzas(raw: str) -> list[list[str]]:
    """Split file content into stanzas (lists of non-empty, non-comment lines)."""
    stanzas: list[list[str]] = []
    current: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current:
                stanzas.append(current)
                current = []
            continue
        current.append(stripped)
    if current:
        stanzas.append(current)
    return stanzas


def _parse_stanza(lines: list[str], unknown_anchor: str) -> Probe:
    fields: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            raise ProbeBankError(f"Malformed line (no colon): {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in _REQUIRED_FIELDS:
            raise ProbeBankError(f"Unknown field {key!r} in stanza")
        if key in fields:
            raise ProbeBankError(f"Duplicate field {key!r} in stanza")
        fields[key] = value

    missing = [f for f in _REQUIRED_FIELDS if f not in fields]
    if missing:
        probe_id = fields.get("PROBE_ID", "<unknown>")
        raise ProbeBankError(f"Probe {probe_id}: missing required fields {missing}")

    # SA_LEVEL
    try:
        sa_level = int(fields["SA_LEVEL"])
    except ValueError:
        raise ProbeBankError(f"Probe {fields['PROBE_ID']}: SA_LEVEL must be integer")
    if sa_level not in _VALID_DOMAINS:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: SA_LEVEL must be 1, 2, or 3 (got {sa_level})"
        )

    # DOMAIN consistency
    expected_domain = _VALID_DOMAINS[sa_level]
    if fields["DOMAIN"] != expected_domain:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: DOMAIN={fields['DOMAIN']!r} "
            f"inconsistent with SA_LEVEL={sa_level} (expected {expected_domain!r})"
        )

    # OPTIONS
    options = tuple(o.strip() for o in fields["OPTIONS"].split("|") if o.strip())
    if not 2 <= len(options) <= 6:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: OPTIONS must have 2-6 entries (got {len(options)})"
        )

    # CORRECT must appear in OPTIONS
    if fields["CORRECT"] not in options:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: CORRECT={fields['CORRECT']!r} not in OPTIONS"
        )

    # Auto-append uncertainty anchor (silent — documented behaviour)
    if unknown_anchor not in options:
        options = (*options, unknown_anchor)

    # TIMEOUT_SEC
    try:
        timeout_sec = int(fields["TIMEOUT_SEC"])
    except ValueError:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: TIMEOUT_SEC must be integer"
        )
    if not 5 <= timeout_sec <= 60:
        raise ProbeBankError(
            f"Probe {fields['PROBE_ID']}: TIMEOUT_SEC must be 5-60 (got {timeout_sec})"
        )

    return Probe(
        probe_id=fields["PROBE_ID"],
        sa_level=sa_level,
        domain=fields["DOMAIN"],
        question=fields["QUESTION"],
        options=options,
        correct=fields["CORRECT"],
        timeout_sec=timeout_sec,
    )


def validate_bank(probes: list[Probe]) -> None:
    """Validate an already-parsed list of probes (cross-probe checks)."""
    seen: set[str] = set()
    for p in probes:
        if p.probe_id in seen:
            raise ProbeBankError(f"Duplicate probe_id in bank: {p.probe_id}")
        seen.add(p.probe_id)


def write_freeze_file(
    path: Path,
    probes: list[Probe],
    header: dict[str, object] | None = None,
) -> None:
    """Write a per-freeze probe file (inverse of load_probes).

    The auto-appended "Unknown"/"No sé" anchor is NOT written back — the file
    is regenerated by load_probes' reader from the bank-language inference.
    """
    raise NotImplementedError  # filled in Task 2
