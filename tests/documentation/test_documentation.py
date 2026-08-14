from pathlib import Path
import sys

from scripts.verify_documentation import (
    ROOT_ANCHORS,
    REQUIRED_MODULE_PATHS,
    compare_root_anchors,
    find_broken_links,
    find_safety_violations,
    main,
    repository_markdown_files,
    validate_json_fixtures,
    validate_language_switch,
    validate_platform_pairs,
    validate_required_coverage,
    verify_repository,
    validate_command_contracts,
)


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
