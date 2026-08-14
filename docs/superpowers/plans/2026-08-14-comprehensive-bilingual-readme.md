# Comprehensive Bilingual README and Examples Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository landing documentation with comprehensive, structurally mirrored English and Spanish guides and runnable synthetic examples for every active MATB workflow.

**Architecture:** Treat documentation as a tested interface: two root guides share stable section anchors, workflow-specific example directories own their runnable assets, and one dependency-free Python verifier checks paths, links, bilingual structure, fixtures, commands, and safety invariants offline. Examples call current Python CLIs, HTTP routes, Node package exports, and checked-in launchers without changing application behavior.

**Tech Stack:** Markdown/GitHub Flavored Markdown, Python 3.12 standard library and pytest, Bash, PowerShell 7, Node.js 22/npm workspaces, FastAPI, Next.js, Vitest, Docker/Compose, OpenMATB-compatible CSV and scenario formats.

## Global Constraints

- Primary audience is first-time users and researchers.
- `README.md` and `README.es.md` must be complete, mirrored guides with a visible language switch.
- Document Linux and Windows; use native PowerShell only for supported workflows and WSL2 for POSIX-only launchers and Unix-permission contracts.
- Cover OpenMATB research tooling, the Research Console, the synthetic sUAS simulator, the entire `SMS/` monorepo, and `aircraft_monitor/`.
- Do not change application behavior, APIs, safety logic, statistical methods, release evidence, or operational-readiness state.
- Do not vendor or imply that the external OpenMATB runner is bundled.
- All example identifiers and inputs must be synthetic and deterministic; examples may write only to their selected output directory.
- Examples must contain no PII, health data, real operational telemetry, credentials, private keys, controller leases in output, or institutional signatures.
- The sUAS examples remain synthetic, non-kinetic, observer-safe, and incapable of controlling real aircraft or weapons.
- SMS automated checks are not institutional approval; acceptance examples remain unsigned and `operationalReady=false`.
- Documentation must preserve fail-closed behavior and must not recommend bypassing validation, signatures, loopback defaults, or owner-only permissions.
- Commands must trace to a current CLI parser, route, package script, or checked-in launcher; the guides describe current behavior rather than historical pull-request status.
- Verification is offline and dependency-light; browser, Docker, external OpenMATB, and long-running service procedures are checked against existing integration suites rather than launched by documentation unit tests.
- Preserve all unrelated user-owned changes and keep work isolated on `docs/comprehensive-bilingual-readme`.

---

## File Map and Documentation Contracts

### Root guides

- Modify `README.md`: complete English landing guide, workflow chooser, architecture, five quick starts, full module catalog, operations, troubleshooting, safety, references, and license.
- Create `README.es.md`: complete Spanish guide in the same order with identical stable anchor IDs, commands, tables, examples, warnings, and path references.
- Both files use the following stable anchor contract so translated headings can still be compared and linked:

```markdown
<a id="identity-and-safety"></a>
## Identity and safety boundary
```

The ordered root anchor IDs are:

```text
identity-and-safety
choose-a-workflow
architecture-and-data-flow
prerequisites
quick-start-openmatb
quick-start-research-console
quick-start-suas
quick-start-sms
quick-start-legacy-monitor
module-catalog
operations-and-maintenance
troubleshooting
security-privacy-and-governance
repository-map
glossary
references
contributing
license
```

### Example tree

- Create `examples/README.md` and `examples/README.es.md`: bilingual example chooser and shared safety/output contract.
- Create `examples/openmatb-research/README.md`, `README.es.md`, `run_example.py`, `run.sh`, `run.ps1`, and `fixtures/{low,medium,high}.csv`.
- Create `examples/research-console/README.md`, `README.es.md`, `api_walkthrough.sh`, and `api_walkthrough.ps1`.
- Create `examples/suas-simulator/README.md`, `README.es.md`, `cli_demo.sh`, `api_walkthrough.sh`, and `api_walkthrough.ps1`.
- Create `examples/sms-platform/README.md`, `README.es.md`, `package-tour.mjs`, `run.sh`, `run.ps1`, and `fixtures/controlled-evidence.txt`.
- Create `examples/legacy-monitor/README.md`, `README.es.md`, `run.sh`, and `run.ps1`.

### Verification

- Create `scripts/verify_documentation.py`: dependency-free verifier with importable functions and a CLI returning nonzero when any check fails.
- Create `tests/documentation/__init__.py` and `tests/documentation/test_documentation.py`: focused tests for link resolution, mirrored anchors, required coverage, structured fixtures, platform pairs, safe examples, package-script/CLI references, and fast example smoke tests.

### Interfaces between tasks

`scripts.verify_documentation.verify_repository(root: Path) -> list[str]` is the single verification interface. It returns stable, human-readable error strings and performs no writes. Every later documentation task is complete only when its files remove the corresponding errors from this function.

The Python example interface is:

```text
python examples/openmatb-research/run_example.py --output-dir PATH
```

It creates `scenarios/`, `metrics.jsonl`, and `suhir.json` under `PATH`, prints only relative output summaries, and never invokes the external OpenMATB runtime.

The SMS example interface is:

```text
cd SMS
npm run build:packages
node ../examples/sms-platform/package-tour.mjs
```

