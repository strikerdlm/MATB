"""HCF (human capacity factor) input contract.

HCF cannot be produced by the simulator (Suhir §5.9, §9.5); it is supplied by
an external baseline neurocognitive screen (separate sub-project). When no
estimate exists, the model runs in the Eq. 5.16 ordinary-capacity form, i.e.
F = F0 (ratio 1.0), which is mathematically exact, not a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Dimensionless baseline HCF: F = F0 -> F/F0 = 1.0.
F0_DEFAULT = 1.0


@dataclass
class HCFEstimate:
    participant_id: str
    value: float                                   # dimensionless, MWL-scale
    source: str = "F0_default"                     # "screen" | "metadata_fom" | "F0_default"
    components: dict[str, float] = field(default_factory=dict)


def resolve(participant_id: str, store: dict[str, HCFEstimate] | None = None) -> HCFEstimate:
    """Return the screen-derived HCF if present, else the F0 default."""
    if store is not None and participant_id in store:
        return store[participant_id]
    return HCFEstimate(participant_id=participant_id, value=F0_DEFAULT, source="F0_default")
