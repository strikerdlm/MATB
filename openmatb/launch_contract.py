"""Backward-compatible command-line contract for synchronized MATB launches."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
from uuid import UUID


class LaunchContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LaunchContract:
    scenario: Path
    session_id: str
    output_dir: Path
    output_csv: Path
    events_jsonl: Path


_SYNCHRONIZED_FLAGS = {"--scenario", "--session-id", "--output-dir"}


def parse_launch_contract(arguments: list[str]) -> LaunchContract | None:
    """Parse only the opt-in launch form and leave legacy argv untouched."""

    if not any(argument in _SYNCHRONIZED_FLAGS for argument in arguments):
        return None
    parser = argparse.ArgumentParser(prog="openmatb", add_help=False)
    parser.add_argument("--scenario")
    parser.add_argument("--session-id")
    parser.add_argument("--output-dir")
    try:
        namespace, unknown = parser.parse_known_args(arguments)
    except SystemExit as exc:
        raise LaunchContractError("invalid_synchronized_arguments") from exc
    if unknown:
        raise LaunchContractError("invalid_synchronized_arguments")
    if not namespace.scenario or not namespace.session_id or not namespace.output_dir:
        raise LaunchContractError("synchronized_arguments_required")
    try:
        parsed_id = UUID(namespace.session_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise LaunchContractError("invalid_session_id") from exc
    if str(parsed_id) != namespace.session_id.casefold():
        raise LaunchContractError("invalid_session_id")
    scenario = Path(namespace.scenario).resolve()
    if not scenario.is_file():
        raise LaunchContractError("scenario_not_found")
    output_dir = Path(namespace.output_dir).resolve()
    if output_dir.exists() and not output_dir.is_dir():
        raise LaunchContractError("output_directory_invalid")
    return LaunchContract(
        scenario=scenario,
        session_id=str(parsed_id),
        output_dir=output_dir,
        output_csv=output_dir / "openmatb-session.csv",
        events_jsonl=output_dir / "openmatb-events.jsonl",
    )


def activate_launch_contract(contract: LaunchContract) -> None:
    contract.output_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        contract.output_dir.chmod(0o700)
    os.environ["OPENMATB_SESSION_ID"] = contract.session_id
    os.environ["OPENMATB_OUTPUT_CSV"] = str(contract.output_csv)
    os.environ["OPENMATB_EVENTS_JSONL"] = str(contract.events_jsonl)


__all__ = [
    "LaunchContract",
    "LaunchContractError",
    "activate_launch_contract",
    "parse_launch_contract",
]