It emits one JSON object with keys `evidence`, `energy`, `fleet`, `geo`, `telemetry`, `safetyKernel`, `sms`, `humanPerformance`, and `research`; the safety-kernel result is deliberately blocked by missing accepted evidence.

---

### Task 1: Add the offline documentation contract verifier

**Files:**
- Create: `scripts/verify_documentation.py`
- Create: `tests/documentation/__init__.py`
- Create: `tests/documentation/test_documentation.py`
- Test: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: repository Markdown files, JSON fixtures, Python CLI sources, and `SMS/package.json`.
- Produces: `verify_repository(root: Path) -> list[str]` and CLI output `PASS documentation verification` on success.

- [ ] **Step 1: Write unit tests for link, anchor, and safety behavior**

Create the test package marker and tests with temporary repositories so failures are specific rather than coupled to the unfinished guide:

```python
from pathlib import Path

from scripts.verify_documentation import (
    compare_root_anchors,
    find_broken_links,
    find_safety_violations,
)


def test_relative_links_resolve_and_code_fences_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("<a id=\"ok\"></a>\n# Target\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text(
        "[valid](target.md#ok)\n```markdown\n[example](missing.md)\n```\n",
        encoding="utf-8",
    )
    assert find_broken_links(tmp_path, [source]) == []


def test_missing_file_and_anchor_are_reported(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("# Target\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("[file](missing.md) [anchor](target.md#absent)\n", encoding="utf-8")
    errors = find_broken_links(tmp_path, [source])
    assert any("missing.md" in error for error in errors)
    assert any("#absent" in error for error in errors)


def test_translated_headings_share_stable_anchor_order(tmp_path: Path) -> None:
    en = tmp_path / "README.md"
    es = tmp_path / "README.es.md"
    en.write_text('<a id="identity-and-safety"></a>\n## Identity\n', encoding="utf-8")
    es.write_text('<a id="identity-and-safety"></a>\n## Identidad\n', encoding="utf-8")
    assert compare_root_anchors(en, es) == []
    es.write_text('<a id="different"></a>\n## Identidad\n', encoding="utf-8")
    assert compare_root_anchors(en, es)


def test_committed_examples_reject_secrets_and_false_readiness(tmp_path: Path) -> None:
    bad = tmp_path / "example.json"
    bad.write_text('{"privateKey":"secret","operationalReady":true}', encoding="utf-8")
    errors = find_safety_violations([bad])
    assert any("private key" in error.lower() for error in errors)
    assert any("operationalReady" in error for error in errors)
```

- [ ] **Step 2: Run the focused tests and confirm the module is absent**

Run:

```bash
python -m pytest tests/documentation/test_documentation.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.verify_documentation'`.

- [ ] **Step 3: Implement the parsing and validation primitives**

Use only `argparse`, `json`, `pathlib`, `re`, `sys`, and `urllib.parse` from the standard library. Implement the public functions below; keep private helpers in the same file because this verifier has one responsibility and no runtime dependency:

```python
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
    if en != list(ROOT_ANCHORS):
        errors.append(f"README.md anchor order differs: {en!r}")
    if es != list(ROOT_ANCHORS):
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


def validate_command_contracts(root: Path) -> list[str]:
    scripts = json.loads((root / "SMS/package.json").read_text(encoding="utf-8"))["scripts"]
    errors: list[str] = []
    docs = [root / "README.md", root / "README.es.md", *sorted((root / "examples").rglob("README*.md"))]
    for path in docs:
        for name in re.findall(r"\bnpm run ([\w:-]+)", path.read_text(encoding="utf-8")):
            if "SMS" in path.parts or "sms-platform" in path.parts or path.parent == root:
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
```

During implementation, refine the SMS command check to distinguish root-level workspace commands from frontend-local commands by the code block's nearest `cd` command; add a test for each context. This prevents a valid frontend `npm run dev` from being interpreted as an SMS root script while still rejecting misspelled SMS commands.

- [ ] **Step 4: Run unit tests and observe repository-contract failures**

Run:

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Expected: unit tests pass; the CLI fails because `README.es.md` and the `examples/` contract do not exist yet. This is the intended red state for the remaining tasks.

- [ ] **Step 5: Commit the verifier foundation**

```bash
git add scripts/verify_documentation.py tests/documentation
git commit -m "test: define bilingual documentation contract"
```

---

### Task 2: Add deterministic OpenMATB research and legacy-monitor examples

**Files:**
- Create: `examples/openmatb-research/README.md`
- Create: `examples/openmatb-research/README.es.md`
- Create: `examples/openmatb-research/run_example.py`
- Create: `examples/openmatb-research/run.sh`
- Create: `examples/openmatb-research/run.ps1`
- Create: `examples/openmatb-research/fixtures/low.csv`
- Create: `examples/openmatb-research/fixtures/medium.csv`
- Create: `examples/openmatb-research/fixtures/high.csv`
- Create: `examples/legacy-monitor/README.md`
- Create: `examples/legacy-monitor/README.es.md`
- Create: `examples/legacy-monitor/run.sh`
- Create: `examples/legacy-monitor/run.ps1`
- Modify: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: `matb_integration.scenario_builder`, `matb_integration.scenario_manifest`, `matb_integration.log_converter`, `matb_integration.suhir.pipeline`, and `python -m aircraft_monitor`.
- Produces: an offline Python research tour and paired native Bash/PowerShell entry points; legacy examples write only below a caller-selected output directory.

