"""Streamlit UI for editing config.ini with provenance guidance.

The UI exposes the user and OpenMATB sections, validates inputs, and
persists modifications while preserving the existing inline comments.
"""

from __future__ import annotations

from collections import defaultdict
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import streamlit as st

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONFIG_PATH: Final[Path] = PROJECT_ROOT / "config.ini"
SCENARIO_DIR: Final[Path] = PROJECT_ROOT / "includes" / "scenarios"
LOCALE_DIR: Final[Path] = PROJECT_ROOT / "locales"
MANUAL_REF: Final[str] = "Docs/Manual.md"

GUIDE_SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "Participant provenance (Manual §11.7)",
        "Record a numeric participant id plus the optional descriptive fields."
        " These fields propagate to the UI banner, per-user history, and every"
        " session export so longitudinal analyses remain traceable.",
    ),
    (
        "Scenario reproducibility (Manual §11.5)",
        "Scenario paths should reference files under includes/scenarios/. Each"
        " session snapshot stores scenario/script copies and hashes, so keeping"
        " these paths accurate is critical for audit trails.",
    ),
    (
        "Difficulty documentation (Manual §11.1)",
        "Scenario selections drive the workload ladder. Use the provided list to"
        " match the desired event-rate band, or enter a manual path for custom"
        " studies while noting the difficulty level in your scenario metadata.",
    ),
)

COMPUTATION_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("language", "Locale resources for prompts, warnings, and instructions."),
    ("screen_index", "Determines which monitor renders MATB to keep capture setups deterministic."),
    ("fullscreen", "Enables consistent viewport size for workload scoring."),
    ("clock_speed", "Scales the master timeline; leave at 1.0 for valid KPI computation."),
    ("scenario_path", "Points to the scenario script that defines workload and event timing."),
    ("display_session_number", "Ensures provenance across exported summaries."),
)


@dataclass(frozen=True, slots=True)
class OpenMatbSettings:
    """Settings stored under the [Openmatb] section of config.ini."""

    language: str
    screen_index: int
    font_name: str
    fullscreen: bool
    clock_speed: float
    scenario_path: str
    display_session_number: bool
    hide_on_pause: bool
    highlight_aoi: bool
    top_bounds: tuple[float, float]
    bottom_bounds: tuple[float, float]


@dataclass(frozen=True, slots=True)
class UserSettings:
    """Settings stored under the [User] section of config.ini."""

    participant_id: str
    name: str
    cohort: str
    notes: str


@dataclass(frozen=True, slots=True)
class ConfigValues:
    """Aggregated configuration sections."""

    openmatb: OpenMatbSettings
    user: UserSettings


def read_config(config_path: Path) -> tuple[str, ConfigValues]:
    """Return the raw config text and parsed values."""

    raw_text = config_path.read_text(encoding="utf-8")
    parser = ConfigParser()
    parser.read_string(raw_text)
    openmatb_section = parser["Openmatb"]
    user_section = parser["User"]
    values = ConfigValues(
        openmatb=OpenMatbSettings(
            language=openmatb_section.get("language", fallback="en_EN"),
            screen_index=openmatb_section.getint("screen_index", fallback=0),
            font_name=openmatb_section.get("font_name", fallback=""),
            fullscreen=openmatb_section.getboolean("fullscreen", fallback=True),
            clock_speed=openmatb_section.getfloat("clock_speed", fallback=1.0),
            scenario_path=openmatb_section.get("scenario_path", fallback="default.txt"),
            display_session_number=openmatb_section.getboolean(
                "display_session_number", fallback=True
            ),
            hide_on_pause=openmatb_section.getboolean("hide_on_pause", fallback=False),
            highlight_aoi=openmatb_section.getboolean("highlight_aoi", fallback=False),
            top_bounds=parse_bounds(openmatb_section.get("top_bounds", "[0.35, 0.85]")),
            bottom_bounds=parse_bounds(
                openmatb_section.get("bottom_bounds", "[0.30, 0.85]")
            ),
        ),
        user=UserSettings(
            participant_id=user_section.get("id", fallback="0000"),
            name=user_section.get("name", fallback=""),
            cohort=user_section.get("cohort", fallback=""),
            notes=user_section.get("notes", fallback=""),
        ),
    )
    return raw_text, values


