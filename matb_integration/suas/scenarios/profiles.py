"""sUAS-specific counterbalancing and closed SAGAT probe registry."""

from __future__ import annotations

from typing import Final

from matb_integration.suas.domain.enums import WorkloadProfile


SUAS_PROBE_IDS: Final[frozenset[str]] = frozenset({
    "suas_l1_lost_links", "suas_l1_lowest_battery", "suas_l1_unreported",
    "suas_l2_largest_gap", "suas_l2_attention", "suas_l2_mission_state",
    "suas_l3_reserve_first", "suas_l3_next_sector", "suas_l3_conflict_risk",
})

LATIN_SQUARE_3: Final[tuple[tuple[WorkloadProfile, ...], ...]] = (
    (WorkloadProfile.LOW, WorkloadProfile.MEDIUM, WorkloadProfile.HIGH),
    (WorkloadProfile.LOW, WorkloadProfile.HIGH, WorkloadProfile.MEDIUM),
    (WorkloadProfile.MEDIUM, WorkloadProfile.LOW, WorkloadProfile.HIGH),
    (WorkloadProfile.MEDIUM, WorkloadProfile.HIGH, WorkloadProfile.LOW),
    (WorkloadProfile.HIGH, WorkloadProfile.LOW, WorkloadProfile.MEDIUM),
    (WorkloadProfile.HIGH, WorkloadProfile.MEDIUM, WorkloadProfile.LOW),
)


def block_order_for_participant(participant_id: str) -> tuple[WorkloadProfile, ...]:
    """Return the repository's six-row LOW/MEDIUM/HIGH Latin-square order."""

    digits = "".join(character for character in participant_id if character.isdigit())
    number = int(digits) if digits else 0
    return LATIN_SQUARE_3[number % len(LATIN_SQUARE_3)]