- [ ] **Step 1: Add a failing Python-example smoke test**

```python
import json
import subprocess
import sys


def test_openmatb_example_runs_offline(repo_root: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "examples/openmatb-research/run_example.py", "--output-dir", str(tmp_path)],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "scenarios").glob("*.txt"))) == 3
    records = [json.loads(line) for line in (tmp_path / "metrics.jsonl").read_text().splitlines()]
    assert [record["workload_level"] for record in records] == ["LOW", "MEDIUM", "HIGH"]
    assert json.loads((tmp_path / "suhir.json").read_text())["participant_id"] == "SYNTH-P01"
```

Run `python -m pytest tests/documentation/test_documentation.py::test_openmatb_example_runs_offline -q`; expected failure is a missing `run_example.py`.

- [ ] **Step 2: Add three minimal synthetic session CSVs**

Each CSV uses the exact OpenMATB converter header and deterministic workload differences. `low.csv` contains:

```csv
scenario_time,type,module,address,value
10.0,performance,sysmon,signal_detection,HIT
10.1,performance,sysmon,response_time,650
30.0,performance,sysmon,signal_detection,HIT
60.0,performance,sysmon,signal_detection,MISS
90.0,performance,genericscales,Workload,2
900.0,performance,genericscales,Mental demand,3
900.0,performance,genericscales,Physical demand,1
900.0,performance,genericscales,Time pressure,2
900.0,performance,genericscales,Performance,3
900.0,performance,genericscales,Effort,2
900.0,performance,genericscales,Frustration,1
```

Use the same schema in `medium.csv` and `high.csv`; set the six NASA-TLX values to `5,2,5,5,5,3` and `8,3,8,7,8,6`, respectively, and retain one deterministic SYSMON miss in medium and two misses in high. All three levels need at least one failure time because the current DEPDF fit requires three observed-failure levels. Do not copy any real session file.

- [ ] **Step 3: Implement the OpenMATB research tour**

Implement `run_example.py` with `argparse --output-dir`, fixed participant `SYNTH-P01`, fixed seed `42`, and these production calls:

```python
from matb_integration.log_converter import convert_session
import subprocess
import sys

from matb_integration.suhir.pipeline import fit_participant

LEVELS = (("LOW", WorkloadLevel.LOW, "low.csv"),
          ("MEDIUM", WorkloadLevel.MEDIUM, "medium.csv"),
          ("HIGH", WorkloadLevel.HIGH, "high.csv"))
```

First invoke the supported generator CLI with `subprocess.run([sys.executable, "-m", "matb_integration.scenario_builder", "--output-dir", str(output_dir / "scenarios"), "--block-duration", "900", "--seed", "42"], check=True)`. Confirm each generated `*.txt.manifest.json` parses and its `scenario.sha256` matches the adjacent scenario before continuing. For each CSV level, call `convert_session`, retain `parse_csv` rows for `fit_participant`, append canonical JSON records to `metrics.jsonl`, then serialize the DEPDF result to `suhir.json`. Resolve fixtures from `Path(__file__).parent`, create only `args.output_dir`, and print the generated relative names plus the sentence `External OpenMATB was not started.`

- [ ] **Step 4: Add platform entry points and bilingual instructions**

`run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/openmatb-research}"
cd "$repo_root"
python3 examples/openmatb-research/run_example.py --output-dir "$output_dir"
```

`run.ps1`:

```powershell
param([string]$OutputDir = "")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "examples/output/openmatb-research" }
Set-Location $RepoRoot
python examples/openmatb-research/run_example.py --output-dir $OutputDir
```

The paired READMEs explain scenario generation, manifest provenance, conversion, questionnaire fields, DEPDF fitting, and the exact frequentist/Bayesian CLI input shapes. Clearly state that the external OpenMATB runner is separately installed and that PyMC sampling is intentionally not part of this fast tour.

- [ ] **Step 5: Add paired legacy-monitor examples**

`run.sh` accepts `uav|fighter|combined|experiment`, defaults to `combined`, runs with `--headless --event-delay 0.05 --seed 42`, and adds `--participant-id SYNTH-P01 --session-id SYNTH-S01 --research-output-dir PATH` only for experiment mode. `run.ps1` provides the same contract with `ValidateSet` and native paths. Both workflow guides show all four modes, expected completion output, Ctrl-C behavior, output inspection, and deletion of only `examples/output/legacy-monitor`.

- [ ] **Step 6: Run smoke and module regressions**

```bash
python -m pytest tests/documentation/test_documentation.py tests/test_scenario_builder.py tests/test_scenario_manifest.py tests/test_log_converter.py tests/suhir -q
python -m aircraft_monitor --help
```

Expected: all tests pass and help lists `uav`, `fighter`, `combined`, and `experiment`.

- [ ] **Step 7: Commit the research examples**

```bash
git add examples/openmatb-research examples/legacy-monitor tests/documentation/test_documentation.py
git commit -m "docs: add synthetic research workflow examples"
```

---

### Task 3: Add Research Console and synthetic sUAS walkthroughs

