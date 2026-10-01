"""Check installed versions against the launcher's recursive requirements.

This is a read-only check. It does not import graphical/native optional plugins,
install packages, or write research data. pip check separately checks the closure.
"""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sys


def check_requirements(path: Path, seen: set[Path] | None = None) -> list[dict]:
    from packaging.requirements import Requirement

    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    issues = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            issues.extend(check_requirements(path.parent / line[3:].strip(), seen))
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            issues.append({"package": requirement.name, "reason": "missing"})
            continue
        if not requirement.specifier.contains(installed, prereleases=True):
            issues.append({"package": requirement.name, "reason": "incompatible_version",
                           "installed": installed, "required": str(requirement.specifier)})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args()
    try:
        issues = check_requirements(args.requirements)
    except (ImportError, OSError, ValueError) as exc:
        issues = [{"reason": "check_failed", "message": str(exc)}]
    print(json.dumps({"ready": not issues, "issues": issues}, ensure_ascii=True))
    return int(bool(issues))


if __name__ == "__main__":
    sys.exit(main())