def parse_bounds(bounds_value: str) -> tuple[float, float]:
    """Parse a `[low, high]` bounds string."""

    cleaned = bounds_value.strip()
    if not cleaned.startswith("[") or not cleaned.endswith("]"):
        raise ValueError(f"Bounds must be wrapped in [], got {bounds_value!r}")
    body = cleaned[1:-1]
    parts = [part.strip() for part in body.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Bounds must contain two numbers, got {bounds_value!r}")
    lower, upper = (float(part) for part in parts)
    if not 0.0 <= lower <= 1.0 or not 0.0 <= upper <= 1.0:
        raise ValueError(f"Bounds must be between 0 and 1, got {bounds_value!r}")
    if lower >= upper:
        raise ValueError(f"Lower bound must be < upper bound, got {bounds_value!r}")
    return lower, upper


def format_bounds(bounds: tuple[float, float]) -> str:
    """Format a bounds tuple back into the `[low, high]` string form."""

    return f"[{_format_float(bounds[0])}, {_format_float(bounds[1])}]"


def _format_float(value: float) -> str:
    """Format a float without trailing zeros."""

    as_str = f"{value:.4f}"
    trimmed = as_str.rstrip("0").rstrip(".")
    return trimmed or "0"


def discover_locales() -> list[str]:
    """Return available locale identifiers based on locales/ subfolders."""

    locales: list[str] = []
    if LOCALE_DIR.exists():
        for entry in LOCALE_DIR.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                locales.append(entry.name)
    if not locales:
        locales.append("en_EN")
    return sorted(locales)


def discover_scenarios() -> list[str]:
    """Return scenario paths relative to includes/scenarios/."""

    if not SCENARIO_DIR.exists():
        return ["default.txt"]
    paths = [
        str(path.relative_to(SCENARIO_DIR).as_posix())
        for path in sorted(SCENARIO_DIR.rglob("*.txt"))
    ]
    return paths or ["default.txt"]


def update_config_text(
    original_text: str, new_values: dict[str, dict[str, str]]
) -> str:
    """Return a config string with updated key/value pairs."""

    if not new_values:
        return original_text

    lines = original_text.splitlines()
    section_headers: list[tuple[str, int]] = []
    current_section: str | None = None
    seen = defaultdict(set)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            section_headers.append((current_section, idx))
            continue
        if (
            current_section is None
            or current_section not in new_values
            or "=" not in line
            or stripped.startswith("#")
            or stripped.startswith(";")
        ):
            continue
        key, _ = line.split("=", maxsplit=1)
        normalized_key = key.strip()
        if normalized_key in new_values[current_section]:
            new_value = new_values[current_section][normalized_key]
            prefix = line.split("=", maxsplit=1)[0]
            indent = prefix[: len(prefix) - len(prefix.lstrip())]
            lines[idx] = f"{indent}{normalized_key}={new_value}"
            seen[current_section].add(normalized_key)

    section_headers.append(("__END__", len(lines)))
    for idx, (section, _start) in enumerate(section_headers[:-1]):
        if section not in new_values:
            continue
        missing_keys = [
            key for key in new_values[section] if key not in seen.get(section, set())
        ]
        if not missing_keys:
            continue
        next_idx = section_headers[idx + 1][1]
        insert_position = next_idx
        additions = [f"{key}={new_values[section][key]}" for key in missing_keys]
        lines[insert_position:insert_position] = additions

    result = "\n".join(lines)
    if not result.endswith("\n"):
        result = f"{result}\n"
    return result


def persist_config(config_path: Path, new_text: str, previous_text: str) -> None:
    """Back up the old config.ini and write the new one safely."""

    backup_path = config_path.with_suffix(".ini.bak")
    backup_path.write_text(previous_text, encoding="utf-8")
    config_path.write_text(new_text, encoding="utf-8")


def validate_user_id(participant_id: str) -> str:
    """Ensure participant id is numeric."""

    candidate = participant_id.strip()
    if not candidate.isdigit():
        raise ValueError("Participant id must contain digits only.")
    return candidate.zfill(4)


def validate_clock_speed(clock_speed: float) -> float:
    """Ensure the MATB clock multiplier stays within a safe range."""

    if clock_speed <= 0.0:
        raise ValueError("Clock speed must be greater than zero.")
    if clock_speed > 4.0:
        raise ValueError("Clock speed above 4.0 is unsupported for MATB timing.")
    return round(clock_speed, 4)


def main() -> None:
    """Entry point for the Streamlit application."""

    st.set_page_config(
        page_title="OpenMATB Config Studio",
        page_icon="🛠️",
        layout="wide",
    )
    config_text, values = read_config(CONFIG_PATH)
    locale_options = discover_locales()
    scenario_options = discover_scenarios()

    st.sidebar.title("Config Programming Guide")
    st.sidebar.caption(f"Source: {MANUAL_REF}")
    for title, body in GUIDE_SECTIONS:
        with st.sidebar.expander(title, expanded=False):
            st.write(body)
    st.sidebar.subheader("Required MATB fields")
    for name, description in COMPUTATION_FIELDS:
        st.sidebar.write(f"- **{name}** – {description}")

    st.header("OpenMATB Configuration")
    st.caption(
        "Fill the form below to update `config.ini`. The tool preserves inline comments"
        " and writes a backup as `config.ini.bak` before saving."
    )

    with st.form("config_form"):
        openmatb_col, user_col = st.columns(2)
        with openmatb_col:
            st.subheader("[Openmatb]")
            language = st.selectbox(
                "Locale",
                options=locale_options,
                index=locale_options.index(values.openmatb.language)
                if values.openmatb.language in locale_options
                else 0,
                help="Locales available under locales/. Manual §11.7 requires user banner parity.",
            )
            screen_index = int(
                st.number_input(
                    "Screen index",
                    min_value=0,
                    max_value=8,
                    value=values.openmatb.screen_index,
                    step=1,
                    help="Primary monitor index (0 = default).",
                )
            )
            font_name = st.text_input(
                "Font override",
                value=values.openmatb.font_name,
                help="Optional font family name; leave blank for OS default.",
            )
            fullscreen = st.checkbox(
                "Fullscreen",
                value=values.openmatb.fullscreen,
                help="Toggle fullscreen startup behavior.",
            )
            clock_speed = st.number_input(
                "Clock speed multiplier",
                min_value=0.1,
                max_value=4.0,
                value=float(values.openmatb.clock_speed),
                step=0.1,
                help="Manual §11 requires nominal timing (1.0). Adjust only for deterministic replays.",
            )
            scenario_choice = st.selectbox(
                "Scenario (discoverable)",
                options=["Manual entry"] + scenario_options,
                index=(
                    1 + scenario_options.index(values.openmatb.scenario_path)
                    if values.openmatb.scenario_path in scenario_options
                    else 0
                ),
                help="Pick from includes/scenarios/ or select Manual entry.",
            )
            scenario_path = st.text_input(
                "Scenario path",
                value=values.openmatb.scenario_path
                if scenario_choice == "Manual entry"
                else scenario_choice,
                help="Relative to includes/scenarios/. Manual §11.5 stresses provenance.",
            )
            display_session_number = st.checkbox(
                "Display session number",
                value=values.openmatb.display_session_number,
                help="Overlays the rolling session count at start.",
            )
            hide_on_pause = st.checkbox(
                "Hide environment on pause",
                value=values.openmatb.hide_on_pause,
                help="When enabled, Pause hides all widgets (privacy requirement).",
            )
            highlight_aoi = st.checkbox(
                "Highlight AOI frames",
                value=values.openmatb.highlight_aoi,
                help="Debug overlay that draws red frames for each widget.",
            )
            top_bounds = st.slider(
                "Top bounds (fractional)",
                min_value=0.0,
                max_value=1.0,
                value=values.openmatb.top_bounds,
                step=0.01,
            )
            bottom_bounds = st.slider(
                "Bottom bounds (fractional)",
                min_value=0.0,
                max_value=1.0,
                value=values.openmatb.bottom_bounds,
                step=0.01,
            )

        with user_col:
            st.subheader("[User]")
            participant_id_raw = st.text_input(
                "Participant id",
                value=values.user.participant_id,
                help="Numeric identifier recorded in session exports (Manual §11.7).",
                max_chars=8,
            )
            name = st.text_input(
                "Name",
                value=values.user.name,
                help="Optional descriptive label mirrored in summary exports.",
                max_chars=64,
            )
            cohort = st.text_input(
                "Cohort",
                value=values.user.cohort,
                help="Use to tag experimental groups or conditions.",
                max_chars=64,
            )
            notes = st.text_area(
                "Notes",
                value=values.user.notes,
                help="Free-form notes stored in config snapshots and session summaries.",
                max_chars=512,
                height=150,
            )

        submit = st.form_submit_button("Save config.ini")

    scenario_file = (SCENARIO_DIR / scenario_path).resolve()
    if not scenario_file.exists():
        st.warning(
            f"Scenario path `{scenario_path}` does not exist under includes/scenarios/."
            " The simulator will error at startup until this path is valid."
        )

    if submit:
        try:
            participant_id = validate_user_id(participant_id_raw)
            safe_clock_speed = validate_clock_speed(clock_speed)
            openmatb_settings = OpenMatbSettings(
                language=language,
                screen_index=screen_index,
                font_name=font_name,
                fullscreen=fullscreen,
                clock_speed=safe_clock_speed,
                scenario_path=scenario_path,
                display_session_number=display_session_number,
                hide_on_pause=hide_on_pause,
                highlight_aoi=highlight_aoi,
                top_bounds=(float(top_bounds[0]), float(top_bounds[1])),
                bottom_bounds=(float(bottom_bounds[0]), float(bottom_bounds[1])),
            )
            user_settings = UserSettings(
                participant_id=participant_id,
                name=name.strip(),
                cohort=cohort.strip(),
                notes=notes.strip(),
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            updated_text = update_config_text(
                config_text,
                {
                    "Openmatb": to_string_dict(openmatb_settings),
                    "User": to_string_dict(user_settings),
                },
            )
            if updated_text == config_text:
                st.info("No changes detected; config.ini left untouched.")
            else:
                persist_config(CONFIG_PATH, updated_text, config_text)
                st.success("config.ini updated and backup saved.")
                st.rerun()

    with st.expander("Current config.ini preview", expanded=False):
        st.code(config_text, language="ini")


def to_string_dict(section: OpenMatbSettings | UserSettings) -> dict[str, str]:
    """Convert a dataclass section into the config.ini string representation."""

    if isinstance(section, OpenMatbSettings):
        return {
            "language": section.language,
            "screen_index": str(section.screen_index),
            "font_name": section.font_name,
            "fullscreen": str(section.fullscreen),
            "clock_speed": _format_float(section.clock_speed),
            "scenario_path": section.scenario_path,
            "display_session_number": str(section.display_session_number),
            "hide_on_pause": str(section.hide_on_pause),
            "highlight_aoi": str(section.highlight_aoi),
            "top_bounds": format_bounds(section.top_bounds),
            "bottom_bounds": format_bounds(section.bottom_bounds),
        }
    return {
        "id": section.participant_id,
        "name": section.name,
        "cohort": section.cohort,
        "notes": section.notes,
    }


if __name__ == "__main__":
    main()