**Files:**
- Create: `examples/research-console/README.md`
- Create: `examples/research-console/README.es.md`
- Create: `examples/research-console/api_walkthrough.sh`
- Create: `examples/research-console/api_walkthrough.ps1`
- Create: `examples/suas-simulator/README.md`
- Create: `examples/suas-simulator/README.es.md`
- Create: `examples/suas-simulator/cli_demo.sh`
- Create: `examples/suas-simulator/api_walkthrough.sh`
- Create: `examples/suas-simulator/api_walkthrough.ps1`
- Modify: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: FastAPI routes at `127.0.0.1:8000`, frontend at `127.0.0.1:3100`, `scripts/install_suas.sh`, `scripts/run_suas.sh`, and `matb_integration.suas.cli`.
- Produces: safe HTTP walkthroughs and a deterministic CLI-only simulator run; lease values remain shell variables and request headers only.

- [ ] **Step 1: Add failing static safety tests for HTTP walkthroughs**

```python
def test_suas_walkthrough_keeps_lease_out_of_urls(repo_root: Path) -> None:
    for name in ("api_walkthrough.sh", "api_walkthrough.ps1"):
        text = (repo_root / "examples/suas-simulator" / name).read_text(encoding="utf-8")
        assert "X-Simulation-Controller" in text
        assert "?lease=" not in text
        assert "controller_lease" not in "\n".join(
            line for line in text.splitlines() if "echo" in line.lower() or "write-host" in line.lower()
        )


def test_http_walkthroughs_use_synthetic_identity(repo_root: Path) -> None:
    texts = [path.read_text(encoding="utf-8") for path in
             (repo_root / "examples/research-console").glob("api_walkthrough.*")]
    assert texts and all("SYNTH-P01" in text for text in texts)
```

Run the two tests; expected failure is missing walkthrough files.

- [ ] **Step 2: Implement Research Console Bash and PowerShell API tours**

The Bash script uses `curl --fail-with-body` to:

```bash
curl --fail-with-body "$base_url/health"
curl --fail-with-body -H 'Content-Type: application/json' \
  -d '{"id":"SYNTH-P01","enrollment_date":"2026-08-14"}' \
  "$base_url/participants"
curl --fail-with-body -F 'participant_id=SYNTH-P01' -F 'visit_ordinal=1' \
  -F 'workload_level=LOW' \
  -F "file=@$repo_root/examples/openmatb-research/fixtures/low.csv;type=text/csv" \
  "$base_url/ingest"
curl --fail-with-body "$base_url/tracker"
curl --fail-with-body "$base_url/exports/research-context"
curl --fail-with-body -H 'Content-Type: application/json' -d '{"figures":[]}' \
  --output "$output_dir/research-bundle.zip" "$base_url/exports/research-bundle"
```

Accept `BASE_URL` and output directory overrides, detect a pre-existing synthetic participant, and explain that rerunning against the same database can return 409 until the documented example data directory is cleaned. The PowerShell version uses `Invoke-RestMethod`, `Invoke-WebRequest`, `-Form`, and `-OutFile` for the same route sequence.

- [ ] **Step 3: Add complete Research Console instructions**

Both guides cover Python 3.12, Node 20+ for the launcher, frontend Node dependencies, native backend/frontend development commands, Linux/WSL2 offline install and launcher, Windows PowerShell development startup, ports 8000/3100, `MATB_DB_PATH`, data/export locations, health checks, shutdown, cleanup, duplicate-ingest behavior, missing manifests, and the browser routes for tracker, upload, visualization, analysis, Bayesian analysis, screen, and research-bundle export. Link to `webui/backend/README.md` and `webui/frontend/README.md` for endpoint/UI depth.

- [ ] **Step 4: Implement the deterministic sUAS CLI demo**

`cli_demo.sh` runs without a service or browser:

```bash
#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/suas-simulator}"
scenario="$repo_root/scenarios/suas/reference_area_search.yaml"
mkdir -p "$output_dir"
cd "$repo_root"
python3 -m matb_integration.suas.cli validate "$scenario"
python3 -m matb_integration.suas.cli run "$scenario" --block PRACTICE --ticks 10
python3 -m matb_integration.suas.cli record "$scenario" --block PRACTICE --ticks 10 \
  --session-id SYNTH-SUAS-01 --output "$output_dir"
python3 -m matb_integration.suas.cli verify "$output_dir/SYNTH-SUAS-01"
```

Before finalizing the path, run the command once and adjust only to the actual recorder directory emitted by the CLI. The script must not guess or search arbitrary directories.

- [ ] **Step 5: Implement lease-safe sUAS API tours**

The Bash and PowerShell scripts perform this exact sequence: health, create `SYNTH-P01` if absent, list scenarios, prepare a session for `reference_area_search`, store `id` and `controller_lease` in local variables, start block `PRACTICE` with `X-Simulation-Controller`, request the public state without a lease, finish with `{"disposition":"complete"}`, fetch debrief and artifact metadata, and unset/clear the lease variable. Do not submit commands that resemble real aircraft control; use lifecycle-only mutations. Do not print the prepared response wholesale because it contains the one-time lease.

- [ ] **Step 6: Add sUAS bilingual instructions and WSL2 boundary**

