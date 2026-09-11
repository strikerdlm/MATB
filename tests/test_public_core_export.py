from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.export_public_core import (
    ROOT,
    _git_visible_files,
    export_candidate,
    load_manifest,
    selected_files,
)


def test_public_core_selection_excludes_sensitive_product_trees() -> None:
    manifest = load_manifest()
    files = selected_files(ROOT, manifest)
    names = {path.as_posix() for path in files}
    assert "matb_integration/qualification/contracts.py" in names
    assert "openmatb/LICENSE" in names
    assert not any(name.startswith("SMS/") for name in names)
    assert not any(name.startswith("matb_integration/suas/") for name in names)
    assert "webui/backend/app/routers/geography.py" not in names
    assert "webui/backend/app/traffic_service.py" not in names
    assert not any(name.startswith("webui/frontend/src/lib/geography/") for name in names)
    assert not any(name.startswith("webui/frontend/public/scenes/") for name in names)
    assert not any(name.startswith("matb_integration/liftoff/") for name in names)
    assert not any(name.startswith("openmatb/sessions/") for name in names)
    assert not any("/test-results/" in name for name in names)
    assert not any(name.endswith(".tsbuildinfo") for name in names)
    assert not any(name.endswith((".db", ".db-wal", ".db-shm", ".db-journal")) for name in names)


def test_public_core_selection_fails_closed_without_git_metadata(
    tmp_path: Path,
) -> None:
    """Publishing from an unverifiable copied tree must never recurse broadly."""
    safe = tmp_path / "openmatb" / "core" / "runtime.py"
    safe.parent.mkdir(parents=True)
    safe.write_text("# safe source\n", encoding="utf-8")
    artifacts = (
        tmp_path / "openmatb" / "sessions" / "participant.csv",
        tmp_path / "webui" / "backend" / "matb_webui.db",
        tmp_path / "webui" / "frontend" / "tsconfig.tsbuildinfo",
        tmp_path / "webui" / "frontend" / "test-results" / "trace.json",
    )
    for artifact in artifacts:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("sensitive\n", encoding="utf-8")
    manifest = {
        "include": ["openmatb", "webui"],
        "exclude": [],
        "forbidden_prefixes": [],
    }

    with pytest.raises(RuntimeError, match="tracked-file inventory"):
        selected_files(tmp_path, manifest)


def test_git_visible_inventory_excludes_unstaged_deletions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement = tmp_path / "webui" / "vitest.config.mts"
    replacement.parent.mkdir(parents=True)
    replacement.write_text("export default {};\n", encoding="utf-8")
    completed = subprocess.CompletedProcess(
        args=["git", "ls-files"],
        returncode=0,
        stdout=b"webui/vitest.config.ts\0webui/vitest.config.mts\0",
        stderr=b"",
    )
    monkeypatch.setattr(
        "scripts.export_public_core.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    assert _git_visible_files(tmp_path) == frozenset(
        {Path("webui/vitest.config.mts")}
    )


def test_public_core_selection_rejects_tracked_symlinks_and_secret_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "openmatb" / "core" / "runtime.py"
    safe.parent.mkdir(parents=True)
    safe.write_text("# safe source\n", encoding="utf-8")
    secret = tmp_path / "openmatb" / ".env.production"
    secret.write_text("TOKEN=secret\n", encoding="utf-8")
    link = tmp_path / "openmatb" / "core" / "linked.py"
    link.symlink_to(safe)
    monkeypatch.setattr(
        "scripts.export_public_core._git_visible_files",
        lambda _root: frozenset(
            {
                Path("openmatb/core/runtime.py"),
                Path("openmatb/.env.production"),
                Path("openmatb/core/linked.py"),
            }
        ),
    )
    manifest = {"include": ["openmatb"], "exclude": [], "forbidden_prefixes": []}

    with pytest.raises(ValueError, match="symlink|sensitive"):
        selected_files(tmp_path, manifest)


