from __future__ import annotations

from matb_integration.communications_profile import (
    COMM_AUDIO_INVENTORY_SHA256,
    COMM_AUDIO_PROFILE_ID,
    COMM_PROMPT_UPPER_BOUND_SEC,
    verify_communications_audio_profile,
)


def test_pinned_communications_audio_profile_is_present_and_within_bound() -> None:
    profile = verify_communications_audio_profile()

    assert profile["profile_id"] == COMM_AUDIO_PROFILE_ID
    assert profile["asset_inventory_sha256"] == COMM_AUDIO_INVENTORY_SHA256
    assert profile["wav_file_count"] == 44
    assert 0 < profile["measured_conservative_upper_bound_sec"] <= COMM_PROMPT_UPPER_BOUND_SEC