Document Linux/WSL2 installation with:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/suas-service"
```

Explain loopback defaults, explicit origin configuration for any non-loopback bind, controller versus observer behavior, disconnect/pause semantics, checkpoint recovery, sealed terminal artifacts, public redaction, ports, Ctrl-C teardown, owner-only data, and verification. State that Windows runs these POSIX launchers under WSL2; PowerShell may call the loopback API once WSL2 hosts the service.

- [ ] **Step 7: Run focused route and simulator regressions**

```bash
python -m pytest tests/documentation/test_documentation.py tests/suas webui/backend/tests/test_health.py webui/backend/tests/test_participants.py webui/backend/tests/test_endpoints.py webui/backend/tests/test_simulation_endpoints.py -q
bash tests/scripts/test_suas_scripts.sh
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit console and simulator examples**

```bash
git add examples/research-console examples/suas-simulator tests/documentation/test_documentation.py
git commit -m "docs: add console and synthetic sUAS walkthroughs"
```

---

### Task 4: Add an executable FAC ISR SMS capability tour

**Files:**
- Create: `examples/sms-platform/README.md`
- Create: `examples/sms-platform/README.es.md`
- Create: `examples/sms-platform/package-tour.mjs`
- Create: `examples/sms-platform/run.sh`
- Create: `examples/sms-platform/run.ps1`
- Create: `examples/sms-platform/fixtures/controlled-evidence.txt`
- Modify: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: compiled exports in `SMS/packages/*/dist`, workspace scripts in `SMS/package.json`, edge API/console package scripts, map-packager CLI, research-tool CLI, and release/verification scripts.
- Produces: one deterministic JSON capability summary; the result remains non-operational and deliberately fail-closed.

- [ ] **Step 1: Add a failing SMS tour smoke test**

```python
def test_sms_package_tour_is_deterministic(repo_root: Path) -> None:
    if not (repo_root / "SMS/packages/evidence/dist/index.js").exists():
        pytest.skip("run npm run build:packages before the SMS example smoke test")
    first = subprocess.run(["node", "../examples/sms-platform/package-tour.mjs"],
                           cwd=repo_root / "SMS", capture_output=True, text=True, check=False)
    second = subprocess.run(["node", "../examples/sms-platform/package-tour.mjs"],
                            cwd=repo_root / "SMS", capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert set(result) == {"evidence", "energy", "fleet", "geo", "telemetry",
                           "safetyKernel", "sms", "humanPerformance", "research"}
    assert result["safetyKernel"]["status"] == "blocked"
    assert result["research"]["nonDispatchable"] is True
```

Run after `cd SMS && npm run build:packages`; expected failure is missing `package-tour.mjs`.

- [ ] **Step 2: Implement evidence, energy, fleet, geo, and telemetry examples**

Import from explicit relative compiled indexes such as `../../SMS/packages/evidence/dist/index.js` so the script works from the documented `SMS/` current directory. Use production functions and fixed UTC timestamps:

```javascript
const evidenceHash = await sha256File(
  new URL("./fixtures/controlled-evidence.txt", import.meta.url),
);
const energy = calculateMissionEnergy(validEnergyInput);
const capability = evaluateCapability(
  { id: "CAP-SYNTH-1", subjectId: "UAS-SYNTH-1", capability: "vlos", value: true,
    operatingConditions: {}, evidenceRefs: ["EV-SYNTH-1"], confidence: "qualified",
    validFromUtc: "2026-08-01T00:00:00Z" },
  {},
  { current: true, acceptedEvidenceRefs: ["EV-SYNTH-1"], approved: true,
    asOfUtc: "2026-08-14T00:00:00Z", subjectId: "UAS-SYNTH-1" },
);
const route = buildRoute({
  id: "ROUTE-SYNTH-1",
  waypoints: [
    { id: "WP-1", lat: 4.70, lon: -74.10, altitude: 2600, altitudeReference: "MSL", role: "route" },
    { id: "WP-2", lat: 4.80, lon: -74.00, altitude: 2650, altitudeReference: "MSL", role: "recovery" },
  ],
  flightRule: "VFR", visualCondition: "VLOS", altitudeReference: "MSL",
  sourcePackageIds: ["MAP-SYNTH-1"],
});
const replay = await new ReplayGateway({
  aircraftId: "UAS-SYNTH-1", now: () => "2026-08-14T00:00:10.000Z", maxDelayMs: 5000,
}).replay([{ eventId: "TEL-SYNTH-1", aircraftId: "UAS-SYNTH-1",
  observedAtUtc: "2026-08-14T00:00:01.000Z", sourcePackageIds: ["TEL-PKG-SYNTH-1"] }]);
```

Copy the complete valid energy object shape from `SMS/packages/energy/test/fixtures.ts`, replacing identifiers with `SYNTH` values while preserving its approved-performance evidence requirements. Summarize only stable result fields: hash, status, reserve percentage, capability status, route segment count/hash, and telemetry record statuses.

- [ ] **Step 3: Implement fail-closed safety, SMS, human-performance, and research examples**

Build a synthetic unarmed VLOS mission from the shape in `SMS/packages/safety-kernel/test/evaluate.test.ts`, but give its hard requirement an empty `sourceRefs` array. Store `const safetyResult = evaluateMission(safetyInput)` and assert `safetyResult.status === "blocked"`; an unexpected ready result throws. Demonstrate:

