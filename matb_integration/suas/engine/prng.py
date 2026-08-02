"""PCG32 pseudo-random streams with checkpoint-safe state handling."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


MASK_64 = (1 << 64) - 1
PCG_MULTIPLIER = 6364136223846793005


@dataclass(frozen=True, slots=True)
class PCG32State:
    """Private, exact checkpoint state.  It is not a public world snapshot."""

    state: int
    increment: int


class PCG32:
    """The reference PCG XSH-RR 64/32 generator."""

    def __init__(self, *, seed: int, stream: int) -> None:
        _require_uint64(seed, "seed")
        _require_uint64(stream, "stream")
        self._state = 0
        self._increment = ((stream << 1) | 1) & MASK_64
        self.next_uint32()
        self._state = (self._state + seed) & MASK_64
        self.next_uint32()

    def next_uint32(self) -> int:
        old = self._state
        self._state = (old * PCG_MULTIPLIER + self._increment) & MASK_64
        xorshifted = (((old >> 18) ^ old) >> 27) & 0xFFFFFFFF
        rotation = (old >> 59) & 31
        return ((xorshifted >> rotation) | (xorshifted << ((-rotation) & 31))) & 0xFFFFFFFF

    def bernoulli_ppm(self, probability_ppm: int) -> bool:
        if isinstance(probability_ppm, bool) or not isinstance(probability_ppm, int) or not 0 <= probability_ppm <= 1_000_000:
            raise ValueError("probability_ppm must be in [0, 1000000]")
        threshold = (probability_ppm * (1 << 32)) // 1_000_000
        return self.next_uint32() < threshold

    def get_state(self) -> PCG32State:
        return PCG32State(state=self._state, increment=self._increment)

    def set_state(self, state: PCG32State) -> None:
        if not isinstance(state, PCG32State):
            raise TypeError("state must be a PCG32State")
        _require_uint64(state.state, "state")
        _require_uint64(state.increment, "increment")
        if not state.increment & 1:
            raise ValueError("increment must be odd")
        self._state = state.state
        self._increment = state.increment

    @classmethod
    def from_state(cls, state: PCG32State) -> PCG32:
        instance = cls.__new__(cls)
        instance.set_state(state)
        return instance


def derive_stream_seed(scenario_seed: int, subsystem: str, entity_id: str) -> tuple[int, int]:
    """Derive a reproducible independent seed/increment pair by name."""

    if isinstance(scenario_seed, bool) or not isinstance(scenario_seed, int):
        raise TypeError("scenario_seed must be an integer")
    if not isinstance(subsystem, str) or not isinstance(entity_id, str):
        raise TypeError("subsystem and entity_id must be strings")
    raw = f"{scenario_seed}\0{subsystem}\0{entity_id}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")


def _require_uint64(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MASK_64:
        raise ValueError(f"{name} must be an unsigned 64-bit integer")
