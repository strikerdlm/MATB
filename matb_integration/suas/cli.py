"""Headless validation and deterministic execution entry point."""

from __future__ import annotations

import argparse
import json
import sys

from matb_integration.suas.domain.serialization import canonical_json
from matb_integration.suas.engine.runtime import ENGINE_VERSION, SimulationEngine
from matb_integration.suas.scenarios.loader import load_scenario


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m matb_integration.suas.cli")
    subcommands = parser.add_subparsers(dest="action", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("path")
    run = subcommands.add_parser("run")
    run.add_argument("path")
    run.add_argument("--block", required=True)
    run.add_argument("--ticks", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        loaded = load_scenario(args.path)
        if args.action == "validate":
            print(canonical_json({
                "scenario_id": loaded.definition.scenario_id,
                "scenario_sha256": loaded.sha256,
                "profile_counts": {
                    block_id: {"aircraft": len(block.aircraft_ids), "contacts": len(block.contact_ids)}
                    for block_id, block in sorted(loaded.definition.blocks.items())
                },
            }))
            return 0
        if args.ticks <= 0:
            raise ValueError("ticks must be a positive integer")
        engine = SimulationEngine(loaded.definition, args.block)
        event_count = 0
        for _ in range(args.ticks):
            event_count += len(engine.step().events)
        snapshot = engine.snapshot()
        print(canonical_json({
            "engine_version": ENGINE_VERSION,
            "ticks": args.ticks,
            "simulation_time_ms": snapshot["simulation_time_ms"],
            "event_count": event_count,
            "state_sha256": engine.state_hash,
            "snapshot": snapshot,
        }))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