```javascript
const hazard = promoteMissionHazard({
  missionHazard: { id: "MH-SYNTH-1", title: "Synthetic wildlife activity",
    description: "Training-only scenario", causes: ["synthetic seasonal activity"],
    consequences: ["exercise interruption"], residualRiskId: "RISK-SYNTH-1" },
  organizationalOwnerId: "SMS-SYNTH-OWNER",
});
const spi = evaluateSpi({ value: 4, unit: "synthetic-events/100-hours" },
                        { alertAt: 3, actionAt: 5 });
const humanPerformance = evaluateOperationalStatus(
  { userId: "OP-SYNTH-1", role: "operator", dutyPeriodId: "DUTY-SYNTH-1",
    qualificationStatus: "current", fatigueSelfDeclaration: "able",
    screenExposureMinutes: 45, workloadLevel: "moderate", alertLoad: 2,
    status: "available", evidenceRefs: ["EV-HF-SYNTH-1"] },
  { maxScreenExposureMinutes: 120, maxAlertLoad: 4, policyVersion: "HF-SYNTH-1" },
);
const protocol = registerProtocol({ id: "PROTOCOL-SYNTH-1", version: "1.0.0",
  title: "Synthetic MATB tour", investigatorId: "INV-SYNTH-1",
  ethicsApprovalId: "ETHICS-SYNTH-1", permittedInstruments: ["NASA-TLX"],
  permittedSensors: ["matb"], retentionDays: 30, status: "approved" });
```

Open a consented synthetic session using the exact current protocol API, verify `nonDispatchable === true`, feed one `MatbResearchAdapter` event, and run `exportDeidentified`. The summary includes no names, clinical facts, operational user IDs, or mission-release fields. Include hazard, SPI, audit/CAPA/ERP/MOC capability names in the result, using blocked/incomplete demonstrations when accountable evidence is absent.

- [ ] **Step 4: Add cross-platform runners**

`run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root/SMS"
npm ci
npm run build:packages
node ../examples/sms-platform/package-tour.mjs
```

`run.ps1` performs `Set-Location (Join-Path $RepoRoot "SMS")`, `npm ci`, `npm run build:packages`, and `node ../examples/sms-platform/package-tour.mjs`, stopping on a nonzero `$LASTEXITCODE` after each native command.

- [ ] **Step 5: Write comprehensive SMS example guides**

Both guides explain Node 22.x, `npm ci`, package build/test/typecheck/lint, edge API and console development startup, loopback ports from their manifests, Docker Compose/offline deployment, data directories, TLS/environment requirements, and every package/tool role. Include verified commands for:

```text
npm run build
npm test
npm run typecheck
npm run lint
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
npm run release:manifest
npm run release:sign
npm run release:verify
npm run verify:matrix
npm run acceptance:packets
npm run verify:acceptance
npm run verify:all
```

Explain map-package and research-package CLI help from their current parser source. Clearly distinguish generated unsigned reviewer packets from `acceptance:record`, which requires human-supplied controlled decisions and must not be run with fabricated values. State that a passing test/verification matrix can coexist with `operationalReady=false`.

- [ ] **Step 6: Build and run SMS verification**

```bash
cd SMS
npm run build:packages
node ../examples/sms-platform/package-tour.mjs
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

Expected: package tour prints valid JSON, its safety kernel is blocked, its research record is non-dispatchable, and all selected SMS checks pass.

- [ ] **Step 7: Commit the SMS examples**

```bash
git add examples/sms-platform tests/documentation/test_documentation.py
git commit -m "docs: add FAC ISR SMS capability examples"
```

---

### Task 5: Replace the English root README and add the example index

**Files:**
- Modify: `README.md`
- Create: `examples/README.md`
- Modify: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: all example interfaces from Tasks 2–4 and authoritative specialist docs/launchers.
- Produces: the default newcomer landing page and English example chooser.

- [ ] **Step 1: Add English coverage assertions**

```python
def test_english_guide_has_complete_information_architecture(repo_root: Path) -> None:
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    anchors = markdown_anchors(repo_root / "README.md")
    assert [anchor for anchor in anchors if anchor in ROOT_ANCHORS] == list(ROOT_ANCHORS)
    for path in REQUIRED_MODULE_PATHS:
        assert path in text
    for workflow in ("openmatb-research", "research-console", "suas-simulator",
                     "sms-platform", "legacy-monitor"):
        assert f"examples/{workflow}/README.md" in text


def test_root_guide_has_no_historical_pr_status(repo_root: Path) -> None:
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"\bPR\s*#\d+|pull request\s*#\d+", text, re.IGNORECASE)
```

Run these tests; expected failure is the old README structure.

- [ ] **Step 2: Write identity, chooser, architecture, and prerequisites**

Replace the old README rather than appending to it. Begin with:

```markdown
# MATB — Human-Factors Research and Aviation Safety Assurance

[English](README.md) | [Español](README.es.md)

