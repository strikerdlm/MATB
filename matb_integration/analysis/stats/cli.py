"""CLI: write a reproducible analysis artifact for the manuscript.

Usage:
  python3 -m matb_integration.analysis.stats.cli run \
      --metrics-json metrics.json --fits-json fits.json -o artifact.json

metrics.json: JSON array of /metrics/long rows; fits.json: array of /fits rows.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .engine import run_analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matb-stats", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the pre-specified analysis")
    run.add_argument("--metrics-json", required=True, type=Path)
    run.add_argument("--fits-json", required=True, type=Path)
    run.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics_json.read_text())
    fits = json.loads(args.fits_json.read_text())
    artifact = run_analysis(
        metrics, fits, created_utc=datetime.now(timezone.utc).isoformat())
    args.output.write_text(json.dumps(artifact, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
