from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATHS = (REPO_ROOT / "README.md", REPO_ROOT / "README.es.md")


def _readme_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative_links(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text)]


def _assert_relative_links_exist(text: str) -> None:
    for target in _relative_links(text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith("#"):
            continue
        relative_target = unquote(parsed.path)
        assert relative_target, f"empty README link target: {target}"
        assert (REPO_ROOT / relative_target).exists(), f"README link does not exist: {target}"


def test_bilingual_readmes_exist_and_switch_languages() -> None:
    english, spanish = README_PATHS
    assert english.exists()
    assert spanish.exists()

    english_text = _readme_text(english)
    spanish_text = _readme_text(spanish)
    assert "README.es.md" in english_text
    assert "README.md" in spanish_text


def test_each_readme_covers_all_repository_workflows() -> None:
    required_paths = (
        "matb_integration/",
        "openmatb/",
        "webui/",
        "SMS/",
        "aircraft_monitor/",
        "scripts/install_suas.sh",
        "scripts/run_suas.sh",
    )
    for path in README_PATHS:
        text = _readme_text(path)
        for required_path in required_paths:
            assert required_path in text, f"{path.name} omits {required_path}"


def test_each_readme_has_researcher_guide_and_safety_sections() -> None:
    required_markers = {
        "README.md": (
            "Quick start",
            "Capabilities",
            "Research potential",
            "Safety",
            "Troubleshooting",
            "Repository map",
        ),
        "README.es.md": (
            "Inicio rápido",
            "Capacidades",
            "Potencial de investigación",
            "Seguridad",
            "Solución de problemas",
            "Mapa del repositorio",
        ),
    }
    for path in README_PATHS:
        text = _readme_text(path)
        for marker in required_markers[path.name]:
            assert marker.lower() in text.lower(), f"{path.name} omits section: {marker}"


def test_readmes_have_balanced_code_fences_and_valid_relative_links() -> None:
    for path in README_PATHS:
        text = _readme_text(path)
        assert text.count("```") % 2 == 0, f"unbalanced code fence in {path.name}"
        _assert_relative_links_exist(text)


def test_readmes_do_not_repeat_known_stale_runtime_claims() -> None:
    stale_claims = (
        "broken vendored openmatb submodule",
        "task runner is no longer vendored",
        "the task runner is not vendored",
    )
    for path in README_PATHS:
        text = _readme_text(path).lower()
        for claim in stale_claims:
            assert claim not in text, f"stale runtime claim in {path.name}: {claim}"