> Research and safety-assurance software only. MATB is not a clinical device,
> certified operational system, aircraft-control channel, weapon system, or a
> substitute for accountable human approval.
```

Then use the stable anchors from the file map. Include a chooser table with columns `Goal`, `Start here`, `Runtime`, `Example`, and `Expected output`. Add a compact repository tree and four Mermaid-free text flows so the README renders everywhere:

```text
External OpenMATB -> session CSV + scenario manifest -> metrics -> DEPDF/statistics -> research bundle
Browser -> FastAPI Research Console -> local SQLite/artifacts -> tracker/analysis/export
Synthetic YAML -> deterministic sUAS engine -> observer-safe state -> replay/debrief artifacts
Signed local evidence + read-only telemetry -> edge API/safety kernel -> console/audit -> offline verification
```

The prerequisites matrix states Python 3.12+ for sUAS, Node 22.x for `SMS/`, Node 20+ for the research-console launcher, and labels Git, npm, Docker, Chromium, external OpenMATB, Xvfb, and WSL2 as required/optional/workflow-specific based on source scripts.

- [ ] **Step 3: Write all five guided quick starts**

Each stable quick-start section follows the exact subheading order:

```markdown
### Prerequisites
### Install
### Configure
### Run
### Try the synthetic example
### Expected result
### Verify
### Stop and clean up
### Troubleshooting
```

Provide separate Linux Bash and Windows PowerShell blocks. Use WSL2 only where `setup.sh`, `install_suas.sh`, `run_suas.sh`, Docker verification, or Unix permission behavior is involved. Never use a developer-specific home-directory virtual environment or absolute path; all paths derive from the clone root.

- [ ] **Step 4: Write the complete module catalog**

Use one compact table per subsystem. Each module row answers purpose, user, inputs/outputs, runtime, example, verification, and limitation. Explicitly cover every path in `REQUIRED_MODULE_PATHS` plus:

- scenario/manifest/questionnaire generation, frequentist and Bayesian engines, Suhir DEPDF, and exploratory screen mapping;
- backend/frontend tracker, ingestion, visualization, screen, analysis, and export;
- sUAS scenario, session, controller-lease, observer stream, lifecycle, replay, debrief, and artifacts;
- edge API and console;
- all nine SMS packages, both tools, offline bundle, SBOM/manifest, no-C2, data separation, verification matrix, acceptance packets, and decision intake;
- legacy combined, UAV, fighter, and experiment modes.

Link advanced claims to specialist docs already under `webui/`, `matb_integration/suhir/`, `SMS/docs/`, and `docs/` rather than copying their full evidence reviews.

- [ ] **Step 5: Write operations, troubleshooting, governance, and maintenance sections**

Document test suites, ports, environment variables, generated data, constrained cleanup targets, offline behavior, release verification, contribution expectations, license, and a glossary. Troubleshooting is symptom-oriented and includes wrong versions, inactive venv, missing external OpenMATB, display/Pyglet, PowerShell policy/path quoting, WSL2 paths/ports, occupied 8000/3100 ports, missing Chromium, unavailable Docker, evidence expiry/tamper, and readiness remaining blocked after tests pass.

The governance section repeats the no-C2/non-kinetic boundary, pseudonymization, exploratory research limits, controlled evidence and UTC/hash requirements, and institutional human acceptance. It must never advise weakening checks.

- [ ] **Step 6: Write the English example chooser**

`examples/README.md` links the five workflow guides, states shared synthetic/output/cleanup constraints, provides the verifier command, and explains which examples are fast/offline versus service, browser, Docker, or external-runtime integration procedures.

- [ ] **Step 7: Run English documentation checks**

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Expected: English coverage tests pass; the full verifier may still fail only because Spanish files are incomplete.

- [ ] **Step 8: Commit the English guide**

```bash
git add README.md examples/README.md tests/documentation/test_documentation.py
git commit -m "docs: replace root guide with comprehensive workflow documentation"
```

---

### Task 6: Create the structurally mirrored Spanish guides

**Files:**
- Create: `README.es.md`
- Create: `examples/README.es.md`
- Modify: `examples/openmatb-research/README.es.md`
- Modify: `examples/research-console/README.es.md`
- Modify: `examples/suas-simulator/README.es.md`
- Modify: `examples/sms-platform/README.es.md`
- Modify: `examples/legacy-monitor/README.es.md`
- Modify: `tests/documentation/test_documentation.py`

**Interfaces:**
- Consumes: English guides and the stable anchor contract.
- Produces: complete Spanish navigation with identical command semantics and file coverage.

- [ ] **Step 1: Add mirror tests before translation**

```python
def test_root_guides_are_structurally_mirrored(repo_root: Path) -> None:
    assert compare_root_anchors(repo_root / "README.md", repo_root / "README.es.md") == []


def test_each_workflow_has_a_spanish_guide(repo_root: Path) -> None:
    for workflow in ("openmatb-research", "research-console", "suas-simulator",
                     "sms-platform", "legacy-monitor"):
        directory = repo_root / "examples" / workflow
        assert (directory / "README.md").is_file()
        assert (directory / "README.es.md").is_file()
