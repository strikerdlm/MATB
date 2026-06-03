"""CLI for the Suhir DEPDF layer.

Usage:
    python3 -m matb_integration.suhir.cli fit \
        --participant P01 \
        --low  LOW.csv  --medium MED.csv --high HIGH.csv \
        --source raw_tlx --out P01_suhir.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from matb_integration.log_converter import convert_session, parse_csv
from matb_integration.suhir.pipeline import fit_participant


def _build_block(csv_path: str, level: str, participant: str):
    path = Path(csv_path)
    record = convert_session(path, participant_id=participant, workload_level=level)
    rows = parse_csv(path)
    return record, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matb-suhir")
    sub = parser.add_subparsers(dest="cmd", required=True)

    fit = sub.add_parser("fit", help="fit per-participant DEPDF parameters")
    fit.add_argument("--participant", required=True)
    fit.add_argument("--low", required=True)
    fit.add_argument("--medium", required=True)
    fit.add_argument("--high", required=True)
    fit.add_argument("--source", default="raw_tlx")
    fit.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "fit":
        blocks = {
            "LOW": _build_block(args.low, "LOW", args.participant),
            "MEDIUM": _build_block(args.medium, "MEDIUM", args.participant),
            "HIGH": _build_block(args.high, "HIGH", args.participant),
        }
        out = fit_participant(args.participant, blocks, source=args.source)
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
