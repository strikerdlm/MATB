"""Offline checks for the bilingual MATB documentation contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


ROOT_ANCHORS = (
    "identity-and-safety", "choose-a-workflow", "architecture-and-data-flow",
    "prerequisites", "quick-start-openmatb", "quick-start-research-console",
    "quick-start-suas", "quick-start-sms", "quick-start-legacy-monitor",
    "module-catalog", "operations-and-maintenance", "troubleshooting",
    "security-privacy-and-governance", "repository-map", "glossary",
    "references", "contributing", "license",
)
REQUIRED_MODULE_PATHS = (
    "matb_integration/scenario_builder.py", "matb_integration/scenario_manifest.py",
    "matb_integration/log_converter.py", "matb_integration/questionnaires/",
    "matb_integration/analysis/", "matb_integration/suhir/", "matb_integration/screen/",
    "webui/backend/", "webui/frontend/", "matb_integration/suas/",
    "SMS/apps/edge-api/", "SMS/apps/console/", "SMS/packages/evidence/",
    "SMS/packages/energy/", "SMS/packages/fleet/", "SMS/packages/geo/",
    "SMS/packages/human-performance/", "SMS/packages/research/",
    "SMS/packages/safety-kernel/", "SMS/packages/sms/", "SMS/packages/telemetry/",
    "SMS/tools/map-packager/", "SMS/tools/research/", "aircraft_monitor/",
)
PAIR_DIRS = ("openmatb-research", "research-console", "sms-platform", "legacy-monitor")
LINK_RE = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")
ANCHOR_RE = re.compile(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', re.IGNORECASE)


def strip_fenced_code(text: str) -> str:
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            fence = None if fence == token else token if fence is None else fence
            continue
        if fence is None:
            kept.append(line)
    return "\n".join(kept)


def markdown_links(path: Path) -> list[tuple[str, int]]:
    links: list[tuple[str, int]] = []
    fenced = False
    fence_token = ""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            if not fenced:
                fenced, fence_token = True, token
            elif token == fence_token:
                fenced, fence_token = False, ""
            continue
        if fenced:
            continue
        for raw in LINK_RE.findall(line):
            destination = raw.strip().split(maxsplit=1)[0].strip("<>")
            links.append((destination, number))
    return links


def _slug(text: str) -> str:
    value = re.sub(r"[^\w\- ]", "", text.strip().lower(), flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def markdown_anchors(path: Path) -> list[str]:
    text = strip_fenced_code(path.read_text(encoding="utf-8"))
    anchors = ANCHOR_RE.findall(text)
    anchors.extend(_slug(match.group(1)) for match in re.finditer(r"^#{1,6}\s+(.+)$", text, re.MULTILINE))
    return anchors


def find_broken_links(root: Path, markdown_files: list[Path]) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    for source in markdown_files:
        for destination, line in markdown_links(source):
            parsed = urlsplit(destination)
            if parsed.scheme in {"http", "https", "mailto", "data"}:
                continue
            relative = unquote(parsed.path)
            target = source if not relative else source.parent / relative
            resolved = target.resolve()
            if root != resolved and root not in resolved.parents:
                errors.append(f"{source.relative_to(root)}:{line}: link escapes repository: {destination}")
                continue
            if not resolved.exists():
                errors.append(f"{source.relative_to(root)}:{line}: missing link target: {destination}")
                continue
            if parsed.fragment and resolved.is_file() and parsed.fragment not in markdown_anchors(resolved):
                errors.append(f"{source.relative_to(root)}:{line}: missing anchor #{parsed.fragment}")
    return errors


def compare_root_anchors(english: Path, spanish: Path) -> list[str]:
    if not english.is_file() or not spanish.is_file():
        missing = english if not english.is_file() else spanish
        return [f"missing bilingual root guide: {missing.name}"]

    def explicit(path: Path) -> list[str]:
        return ANCHOR_RE.findall(strip_fenced_code(path.read_text(encoding="utf-8")))

    en, es = explicit(english), explicit(spanish)
    errors = []
    # This primitive is also useful for small fixtures that contain only the
    # anchors relevant to the example under test.  The repository-level check
    # below enforces the complete contract once both root guides are present.
    if len(en) == len(ROOT_ANCHORS) and en != list(ROOT_ANCHORS):
        errors.append(f"README.md anchor order differs: {en!r}")
    if len(es) == len(ROOT_ANCHORS) and es != list(ROOT_ANCHORS):
        errors.append(f"README.es.md anchor order differs: {es!r}")
    if en != es:
        errors.append("English and Spanish root anchors are not mirrored")
    return errors


def validate_json_fixtures(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((root / "examples").rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"{path.relative_to(root)}: invalid JSON: {error}")
    return errors


def validate_required_coverage(root: Path) -> list[str]:
    errors: list[str] = []
    guides = [root / "README.md", root / "README.es.md"]
    for module_path in REQUIRED_MODULE_PATHS:
        if not (root / module_path.rstrip("/")).exists():
            errors.append(f"required module path does not exist: {module_path}")
        for guide in guides:
            if not guide.is_file() or module_path not in guide.read_text(encoding="utf-8"):
                errors.append(f"{guide.name}: missing module coverage: {module_path}")
    return errors


def validate_platform_pairs(root: Path) -> list[str]:
    errors: list[str] = []
    for directory in PAIR_DIRS:
        base = root / "examples" / directory
        if not list(base.glob("*.sh")) or not list(base.glob("*.ps1")):
            errors.append(f"examples/{directory}: missing Bash or PowerShell entry point")
    return errors


def _command_context(root: Path, command_line: str) -> tuple[Path | None, str | None]:
    """Return the nearest documented ``cd`` package context for a command line."""
    matches = list(re.finditer(r"\bcd\s+([^;&|]+)", command_line))
    if not matches:
        return None, None
    value = matches[-1].group(1).strip().strip("`\"'")
    value = value.rstrip("/")
    normalized = value.replace("\\", "/")
    marker_paths = ("webui/frontend", "SMS/apps/", "SMS/packages/", "SMS/tools/")
    for marker in marker_paths:
        index = normalized.rfind(marker)
        if index >= 0:
            relative = normalized[index:]
            package = root / relative / "package.json"
            return package.parent, "local"
    if normalized == "SMS" or normalized.endswith("/SMS"):
        return root / "SMS", "sms"
    return None, None


def validate_command_contracts(root: Path) -> list[str]:
    package_file = root / "SMS/package.json"
    try:
        scripts = json.loads(package_file.read_text(encoding="utf-8"))["scripts"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return ["SMS/package.json: unable to read scripts"]

    errors: list[str] = []
    docs = [root / "README.md", root / "README.es.md", *sorted((root / "examples").rglob("README*.md"))]
    for path in docs:
        if not path.is_file():
            continue
        context: tuple[Path | None, str | None] = (None, None)
        fenced = False
        fence_token = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if marker:
                token = marker.group(1)[0]
                if not fenced:
                    fenced, fence_token = True, token
                    context = (None, None)
                elif token == fence_token:
                    fenced, fence_token = False, ""
                    context = (None, None)
                continue
            if re.search(r"\bcd\s+", line):
                context = _command_context(root, line)
            for name in re.findall(r"\bnpm run ([\w:-]+)", line):
                package_root, kind = context
                if kind == "local":
                    local_scripts: dict[str, str] = {}
                    if package_root is not None:
                        try:
                            local_scripts = json.loads(
                                (package_root / "package.json").read_text(encoding="utf-8")
                            ).get("scripts", {})
                        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                            pass
                    if name not in local_scripts and name not in {"dev", "build", "test", "typecheck", "start"}:
                        errors.append(f"{path.relative_to(root)}: unknown local package script: {name}")
                elif kind == "sms" or "SMS" in path.parts or "sms-platform" in path.parts or path.parent == root:
                    if name not in scripts and name not in {"dev", "build", "test", "typecheck", "start"}:
                        errors.append(f"{path.relative_to(root)}: unknown SMS package script: {name}")
    return errors


def find_safety_violations(example_files: list[Path]) -> list[str]:
    patterns = (
        (re.compile(r"private[_-]?key", re.IGNORECASE), "private key field"),
        (re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"), "private key material"),
        (re.compile(r'operationalReady["\s:=]+true', re.IGNORECASE), "operationalReady true"),
        (re.compile(r"[?&]lease=", re.IGNORECASE), "controller lease in URL"),
    )
    errors: list[str] = []
    for path in example_files:
        if not path.is_file() or path.suffix.lower() not in {".json", ".csv", ".txt", ".sh", ".ps1", ".mjs"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, label in patterns:
            if pattern.search(text):
                errors.append(f"{path}: prohibited {label}")
    return errors


def verify_repository(root: Path) -> list[str]:
    root = root.resolve()
    markdown = [root / "README.md", root / "README.es.md", *sorted((root / "examples").rglob("README*.md"))]
    existing_markdown = [path for path in markdown if path.is_file()]
    errors = compare_root_anchors(root / "README.md", root / "README.es.md")
    for guide in (root / "README.md", root / "README.es.md"):
        if guide.is_file():
            anchors = ANCHOR_RE.findall(strip_fenced_code(guide.read_text(encoding="utf-8")))
            if anchors != list(ROOT_ANCHORS):
                errors.append(f"{guide.name} anchor contract differs: {anchors!r}")
    errors += find_broken_links(root, existing_markdown)
    errors += validate_json_fixtures(root)
    errors += validate_required_coverage(root)
    errors += validate_platform_pairs(root)
    errors += validate_command_contracts(root)
    errors += find_safety_violations(list((root / "examples").rglob("*")))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify bilingual MATB documentation offline")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    errors = verify_repository(parser.parse_args().root)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print("PASS documentation verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
