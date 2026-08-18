from __future__ import annotations

from matb_integration.recording.artifacts import (
    ArtifactProfile,
    build_checksum_file,
    verify_checksum_file,
)


def test_liftoff_profile_checksums_only_declared_files(tmp_path):
    profile = ArtifactProfile(
        frozen_names=("session-manifest.json", "telemetry.jsonl"),
        sealed_names=("metrics.json", "debrief.json"),
    )
    for name in (*profile.frozen_names, *profile.sealed_names):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "private.tmp").write_text("ignore", encoding="utf-8")

    checksum = build_checksum_file(tmp_path, profile=profile)

    assert verify_checksum_file(checksum, profile=profile) == ()
    assert "private.tmp" not in checksum.read_text(encoding="utf-8")
