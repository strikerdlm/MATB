"""Short-lived SQLModel persistence adapter for native simulation metadata."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from sqlmodel import Session, select

from matb_integration.suas.recording.records import ArtifactInfo

from .simulation_models import (
    ProtocolDeviation,
    SimulationArtifact,
    SimulationBlock,
    SimulationSession,
    TechnicalProtocolDeviation,
    TechnicalSimulationArtifact,
    TechnicalSimulationBlock,
    TechnicalSimulationSession,
)


SessionRow = SimulationSession | TechnicalSimulationSession
BlockRow = SimulationBlock | TechnicalSimulationBlock


class SimulationPersistence(Protocol):
    def load_session(self, session_id: str) -> SessionRow | None: ...

    def load_block(self, session_id: str, block_id: str) -> BlockRow | None: ...

    def update_session(self, session_id: str, **fields: object) -> None: ...
    def update_block(self, session_id: str, block_id: str, **fields: object) -> None: ...
    def add_deviation(
        self, session_id: str, block_id: str | None, code: str, severity: str,
        simulation_time_ms: int, detail: Mapping[str, object],
    ) -> None: ...
    def replace_artifacts(self, session_id: str, artifacts: Sequence[ArtifactInfo]) -> None: ...


_SESSION_FIELDS = frozenset({
    "lifecycle", "active_block_id", "validity", "started_at", "finished_at", "interrupted_at",
})
_BLOCK_FIELDS = frozenset({
    "lifecycle", "validity", "simulation_started_ms", "simulation_finished_ms", "started_at",
    "finished_at", "was_interrupted", "recovered_from_checkpoint", "metrics_json",
})


class SQLModelSimulationPersistence:
    """Use one short-lived DB session per mutation and fail closed on fields."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def load_session(self, session_id: str) -> SessionRow | None:
        with Session(self.engine) as db:
            row = db.get(SimulationSession, session_id)
            if row is None:
                row = db.get(TechnicalSimulationSession, session_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    def load_block(self, session_id: str, block_id: str) -> BlockRow | None:
        with Session(self.engine) as db:
            row = db.exec(
                select(SimulationBlock).where(
                    SimulationBlock.session_id == session_id,
                    SimulationBlock.block_id == block_id,
                )
            ).one_or_none()
            if row is None:
                row = db.exec(
                    select(TechnicalSimulationBlock).where(
                        TechnicalSimulationBlock.session_id == session_id,
                        TechnicalSimulationBlock.block_id == block_id,
                    )
                ).one_or_none()
            if row is None:
                return None
            db.expunge(row)
            return row

    def mark_orphaned_sessions(self) -> int:
        """Fail closed for rows left active by a prior process."""

        changed = 0
        with Session(self.engine) as db:
            rows = db.exec(
                select(SimulationSession).where(SimulationSession.lifecycle.in_(("RUNNING", "PAUSED")))
            ).all()
            for row in rows:
                row.lifecycle = "INTERRUPTED"
                row.validity = "invalid"
                row.interrupted_at = datetime.now().astimezone()
                db.add(row)
                changed += 1
            technical_rows = db.exec(
                select(TechnicalSimulationSession).where(
                    TechnicalSimulationSession.lifecycle.in_(("RUNNING", "PAUSED"))
                )
            ).all()
            for row in technical_rows:
                row.lifecycle = "INTERRUPTED"
                row.validity = "technical_only_with_deviation"
                row.interrupted_at = datetime.now().astimezone()
                db.add(row)
                changed += 1
            if changed:
                db.commit()
        return changed

    def update_session(self, session_id: str, **fields: object) -> None:
        self._check_fields(fields, _SESSION_FIELDS)
        with Session(self.engine) as db:
            row = db.get(SimulationSession, session_id)
            if row is None:
                row = db.get(TechnicalSimulationSession, session_id)
            if row is None:
                raise KeyError(session_id)
            for key, value in fields.items():
                setattr(row, key, value)
            db.add(row)
            db.commit()

    def update_block(self, session_id: str, block_id: str, **fields: object) -> None:
        self._check_fields(fields, _BLOCK_FIELDS)
        with Session(self.engine) as db:
            row = db.exec(
                select(SimulationBlock).where(
                    SimulationBlock.session_id == session_id,
                    SimulationBlock.block_id == block_id,
                )
            ).one_or_none()
            if row is None:
                row = db.exec(
                    select(TechnicalSimulationBlock).where(
                        TechnicalSimulationBlock.session_id == session_id,
                        TechnicalSimulationBlock.block_id == block_id,
                    )
                ).one_or_none()
            if row is None:
                raise KeyError(f"{session_id}/{block_id}")
            for key, value in fields.items():
                setattr(row, key, value)
            db.add(row)
            db.commit()

    def add_deviation(
        self, session_id: str, block_id: str | None, code: str, severity: str,
        simulation_time_ms: int, detail: Mapping[str, object],
    ) -> None:
        with Session(self.engine) as db:
            technical = db.get(TechnicalSimulationSession, session_id) is not None
            deviation_model = TechnicalProtocolDeviation if technical else ProtocolDeviation
            db.add(deviation_model(
                session_id=session_id,
                block_id=block_id,
                code=code,
                severity=severity,
                simulation_time_ms=simulation_time_ms,
                detail_json=json.dumps(dict(detail), sort_keys=True, separators=(",", ":")),
            ))
            db.commit()

    def replace_artifacts(self, session_id: str, artifacts: Sequence[ArtifactInfo]) -> None:
        with Session(self.engine) as db:
            technical = db.get(TechnicalSimulationSession, session_id) is not None
            artifact_model = TechnicalSimulationArtifact if technical else SimulationArtifact
            old = db.exec(select(artifact_model).where(artifact_model.session_id == session_id)).all()
            for row in old:
                db.delete(row)
            for artifact in artifacts:
                relative = artifact.path.name
                if artifact.path.parent.name == "checkpoints":
                    relative = f"checkpoints/{relative}"
                db.add(artifact_model(
                    session_id=session_id,
                    kind=artifact.kind,
                    relative_path=relative,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                ))
            db.commit()

    @staticmethod
    def _check_fields(fields: Mapping[str, object], allowed: frozenset[str]) -> None:
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported simulation metadata fields: {', '.join(sorted(unknown))}")


class InMemorySimulationPersistence:
    """Small test adapter with the same mutation surface as the SQL adapter."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, object]] = {}
        self.blocks: dict[tuple[str, str], dict[str, object]] = {}
        self.deviations: list[dict[str, object]] = []
        self.artifacts: dict[str, tuple[ArtifactInfo, ...]] = {}

    def load_session(self, session_id: str) -> SessionRow | None:
        return None

    def load_block(self, session_id: str, block_id: str) -> BlockRow | None:
        return None

    def mark_orphaned_sessions(self) -> int:
        return 0

    def update_session(self, session_id: str, **fields: object) -> None:
        self.sessions.setdefault(session_id, {}).update(fields)

    def update_block(self, session_id: str, block_id: str, **fields: object) -> None:
        self.blocks.setdefault((session_id, block_id), {}).update(fields)

    def add_deviation(self, session_id: str, block_id: str | None, code: str, severity: str,
                      simulation_time_ms: int, detail: Mapping[str, object]) -> None:
        self.deviations.append({
            "session_id": session_id, "block_id": block_id, "code": code,
            "severity": severity, "simulation_time_ms": simulation_time_ms, "detail": dict(detail),
        })

    def replace_artifacts(self, session_id: str, artifacts: Sequence[ArtifactInfo]) -> None:
        self.artifacts[session_id] = tuple(artifacts)


__all__ = ["InMemorySimulationPersistence", "SQLModelSimulationPersistence", "SimulationPersistence"]
