"""Checksum sealing, ZIP packing, and bounded validation for research bundles."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from .schema import BUNDLE_SCHEMA_VERSION, SAMPLE_FIELDS, TRIAL_FIELDS


REQUIRED_ARTIFACTS = frozenset({
    "events.csv",
    "samples.csv",
    "samples.parquet",
    "trials.csv",
    "summary.json",
    "manifest.json",
    "data_dictionary.json",
    "quality.json",
})
CHECKSUM_NAME = "checksums.sha256"
MAX_ZIP_ENTRIES = 32
MAX_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024


def _artifact_paths(run_dir: Path) -> tuple[Path, ...]:
    return tuple(sorted(
        (
            path
            for path in run_dir.iterdir()
            if path.is_file() and path.name not in {CHECKSUM_NAME} and not path.name.endswith(".tmp")
        ),
        key=lambda path: path.name,
    ))


def write_checksums(run_dir: Path) -> Path:
    root = Path(run_dir)
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in _artifact_paths(root)]
    destination = root / CHECKSUM_NAME
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def pack_bundle(run_dir: Path) -> Path:
    root = Path(run_dir)
    stem = root.name.removesuffix(".research")
    destination = root.with_name(f"{stem}.matb.zip")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if path.is_file() and not path.name.endswith(".tmp"):
                archive.write(path, arcname=path.name)
    temporary.replace(destination)
    return destination


def _checksum_codes(run_dir: Path) -> list[str]:
    checksum_path = run_dir / CHECKSUM_NAME
    if not checksum_path.is_file():
        return ["checksum_missing"]
    try:
        lines = checksum_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ["checksum_unreadable"]
    codes: list[str] = []
    expected: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if len(line) < 67 or line[64:66] != "  ":
            codes.append(f"checksum_invalid_line:{line_number}")
            continue
        digest, name = line[:64], line[66:]
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not name
            or Path(name).is_absolute()
            or len(Path(name).parts) != 1
        ):
            codes.append(f"checksum_invalid_line:{line_number}")
            continue
        expected[name] = digest
    for name, digest in sorted(expected.items()):
        path = run_dir / name
        if not path.is_file():
            codes.append(f"checksum_missing:{name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            codes.append(f"checksum_mismatch:{name}")
    actual = {path.name for path in _artifact_paths(run_dir)}
    for name in sorted(actual - set(expected)):
        codes.append(f"checksum_unlisted:{name}")
    return codes


def _directory_validation(run_dir: Path) -> dict[str, object]:
    names = {path.name for path in run_dir.iterdir() if path.is_file()}
    codes = [f"artifact_missing:{name}" for name in sorted(REQUIRED_ARTIFACTS - names)]
    codes.extend(_checksum_codes(run_dir))
    if not any(code.startswith(("artifact_missing:", "checksum_")) for code in codes):
        codes.extend(_semantic_codes(run_dir))
    return {"status": "error" if codes else "ok", "codes": codes}


def _semantic_codes(run_dir: Path) -> list[str]:
    codes: list[str] = []
    documents: dict[str, object] = {}
    for name in ("manifest.json", "summary.json", "data_dictionary.json", "quality.json"):
        try:
            documents[name] = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            codes.append(f"json_invalid:{name}")
    for name in ("manifest.json", "summary.json", "data_dictionary.json"):
        document = documents.get(name)
        if isinstance(document, dict) and document.get("schema_version") != BUNDLE_SCHEMA_VERSION:
            codes.append(f"schema_mismatch:{name}")
        elif document is not None and not isinstance(document, dict):
            codes.append(f"json_root_invalid:{name}")
    expected_headers = {
        "samples.csv": [field.name for field in SAMPLE_FIELDS],
        "trials.csv": [field.name for field in TRIAL_FIELDS],
    }
    for name, expected in expected_headers.items():
        try:
            with (run_dir / name).open(encoding="utf-8", newline="") as stream:
                observed = next(csv.reader(stream))
        except (OSError, UnicodeDecodeError, StopIteration):
            codes.append(f"csv_header_invalid:{name}")
        else:
            if observed != expected:
                codes.append(f"csv_schema_mismatch:{name}")
    try:
        parquet = (run_dir / "samples.parquet").read_bytes()
    except OSError:
        parquet = b""
    if len(parquet) < 8 or parquet[:4] != b"PAR1" or parquet[-4:] != b"PAR1":
        codes.append("parquet_magic_invalid:samples.parquet")
    summary = documents.get("summary.json")
    if isinstance(summary, dict):
        run_status = summary.get("status")
        if run_status not in {"complete", "partial"}:
            codes.append("summary_status_invalid")
        if run_status == "partial" and "partial-run.json" not in {path.name for path in run_dir.iterdir()}:
            codes.append("partial_marker_missing")
        if run_status == "complete" and (run_dir / "partial-run.json").exists():
            codes.append("partial_marker_unexpected")
    return codes


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> tuple[str, ...]:
    infos = archive.infolist()
    codes: list[str] = []
    if len(infos) > MAX_ZIP_ENTRIES:
        codes.append("zip_too_many_entries")
    if sum(info.compress_size for info in infos) > MAX_COMPRESSED_BYTES:
        codes.append("zip_compressed_size")
    if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
        codes.append("zip_expanded_size")
    names: set[str] = set()
    for info in infos:
        path = Path(info.filename)
        if info.is_dir() or path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
            codes.append(f"zip_unsafe_path:{info.filename}")
        elif info.filename in names:
            codes.append(f"zip_duplicate_entry:{info.filename}")
        else:
            names.add(info.filename)
    if codes:
        return tuple(codes)
    for info in infos:
        target = destination / info.filename
        with archive.open(info) as source, target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
    return ()


def validate_bundle(path: Path) -> dict[str, object]:
    source = Path(path)
    if source.is_dir():
        return _directory_validation(source)
    if not source.is_file() or not zipfile.is_zipfile(source):
        return {"status": "error", "codes": ["bundle_not_zip_or_directory"]}
    with tempfile.TemporaryDirectory(prefix="matb-bundle-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(source) as archive:
            extraction_codes = _safe_extract(archive, root)
        if extraction_codes:
            return {"status": "error", "codes": list(extraction_codes)}
        return _directory_validation(root)


__all__ = [
    "CHECKSUM_NAME",
    "MAX_COMPRESSED_BYTES",
    "MAX_EXPANDED_BYTES",
    "MAX_ZIP_ENTRIES",
    "REQUIRED_ARTIFACTS",
    "pack_bundle",
    "validate_bundle",
    "write_checksums",
]
