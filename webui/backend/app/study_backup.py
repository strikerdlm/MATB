"""Consistent local-study bundles and staged, empty-workspace restoration.

Only stdlib is required to restore. SQLite's writer lock spans the entire backup,
including file hashing. Acquisition and workers must already be in maintenance.
Checksums detect modification; they do not authenticate an untrusted publisher.
"""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import secrets
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
import zipfile

SCHEMA = "matb-whole-study-v1"
ROOT_ENV = (
    "MATB_OPENMATB_OUTPUT_DIR",
    "MATB_PHYSIOLOGY_DIR",
    "MATB_LIFTOFF_OUTPUT_DIR",
    "MATB_SIMULATION_OUTPUT_DIR",
    "MATB_SIMULATION_SCENARIO_DIR",
)
OPTIONAL_TABLES = {
    "openmatb_suite_session": "app.openmatb_component",
    "polar_capture": "app.physiology_component",
    "liftoff_session": "app.liftoff_component",
    "simulation_session": "app.simulation_component",
    "technical_simulation_session": "app.simulation_component",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def tables(db):
    return {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def rows(db, table):
    if table not in tables(db):
        return []
    return [dict(row) for row in db.execute('SELECT * FROM "' + table + '"')]


def require_idle(db):
    state = rows(db, "station_state")
    if not state or not state[0]["maintenance"]:
        raise ValueError("Exclusive station maintenance is required before backup.")
    if json.loads(state[0]["reservation_json"]) or json.loads(state[0]["lanes_json"]):
        raise ValueError("Live collection prevents maintenance backup.")
    if any(
        r["status"] in {"running", "cancelling", "uncertain"}
        for r in rows(db, "station_job")
    ):
        raise ValueError("Live writer prevents maintenance backup.")


def validate_database(db):
    """Check semantic identities as well as SQLite FKs, without rewriting history."""
    if (
        db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
        or db.execute("PRAGMA foreign_key_check").fetchall()
    ):
        raise ValueError("Database integrity or foreign key violation")
    versions = {r["id"]: r for r in rows(db, "study_version")}
    for row in versions.values():
        for payload, hashed in [
            ("study_json", "study_sha256"),
            ("analysis_json", "analysis_sha256"),
        ]:
            if digest(canonical(json.loads(row[payload])).encode()) != row[hashed]:
                raise ValueError("Frozen study/plan fingerprint mismatch")
    assignments = {r["id"]: r for r in rows(db, "study_assignment")}
    attempts = {r["id"]: r for r in rows(db, "assessment_attempt")}
    preparations = {r["id"]: r for r in rows(db, "study_preparation")}
    events = {r["id"]: r for r in rows(db, "study_preparation_event")}
    for prep in preparations.values():
        presentation = json.loads(prep["presentation_json"])
        identity = dict(
            version_id=prep["version_id"],
            presentation=presentation,
            requirement=json.loads(prep["requirement_json"]),
        )
        if (
            digest(canonical(identity).encode()) != prep["identity_sha256"]
            or digest(canonical(presentation["config"]).encode())
            != prep["config_sha256"]
        ):
            raise ValueError("Preparation snapshot identity/configuration mismatch")
    for row in rows(db, "study_preparation_admission"):
        snapshot = json.loads(row["snapshot_json"])
        assignment = assignments[row["assignment_id"]]
        version = versions[assignment["version_id"]]
        if (
            digest(canonical(snapshot).encode()) != row["snapshot_sha256"]
            or snapshot["attempt_id"] != row["attempt_id"]
            or snapshot["assignment_id"] != assignment["id"]
            or snapshot["version_id"] != version["id"]
            or snapshot["study_sha256"] != version["study_sha256"]
            or json.loads(assignment["occasions_json"])[snapshot["occasion_key"]]
            != attempts[row["attempt_id"]]["occasion_id"]
        ):
            raise ValueError("Preparation admission identity mismatch")
        for requirement in snapshot["requirements"]:
            prep = preparations[requirement["preparation_id"]]
            if (
                prep["assignment_id"] != assignment["id"]
                or prep["version_id"] != version["id"]
                or prep["identity_sha256"] != requirement["identity_sha256"]
                or prep["config_sha256"] != requirement["config_sha256"]
            ):
                raise ValueError("Preparation assignment/configuration mismatch")
            accepted = set()
            for frozen in requirement["event_frontier"]:
                event = events[frozen["id"]]
                if (
                    event["preparation_id"] != prep["id"]
                    or event["stage"] != frozen["stage"]
                    or event["passed"] != frozen["passed"]
                    or event["attempt_id"] != frozen["attempt_id"]
                    or digest(event["payload_json"].encode())
                    != frozen["payload_sha256"]
                ):
                    raise ValueError("Preparation event frontier mismatch")
                if event["passed"]:
                    accepted.add(event["id"])
            if not set(requirement["decision_event_ids"]) <= accepted:
                raise ValueError("Preparation decision is outside accepted frontier")
    for row in rows(db, "study_native_rating"):
        if digest(row["payload_json"].encode()) != row["payload_sha256"]:
            raise ValueError("Native rating checksum mismatch")
    for table in sorted(tables(db)):
        columns = {r[1] for r in db.execute('PRAGMA table_info("' + table + '")')}
        if {"content", "sha256"} <= columns:
            for row in db.execute('SELECT content,sha256 FROM "' + table + '"'):
                if digest(row["content"]) != row["sha256"]:
                    raise ValueError("Immutable blob checksum mismatch: " + table)
    for row in rows(db, "study_analysis_execution"):
        snapshot = json.loads(row["snapshot_json"])
        if (
            digest(canonical(snapshot).encode()) != row["data_sha256"]
            or digest(canonical(snapshot["implementation"]).encode())
            != row["implementation_sha256"]
            or versions[row["version_id"]]["analysis_sha256"] != row["plan_sha256"]
        ):
            raise ValueError("Analysis execution fingerprint mismatch")
    for row in rows(db, "study_analysis_input"):
        if (
            digest(
                canonical(
                    dict(
                        snapshot=json.loads(row["snapshot_json"]),
                        request=json.loads(row["request_json"]),
                    )
                ).encode()
            )
            != row["id"]
        ):
            raise ValueError("Frozen selection fingerprint mismatch")
    for row in rows(db, "hcf_derivation"):
        if digest(canonical(json.loads(row["snapshot_json"])).encode()) != row["id"]:
            raise ValueError("HCF derivation fingerprint mismatch")
    workspace = rows(db, "study_workspace")
    if len(workspace) != 1:
        raise ValueError("Exactly one bound study workspace is required")
    if any(v["study_id"] != workspace[0]["study_id"] for v in versions.values()):
        raise ValueError("Frozen version study identity mismatch")
    return workspace[0]


def inventory(db, database):
    from .artifact_paths import resolve_artifact

    roots = {}
    required_files = []
    incomplete = []

    def add(value, environment=None, required=True):
        original = str(value)
        physical = resolve_artifact(original).expanduser().resolve()
        if not physical.exists():
            if required:
                raise ValueError("Required artifact source is missing: " + original)
            roots.setdefault(
                original,
                dict(
                    original=original,
                    physical=str(physical),
                    environment=environment,
                    empty_directory=True,
                ),
            )
            return
        if physical.is_symlink() or Path(value).is_symlink():
            raise ValueError("Symlink artifact roots are not supported")
        roots.setdefault(
            original,
            dict(original=original, physical=str(physical), environment=environment),
        )

    repository = Path(__file__).resolve().parents[3]
    defaults = dict(
        zip(
            ROOT_ENV,
            [
                "exports/openmatb-controlled",
                "exports/physiology",
                "exports/liftoff",
                "exports/simulation",
                "scenarios/suas",
            ],
        )
    )
    for variable in ROOT_ENV:
        configured = os.getenv(variable)
        path = (
            Path(configured).expanduser()
            if configured
            else repository / defaults[variable]
        )
        if not path.is_absolute():
            path = repository / path
        if configured or path.is_dir():
            add(path, variable, required=False)
    for table in sorted(tables(db)):
        columns = {r[1] for r in db.execute('PRAGMA table_info("' + table + '")')}
        relevant = columns & {
            "artifact_root",
            "active_session_csv",
            "session_csv",
            "scenario_paths_json",
            "artifact_state",
            "incomplete_reasons_json",
            "id",
        }
        if not relevant - {"id"}:
            continue
        selected = ",".join('"' + key + '"' for key in sorted(relevant))
        for raw in db.execute("SELECT " + selected + ' FROM "' + table + '"'):
            row = dict(raw)
            if row.get("artifact_root"):
                add(row["artifact_root"])
            for key in ("active_session_csv", "session_csv"):
                if row.get(key):
                    required_files.append(row[key])
            if row.get("scenario_paths_json"):
                required_files.extend(json.loads(row["scenario_paths_json"]).values())
            if row.get("artifact_state") not in (None, "finalized"):
                incomplete.append(
                    dict(
                        table=table,
                        id=str(row.get("id")),
                        state=row["artifact_state"],
                        reasons=row.get("incomplete_reasons_json"),
                    )
                )
    job_root = Path(database).parent / "station-job-artifacts"
    for row in rows(db, "station_job"):
        if row.get("result_json"):
            required_files.append(str(job_root / (row["id"] + ".response")))
    if job_root.exists():
        add(job_root)
    for value in required_files:
        physical = resolve_artifact(value).resolve()
        if not physical.is_file():
            raise ValueError("Required artifact source is missing: " + str(value))
        if not any(
            physical.is_relative_to(Path(r["physical"])) for r in roots.values()
        ):
            add(value)
    # Native sidecar manifests describe required source bytes independently of DB blobs.
    suffixes = dict(
        events=".scientific.events.jsonl",
        timing=".timing.observations.jsonl",
        scenario_manifest=".scenario.manifest.json",
        legacy_csv=".csv",
    )
    for value in required_files:
        csv = resolve_artifact(value)
        manifest_path = csv.with_suffix(".capture.manifest.json")
        if csv.suffix != ".csv" or not manifest_path.is_file():
            continue  # Historical native CSVs genuinely predate sidecar evidence.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for role, item in manifest.get("artifacts", {}).items():
            if role not in suffixes:
                raise ValueError("Unsupported required native artifact role: " + role)
            artifact = csv.with_suffix(suffixes[role])
            if not artifact.is_file() or file_digest(artifact) != item["sha256"]:
                raise ValueError(
                    "Recorded native artifact missing or checksum mismatch"
                )
        if manifest.get("completion") != "completed":
            incomplete.append(
                dict(
                    table="native_manifest",
                    id=str(manifest_path),
                    state=manifest.get("completion"),
                    reasons=manifest.get("failure_reason"),
                )
            )
    # Validate recorded checksums before taking our own inventory of source bytes.
    for table, parent in [
        ("liftoff_artifact", "liftoff_session"),
        ("simulation_artifact", "simulation_session"),
        ("technical_simulation_artifact", "technical_simulation_session"),
    ]:
        sessions = {r["id"]: r for r in rows(db, parent)}
        for row in rows(db, table):
            root = resolve_artifact(
                sessions[row["session_id"]]["artifact_root"]
            ).resolve()
            path = (root / safe_member(row["relative_path"])).resolve()
            if not path.is_relative_to(root) or file_digest(path) != row["sha256"]:
                raise ValueError("Recorded artifact checksum mismatch")
    for row in rows(db, "polar_capture"):
        if not row.get("artifact_root"):
            continue
        root = resolve_artifact(row["artifact_root"]).resolve()
        for item in json.loads(row["manifest_json"] or "{}").get("artifacts", []):
            path = (root / safe_member(item["relative_path"])).resolve()
            if not path.is_relative_to(root) or file_digest(path) != item["sha256"]:
                raise ValueError("Recorded physiology artifact checksum mismatch")
    return list(roots.values()), incomplete


def retire_authority(db):
    db.execute("PRAGMA secure_delete=ON")
    db.execute(
        "CREATE TABLE IF NOT EXISTS study_restored_source (source_table TEXT NOT NULL, source_id TEXT NOT NULL, original_state TEXT, PRIMARY KEY(source_table,source_id))"
    )
    for table in OPTIONAL_TABLES:
        for row in rows(db, table):
            db.execute(
                "INSERT OR IGNORE INTO study_restored_source VALUES (?,?,?)",
                (table, row["id"], row.get("lifecycle", row.get("status"))),
            )
    changes = []
    if "matb_backend_instance_lease" in tables(db):
        db.execute("DELETE FROM matb_backend_instance_lease")
        changes.append("matb_backend_instance_lease")
    for table in sorted(tables(db)):
        columns = {r[1] for r in db.execute('PRAGMA table_info("' + table + '")')}
        for name in columns & {
            "controller_lease_hash",
            "participant_token_hash",
            "owner_token",
        }:
            # Each row gets independently regenerated, non-reusable authority.
            for row in rows(db, table):
                db.execute(
                    f'UPDATE "{table}" SET "{name}"=? WHERE id=?',
                    (digest(secrets.token_bytes(32)), row["id"]),
                )
            changes.append(table + "." + name)
    for row in rows(db, "station_job"):
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            payload.pop("headers", None)
        status = (
            row["status"]
            if row["status"] in {"complete", "cancelled", "failed"}
            else "failed"
        )
        db.execute(
            "UPDATE station_job SET payload_json=?,status=?,error=? WHERE id=?",
            (
                canonical(payload),
                status,
                (
                    row["error"]
                    if status == row["status"]
                    else "restored: interrupted; explicit new request required"
                ),
                row["id"],
            ),
        )
    if "station_state" in tables(db):
        db.execute(
            "UPDATE station_state SET reservation_json='null', lanes_json='{}', maintenance=1, maintenance_actor='workspace restore'"
        )
    if "openmatb_block_attempt" in tables(db):
        db.execute(
            "UPDATE openmatb_block_attempt SET evidence_status='failed', evidence_error='restored: explicit processing request required' WHERE evidence_status IN ('queued','processing')"
        )
    if "bayesresult" in tables(db):
        db.execute(
            "UPDATE bayesresult SET status='failed', error='restored: explicit new request required' WHERE status IN ('queued','running')"
        )
    if "assessment_attempt" in tables(db):
        db.execute(
            "UPDATE assessment_attempt SET acquisition_state='interrupted', interruption_category='unknown' WHERE acquisition_state='started'"
        )
    for table in ("openmatb_suite_session",):
        if table in tables(db):
            db.execute(f"UPDATE {table} SET active_pid=NULL, recovery_pid=NULL")
    return changes


def safe_member(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or PureWindowsPath(name).drive
        or ":" in name
        or path.as_posix() != name
        or any(
            part.endswith((" ", "."))
            or part.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *("COM" + str(i) for i in range(1, 10)),
                *("LPT" + str(i) for i in range(1, 10)),
            }
            for part in path.parts
        )
    ):
        raise ValueError("Unsafe archive member: " + name)
    return path


def backup(database, output):
    database, output = Path(database).resolve(), Path(output).resolve()
    if not database.is_file():
        raise ValueError("Study database does not exist")
    if output.exists():
        raise ValueError("Backup destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="matb-backup-", dir=output.parent) as temp:
        stage = Path(temp)
        with closing(sqlite3.connect(database, timeout=5)) as guard:
            guard.row_factory = sqlite3.Row
            guard.execute("BEGIN IMMEDIATE")
            require_idle(guard)
            binding = validate_database(guard)
            roots, incomplete = inventory(guard, database)
            if any(output.is_relative_to(Path(root["physical"])) for root in roots):
                raise ValueError("Backup output must be outside artifact roots")
            with closing(sqlite3.connect(database)) as reader, closing(
                sqlite3.connect(stage / "study.sqlite3")
            ) as copied:
                reader.backup(copied)
                copied.row_factory = sqlite3.Row
                changes = retire_authority(copied)
                copied.commit()
                copied.execute("VACUUM")
            checks = {"study.sqlite3": file_digest(stage / "study.sqlite3")}
            mappings = []
            with zipfile.ZipFile(
                stage / "bundle.zip",
                "w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                archive.write(stage / "study.sqlite3", "study.sqlite3")
                archived_roots = []
                for index, root in enumerate(
                    sorted(
                        roots,
                        key=lambda r: (len(Path(r["physical"]).parts), r["original"]),
                    )
                ):
                    physical = Path(root["physical"])
                    parent = next(
                        (
                            item
                            for item in archived_roots
                            if physical.is_relative_to(item[0])
                        ),
                        None,
                    )
                    logical = (
                        (
                            parent[1] + "/" + physical.relative_to(parent[0]).as_posix()
                        ).rstrip("/.")
                        if parent
                        else f"artifacts/{index:04d}"
                    )
                    mappings.append(
                        {key: value for key, value in root.items() if key != "physical"}
                        | dict(
                            logical=logical,
                            directory=physical.is_dir()
                            or root.get("empty_directory", False),
                        )
                    )
                    if parent:
                        continue
                    archived_roots.append((physical, logical))
                    files = (
                        sorted(physical.rglob("*")) if physical.is_dir() else [physical]
                    )
                    for path in files:
                        if path.is_symlink():
                            raise ValueError("Symlink artifacts are not supported")
                        if not path.is_file():
                            continue
                        name = logical + (
                            "/" + path.relative_to(physical).as_posix()
                            if physical.is_dir()
                            else ""
                        )
                        safe_member(name)
                        before = file_digest(path)
                        archive.write(path, name)
                        if file_digest(path) != before:
                            raise ValueError(
                                "Artifact changed during exclusive maintenance"
                            )
                        checks[name] = before
                manifest = dict(
                    schema=SCHEMA,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    workspace=binding,
                    roots=mappings,
                    files=checks,
                    incomplete_artifacts=incomplete,
                    operational_fields_regenerated=changes,
                    required_components=[
                        name for name in OPTIONAL_TABLES if rows(guard, name)
                    ],
                )
                archive.writestr("manifest.json", canonical(manifest))
            # Never expose an incomplete archive at the requested destination.
            os.replace(stage / "bundle.zip", output)
    return manifest


def restore(archive, destination, *, expected_study_id, available_components=None):
    destination = Path(destination).absolute()
    if destination.is_symlink() or (
        destination.exists() and any(destination.iterdir())
    ):
        raise ValueError("Restore destination must be empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".matb-restore-", dir=destination.parent
    ) as temp:
        stage = Path(temp) / "workspace"
        stage.mkdir()
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            names = [item.filename for item in members]
            if len(names) != len(set(name.casefold() for name in names)):
                raise ValueError("Duplicate archive members")
            if sum(item.file_size for item in members) > shutil.disk_usage(stage).free:
                raise ValueError("Insufficient disk for restored archive")
            for item in members:
                safe_member(item.filename)
                if item.is_dir() or stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("Unsupported archive member type")
            if (
                "manifest.json" not in names
                or source.getinfo("manifest.json").file_size > 16 * 1024 * 1024
            ):
                raise ValueError("Missing or oversized archive manifest")
            manifest = json.loads(source.read("manifest.json"))
            if manifest.get("schema") != SCHEMA or set(names) != set(
                manifest["files"]
            ) | {"manifest.json"}:
                raise ValueError("Unexpected archive inventory")
            if manifest["workspace"]["study_id"] != expected_study_id:
                raise ValueError("Expected study identity does not match bundle")
            if available_components is not None:
                missing = set(manifest["required_components"]) - set(
                    available_components
                )
                if missing:
                    raise ValueError(
                        "Missing component capability: " + ", ".join(sorted(missing))
                    )
            for name, expected in manifest["files"].items():
                target = stage / safe_member(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(name) as incoming, target.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                if file_digest(target) != expected:
                    raise ValueError("Archive checksum mismatch: " + name)
        with closing(sqlite3.connect(stage / "study.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            binding = validate_database(db)
            if binding != manifest["workspace"]:
                raise ValueError("Workspace binding differs from manifest")
            changes = retire_authority(db)
            db.commit()
            db.execute("VACUUM")
        for item in manifest["roots"]:
            safe_member(item["logical"])
            if item["directory"]:
                (stage / item["logical"]).mkdir(parents=True, exist_ok=True)
        (stage / "relocation.json").write_text(
            canonical(dict(schema=SCHEMA, roots=manifest["roots"])), encoding="utf-8"
        )
        (stage / "original-manifest.json").write_text(
            canonical(manifest), encoding="utf-8"
        )
        environment = {
            "MATB_DB_PATH": str(destination / "study.sqlite3"),
            "MATB_ARTIFACT_RELOCATION": str(destination / "relocation.json"),
            "MATB_API_TOKEN_FILE": str(destination / ".station-secret"),
        }
        for root in manifest["roots"]:
            if root.get("environment"):
                environment[root["environment"]] = str(destination / root["logical"])
        report = dict(
            status="restored_in_maintenance",
            study_id=expected_study_id,
            files_verified=len(manifest["files"]),
            incomplete_artifacts=manifest["incomplete_artifacts"],
            operational_fields_regenerated=changes,
            environment=environment,
            restored_database_sha256=file_digest(stage / "study.sqlite3"),
        )
        (stage / "restore-report.json").write_text(canonical(report), encoding="utf-8")
        (stage / ".station-secret").write_text(
            secrets.token_urlsafe(48), encoding="utf-8"
        )
        (stage / ".station-secret").chmod(0o600)
        # Reserve an empty destination exclusively, then activate by rename.
        if destination.exists():
            destination.rmdir()
        os.rename(stage, destination)
    return report


def reproduce(workspace, output):
    """Recompute every saved descriptive execution in a new, no-index environment."""
    import subprocess
    import sys

    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Offline verification output must not exist")
    output.mkdir(parents=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
        and not key.startswith("PIP_")
    }
    environment.update(
        PYTHONNOUSERSITE="1", PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1"
    )
    reports = []
    with closing(sqlite3.connect(workspace / "study.sqlite3")) as db:
        db.row_factory = sqlite3.Row
        validate_database(db)
        for execution in rows(db, "study_analysis_execution"):
            identity = str(safe_member(execution["id"]))
            root = output / identity
            root.mkdir()
            for row in db.execute(
                "SELECT * FROM study_analysis_artifact WHERE execution_id=?",
                (identity,),
            ):
                target = root / safe_member(row["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(row["content"])
                if file_digest(target) != row["sha256"]:
                    raise ValueError("Frozen analysis artifact mismatch")
            before = file_digest(root / "figure.svg")
            venv = root / ".venv"
            subprocess.run(
                [sys.executable, "-I", "-m", "venv", str(venv)],
                env=environment,
                cwd=output,
                check=True,
                capture_output=True,
                text=True,
            )
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            installation = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--no-index",
                    "--no-cache-dir",
                    "--find-links",
                    str(root / "wheels"),
                    "-r",
                    str(root / "requirements.lock"),
                ],
                env=environment,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            (root / "installation.log").write_text(
                installation.stdout + installation.stderr, encoding="utf-8"
            )
            installation.check_returncode()
            launcher = root / "isolated-replay.py"
            launcher.write_text(
                """import importlib.util, json, pathlib, socket, sys
root = pathlib.Path(sys.argv[1]).resolve()
def offline(*args, **kwargs):
    raise RuntimeError("Network is disabled during descriptive reproduction")
class OfflineSocket(socket.socket):
    connect = offline
    connect_ex = offline
    sendto = offline
socket.socket = OfflineSocket
socket.create_connection = offline
socket.getaddrinfo = offline
assert sys.prefix != sys.base_prefix
assert all("site-packages" not in p or pathlib.Path(p).is_relative_to(sys.prefix) for p in sys.path)
spec = importlib.util.spec_from_file_location("frozen_verify", root / "verify.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.verify(root)
import matb_integration.analysis.study_calculators as calculator
assert pathlib.Path(calculator.__file__).resolve().is_relative_to(root / "source")
result.update(python=sys.version, isolated=sys.flags.isolated, system_site_packages=False,
              network="socket denied", calculator_file=calculator.__file__)
print(json.dumps(result))
""",
                encoding="utf-8",
            )
            run = subprocess.run(
                [str(python), "-I", str(launcher), str(root)],
                env=environment,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            (root / "reproduction.log").write_text(
                run.stdout + run.stderr, encoding="utf-8"
            )
            run.check_returncode()
            actual = json.loads(run.stdout.strip().splitlines()[-1])
            if file_digest(root / "figure.svg") != before:
                raise ValueError("Frozen figure changed during reproduction")
            reports.append(dict(execution_id=identity, figure_sha256=before, **actual))
            # Keep source, figures and command logs; the disposable environment is not evidence.
            shutil.rmtree(venv)
    report = dict(status="reproduced", executions=reports, automatic_model=None)
    (output / "offline-report.json").write_text(canonical(report), encoding="utf-8")
    return report
