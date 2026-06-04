"""CLI: write a reproducible analysis artifact for the manuscript.

Usage:
  python3 -m matb_integration.analysis.stats.cli run \
      --metrics-json metrics.json --fits-json fits.json -o artifact.json

  python3 -m matb_integration.analysis.stats.cli bayes \
      --metrics-json metrics.json --fits-json fits.json -o bayes.json \
      [--draws 1000] [--tune 1000] [--chains 4] [--seed 20260604]

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

    bayes = sub.add_parser("bayes", help="run the Bayesian Q2/Q4 sensitivity")
    bayes.add_argument("--metrics-json", required=True, type=Path)
    bayes.add_argument("--fits-json", required=True, type=Path)
    bayes.add_argument("-o", "--output", required=True, type=Path)
    bayes.add_argument("--seed", type=int, default=20260604)
    bayes.add_argument("--draws", type=int, default=1000)
    bayes.add_argument("--tune", type=int, default=1000)
    bayes.add_argument("--chains", type=int, default=4)

    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics_json.read_text())
    fits = json.loads(args.fits_json.read_text())
    now = datetime.now(timezone.utc).isoformat()
    if args.cmd == "run":
        artifact = run_analysis(metrics, fits, created_utc=now)
    else:
        from .bayes import run_bayes
        artifact = run_bayes(metrics, fits, seed=args.seed, draws=args.draws,
                             tune=args.tune, chains=args.chains, created_utc=now)
    args.output.write_text(json.dumps(artifact, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
