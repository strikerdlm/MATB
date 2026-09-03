"""Validate gettext coverage and compile OpenMATB catalogs without extra dependencies."""

from __future__ import annotations

import argparse
import ast
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
PLACEHOLDER_RE = re.compile(r"%(?:\([^)]+\))?[#0 +\-]?(?:\d+|\*)?(?:\.\d+)?[a-zA-Z%]")


def extract_messages(root: Path = ROOT) -> set[str]:
    """Return literal strings passed to gettext's conventional ``_`` function."""
    messages: set[str] = set()
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                messages.add(node.args[0].value)
    return messages


def parse_po(path: Path) -> dict[str, str]:
    """Parse the singular msgid/msgstr subset used by OpenMATB catalogs."""
    entries: dict[str, str] = {}
    msgid: str | None = None
    msgstr: str | None = None
    field: str | None = None

    def flush() -> None:
        nonlocal msgid, msgstr, field
        if msgid is not None and msgstr is not None:
            entries[msgid] = msgstr
        msgid = msgstr = field = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("msgid "):
            flush()
            msgid = ast.literal_eval(line[6:])
            msgstr = ""
            field = "msgid"
        elif line.startswith("msgstr "):
            msgstr = ast.literal_eval(line[7:])
            field = "msgstr"
        elif line.startswith('"') and field:
            value = ast.literal_eval(line)
            if field == "msgid":
                msgid = (msgid or "") + value
            else:
                msgstr = (msgstr or "") + value
    flush()
    return entries


def validate_catalog(messages: set[str], entries: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for message in sorted(messages):
        translation = entries.get(message)
        if translation is None:
            errors.append(f"Missing msgid: {message!r}")
            continue
        if not translation:
            errors.append(f"Empty msgstr: {message!r}")
            continue
        source_fields = PLACEHOLDER_RE.findall(message)
        translated_fields = PLACEHOLDER_RE.findall(translation)
        if sorted(source_fields) != sorted(translated_fields):
            errors.append(
                f"Placeholder mismatch for {message!r}: "
                f"{source_fields!r} != {translated_fields!r}"
            )
    return errors


def compile_mo(entries: dict[str, str], output: Path) -> None:
    """Write a GNU MO file from parsed catalog entries."""
    encoded = sorted(
        ((msgid.encode("utf-8"), msgstr.encode("utf-8")) for msgid, msgstr in entries.items()),
        key=lambda item: item[0],
    )
    count = len(encoded)
    original_table_offset = 28
    translated_table_offset = original_table_offset + count * 8
    original_blob_offset = translated_table_offset + count * 8

    originals = b""
    translations = b""
    original_table: list[tuple[int, int]] = []
    translated_table: list[tuple[int, int]] = []
    for msgid, _ in encoded:
        original_table.append((len(msgid), original_blob_offset + len(originals)))
        originals += msgid + b"\0"
    translated_blob_offset = original_blob_offset + len(originals)
    for _, msgstr in encoded:
        translated_table.append((len(msgstr), translated_blob_offset + len(translations)))
        translations += msgstr + b"\0"

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as mo_file:
        mo_file.write(
            struct.pack(
                "<7I",
                0x950412DE,
                0,
                count,
                original_table_offset,
                translated_table_offset,
                0,
                0,
            )
        )
        for length, offset in original_table:
            mo_file.write(struct.pack("<2I", length, offset))
        for length, offset in translated_table:
            mo_file.write(struct.pack("<2I", length, offset))
        mo_file.write(originals)
        mo_file.write(translations)


def po_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t") + '"'


def write_template(messages: set[str], output: Path) -> None:
    header = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Project-Id-Version: OpenMATB 1.4.5\\n"\n'
        '"MIME-Version: 1.0\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Content-Transfer-Encoding: 8bit\\n"\n'
    )
    blocks = [header]
    for message in sorted(messages):
        blocks.append(f"msgid {po_quote(message)}\nmsgstr \"\"\n")
    output.write_text("\n".join(blocks), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", default="es_CO")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--write-template", action="store_true")
    args = parser.parse_args()

    messages = extract_messages()
    catalog_dir = LOCALES / args.locale / "LC_MESSAGES"
    po_path = catalog_dir / "openmatb.po"
    entries = parse_po(po_path)

    if args.check:
        errors = validate_catalog(messages, entries)
        if errors:
            print("\n".join(errors))
            return 1
        print(f"Catalog {args.locale}: {len(messages)} source messages covered")
    if args.write_template:
        write_template(messages, LOCALES / "openmatb.pot")
        print(f"Template updated: {LOCALES / 'openmatb.pot'}")
    if args.compile:
        mo_path = catalog_dir / "openmatb.mo"
        compile_mo(entries, mo_path)
        print(f"Compiled: {mo_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
