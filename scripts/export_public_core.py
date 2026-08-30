"""Build a deterministic, allowlisted MATB public-core candidate.

The command refuses a publish-mode export while release blockers remain.  A
candidate export is available for decoupling/build tests and always carries an
inventory binding every exported file to its SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "release" / "core-manifest.json"


def _relative(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe release path: {value!r}")
    return path


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ValueError("unsupported public-core manifest version")
    for key in ("include", "exclude", "forbidden_prefixes", "release_blockers"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"public-core manifest requires a {key} list")
    for value in (*payload["include"], *payload["exclude"], *payload["forbidden_prefixes"]):
        _relative(value.rstrip("/"))
    return payload


def _excluded(relative: Path, exclusions: tuple[Path, ...]) -> bool:
    return any(relative == item or item in relative.parents for item in exclusions)


def selected_files(root: Path, manifest: dict[str, Any]) -> tuple[Path, ...]:
    exclusions = tuple(_relative(value) for value in manifest["exclude"])
    selected: set[Path] = set()
    for value in manifest["include"]:
        relative = _relative(value)
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(f"release include is missing: {relative.as_posix()}")
        candidates: Iterable[Path]
        if source.is_file():
            candidates = (source,)
        else:
            candidates = (path for path in source.rglob("*") if path.is_file())
        for path in candidates:
            candidate = path.relative_to(root)
            if _excluded(candidate, exclusions):
                continue
            if any(part in {"__pycache__", ".pytest_cache", "node_modules", ".next"} for part in candidate.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            selected.add(candidate)
    forbidden = tuple(str(value).replace("\\", "/") for value in manifest["forbidden_prefixes"])
    violations = [path.as_posix() for path in selected if path.as_posix().startswith(forbidden)]
    if violations:
        raise ValueError(f"forbidden public-core paths selected: {violations}")
    return tuple(sorted(selected, key=lambda path: path.as_posix()))


def inventory(root: Path, files: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in files:
        data = (root / relative).read_bytes()
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return rows


def export_candidate(
    destination: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    candidate: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    blockers = list(manifest["release_blockers"])
    if (not manifest.get("publishable") or blockers) and not candidate:
        raise RuntimeError("public release is blocked: " + ", ".join(blockers))
    destination = Path(destination).resolve()
    root = ROOT.resolve()
    if destination == root or root in destination.parents:
        raise ValueError("release destination must be outside the source repository")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("release destination must be absent or empty")
    files = selected_files(root, manifest)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    report = {
        "schema_version": "1.0",
        "release_name": manifest["release_name"],
        "target_version": manifest["target_version"],
        "candidate": bool(candidate),
        "publishable": bool(manifest.get("publishable")) and not blockers,
        "release_blockers": blockers,
        "files": inventory(destination, files),
    }
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (destination / "PUBLIC_CORE_INVENTORY.json").write_text(payload, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_manifest(Path(args.manifest))
    files = selected_files(ROOT, manifest)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "selected_files": len(files),
                    "publishable": bool(manifest.get("publishable")) and not manifest["release_blockers"],
                    "release_blockers": manifest["release_blockers"],
                },
                sort_keys=True,
            )
        )
        return 0
    if not args.destination:
        parser.error("destination is required unless --dry-run is used")
    report = export_candidate(
        Path(args.destination), manifest_path=Path(args.manifest), candidate=args.candidate
    )
    print(json.dumps({"files": len(report["files"]), "publishable": report["publishable"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
