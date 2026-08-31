from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from scripts.verify_documentation import (
    ROOT_ANCHORS,
    REQUIRED_MODULE_PATHS,
    compare_root_anchors,
    find_broken_links,
    find_safety_violations,
    main,
    markdown_anchors,
    repository_markdown_files,
    strip_fenced_code,
    validate_json_fixtures,
    validate_language_switch,
    validate_platform_pairs,
    validate_required_coverage,
    verify_repository,
    validate_command_contracts,
    validate_documented_paths,
    validate_environment_variables,
    validate_unfinished_placeholders,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_english_guide_has_complete_information_architecture() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    anchors = markdown_anchors(repo_root / "README.md")
    assert [anchor for anchor in anchors if anchor in ROOT_ANCHORS] == list(ROOT_ANCHORS)
    for path in REQUIRED_MODULE_PATHS:
        assert path in text
    for workflow in (
        "openmatb-research",
        "research-console",
        "suas-simulator",
        "sms-platform",
        "legacy-monitor",
    ):
        assert f"examples/{workflow}/README.md" in text


def test_root_guide_has_no_historical_pr_status() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"\bPR\s*#\d+|pull request\s*#\d+", text, re.IGNORECASE)


def test_openmatb_bash_wrapper_uses_selected_python(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    invocation_log = tmp_path / "openmatb-python.log"
    selected_python = _recording_python(tmp_path / "selected-python")
    output_directory = tmp_path / "output"
    env = os.environ.copy()
    env.update(MATB_PYTHON=str(selected_python), MATB_TEST_LOG=str(invocation_log))

    result = subprocess.run(
        ["bash", "examples/openmatb-research/run.sh", str(output_directory)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert invocation_log.is_file(), "run.sh ignored MATB_PYTHON"
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        f"examples/openmatb-research/run_example.py --output-dir {output_directory}"
    ]


def test_openmatb_powershell_wrapper_uses_selected_python() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "examples/openmatb-research/run.ps1").read_text(encoding="utf-8")
    assert "$env:MATB_PYTHON" in text
    assert re.search(r"&\s+\$Python\s+.*run_example\.py", text)


def test_suas_powershell_walkthrough_clears_lease_bearing_headers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "examples/suas-simulator/api_walkthrough.ps1").read_text(
        encoding="utf-8"
    )
    last_header_use = text.rindex("-Headers $headers")
    clear_headers = text.index("Clear-Variable headers")
    clear_lease = text.index("Clear-Variable controllerLeaseValue")
    assert last_header_use < clear_headers < clear_lease