```

Run these tests; expected failure identifies missing or incomplete Spanish guides.

- [ ] **Step 2: Translate the root guide completely**

Translate explanatory prose and headings into neutral technical Spanish while preserving:

- every explicit anchor ID and its order;
- every command, code block, environment variable, port, path, JSON key, API route, package name, and expected machine output;
- every table row and warning;
- the language switch, pointing English to `README.md` and Spanish to `README.es.md`;
- terms that are formal API/domain identifiers, with a Spanish explanation instead of renaming the identifier.

The title is `MATB — Investigación de factores humanos y aseguramiento de la seguridad operacional aeronáutica`. Use `seguridad operacional` for safety and `seguridad de la información` when discussing security so the meanings remain distinct.

- [ ] **Step 3: Complete all Spanish workflow guides**

Mirror each English example guide section-for-section. Preserve the exact Bash and PowerShell blocks so the two languages do not drift operationally. Translate expected results, cleanup explanations, warnings, and troubleshooting. Retain the literal safety phrases `operationalReady=false`, `nonDispatchable`, header `X-Simulation-Controller`, and package/CLI identifiers.

- [ ] **Step 4: Run bilingual structure and link checks**

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Expected: all documentation tests and the standalone verifier pass.

- [ ] **Step 5: Commit the Spanish guide**

```bash
git add README.es.md examples/README.es.md examples/*/README.es.md tests/documentation/test_documentation.py
git commit -m "docs: add complete Spanish documentation"
```

---

### Task 7: Verify command accuracy and affected regressions

**Files:**
- Modify if verification exposes a mismatch: `README.md`, `README.es.md`, `examples/**`, `scripts/verify_documentation.py`, `tests/documentation/test_documentation.py`
- Do not modify: application source, generated SMS acceptance artifacts, or user-owned root-worktree files.

**Interfaces:**
- Consumes: all deliverables from Tasks 1–6.
- Produces: evidence that documentation is internally consistent and examples use supported behavior.

- [ ] **Step 1: Scan the plan deliverables for forbidden placeholders and unsafe material**

```bash
rg -n --glob 'README*.md' --glob 'examples/**' \
  'T[B]D|T[O]DO|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|operationalReady["[:space:]:=]+true|\?lease=' \
  README.md README.es.md examples
```

Expected: no matches. Explanatory text about forbidden values should use prose that does not reproduce a secret-shaped field/value pair.

- [ ] **Step 2: Run offline documentation and example verification**

```bash
python scripts/verify_documentation.py
python -m pytest tests/documentation/test_documentation.py -q
python examples/openmatb-research/run_example.py --output-dir /tmp/matb-docs-openmatb
python -m matb_integration.suas.cli validate scenarios/suas/reference_area_search.yaml
python -m aircraft_monitor --help
```

Expected: verifier and tests pass; examples print deterministic summaries without absolute controlled paths or secret values.

- [ ] **Step 3: Verify current Python and backend behavior used by examples**

```bash
python -m pytest \
  tests/test_scenario_builder.py tests/test_scenario_manifest.py tests/test_log_converter.py \
  tests/suhir tests/analysis_stats tests/screen tests/suas \
  webui/backend/tests -q
bash tests/scripts/test_suas_scripts.sh
```

Expected: all selected tests pass, with only pre-existing intentional skips.

- [ ] **Step 4: Verify current frontend commands**

```bash
cd webui/frontend
npm test
npm run typecheck
npm run build
```

Expected: Vitest, TypeScript, and Next.js build pass. Do not update browser snapshots during this task.

- [ ] **Step 5: Verify the SMS tour and workspace contracts**

```bash
cd SMS
npm ci
npm run build
node ../examples/sms-platform/package-tour.mjs
npm test
npm run typecheck
npm run lint
npm run verify:no-c2
npm run verify:data-separation
npm run verify:matrix
npm run verify:acceptance
```

Expected: builds/tests/checks pass; `verify:acceptance` may correctly report blocked institutional readiness while returning according to its current tested contract. The example summary must still report a blocked safety-kernel case and non-dispatchable research data.

- [ ] **Step 6: Inspect the final diff for scope and generated files**

```bash
git status --short
git diff --check
git diff --stat origin/main..HEAD
git diff --name-only origin/main..HEAD
```

Expected: only the design spec, implementation plan, two root guides, `examples/`, documentation verifier, and documentation tests appear. Generated `examples/output/`, `SMS/dist/`, node modules, caches, and local databases must be absent from the diff.

- [ ] **Step 7: Commit verification-driven corrections**

If Step 1–6 required tracked corrections:

```bash
git add README.md README.es.md examples scripts/verify_documentation.py tests/documentation
git commit -m "docs: verify bilingual examples and command contracts"
```

If there are no corrections, do not create an empty commit.

---

### Task 8: Final acceptance review against the approved design

**Files:**
- Review: `docs/superpowers/specs/2026-08-14-comprehensive-bilingual-readme-design.md`
- Review: all changed files from `git diff --name-only origin/main..HEAD`

**Interfaces:**
- Consumes: approved design, verification output, and final diff.
- Produces: a concise completion report with exact test results and any integration procedures not run locally.

- [ ] **Step 1: Check every acceptance criterion explicitly**

Record a local checklist confirming: workflow selection, complete bilingual module coverage, five install-to-verification sequences, synthetic examples, internal links/fixtures, fast smoke tests, affected regressions, safety/governance boundaries, and isolated scope. Resolve any unchecked item before proceeding.

- [ ] **Step 2: Re-run the completion gate**

```bash
python scripts/verify_documentation.py
python -m pytest tests/documentation/test_documentation.py -q
git diff --check
git status --short
```

Expected: all commands pass; status contains only intentional tracked documentation work and no generated output.

- [ ] **Step 3: Prepare the handoff**

Report:

- what the repository is now documented to do;
- the two language entry points;
- the five example entry points;
- Linux/native Windows/WSL2 boundaries;
- documentation-verifier result and regression commands with pass counts;
- any browser, Docker, or external OpenMATB integration step not executed and why;
- the branch name and commit list.

Do not claim institutional acceptance, operational readiness, certification, clinical validation, real-aircraft capability, or tests that were not run.
