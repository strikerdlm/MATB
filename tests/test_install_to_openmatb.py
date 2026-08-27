from __future__ import annotations

from pathlib import Path

from install_to_openmatb import install


def test_installer_adds_concurrent_workload_plugin_required_by_scenarios(tmp_path: Path) -> None:
    external = tmp_path / "openmatb"
    (external / "includes").mkdir(parents=True)
    (external / "plugins").mkdir()
    (external / "plugins" / "__init__.py").write_text(
        "from .abstractplugin import AbstractPlugin\n",
        encoding="utf-8",
    )

    install(external)

    assert (external / "plugins" / "instantaneousworkload.py").is_file()
    init_text = (external / "plugins" / "__init__.py").read_text(encoding="utf-8")
    assert "from .instantaneousworkload import Instantaneousworkload" in init_text
    assert "instantaneousworkload;start" in (
        external / "includes" / "scenarios" / "military_aviation" / "low_workload.txt"
    ).read_text(encoding="utf-8")
    assert (
        external
        / "includes"
        / "scenarios"
        / "military_aviation"
        / "low_workload.txt.manifest.json"
    ).is_file()