def test_publish_export_fails_while_evidence_gates_are_blocked(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="public release is blocked"):
        export_candidate(tmp_path / "public")


@pytest.mark.parametrize("object_id_length", [40, 64])
def test_candidate_export_has_hashed_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, object_id_length: int
) -> None:
    monkeypatch.setattr(
        "scripts.export_public_core._git_source_state",
        lambda _root: ("a" * object_id_length, True, "provisional_dirty_source_tree"),
    )
    report = export_candidate(tmp_path / "candidate", candidate=True)
    assert report["candidate"] is True
    assert report["publishable"] is False
    assert report["files"]
    assert all(len(item["sha256"]) == 64 for item in report["files"])
    assert len(report["source_commit"]) == object_id_length
    assert report["source_dirty"] is True
    assert report["source_provenance_status"] == "provisional_dirty_source_tree"
    assert len(report["release_manifest_sha256"]) == 64
    assert len(report["files_inventory_sha256"]) == 64
    assert (tmp_path / "candidate" / "PUBLIC_CORE_INVENTORY.json").is_file()


def test_publish_mode_refuses_a_dirty_source_even_if_policy_blockers_are_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    manifest.update({"publishable": True, "release_blockers": []})
    manifest_path = tmp_path / "publishable.json"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.export_public_core._git_source_state",
        lambda _root: ("a" * 40, True, "provisional_dirty_source_tree"),
    )

    with pytest.raises(RuntimeError, match="clean Git source tree"):
        export_candidate(
            tmp_path / "public",
            manifest_path=manifest_path,
            candidate=False,
        )


def test_candidate_records_an_explicit_clean_source_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "scripts.export_public_core._git_source_state",
        lambda _root: ("b" * 64, False, "complete"),
    )

    report = export_candidate(tmp_path / "clean-candidate", candidate=True)

    assert report["source_commit"] == "b" * 64
    assert report["source_dirty"] is False
    assert report["source_provenance_status"] == "complete"


def test_custom_publish_policy_is_the_exact_manifest_embedded_in_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    manifest.update({"publishable": True, "release_blockers": []})
    manifest_path = tmp_path / "custom-release-policy.json"
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    monkeypatch.setattr(
        "scripts.export_public_core._git_source_state",
        lambda _root: ("a" * 40, False, "complete"),
    )
    visible_files = _git_visible_files(ROOT)
    assert visible_files is not None
    monkeypatch.setattr(
        "scripts.export_public_core._git_tracked_files",
        lambda _root: visible_files,
    )

    destination = tmp_path / "public"
    report = export_candidate(
        destination,
        manifest_path=manifest_path,
        candidate=False,
    )

    embedded = destination / "release" / "core-manifest.json"
    expected_digest = hashlib.sha256(manifest_bytes).hexdigest()
    assert embedded.read_bytes() == manifest_bytes
    assert report["release_manifest_sha256"] == expected_digest
    inventory_row = next(
        item for item in report["files"]
        if item["path"] == "release/core-manifest.json"
    )
    assert inventory_row["sha256"] == expected_digest


