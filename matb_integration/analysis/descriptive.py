"""
matb_integration/analysis/descriptive.py

Non-parametric descriptive analysis for multi-block MATB JSONL data.

Input:  directory of JSONL files produced by matb_integration.log_converter
        (one line per participant × block)
Output: console summary table + optional TSV

Statistical tests:
  Friedman χ²  — within-subject workload effect across LOW / MEDIUM / HIGH
  Spearman ρ   — monotonic association: condition rank (1/2/3) vs metric value
  Kendall W    — concordance derived from Friedman statistic

Requires: scipy >= 1.10
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

try:
    from scipy import stats as _scipy_stats
    _SCIPY = True
except ImportError:
    _SCIPY = False

LEVEL_RANK: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

# Metrics to analyse — dotted paths into the JSONL record dict
METRICS: list[tuple[str, str]] = [
    ("sysmon.hit_rate",    "SYSMON hit rate"),
    ("sysmon.d_prime",     "SYSMON d'"),
    ("sysmon.mean_rt_ms",  "SYSMON mean RT (ms)"),
    ("isa.mean",           "ISA mean"),
    ("nasatlx.raw_tlx",    "NASA-TLX raw"),
    ("bedford.value",      "Bedford"),
    ("comm.d_prime",       "COMM d'"),
    ("comm.hit_rate",      "COMM hit rate"),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(record: dict[str, Any], path: str) -> float | None:
    """Resolve a dotted path like 'sysmon.hit_rate' into a record."""
    parts = path.split(".")
    node: Any = record
    for p in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(p)
    if node is None or (isinstance(node, float) and math.isnan(node)):
        return None
    try:
        return float(node)
    except (TypeError, ValueError):
        return None


def load_records(source: Path) -> list[dict[str, Any]]:
    """Load all JSONL records from a file or directory of files."""
    records: list[dict[str, Any]] = []
    paths = sorted(source.glob("*.jsonl")) if source.is_dir() else [source]
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return records


def _pivot(
    records: list[dict[str, Any]],
    metric_path: str,
) -> dict[str, dict[str, float]]:
    """Return {participant_id: {workload_level: value}} for one metric.

    Only participants with values for all three levels are included.
    """
    raw: dict[str, dict[str, float]] = defaultdict(dict)
    for r in records:
        pid = r.get("participant_id", "unknown")
        level = str(r.get("workload_level", "")).upper()
        if level not in LEVEL_RANK:
            continue
        v = _get(r, metric_path)
        if v is not None:
            raw[pid][level] = v

    return {
        pid: lvl_dict
        for pid, lvl_dict in raw.items()
        if all(lv in lvl_dict for lv in ("LOW", "MEDIUM", "HIGH"))
    }


def _descriptive(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"n": 0, "median": None, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "median": round(median(values), 4),
        "mean": round(mean(values), 4),
        "sd": round(stdev(values), 4) if len(values) > 1 else None,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def analyse_metric(
    records: list[dict[str, Any]],
    metric_path: str,
    metric_label: str,
) -> dict[str, Any] | None:
    """Run descriptives + Friedman + Spearman for one metric."""
    pivot = _pivot(records, metric_path)
    if not pivot:
        return None

    participants = sorted(pivot.keys())
    n = len(participants)

    low_vals    = [pivot[p]["LOW"]    for p in participants]
    medium_vals = [pivot[p]["MEDIUM"] for p in participants]
    high_vals   = [pivot[p]["HIGH"]   for p in participants]

    result: dict[str, Any] = {
        "metric": metric_label,
        "path": metric_path,
        "n_participants": n,
        "descriptives": {
            "LOW":    _descriptive(low_vals),
            "MEDIUM": _descriptive(medium_vals),
            "HIGH":   _descriptive(high_vals),
        },
        "friedman": None,
        "spearman_rho": None,
    }

    if not _SCIPY:
        return result

    # Friedman χ² (within-subject, 3 conditions)
    if n >= 3:
        stat, p = _scipy_stats.friedmanchisquare(low_vals, medium_vals, high_vals)
        # Kendall W from Friedman: W = χ² / (n × (k−1)) where k=3
        kendall_w = stat / (n * 2) if n > 0 else None
        result["friedman"] = {
            "statistic": round(float(stat), 4),
            "p_value": round(float(p), 6),
            "kendall_w": round(kendall_w, 4) if kendall_w is not None else None,
            "n": n,
        }

    # Spearman ρ: for each participant, correlate (1,2,3) with (low,med,high)
    # With only 3 points per participant, individual ρ values are ±1 or 0.
    # We report the mean ρ across participants and a sign-test p-value.
    ranks = [1, 2, 3]
    rhos: list[float] = []
    for p_id in participants:
        vals = [pivot[p_id]["LOW"], pivot[p_id]["MEDIUM"], pivot[p_id]["HIGH"]]
        rho, _ = _scipy_stats.spearmanr(ranks, vals)
        if not math.isnan(rho):
            rhos.append(float(rho))

    if rhos:
        n_positive = sum(1 for r in rhos if r > 0)
        # Sign test: H0 ρ=0 (median), two-tailed binomial
        if len(rhos) >= 3:
            binom_p = float(_scipy_stats.binomtest(n_positive, len(rhos), 0.5).pvalue)
        else:
            binom_p = float("nan")
        result["spearman_rho"] = {
            "mean_rho": round(mean(rhos), 4),
            "median_rho": round(median(rhos), 4),
            "n_positive": n_positive,
            "n_total": len(rhos),
            "sign_test_p": round(binom_p, 6) if not math.isnan(binom_p) else None,
        }

    return result


def run_analysis(
    source: Path,
    metrics: list[tuple[str, str]] | None = None,
    output_tsv: Path | None = None,
) -> list[dict[str, Any]]:
    """Run the full analysis pipeline and print a summary.

    Args:
        source: JSONL file or directory of JSONL files.
        metrics: List of (dotted_path, label) pairs. Defaults to METRICS.
        output_tsv: If provided, write a per-metric summary to this TSV.

    Returns:
        List of per-metric result dicts.
    """
    if metrics is None:
        metrics = METRICS

    records = load_records(source)
    if not records:
        print(f"No records found in {source}", file=sys.stderr)
        return []

    n_total = len(records)
    pids = {r.get("participant_id") for r in records}
    print(f"\n{'='*68}")
    print(f"  MATB descriptive analysis")
    print(f"  Source : {source}")
    print(f"  Records: {n_total}  |  Participants: {len(pids)}")
    if not _SCIPY:
        print("  [WARNING] scipy not found — statistical tests skipped")
    print(f"{'='*68}\n")

    results: list[dict[str, Any]] = []
    tsv_rows: list[list[str]] = []

    for path, label in metrics:
        res = analyse_metric(records, path, label)
        if res is None:
            continue
        results.append(res)

        # Console output
        d = res["descriptives"]
        n = res["n_participants"]
        print(f"  {label} (n={n})")
        for level in ("LOW", "MEDIUM", "HIGH"):
            dd = d[level]
            med = f"{dd['median']:.3f}" if dd["median"] is not None else "—"
            mn  = f"{dd['mean']:.3f}"   if dd["mean"]   is not None else "—"
            print(f"    {level:<8}  median={med:<8}  mean={mn}")

        fr = res.get("friedman")
        if fr:
            sig = "✓" if fr["p_value"] < 0.05 else "○"
            print(f"    Friedman  χ²={fr['statistic']:.3f}  p={fr['p_value']:.4f}  "
                  f"W={fr['kendall_w']:.3f}  {sig}")

        sp = res.get("spearman_rho")
        if sp:
            print(f"    Spearman  mean_ρ={sp['mean_rho']:.3f}  "
                  f"({sp['n_positive']}/{sp['n_total']} positive)  "
                  f"sign-test p={sp['sign_test_p']}")

        print()

        # TSV row
        for level in ("LOW", "MEDIUM", "HIGH"):
            dd = d[level]
            fr_stat = str(fr["statistic"]) if fr else ""
            fr_p    = str(fr["p_value"])   if fr else ""
            sp_rho  = str(sp["mean_rho"])  if sp else ""
            sp_p    = str(sp["sign_test_p"]) if sp else ""
            tsv_rows.append([
                label, level, str(dd["n"]),
                str(dd["median"]) if dd["median"] is not None else "",
                str(dd["mean"])   if dd["mean"]   is not None else "",
                str(dd["sd"])     if dd["sd"]     is not None else "",
                fr_stat, fr_p, sp_rho, sp_p,
            ])

    if output_tsv is not None:
        header = [
            "metric", "level", "n", "median", "mean", "sd",
            "friedman_chi2", "friedman_p", "spearman_rho", "spearman_sign_p",
        ]
        output_tsv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_tsv, "w", encoding="utf-8") as fh:
            fh.write("\t".join(header) + "\n")
            for row in tsv_rows:
                fh.write("\t".join(row) + "\n")
        print(f"  TSV written → {output_tsv}\n")

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Descriptive statistics and non-parametric tests for MATB JSONL data."
    )
    parser.add_argument(
        "source", type=Path,
        help="JSONL file or directory of JSONL files (one record per participant×block)"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write per-metric summary to this TSV file"
    )
    args = parser.parse_args()
    run_analysis(args.source, output_tsv=args.output)
