from pathlib import Path

from scripts.verify_documentation import (
    compare_root_anchors,
    find_broken_links,
    find_safety_violations,
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
    (tmp_path / "SMS").mkdir()
    (tmp_path / "SMS" / "package.json").write_text(
        '{"scripts":{"build":"echo build"}}', encoding="utf-8"
    )
    docs = tmp_path / "README.md"
    docs.write_text("cd SMS/apps/console\nnpm run dev\n", encoding="utf-8")
    assert validate_command_contracts(tmp_path) == []


def test_sms_root_commands_are_checked_against_sms_context(tmp_path: Path) -> None:
    (tmp_path / "SMS").mkdir()
    (tmp_path / "SMS" / "package.json").write_text(
        '{"scripts":{"build":"echo build"}}', encoding="utf-8"
    )
    docs = tmp_path / "README.md"
    docs.write_text("cd SMS\nnpm run typo\n", encoding="utf-8")
    errors = validate_command_contracts(tmp_path)
    assert any("unknown SMS package script: typo" in error for error in errors)
