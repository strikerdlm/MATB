"""Build a deterministic, allowlisted MATB public-core candidate.

The command refuses a publish-mode export while release blockers remain.  A
candidate export is available for decoupling/build tests and always carries an
inventory binding every exported file to its SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "release" / "core-manifest.json"
_RUNTIME_ARTIFACT_DIRECTORIES = frozenset(
    {
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "htmlcov",
        "node_modules",
        "playwright-report",
        "exports",
        ".matb-core-e2e",
        ".suas-e2e",
        "sessions",
        "test-results",
    }
)
_SENSITIVE_FILENAMES = frozenset(
    {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
)
_SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")
_RUNTIME_ARTIFACT_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
)


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


def _runtime_artifact(relative: Path) -> bool:
    return (
        any(part in _RUNTIME_ARTIFACT_DIRECTORIES for part in relative.parts)
        or relative.name == ".coverage"
        or relative.name.endswith(_RUNTIME_ARTIFACT_SUFFIXES)
    )


def _sensitive_path(relative: Path) -> bool:
    name = relative.name.lower()
    return (
        name in _SENSITIVE_FILENAMES
        or name.startswith(".env.")
        or name.endswith(_SENSITIVE_SUFFIXES)
    )


def _git_visible_files(root: Path) -> frozenset[Path] | None:
    """Return tracked and non-ignored source candidates when Git metadata exists."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    inventory = frozenset(
        Path(value.decode("utf-8"))
        for value in completed.stdout.split(b"\0")
        if value
    )
    # ``git ls-files --cached --others`` includes paths deleted in an unstaged
    # rename. Candidate mode represents the visible worktree, so retain only
    # entries that currently exist. Keep symlinks in the inventory so the
    # caller can reject them explicitly instead of silently filtering them.
    return frozenset(
        relative
        for relative in inventory
        if (root / relative).exists() or (root / relative).is_symlink()
    )


def _git_tracked_files(root: Path) -> frozenset[Path] | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return frozenset(
        Path(value.decode("utf-8"))
        for value in completed.stdout.split(b"\0")
        if value
    )


def _git_source_state(root: Path) -> tuple[str, bool | None, str]:
    commit_process = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = commit_process.stdout.strip().lower()
    if commit_process.returncode != 0 or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit) is None:
        return "unknown", None, "provisional_missing_source_commit"
    status_process = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status_process.returncode != 0:
        return commit, None, "provisional_unknown_source_state"
    dirty = bool(status_process.stdout)
    return commit, dirty, "provisional_dirty_source_tree" if dirty else "complete"


def selected_files(
    root: Path,
    manifest: dict[str, Any],
    *,
    tracked_only: bool = False,
) -> tuple[Path, ...]:
    exclusions = tuple(_relative(value) for value in manifest["exclude"])
    git_inventory = _git_tracked_files(root) if tracked_only else _git_visible_files(root)
    if git_inventory is None:
        raise RuntimeError(
            "public-core export requires a Git tracked-file inventory; refusing recursive fallback"
        )
    selected: set[Path] = set()
    for value in manifest["include"]:
        relative = _relative(value)
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(f"release include is missing: {relative.as_posix()}")
        candidates: Iterable[Path]
        if source.is_file():
            if relative not in git_inventory:
                if tracked_only:
                    raise RuntimeError(
                        f"publish-mode release include is not tracked: {relative.as_posix()}"
                    )
                continue
            candidates = (source,)
        else:
            # Iterate the version-control inventory instead of recursively
            # walking broad source trees (which can encounter ignored dependency
            # symlinks, runtime data, or secrets before they are filtered).
            candidates = (
                root / candidate
                for candidate in git_inventory
                if relative in candidate.parents
            )
        for path in candidates:
            candidate = path.relative_to(root)
            if _excluded(candidate, exclusions):
                continue
            if _runtime_artifact(candidate):
                continue
            if candidate not in git_inventory:
                continue
            if path.is_symlink():
                raise ValueError(f"public-core export refuses symlink: {candidate.as_posix()}")
            if _sensitive_path(candidate):
                raise ValueError(f"sensitive public-core path selected: {candidate.as_posix()}")
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
    manifest_path = Path(manifest_path).resolve()
    governing_manifest_bytes = manifest_path.read_bytes()
    manifest = load_manifest(manifest_path)
    blockers = list(manifest["release_blockers"])
    if (not manifest.get("publishable") or blockers) and not candidate:
        raise RuntimeError("public release is blocked: " + ", ".join(blockers))
    source_commit, source_dirty, source_provenance_status = _git_source_state(ROOT)
    if not candidate and (
        source_dirty is not False or source_provenance_status != "complete"
    ):
        raise RuntimeError(
            "publish-mode export requires a clean Git source tree with a full commit identity"
        )
    destination = Path(destination).resolve()
    root = ROOT.resolve()
    if destination == root or root in destination.parents:
        raise ValueError("release destination must be outside the source repository")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("release destination must be absent or empty")
    files = selected_files(root, manifest, tracked_only=not candidate)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    # The release must carry the exact policy bytes that authorized its file
    # selection. A custom --manifest must never leave the repository's default
    # policy inside the artifact while the report hashes a different document.
    embedded_manifest = destination / "release" / "core-manifest.json"
    embedded_manifest.parent.mkdir(parents=True, exist_ok=True)
    embedded_manifest.write_bytes(governing_manifest_bytes)
    inventory_files = tuple(sorted(
        {*files, Path("release/core-manifest.json")},
        key=lambda path: path.as_posix(),
    ))
    file_inventory = inventory(destination, inventory_files)
    inventory_payload = json.dumps(
        file_inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    report = {
        "schema_version": "1.0",
        "release_name": manifest["release_name"],
        "target_version": manifest["target_version"],
        "candidate": bool(candidate),
        "publishable": (not candidate) and bool(manifest.get("publishable")) and not blockers,
        "release_blockers": blockers,
        "source_commit": source_commit,
        "source_dirty": source_dirty,
        "source_provenance_status": source_provenance_status,
        "release_manifest_sha256": hashlib.sha256(governing_manifest_bytes).hexdigest(),
        "files_inventory_sha256": hashlib.sha256(inventory_payload).hexdigest(),
        "file_selection_basis": "git_visible_worktree" if candidate else "git_tracked_clean_commit",
        "files": file_inventory,
    }
    payload = json.dumps(
        report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ) + "\n"
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
    files = selected_files(ROOT, manifest, tracked_only=not args.candidate)
    if args.dry_run:
        source_commit, source_dirty, source_status = _git_source_state(ROOT)
        print(
            json.dumps(
                {
                    "selected_files": len(files),
                    "publishable": bool(manifest.get("publishable")) and not manifest["release_blockers"],
                    "release_blockers": manifest["release_blockers"],
                    "source_commit": source_commit,
                    "source_dirty": source_dirty,
                    "source_provenance_status": source_status,
                    "file_selection_basis": (
                        "git_visible_worktree" if args.candidate else "git_tracked_clean_commit"
                    ),
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
