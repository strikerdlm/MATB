"""Local whole-study backup, safe restoration and offline descriptive reproduction."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webui/backend"))
from app.study_backup import OPTIONAL_TABLES, backup, restore, reproduce


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser(
        "backup", help="Requires a bound study in exclusive station maintenance"
    )
    save.add_argument("database")
    save.add_argument("output")
    load = commands.add_parser(
        "restore", help="Restores only to an empty workspace, remaining in maintenance"
    )
    load.add_argument("archive")
    load.add_argument("destination")
    load.add_argument("--study-id", required=True)
    verify = commands.add_parser(
        "reproduce",
        help="No-index fresh-environment descriptive replay of restored results",
    )
    verify.add_argument("workspace")
    verify.add_argument("output")
    args = parser.parse_args()
    if args.command == "backup":
        result = backup(args.database, args.output)
    elif args.command == "restore":
        available = {
            table
            for table, module in OPTIONAL_TABLES.items()
            if importlib.util.find_spec(module)
        }
        result = restore(
            args.archive,
            args.destination,
            expected_study_id=args.study_id,
            available_components=available,
        )
    else:
        result = reproduce(args.workspace, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