def test_suas_cli_wrapper_uses_matb_venv_python(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    invocation_log = tmp_path / "suas-python.log"
    venv = tmp_path / "selected-venv"
    selected_python = _recording_python(venv / "bin" / "python")
    output_directory = tmp_path / "output"
    env = os.environ.copy()
    env.pop("MATB_PYTHON", None)
    env.update(MATB_VENV=str(venv), MATB_TEST_LOG=str(invocation_log))

    result = subprocess.run(
        ["bash", "examples/suas-simulator/cli_demo.sh", str(output_directory)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert invocation_log.is_file(), "cli_demo.sh ignored MATB_VENV"
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 4
    assert all(line.startswith("-m matb_integration.suas.cli ") for line in invocations)
    assert invocations[-1] == f"-m matb_integration.suas.cli verify {output_directory}"


def test_workflow_guides_select_installed_python_and_scope_legacy_verification() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    root_text = (repo_root / "README.md").read_text(encoding="utf-8")
    openmatb = root_text.split('<a id="quick-start-openmatb"></a>', 1)[1].split(
        '<a id="quick-start-research-console"></a>', 1
    )[0]
    legacy = root_text.split('<a id="quick-start-legacy-monitor"></a>', 1)[1].split(
        '<a id="module-catalog"></a>', 1
    )[0]

    assert "requirements-dev.txt" in openmatb
    assert "MATB_PYTHON" in openmatb
    assert 'pytest "$REPO_ROOT/tests"' not in legacy
    assert 'Join-Path $RepoRoot "tests"' not in legacy
    assert "tests/test_dashboard_behavior.py" in legacy
    assert "tests/test_research_protocol.py" in legacy

    for path in (
        repo_root / "examples/openmatb-research/README.md",
        repo_root / "examples/openmatb-research/README.es.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert "requirements-dev.txt" in text
        assert "MATB_PYTHON" in text

    for path in (
        repo_root / "examples/suas-simulator/README.md",
        repo_root / "examples/suas-simulator/README.es.md",
    ):
        assert "MATB_VENV" in path.read_text(encoding="utf-8").split(
            "CLI", 1
        )[-1]


def test_openmatb_example_runs_offline(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "examples/openmatb-research/run_example.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "scenarios").glob("*.txt"))) == 3
    records = [json.loads(line) for line in (tmp_path / "metrics.jsonl").read_text().splitlines()]
    assert [record["workload_level"] for record in records] == ["LOW", "MEDIUM", "HIGH"]
    assert json.loads((tmp_path / "suhir.json").read_text())["participant_id"] == "SYNTH-P01"


@pytest.mark.parametrize("package_name", ["energy", "fleet"])
def test_sms_package_build_configs_emit_compiled_entry_points(
    tmp_path: Path, package_name: str
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    typescript = repo_root / "SMS/node_modules/typescript/bin/tsc"
    if not typescript.is_file():
        pytest.skip("run `cd SMS && npm ci` before the SMS build smoke tests")
    output_directory = tmp_path / package_name
    result = subprocess.run(
        [
            "node",
            "node_modules/typescript/bin/tsc",
            "--project",
            f"packages/{package_name}/tsconfig.build.json",
            "--outDir",
            str(output_directory),
        ],
        cwd=repo_root / "SMS",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (output_directory / "index.js").is_file()


def test_sms_package_tour_is_deterministic() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    package_names = (
        "evidence",
        "energy",
        "fleet",
        "geo",
        "telemetry",
        "safety-kernel",
        "sms",
        "human-performance",
        "research",
    )
    missing = [
        str(path.relative_to(repo_root))
        for package_name in package_names
        if not (path := repo_root / f"SMS/packages/{package_name}/dist/index.js").is_file()
    ]
    if missing:
        pytest.skip(
            "run `cd SMS && npm ci && npm run build:packages` before the SMS package-tour smoke test; "
            f"missing compiled entry points: {missing}"
        )
    first = subprocess.run(
        ["node", "../examples/sms-platform/package-tour.mjs"],
        cwd=repo_root / "SMS",
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        ["node", "../examples/sms-platform/package-tour.mjs"],
        cwd=repo_root / "SMS",
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert set(result) == {
        "evidence",
        "energy",
        "fleet",
        "geo",
        "telemetry",
        "safetyKernel",
        "sms",
        "humanPerformance",
        "research",
    }
    assert result["safetyKernel"]["status"] == "blocked"
    assert result["research"]["nonDispatchable"] is True
    assert result["evidence"]["unsignedManifest"] == {
        "shapeStatus": "valid",
        "signatureStatus": "rejected",
    }
    assert result["fleet"]["crewQualificationStatus"] == "available"
    assert result["geo"]["airspaceStatus"] == "pass"
    assert result["geo"]["weatherStatus"] == "pass"
    assert result["research"]["replayedEventIds"] == ["MATB-SYNTH-1"]


def test_relative_links_resolve_and_code_fences_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text('<a id="ok"></a>\n# Target\n', encoding="utf-8")
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


def test_root_guides_are_structurally_mirrored(repo_root: Path) -> None:
    assert compare_root_anchors(repo_root / "README.md", repo_root / "README.es.md") == []


def test_each_workflow_has_a_spanish_guide(repo_root: Path) -> None:
    for workflow in (
        "openmatb-research",
        "research-console",
        "suas-simulator",
        "sms-platform",
        "legacy-monitor",
    ):
        directory = repo_root / "examples" / workflow
        assert (directory / "README.md").is_file()
        assert (directory / "README.es.md").is_file()


def _normalized_inline_code_tokens(path: Path) -> Counter[str]:
    text = strip_fenced_code(path.read_text(encoding="utf-8"))
    tokens = re.findall(r"(?<!`)`([^`]+)`(?!`)", text)
    return Counter(re.sub(r"\s+", " ", token.strip()) for token in tokens)


def test_bilingual_guides_preserve_inline_code_tokens(repo_root: Path) -> None:
    pairs = [(repo_root / "README.md", repo_root / "README.es.md")]
    pairs.append((repo_root / "examples/README.md", repo_root / "examples/README.es.md"))
    for workflow in (
        "openmatb-research",
        "research-console",
        "suas-simulator",
        "sms-platform",
        "legacy-monitor",
    ):
        directory = repo_root / "examples" / workflow
        pairs.append((directory / "README.md", directory / "README.es.md"))

    for english, spanish in pairs:
        english_tokens = _normalized_inline_code_tokens(english)
        spanish_tokens = _normalized_inline_code_tokens(spanish)
        assert spanish_tokens == english_tokens, (
            f"{spanish.relative_to(repo_root)} changes inline command/API tokens; "
            f"English-only={english_tokens - spanish_tokens}, "
            f"Spanish-only={spanish_tokens - english_tokens}"
        )


def test_spanish_workflow_guides_preserve_safety_meaning(repo_root: Path) -> None:
    sms = (repo_root / "examples/sms-platform/README.es.md").read_text(encoding="utf-8")
    openmatb = (repo_root / "examples/openmatb-research/README.es.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "paquetes geográficos sin conexión firmados",
        "decisiones de auditoría de solo anexado",
        "evidencia dura desconocida produce un bloqueo seguro",
        "exportaciones desidentificadas separadas de las operaciones",
        "ingesta de paquetes en modo seguro",
        "valida artefactos de fuente registrados localmente",
        "resultados esperados de bloqueo seguro",
        "formación/promoción de seguridad operacional",
        "operationalReady=false",
        "nonDispatchable",
    ):
        assert required in sms
    assert "sistema operacional desplegado" in openmatb
    assert "sistema operativo" not in openmatb


def test_committed_examples_reject_secrets_and_false_readiness(tmp_path: Path) -> None:
    bad = tmp_path / "example.json"
    bad.write_text('{"privateKey":"secret","operationalReady":true}', encoding="utf-8")
    errors = find_safety_violations([bad])
    assert any("private key" in error.lower() for error in errors)
    assert any("operationalReady" in error for error in errors)


def test_frontend_local_commands_are_checked_against_frontend_context(tmp_path: Path) -> None:
    (tmp_path / "SMS" / "apps" / "console").mkdir(parents=True)
    (tmp_path / "SMS" / "package.json").write_text(
        '{"scripts":{"build":"echo build"}}', encoding="utf-8"
    )
    (tmp_path / "SMS" / "apps" / "console" / "package.json").write_text(
        '{"scripts":{"dev":"vite"}}', encoding="utf-8"
    )
    docs = tmp_path / "README.md"
    docs.write_text("```bash\ncd SMS/apps/console\nnpm run dev\nnpm run typo\n```\n", encoding="utf-8")
    errors = validate_command_contracts(tmp_path)
    assert not any("unknown local package script: dev" in error for error in errors)
    assert any("unknown local package script: typo" in error for error in errors)


def test_sms_root_commands_are_checked_against_sms_context(tmp_path: Path) -> None:
    (tmp_path / "SMS").mkdir()
    (tmp_path / "SMS" / "package.json").write_text(
        '{"scripts":{"build":"echo build"}}', encoding="utf-8"
    )
    docs = tmp_path / "README.md"
    docs.write_text("cd SMS\nnpm run typo\n", encoding="utf-8")
    errors = validate_command_contracts(tmp_path)
    assert any("unknown SMS package script: typo" in error for error in errors)


def test_safety_rejects_credentials_tokens_and_lease_fields(tmp_path: Path) -> None:
    bad = tmp_path / "credentials.md"
    bad.write_text(
        "```json\n"
        '{"apiToken":"tok_live_123", "access_token":"abc", '
        '"controller_lease":"lease-secret"}\n'
        "```\n",
        encoding="utf-8",
    )
    errors = find_safety_violations([bad])
    assert any("credential" in error.lower() or "token" in error.lower() for error in errors)
    assert any("lease" in error.lower() for error in errors)


def test_safety_allows_runtime_credential_references_without_embedded_values(
    tmp_path: Path,
) -> None:
    shell = tmp_path / "walkthrough.sh"
    shell.write_text(
        'api_token="${MATB_API_TOKEN:?Set MATB_API_TOKEN}"\n'
        'MATB_API_TOKEN="$(<var/service/api-token)"\n',
        encoding="utf-8",
    )
    powershell = tmp_path / "walkthrough.ps1"
    powershell.write_text(
        '[string]$ApiToken = $env:MATB_API_TOKEN\n'
        '$env:MATB_API_TOKEN = Read-Host "MATB API token"\n',
        encoding="utf-8",
    )

    assert find_safety_violations([shell, powershell]) == []


def test_safety_rejects_signatures_and_pii_identity_fields(tmp_path: Path) -> None:
    bad = tmp_path / "identity.json"
    bad.write_text(
        '{"participantName":"Ada Example", "email":"ada@example.org", '
        '"institutionalSignature":"signed-by-reviewer"}',
        encoding="utf-8",
    )
    errors = find_safety_violations([bad])
    assert any("pii" in error.lower() or "identity" in error.lower() for error in errors)
    assert any("signature" in error.lower() for error in errors)


def test_safety_requires_unsigned_acceptance_and_false_readiness(tmp_path: Path) -> None:
    acceptance = tmp_path / "acceptance-review.json"
    acceptance.write_text('{"operationalReady": true}', encoding="utf-8")
    errors = find_safety_violations([acceptance])
    assert any("operationalready" in error.lower() for error in errors)
    assert any("false" in error.lower() or "acceptance" in error.lower() for error in errors)
    acceptance.write_text('{"operationalReady": false}', encoding="utf-8")
    assert find_safety_violations([acceptance]) == []


def test_safety_ignores_explanatory_markdown_prohibitions(tmp_path: Path) -> None:
    guide = tmp_path / "README.md"
    guide.write_text(
        "Never commit private keys, credentials, PII, signatures, or controller leases.\n",
        encoding="utf-8",
    )
    assert find_safety_violations([guide]) == []


def test_suas_walkthrough_keeps_lease_out_of_urls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("api_walkthrough.sh", "api_walkthrough.ps1"):
        text = (repo_root / "examples/suas-simulator" / name).read_text(encoding="utf-8")
        assert "X-Simulation-Controller" in text
        assert "?lease=" not in text
        assert "controller_lease" not in "\n".join(
            line for line in text.splitlines() if "echo" in line.lower() or "write-host" in line.lower()
        )


def test_http_walkthroughs_use_synthetic_identity() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    texts = [
        path.read_text(encoding="utf-8")
        for path in (repo_root / "examples/research-console").glob("api_walkthrough.*")
    ]
    assert texts and all("SYNTH-P01" in text for text in texts)


def test_research_console_walkthroughs_run_analysis_and_validate_returned_status() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bash = (repo_root / "examples/research-console/api_walkthrough.sh").read_text(
        encoding="utf-8"
    )
    powershell = (
        repo_root / "examples/research-console/api_walkthrough.ps1"
    ).read_text(encoding="utf-8")

    assert '"$base_url/analysis/run"' in bash
    assert "analysis_status" in bash
    assert "insufficient_data" in bash
    assert '"$BaseUrl/analysis/run"' in powershell
    assert "analysis_status" in powershell
    assert "insufficient_data" in powershell


def test_legacy_powershell_wrapper_propagates_native_python_failure() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "examples/legacy-monitor/run.ps1").read_text(encoding="utf-8")
    python_call = text.index("& python -m aircraft_monitor")
    after_python = text[python_call:]
    assert re.search(r"if\s*\(\$LASTEXITCODE\s*-ne\s*0\)", after_python)
    assert re.search(r"exit\s+\$LASTEXITCODE", after_python)


def test_console_and_suas_guides_require_powershell_7_for_walkthroughs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for guide in (
        repo_root / "examples/research-console/README.md",
        repo_root / "examples/research-console/README.es.md",
        repo_root / "examples/suas-simulator/README.md",
        repo_root / "examples/suas-simulator/README.es.md",
    ):
        assert "PowerShell 7+" in guide.read_text(encoding="utf-8")


def test_launcher_guides_distinguish_dependency_install_from_offline_service() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for guide in (
        repo_root / "examples/research-console/README.md",
        repo_root / "examples/research-console/README.es.md",
        repo_root / "examples/suas-simulator/README.md",
        repo_root / "examples/suas-simulator/README.es.md",
    ):
        text = guide.read_text(encoding="utf-8").lower()
        assert "network" in text or "red" in text
        assert "cache" in text or "caché" in text
        assert "offline-capable" in text or "sin conexión" in text


def test_safety_rejects_provider_prefixed_credential_and_token_fields(tmp_path: Path) -> None:
    bad = tmp_path / "provider-credentials.json"
    bad.write_text(
        '{"openai_api_key":"sk-live-123", "github_personal_access_token":"ghp_123", '
        '"stripe_secret_key":"whsec_123"}',
        encoding="utf-8",
    )
    errors = find_safety_violations([bad])
    assert any("credential" in error.lower() or "token" in error.lower() for error in errors)


def test_safety_rejects_generalized_signed_state_but_allows_unsigned_values(tmp_path: Path) -> None:
    for filename, payload in (
        ("is-signed.json", '{"isSigned": true}'),
        ("signed-yes.json", '{"signed": "yes"}'),
    ):
        bad = tmp_path / filename
        bad.write_text(payload, encoding="utf-8")
        errors = find_safety_violations([bad])
        assert any("unsigned" in error.lower() or "signed" in error.lower() for error in errors)

    safe = tmp_path / "unsigned.json"
    safe.write_text('{"isSigned": false, "signed": "no", "signature": null}', encoding="utf-8")
    assert find_safety_violations([safe]) == []


def test_verify_repository_checks_complete_contract_in_a_temporary_root(tmp_path: Path) -> None:
    _populate_contract_root(tmp_path)
    assert verify_repository(tmp_path) == []


def test_cli_reports_pass_for_a_complete_temporary_root(tmp_path: Path, monkeypatch, capsys) -> None:
    _populate_contract_root(tmp_path)
    monkeypatch.setattr(sys, "argv", ["verify_documentation.py", "--root", str(tmp_path)])
    assert main() == 0
    assert "PASS documentation verification" in capsys.readouterr().out


def test_complete_anchor_contract_is_required(tmp_path: Path) -> None:
    en = tmp_path / "README.md"
    es = tmp_path / "README.es.md"
    complete = "\n".join(f'<a id="{anchor}"></a>' for anchor in ROOT_ANCHORS)
    en.write_text(complete, encoding="utf-8")
    es.write_text(complete, encoding="utf-8")
    assert compare_root_anchors(en, es) == []
    es.write_text("\n".join(f'<a id="{anchor}"></a>' for anchor in reversed(ROOT_ANCHORS)), encoding="utf-8")
    assert compare_root_anchors(en, es)


def test_required_module_coverage_reports_missing_path_and_guide_reference(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    (tmp_path / "README.es.md").write_text("", encoding="utf-8")
    errors = validate_required_coverage(tmp_path)
    assert any(REQUIRED_MODULE_PATHS[0] in error for error in errors)
    assert any("missing module coverage" in error for error in errors)


def test_platform_pairs_and_malformed_json_are_reported(tmp_path: Path) -> None:
    examples = tmp_path / "examples" / "openmatb-research"
    examples.mkdir(parents=True)
    (examples / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    errors = validate_platform_pairs(tmp_path)
    assert any("Bash or PowerShell" in error for error in errors)
    fixture = examples / "bad.json"
    fixture.write_text("{not json}", encoding="utf-8")
    json_errors = validate_json_fixtures(tmp_path)
    assert any("invalid JSON" in error for error in json_errors)


def test_all_project_markdown_links_are_checked_but_generated_trees_are_excluded(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("[broken](missing.md)\n", encoding="utf-8")
    for directory in (".git", ".worktrees", ".superpowers", "node_modules", "dist"):
        generated = tmp_path / directory
        generated.mkdir()
        (generated / "generated.md").write_text("[ignored](missing.md)\n", encoding="utf-8")
    files = repository_markdown_files(tmp_path)
    assert docs / "guide.md" in files
    assert all(directory not in path.parts for path in files for directory in (".git", "node_modules", "dist"))
    errors = find_broken_links(tmp_path, files)
    assert any("docs/guide.md" in error and "missing.md" in error for error in errors)
    assert all("generated.md" not in error for error in errors)
    _populate_contract_root(tmp_path)
    (tmp_path / "docs" / "guide.md").write_text("[broken](missing.md)\n", encoding="utf-8")
    repository_errors = verify_repository(tmp_path)
    assert any("docs/guide.md" in error and "missing.md" in error for error in repository_errors)


def test_language_switch_requires_reciprocal_visible_links(tmp_path: Path) -> None:
    en = tmp_path / "README.md"
    es = tmp_path / "README.es.md"
    en.write_text("[Español](README.es.md)\n", encoding="utf-8")
    es.write_text("## Español\n", encoding="utf-8")
    errors = validate_language_switch(en, es)
    assert any("README.es.md" in error and "language switch" in error for error in errors)


def test_documented_pytest_paths_and_supported_modules_must_resolve(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "```bash\npython -m pytest tests/missing -q\n"
        "python -m matb_integration.missing\n```\n",
        encoding="utf-8",
    )
    errors = validate_documented_paths(tmp_path)
    assert any("tests/missing" in error and "pytest path" in error for error in errors)
    assert any("matb_integration.missing" in error and "module entry point" in error for error in errors)


def test_unfinished_placeholders_are_rejected_only_in_current_user_docs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Setup remains TODO before release.\n", encoding="utf-8")
    plan = tmp_path / "docs" / "superpowers" / "plans"
    plan.mkdir(parents=True)
    (plan / "old-plan.md").write_text("TODO is allowed in historical plans.\n", encoding="utf-8")
    errors = validate_unfinished_placeholders(tmp_path)
    assert any("README.md" in error and "TODO" in error for error in errors)
    assert all("old-plan.md" not in error for error in errors)


def test_documented_project_environment_variables_require_checked_in_support(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "Set `MATB_SUPPORTED` or `MATB_GHOST_SETTING`.\n", encoding="utf-8"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run.sh").write_text(
        'value="${MATB_SUPPORTED:-safe}"\n', encoding="utf-8"
    )
    errors = validate_environment_variables(tmp_path)
    assert not any("MATB_SUPPORTED" in error for error in errors)
    assert any("MATB_GHOST_SETTING" in error for error in errors)


def _recording_python(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${MATB_TEST_LOG:?}\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _populate_contract_root(root: Path) -> None:
    anchors = "\n".join(f'<a id="{anchor}"></a>' for anchor in ROOT_ANCHORS)
    switch = "[Español](README.es.md)\n"
    coverage = "\n".join(REQUIRED_MODULE_PATHS)
    (root / "README.md").write_text(switch + anchors + "\n" + coverage, encoding="utf-8")
    (root / "README.es.md").write_text("[English](README.md)\n" + anchors + "\n" + coverage, encoding="utf-8")
    for module_path in REQUIRED_MODULE_PATHS:
        target = root / module_path.rstrip("/")
        if module_path.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
    (root / "SMS").mkdir(exist_ok=True)
    (root / "SMS" / "package.json").write_text('{"scripts": {"build": "echo build"}}', encoding="utf-8")
    for directory in ("openmatb-research", "research-console", "sms-platform", "legacy-monitor"):
        example = root / "examples" / directory
        example.mkdir(parents=True, exist_ok=True)
        (example / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (example / "run.ps1").write_text("Write-Output ok\n", encoding="utf-8")
