from hashlib import sha256

from matb_integration.evidence.contracts import canonical_bytes, strict_json
from matb_integration.evidence.reference import synthetic_capture


def test_missed_response_links_opportunity_and_quality_without_invented_exposure(client, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path)
    events = [strict_json(line) for line in bundle["events"].splitlines()]
    missed = next(e for e in events if e["event_type"] == "sysmon.opportunity.closed")
    missed["payload"]["opportunity"].update(outcome="MISS", response_time_ms=None)
    missed["payload"]["value"] = canonical_bytes(missed["payload"]["opportunity"]).decode().strip()
    bundle["events"] = b"".join(canonical_bytes(e) for e in events)
    manifest = strict_json(bundle["capture_manifest"])
    manifest["artifacts"]["events"].update(sha256=sha256(bundle["events"]).hexdigest(), size_bytes=len(bundle["events"]))
    bundle["capture_manifest"] = canonical_bytes(manifest)
    capture = client.post("/ingest/evidence", files={k: (k, v) for k, v in bundle.items()}).json()
    prefix = f"/evidence/captures/{capture['id']}"
    context = client.get(prefix + f"/events/{missed['event_id']}/context")
    assert context.status_code == 200, context.text
    value = context.json()
    assert [e["record"]["event_type"] for e in value["events"]] == ["sysmon.opportunity.opened", "sysmon.opportunity.closed"]
    assert value["events"][-1]["record"]["payload"]["opportunity"]["outcome"] == "MISS"
    assert value["timing"] and all(isinstance(t["value_text"], str) for t in value["timing"])
    assert "native_visual_exposure" in value["unavailable_streams"]
    assert "synchronized_physiology" in value["unavailable_streams"]
    assert not any(value["truncated"].values())
    assert client.get(prefix + "/events/unknown/context").status_code == 404


def test_interrupted_index_transaction_rolls_back_and_can_be_reimported(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    bundle = synthetic_capture(tmp_path / "source", purpose="exploration")
    for role, content in bundle.items():
        (tmp_path / f"{role}.source").write_bytes(content)
    root = Path(__file__).resolve().parents[3]
    script = '''
from pathlib import Path
import os, sys
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy import event
from app import main
from app.evidence_service import ingest_evidence
from app.evidence_models import EvidenceCapture
from app.models import Participant, Visit
from datetime import date
folder=Path(sys.argv[1]); engine=create_engine('sqlite:///'+(folder/'interrupted.sqlite').as_posix())
SQLModel.metadata.create_all(engine)
source={p.name.removesuffix('.source'):p.read_bytes() for p in folder.glob('*.source')}
with Session(engine) as db:
    if db.get(Participant,'P01') is None:
        db.add(Participant(id='P01',enrollment_date=date(2026,9,9))); db.flush()
        db.add(Visit(participant_id='P01',visit_ordinal=1,scheduled_day=0)); db.commit()
if sys.argv[2]=='crash':
    @event.listens_for(engine,'after_cursor_execute')
    def interrupt(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO evidence_record'):
            os._exit(73)
with Session(engine) as db:
    assert not db.exec(select(EvidenceCapture)).all()
    capture,created=ingest_evidence(db,source)
    assert created
'''
    env = dict(os.environ, PYTHONPATH=str(root / "webui/backend") + os.pathsep + str(root),
               MATB_DB_PATH=str(tmp_path / "unused.sqlite"), PYTHONDONTWRITEBYTECODE="1")
    crashed = subprocess.run([sys.executable, "-c", script, str(tmp_path), "crash"], env=env,
                             capture_output=True, text=True, timeout=60)
    assert crashed.returncode == 73, crashed.stdout + crashed.stderr
    recovered = subprocess.run([sys.executable, "-c", script, str(tmp_path), "recover"], env=env,
                               capture_output=True, text=True, timeout=60)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
