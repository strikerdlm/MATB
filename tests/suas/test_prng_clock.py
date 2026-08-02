from __future__ import annotations

import pytest

from matb_integration.suas.engine.clock import SimulationClock
from matb_integration.suas.engine.prng import PCG32, derive_stream_seed


def test_pcg32_reference_vector_and_stream_independence() -> None:
    rng = PCG32(seed=42, stream=54)
    assert [rng.next_uint32() for _ in range(6)] == [
        0xA15C02B7, 0x7B47F409, 0xBA1D3330,
        0x83D2F293, 0xBFA4784B, 0xCBED606E,
    ]
    assert derive_stream_seed(7, "sensor", "UAS-01:C-01") != derive_stream_seed(
        7, "sensor", "UAS-02:C-01"
    )


def test_clock_advances_only_in_exact_100_ms_ticks() -> None:
    clock = SimulationClock()
    assert [clock.advance() for _ in range(3)] == [100, 200, 300]
    clock.pause()
    assert clock.advance() == 300


def test_pcg_state_round_trip_continues_exact_stream() -> None:
    rng = PCG32(seed=42, stream=54)
    rng.next_uint32()
    saved = rng.get_state()
    expected = [rng.next_uint32() for _ in range(4)]
    restored = PCG32.from_state(saved)
    assert [restored.next_uint32() for _ in range(4)] == expected


def test_pcg_state_rejects_invalid_private_checkpoint() -> None:
    rng = PCG32(seed=1, stream=1)
    state = rng.get_state()
    with pytest.raises(ValueError, match="odd"):
        rng.set_state(type(state)(state=state.state, increment=2))
