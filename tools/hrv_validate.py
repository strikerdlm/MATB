"""HRV export validation utility.

Usage:
    python tools/hrv_validate.py --session sessions/user_0001/2025-11-28/session_0001_120000

The script checks for the presence and consistency of the HRV export
artifacts described in Docs/Manual.md §18.5:

* hrv/rr_intervals.csv          (raw RR stream)
* hrv/hrv_windows.csv           (per-window metrics)
* hrv/hrv_windows.parquet       (optional, requires pandas + parquet engine)
* hrv/hrv_alerts.json           (alert log)
* hrv/hrv_baseline.json         (baseline statistics)
* hrv/polar_metadata.json       (device provenance)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


def _load_rr(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f'missing RR file: {path}')
    with path.open(encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f'RR file contains no rows: {path}')
    return rows


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def _compute_rr_stats(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    rr_values = []
    total = 0
    artifacts = 0
    for row in rows:
        total += 1
        artifact = str(row.get('artifact', 'false')).lower() == 'true'
        if artifact:
            artifacts += 1
            continue
        try:
            rr_ms = float(row['rr_ms'])
        except (KeyError, ValueError) as exc:
            raise ValueError(f'Invalid rr_ms value: {row}') from exc
        rr_values.append(rr_ms)

    if not rr_values:
        raise ValueError('RR stream contains only artifacts')

    mean_rr = sum(rr_values) / len(rr_values)
    diffs = [
        rr_values[i + 1] - rr_values[i]
        for i in range(len(rr_values) - 1)
    ]
    rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs)) if diffs else 0.0

    return {
        'total_samples': total,
        'artifact_rate_percent': (artifacts / total) * 100.0,
        'mean_rr_ms': mean_rr,
        'rmssd_ms': rmssd,
    }


def _validate_windows_csv(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    required_fields = {
        'timestamp',
        'hr',
        'rmssd',
        'sdnn',
        'lf',
        'hf',
        'lf_hf',
        'workload_level',
    }
    if not rows:
        return {'row_count': 0, 'missing_fields': sorted(required_fields)}
    missing = set()
    for field in required_fields:
        if field not in rows[0]:
            missing.add(field)
    return {
        'row_count': len(rows),
        'missing_fields': sorted(missing),
    }


def _validate_parquet(path: Path, expected_rows: int) -> Dict[str, Any]:
    if pd is None:
        return {'available': False, 'reason': 'pandas not installed'}
    if not path.exists():
        return {'available': False, 'reason': 'file missing'}
    df = pd.read_parquet(path)
    return {
        'available': True,
        'rows': len(df),
        'matches_csv': len(df) == expected_rows,
    }


def _print_section(title: str) -> None:
    print(f'\n== {title} ==')


def validate_session(session_path: Path) -> None:
    session_path = session_path.resolve()
    if not session_path.exists():
        raise FileNotFoundError(f'Session path not found: {session_path}')

    hrv_dir = session_path / 'hrv'
    if not hrv_dir.exists():
        raise FileNotFoundError(f'No hrv/ directory found under {session_path}')

    rr_rows = _load_rr(hrv_dir / 'rr_intervals.csv')
    rr_stats = _compute_rr_stats(rr_rows)

    _print_section('RR Stream')
    for key, value in rr_stats.items():
        print(f'{key}: {value}')

    windows_rows = _load_csv(hrv_dir / 'hrv_windows.csv')
    window_stats = _validate_windows_csv(windows_rows)
    _print_section('HRV Windows (CSV)')
    for key, value in window_stats.items():
        print(f'{key}: {value}')

    parquet_info = _validate_parquet(hrv_dir / 'hrv_windows.parquet', window_stats['row_count'])
    _print_section('HRV Windows (Parquet)')
    for key, value in parquet_info.items():
        print(f'{key}: {value}')

    alerts = _load_json(hrv_dir / 'hrv_alerts.json') or []
    print(f'\nAlerts logged: {len(alerts)}')

    baseline = _load_json(hrv_dir / 'hrv_baseline.json')
    if baseline:
        print('Baseline sample count:', baseline.get('sample_count'))
    else:
        print('Baseline: missing or not calibrated')

    metadata = _load_json(hrv_dir / 'polar_metadata.json')
    if metadata:
        _print_section('Polar Metadata')
        for key in ('device_id', 'start_time', 'stop_time', 'duration_seconds'):
            print(f'{key}: {metadata.get(key)}')
        print('Battery samples:', len(metadata.get('battery_samples', [])))
    else:
        print('\nPolar metadata not found')


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate HRV export artifacts.')
    parser.add_argument(
        '--session',
        required=True,
        type=Path,
        help='Path to session directory (e.g., sessions/user_0000/2025-11-28/session_0001_120000)',
    )
    args = parser.parse_args()
    validate_session(args.session)


if __name__ == '__main__':
    main()

