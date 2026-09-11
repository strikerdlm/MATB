"""Resolve retained source paths without changing original manifests or identities."""

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath


def resolve_artifact(value, *, relocation_file=None):
    configured = relocation_file or os.getenv("MATB_ARTIFACT_RELOCATION")
    if not configured:
        database = os.getenv("MATB_DB_PATH")
        candidate = (
            Path(database).resolve().parent / "relocation.json" if database else None
        )
        configured = candidate if candidate and candidate.is_file() else None
    if not configured:
        return Path(value)
    mapping_path = Path(configured).resolve()
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    source = str(value).replace("\\", "/")
    for item in sorted(
        mapping["roots"], key=lambda item: len(item["original"]), reverse=True
    ):
        original = item["original"].replace("\\", "/").rstrip("/")
        if source == original or source.startswith(original + "/"):
            relative = source[len(original) :].lstrip("/")
            if ".." in PurePosixPath(relative).parts or PureWindowsPath(relative).drive:
                raise ValueError("Unsafe relocated artifact path")
            target = (mapping_path.parent / item["logical"] / relative).resolve()
            if not target.is_relative_to(mapping_path.parent):
                raise ValueError("Artifact relocation escapes workspace")
            return target
    # A restored workspace must never quietly fall back to an original external path.
    if Path(value).is_absolute() or PureWindowsPath(str(value)).is_absolute():
        raise ValueError("Original artifact has no relocation mapping: " + str(value))
    return Path(value)


def require_new_acquisition(db, source_table, source_id):
    """Restore is historical activation; resuming an old runtime is forbidden."""
    from sqlalchemy import inspect, text
    from fastapi import HTTPException

    if "study_restored_source" in inspect(db.connection()).get_table_names():
        found = db.execute(
            text(
                "SELECT 1 FROM study_restored_source WHERE source_table=:table AND source_id=:id"
            ),
            {"table": source_table, "id": str(source_id)},
        ).first()
        if found:
            raise HTTPException(
                409,
                dict(
                    code="restored_acquisition_requires_repeat",
                    message="This source was restored. Create an explicit new attempt; restored acquisition cannot resume.",
                ),
            )