def test_candidate_backend_runs_without_optional_product_components(tmp_path: Path) -> None:
    """Catch static imports that make the allowlisted research core unusable."""
    destination = tmp_path / "candidate"
    export_candidate(destination, candidate=True)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(destination), *[part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part and not Path(part).resolve().is_relative_to(ROOT)]])
    environment["MATB_COMPONENTS"] = "core"
    environment["MATB_DB_PATH"] = str(tmp_path / "candidate.sqlite")
    script = """
import asyncio
import httpx
from app.main import app

async def verify():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
        health = await client.get('/health')
        capabilities = await client.get('/capabilities')
    assert health.json() == {'status': 'ok'}
    assert capabilities.status_code == 200
    ids = [item['component_id'] for item in capabilities.json()['components']]
    assert ids == [
        'matb-automation',
        'matb-console',
        'matb-contracts',
        'matb-research',
        'matb-runtime',
    ]
    routes = {route.path for route in app.routes}
    assert '/simulation/sessions' not in routes
    assert '/liftoff/sessions' not in routes


# Exercise real startup/migrations in the physically stripped tree, then restore
# its historical native evidence association and immutable bytes in a new DB.
from datetime import date
from pathlib import Path
import json, sqlite3, os, subprocess, sys
from sqlmodel import Session, select
from app.db import get_engine
from app.models import Participant, Visit
from app.evidence_models import EvidenceArtifact
from app.evidence_service import ingest_evidence
from app.assessment_models import AssessmentSourceLink
from app.study_registry_models import StudyWorkspace
from app.study_protocol import selected_protocol
from app import station_resources
from app.study_backup import backup, restore
from matb_integration.evidence.reference import synthetic_capture

async def restoration():
    database = Path(os.environ['MATB_DB_PATH'])
    original = database.parent / 'legacy native source ñ'
    async with app.router.lifespan_context(app):
        with Session(get_engine()) as db:
            db.add(Participant(id='P01', enrollment_date=date(2026,9,10))); db.flush()
            db.add(Visit(participant_id='P01', visit_ordinal=1, scheduled_day=0)); db.commit()
            artifacts = synthetic_capture(original, identity='core-restoration')
            capture_id, _ = ingest_evidence(db, artifacts)
            protocol = selected_protocol()
            db.add(StudyWorkspace(study_id='core-restore', template_family='pre-post-recovery',
                deployment_protocol_id=protocol.protocol_id, deployment_schedule_sha256=protocol.schedule_sha256))
            station_resources.maintenance(db, True, actor='Dr Synthetic', reason='Core restore')
            db.commit()
    # Recreate the pre-parent-index evidence schema using only this owned DB.
    # Startup must migrate it, retaining unknown historical parentage and bytes.
    get_engine().dispose()
    from contextlib import closing
    with closing(sqlite3.connect(database)) as legacy:
        legacy.execute('DROP INDEX IF EXISTS ix_evidence_capture_parent_session_id')
        legacy.execute('ALTER TABLE evidence_capture DROP COLUMN parent_session_id')
        legacy.commit()
    async with app.router.lifespan_context(app):
        with Session(get_engine()) as db:
            links = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table=='evidence_capture', AssessmentSourceLink.source_id==capture_id)).all()
            assert len(links)==1
            attempt_id = links[0].attempt_id
            stored = {r.role:r.content for r in db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id==capture_id))}
            assert stored==artifacts
    archive = database.parent / 'core-study.zip'
    backup(database, archive)
    original.rename(database.parent / 'original-native-unavailable')
    restored = database.parent / 'restored core ñ'
    report = restore(archive, restored, expected_study_id='core-restore', available_components=set())
    get_engine().dispose()
    import app.db as database_module
    from sqlmodel import create_engine
    database_module._engine = create_engine('sqlite:///' + str(restored/'study.sqlite3'))
    async with app.router.lifespan_context(app):
        with Session(get_engine()) as db:
            links = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table=='evidence_capture', AssessmentSourceLink.source_id==capture_id)).all()
            assert len(links)==1 and links[0].attempt_id==attempt_id
            assert {r.role:r.content for r in db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id==capture_id))}==artifacts
    assert report['status']=='restored_in_maintenance'
    for name in ('study_workspace.py','verify_study_descriptive.py','prepare_study_wheels.py','station_load_matrix.py'):
        assert (Path.cwd().parents[1]/'tools'/name).is_file()
    assert not (Path.cwd().parents[1]/'matb_integration/liftoff').exists()
    assert not (Path.cwd().parents[1]/'matb_integration/suas').exists()

asyncio.run(verify())
asyncio.run(restoration())
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=destination / "webui" / "backend",
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
