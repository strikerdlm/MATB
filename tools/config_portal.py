"""Streamlit UI for editing config.ini and plugin parameters.

The UI exposes:
1. [Openmatb] and [User] sections from config.ini
2. All plugin parameters from parameters.csv with type-aware widgets
3. Sidebar guidance based on Docs/Manual.md

Run with: streamlit run tools/config_portal.py
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from configparser import ConfigParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import streamlit as st

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONFIG_PATH: Final[Path] = PROJECT_ROOT / "config.ini"
PARAMS_CSV_PATH: Final[Path] = PROJECT_ROOT / "parameters.csv"
SCENARIO_DIR: Final[Path] = PROJECT_ROOT / "includes" / "scenarios"
LOCALE_DIR: Final[Path] = PROJECT_ROOT / "locales"
PLUGINS_DIR: Final[Path] = PROJECT_ROOT / "plugins"
INSTRUCTIONS_DIR: Final[Path] = PROJECT_ROOT / "includes" / "instructions"
QUESTIONNAIRES_DIR: Final[Path] = PROJECT_ROOT / "includes" / "questionnaires"
MANUAL_REF: Final[str] = "Docs/Manual.md"

COLORS: Final[tuple[str, ...]] = (
    "white",
    "black",
    "green",
    "red",
    "background",
    "lightgrey",
    "grey",
    "blue",
)

TASK_PLACEMENTS: Final[tuple[str, ...]] = (
    "topleft",
    "topmid",
    "topright",
    "bottomleft",
    "bottommid",
    "bottomright",
    "fullscreen",
    "invisible",
)

GUIDE_SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "Participant provenance (Manual §11.7)",
        "Record a numeric participant id plus optional descriptive fields. "
        "These propagate to the UI banner, per-user history, and every session export.",
    ),
    (
        "Scenario reproducibility (Manual §11.5)",
        "Scenario paths should reference files under includes/scenarios/. Each "
        "session snapshot stores scenario copies and hashes for audit trails.",
    ),
    (
        "Difficulty documentation (Manual §11.1)",
        "Scenario selections drive the workload ladder. Difficulty 1-3 = 0.5× baseline, "
        "4-6 = 1.0× baseline, 7-10 = 1.5-2.0× baseline. See Manual for NASA-TLX targets.",
    ),
    (
        "HRV Integration (Manual §17-18)",
        "Enable polarrlink and physiomonitor plugins for real-time HRV monitoring. "
        "Requires Polar H10 chest strap. Baseline calibration is 5 minutes minimum.",
    ),
    (
        "Plugin Parameters",
        "Each plugin exposes configurable parameters via scenario commands. "
        "Use this portal to understand defaults and valid ranges before writing scenarios.",
    ),
)

COMPUTATION_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("language", "Locale resources for prompts, warnings, and instructions."),
    ("screen_index", "Monitor index for MATB rendering (0 = primary)."),
    ("fullscreen", "Enables consistent viewport size for workload scoring."),
    ("clock_speed", "Scales the master timeline; leave at 1.0 for valid KPI computation."),
    ("scenario_path", "Points to the scenario script defining workload and event timing."),
    ("display_session_number", "Ensures provenance across exported summaries."),
)

# Plugin categories for organized display
PLUGIN_CATEGORIES: Final[dict[str, tuple[str, ...]]] = {
    "Core MATB Tasks": ("sysmon", "track", "scheduling", "communications", "resman"),
    "Instructions & Scales": ("instructions", "genericscales", "performance"),
    "Lab Streaming & Triggers": ("labstreaminglayer", "parallelport", "generictrigger"),
    "HRV & Physiology": ("polarrlink", "physiomonitor", "physiooverlay"),
    "Fighter/HPA Modules": (
        "energymanager",
        "threatboard",
        "weaponsinventory",
        "emergencystack",
        "hmdoverlay",
    ),
    "UAS Modules": (
        "missiondirector",
        "senseandavoid",
        "payloadmanager",
        "operatorcapacity",
        "platformprofile",
        "vtolmanager",
        "vtolpower",
        "launchrecovery",
    ),
    "BVLOS / UTM / MUM-T": (
        "bvlossensory",
        "controltransfer",
        "flighttermination",
        "utmintegration",
        "mumtcoordination",
        "dataoverload",
    ),
    "Advanced Features": (
        "datalink",
        "swarmformation",
        "sensorresource",
        "targetuncertainty",
        "weatheroverlay",
        "dualtasksensor",
        "advancedtraining",
        "autotraining",
        "automationhooks",
        "compositescore",
        "failureinjector",
        "audioalerts",
        "eyetracker",
    ),
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PluginParameter:
    """A single parameter definition from parameters.csv."""

    plugin_alias: str
    variable: str
    description: str
    possible_values: str
    default: str

    @property
    def param_type(self) -> str:
        """Infer the parameter type from possible_values."""
        pv = self.possible_values.lower()
        if "(boolean)" in pv:
            return "boolean"
        if "(positive integer)" in pv or "(integer)" in pv or "(natural integer)" in pv:
            return "integer"
        if "(positive float)" in pv or "(float)" in pv:
            return "float"
        if "(unit_interval" in pv:
            return "unit_interval"
        if "(string)" in pv:
            return "string"
        if "(regular expression)" in pv:
            return "regex"
        if "(keyboard key)" in pv:
            return "key"
        if "(list of string)" in pv or "(list of" in pv:
            return "list"
        if "`on` or `off`" in pv:
            return "on_off"
        if "`on` or `off` or `failure`" in pv:
            return "pump_state"
        if "topleft" in pv and "fullscreen" in pv:
            return "placement"
        if "white" in pv and "black" in pv and "green" in pv:
            return "color"
        if "`own` or `other`" in pv:
            return "own_other"
        if "`english` or `french`" in pv:
            return "voice_idiom"
        if "`male` or `female`" in pv:
            return "voice_gender"
        if "-1, 0, 1" in pv:
            return "side"
        return "string"


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


@dataclass(slots=True)
class ConfigValues:
    """Aggregated configuration sections."""

    openmatb: OpenMatbSettings
    user: UserSettings
    plugin_params: dict[str, list[PluginParameter]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing Functions
# ---------------------------------------------------------------------------
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


def load_parameters_csv(csv_path: Path) -> dict[str, list[PluginParameter]]:
    """Load parameters.csv and return a dict keyed by plugin alias."""
    params: dict[str, list[PluginParameter]] = defaultdict(list)
    if not csv_path.exists():
        return dict(params)

    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = row.get("Plugin alias", "").strip()
            variable = row.get("Variable", "").strip()
            description = row.get("Description", "").strip()
            possible_values = row.get("Possible values", "").strip()
            default = row.get("Default", "").strip()

            if not alias or not variable:
                continue

            # Handle (anytaskalias) as a special shared category
            if alias == "(anytaskalias)":
                alias = "_shared"

            params[alias].append(
                PluginParameter(
                    plugin_alias=alias,
                    variable=variable,
                    description=description,
                    possible_values=possible_values,
                    default=default,
                )
            )

    return dict(params)


def read_config(config_path: Path) -> tuple[str, OpenMatbSettings, UserSettings]:
    """Return the raw config text and parsed values."""
    raw_text = config_path.read_text(encoding="utf-8")
    parser = ConfigParser()
    parser.read_string(raw_text)

    openmatb_section = parser["Openmatb"] if "Openmatb" in parser else {}
    user_section = parser["User"] if "User" in parser else {}

    openmatb = OpenMatbSettings(
        language=openmatb_section.get("language", "en_EN"),
        screen_index=int(openmatb_section.get("screen_index", "0")),
        font_name=openmatb_section.get("font_name", ""),
        fullscreen=openmatb_section.get("fullscreen", "True").lower() == "true",
        clock_speed=float(openmatb_section.get("clock_speed", "1.0")),
        scenario_path=openmatb_section.get("scenario_path", "default.txt"),
        display_session_number=openmatb_section.get("display_session_number", "True").lower()
        == "true",
        hide_on_pause=openmatb_section.get("hide_on_pause", "False").lower() == "true",
        highlight_aoi=openmatb_section.get("highlight_aoi", "False").lower() == "true",
        top_bounds=parse_bounds(openmatb_section.get("top_bounds", "[0.35, 0.85]")),
        bottom_bounds=parse_bounds(openmatb_section.get("bottom_bounds", "[0.30, 0.85]")),
    )

    user = UserSettings(
        participant_id=user_section.get("id", "0000"),
        name=user_section.get("name", ""),
        cohort=user_section.get("cohort", ""),
        notes=user_section.get("notes", ""),
    )

    return raw_text, openmatb, user


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


def discover_plugins() -> list[str]:
    """Return list of available plugin names from the plugins directory."""
    plugins: list[str] = []
    if PLUGINS_DIR.exists():
        for entry in PLUGINS_DIR.iterdir():
            if (
                entry.is_file()
                and entry.suffix == ".py"
                and not entry.name.startswith("_")
                and entry.name != "abstractplugin.py"
                and not entry.name.endswith("_model.py")
                and not entry.name.endswith("_data.py")
            ):
                plugins.append(entry.stem)
    return sorted(plugins)


def discover_instruction_files() -> list[str]:
    """Return available instruction files."""
    files: list[str] = []
    if INSTRUCTIONS_DIR.exists():
        for entry in INSTRUCTIONS_DIR.rglob("*.txt"):
            files.append(str(entry.relative_to(INSTRUCTIONS_DIR).as_posix()))
    return sorted(files) or ["(empty)"]


def discover_questionnaire_files() -> list[str]:
    """Return available questionnaire files."""
    files: list[str] = []
    if QUESTIONNAIRES_DIR.exists():
        for entry in QUESTIONNAIRES_DIR.rglob("*.txt"):
            files.append(str(entry.relative_to(QUESTIONNAIRES_DIR).as_posix()))
    return sorted(files) or ["(empty)"]


# ---------------------------------------------------------------------------
# Config File Writing
# ---------------------------------------------------------------------------
def update_config_text(original_text: str, new_values: dict[str, dict[str, str]]) -> str:
    """Return a config string with updated key/value pairs."""
    if not new_values:
        return original_text

    lines = original_text.splitlines()
    section_headers: list[tuple[str, int]] = []
    current_section: str | None = None
    seen: dict[str, set[str]] = defaultdict(set)

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
        missing_keys = [key for key in new_values[section] if key not in seen.get(section, set())]
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


# ---------------------------------------------------------------------------
# Widget Rendering for Plugin Parameters
# ---------------------------------------------------------------------------
def render_param_widget(
    param: PluginParameter, key_prefix: str, parent_plugin: str = ""
) -> str | None:
    """Render a Streamlit widget for a plugin parameter and return the value as string."""
    # Use parent_plugin to disambiguate shared params rendered in multiple plugin sections
    scope = parent_plugin if parent_plugin else param.plugin_alias
    widget_key = f"{key_prefix}_{scope}_{param.variable}"
    label = f"**{param.variable}**"
    help_text = param.description

    ptype = param.param_type
    default = param.default

    # Handle (empty) default
    if default == "(empty)":
        default = ""

    try:
        if ptype == "boolean":
            default_bool = default.lower() in ("true", "1", "yes") if default else False
            val = st.checkbox(label, value=default_bool, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "integer":
            default_int = int(default) if default and default.isdigit() else 0
            val = st.number_input(
                label,
                value=default_int,
                step=1,
                help=help_text,
                key=widget_key,
            )
            return str(int(val))

        elif ptype == "float":
            default_float = float(default) if default else 0.0
            val = st.number_input(
                label,
                value=default_float,
                step=0.1,
                format="%.2f",
                help=help_text,
                key=widget_key,
            )
            return _format_float(val)

        elif ptype == "unit_interval":
            default_float = float(default) if default else 0.5
            val = st.slider(
                label,
                min_value=0.0,
                max_value=1.0,
                value=default_float,
                step=0.01,
                help=help_text,
                key=widget_key,
            )
            return _format_float(val)

        elif ptype == "color":
            options = list(COLORS)
            idx = options.index(default) if default in options else 0
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "placement":
            options = list(TASK_PLACEMENTS)
            idx = options.index(default) if default in options else 0
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "on_off":
            options = ["on", "off"]
            idx = options.index(default) if default in options else 1
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "pump_state":
            options = ["on", "off", "failure"]
            idx = options.index(default) if default in options else 1
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "voice_idiom":
            options = ["english", "french"]
            idx = options.index(default) if default in options else 0
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "voice_gender":
            options = ["male", "female"]
            idx = options.index(default) if default in options else 1
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "own_other":
            options = ["", "own", "other"]
            idx = options.index(default) if default in options else 0
            val = st.selectbox(label, options=options, index=idx, help=help_text, key=widget_key)
            return str(val)

        elif ptype == "side":
            options = ["-1", "0", "1"]
            idx = options.index(str(default)) if str(default) in options else 1
            val = st.selectbox(
                label,
                options=options,
                index=idx,
                help=f"{help_text} (-1=down, 0=random, 1=up)",
                key=widget_key,
            )
            return str(val)

        elif ptype == "key":
            val = st.text_input(
                label,
                value=default,
                help=f"{help_text} (e.g., F1, space, NUM_1)",
                key=widget_key,
            )
            return str(val)

        elif ptype == "regex":
            val = st.text_input(
                label,
                value=default,
                help=f"{help_text} (regular expression pattern)",
                key=widget_key,
            )
            return str(val)

        elif ptype == "list":
            val = st.text_input(
                label,
                value=default,
                help=f"{help_text} (comma-separated list)",
                key=widget_key,
            )
            return str(val)

        else:  # string or unknown
            val = st.text_input(label, value=default, help=help_text, key=widget_key)
            return str(val)

    except (ValueError, TypeError):
        # Fallback to text input
        val = st.text_input(label, value=default, help=help_text, key=widget_key)
        return str(val)


def render_plugin_section(
    plugin_alias: str,
    params: list[PluginParameter],
    shared_params: list[PluginParameter] | None = None,
) -> None:
    """Render all parameters for a plugin in an expander."""
    with st.expander(f"📦 {plugin_alias}", expanded=False):
        st.caption(f"Parameters for the `{plugin_alias}` plugin")

        if not params and not shared_params:
            st.info("No configurable parameters documented for this plugin.")
            return

        # Group parameters by category (using variable prefix)
        grouped: dict[str, list[PluginParameter]] = defaultdict(list)
        for p in params:
            # Extract group from variable name (e.g., lights-1-name -> lights)
            parts = p.variable.split("-")
            group = parts[0] if len(parts) > 1 else "general"
            grouped[group].append(p)

        # Render grouped parameters
        for group_name, group_params in sorted(grouped.items()):
            if len(grouped) > 1 and len(group_params) > 1:
                st.markdown(f"**{group_name.title()}**")

            cols = st.columns(2)
            for idx, p in enumerate(group_params):
                with cols[idx % 2]:
                    render_param_widget(p, "plugin", plugin_alias)

        # Show shared parameters if applicable
        if shared_params:
            st.markdown("---")
            st.markdown("**Shared Task Feedback Parameters**")
            cols = st.columns(2)
            for idx, p in enumerate(shared_params):
                with cols[idx % 2]:
                    render_param_widget(p, "shared", plugin_alias)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point for the Streamlit application."""
    st.set_page_config(
        page_title="OpenMATB Config Studio",
        page_icon="🛩️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for better appearance
    st.markdown(
        """
        <style>
        .stExpander {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Load data
    config_text, openmatb, user = read_config(CONFIG_PATH)
    plugin_params = load_parameters_csv(PARAMS_CSV_PATH)
    locale_options = discover_locales()
    scenario_options = discover_scenarios()
    available_plugins = discover_plugins()

    # Sidebar - Guide
    st.sidebar.title("📖 Config Programming Guide")
    st.sidebar.caption(f"Reference: {MANUAL_REF}")

    for title, body in GUIDE_SECTIONS:
        with st.sidebar.expander(title, expanded=False):
            st.write(body)

    st.sidebar.markdown("---")
    st.sidebar.subheader("Required MATB Fields")
    for name, description in COMPUTATION_FIELDS:
        st.sidebar.markdown(f"- **{name}**: {description}")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Available Plugins")
    st.sidebar.caption(f"{len(available_plugins)} plugins installed")
    with st.sidebar.expander("View all plugins", expanded=False):
        for plugin in available_plugins:
            has_params = plugin in plugin_params
            icon = "✅" if has_params else "⚪"
            st.write(f"{icon} {plugin}")

    # Main content
    st.title("🛩️ OpenMATB Configuration Studio")
    st.markdown(
        "Configure all aspects of OpenMATB: core settings, user identification, and plugin parameters. "
        "Changes are saved to `config.ini` with automatic backup."
    )

    # Tabs for different sections
    tab_core, tab_plugins, tab_preview, tab_scenario = st.tabs(
        ["⚙️ Core Settings", "🔌 Plugin Parameters", "📄 Config Preview", "📋 Scenario Helper"]
    )

    # ---------------------------------------------------------------------------
    # Tab 1: Core Settings (config.ini)
    # ---------------------------------------------------------------------------
    with tab_core:
        st.header("Core Configuration")

        with st.form("config_form"):
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🖥️ OpenMATB Settings")

                language = st.selectbox(
                    "Language / Locale",
                    options=locale_options,
                    index=locale_options.index(openmatb.language)
                    if openmatb.language in locale_options
                    else 0,
                    help="Locales available under locales/. Affects UI text and prompts.",
                )

                screen_index = int(
                    st.number_input(
                        "Screen Index",
                        min_value=0,
                        max_value=8,
                        value=openmatb.screen_index,
                        step=1,
                        help="Monitor index (0 = primary display).",
                    )
                )

                font_name = st.text_input(
                    "Font Override",
                    value=openmatb.font_name,
                    help="Optional font family name; leave blank for OS default.",
                )

                fullscreen = st.checkbox(
                    "Fullscreen Mode",
                    value=openmatb.fullscreen,
                    help="Run MATB in fullscreen for consistent viewport.",
                )

                clock_speed = st.number_input(
                    "Clock Speed Multiplier",
                    min_value=0.1,
                    max_value=4.0,
                    value=float(openmatb.clock_speed),
                    step=0.1,
                    help="⚠️ Keep at 1.0 for valid KPI computation. Adjust only for debug/replay.",
                )

                if clock_speed != 1.0:
                    st.warning("Clock speed ≠ 1.0 will invalidate workload metrics!")

                scenario_choice = st.selectbox(
                    "Scenario File",
                    options=["Manual entry"] + scenario_options,
                    index=(
                        1 + scenario_options.index(openmatb.scenario_path)
                        if openmatb.scenario_path in scenario_options
                        else 0
                    ),
                    help="Select from includes/scenarios/ or enter manually.",
                )

                scenario_path = st.text_input(
                    "Scenario Path",
                    value=openmatb.scenario_path
                    if scenario_choice == "Manual entry"
                    else scenario_choice,
                    help="Path relative to includes/scenarios/.",
                )

                display_session_number = st.checkbox(
                    "Display Session Number",
                    value=openmatb.display_session_number,
                    help="Show session ID at startup for provenance.",
                )

                hide_on_pause = st.checkbox(
                    "Hide on Pause",
                    value=openmatb.hide_on_pause,
                    help="Hide MATB display when paused (privacy mode).",
                )

                highlight_aoi = st.checkbox(
                    "Highlight AOI Frames",
                    value=openmatb.highlight_aoi,
                    help="Debug: draw red frames around widget areas.",
                )

                st.markdown("**Layout Bounds**")
                top_bounds = st.slider(
                    "Top Bounds (fractional)",
                    min_value=0.0,
                    max_value=1.0,
                    value=openmatb.top_bounds,
                    step=0.01,
                    help="Vertical bounds for top plugin row.",
                )

                bottom_bounds = st.slider(
                    "Bottom Bounds (fractional)",
                    min_value=0.0,
                    max_value=1.0,
                    value=openmatb.bottom_bounds,
                    step=0.01,
                    help="Vertical bounds for bottom plugin row.",
                )

            with col2:
                st.subheader("👤 User / Participant Settings")

                participant_id_raw = st.text_input(
                    "Participant ID",
                    value=user.participant_id,
                    help="Numeric identifier for session exports (Manual §11.7).",
                    max_chars=8,
                )

                name = st.text_input(
                    "Name",
                    value=user.name,
                    help="Optional label for the participant.",
                    max_chars=64,
                )

                cohort = st.text_input(
                    "Cohort / Group",
                    value=user.cohort,
                    help="Experimental group or condition tag.",
                    max_chars=64,
                )

                notes = st.text_area(
                    "Notes",
                    value=user.notes,
                    help="Free-form notes stored in session summaries.",
                    max_chars=512,
                    height=150,
                )

                st.markdown("---")
                st.subheader("📁 Session Output")
                st.info(
                    f"Sessions will be saved to:\n\n"
                    f"`sessions/user_{participant_id_raw.zfill(4) if participant_id_raw.isdigit() else '0000'}/`"
                )

            submit = st.form_submit_button("💾 Save config.ini", use_container_width=True)

        # Validate scenario path
        scenario_file = (SCENARIO_DIR / scenario_path).resolve()
        if not scenario_file.exists():
            st.error(
                f"⚠️ Scenario `{scenario_path}` not found in includes/scenarios/. "
                "The simulator will error at startup."
            )

        # Handle form submission
        if submit:
            try:
                participant_id = validate_user_id(participant_id_raw)
                safe_clock_speed = validate_clock_speed(clock_speed)

                new_openmatb = OpenMatbSettings(
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

                new_user = UserSettings(
                    participant_id=participant_id,
                    name=name.strip(),
                    cohort=cohort.strip(),
                    notes=notes.strip(),
                )

                updated_text = update_config_text(
                    config_text,
                    {
                        "Openmatb": {
                            "language": new_openmatb.language,
                            "screen_index": str(new_openmatb.screen_index),
                            "font_name": new_openmatb.font_name,
                            "fullscreen": str(new_openmatb.fullscreen),
                            "clock_speed": _format_float(new_openmatb.clock_speed),
                            "scenario_path": new_openmatb.scenario_path,
                            "display_session_number": str(new_openmatb.display_session_number),
                            "hide_on_pause": str(new_openmatb.hide_on_pause),
                            "highlight_aoi": str(new_openmatb.highlight_aoi),
                            "top_bounds": format_bounds(new_openmatb.top_bounds),
                            "bottom_bounds": format_bounds(new_openmatb.bottom_bounds),
                        },
                        "User": {
                            "id": new_user.participant_id,
                            "name": new_user.name,
                            "cohort": new_user.cohort,
                            "notes": new_user.notes,
                        },
                    },
                )

                if updated_text == config_text:
                    st.info("No changes detected; config.ini left untouched.")
                else:
                    persist_config(CONFIG_PATH, updated_text, config_text)
                    st.success("✅ config.ini updated! Backup saved as config.ini.bak")
                    st.rerun()

            except ValueError as exc:
                st.error(f"Validation error: {exc}")

    # ---------------------------------------------------------------------------
    # Tab 2: Plugin Parameters
    # ---------------------------------------------------------------------------
    with tab_plugins:
        st.header("Plugin Parameters Reference")
        st.markdown(
            "Browse and understand all configurable parameters for each plugin. "
            "These parameters are set via scenario commands, not config.ini."
        )

        # Get shared parameters
        shared_params = plugin_params.get("_shared", [])

        # Organize by category
        for category, plugins in PLUGIN_CATEGORIES.items():
            st.subheader(f"📂 {category}")

            # Filter to plugins that exist
            existing_plugins = [p for p in plugins if p in available_plugins or p in plugin_params]

            if not existing_plugins:
                st.caption("No plugins in this category are installed.")
                continue

            for plugin_alias in existing_plugins:
                params = plugin_params.get(plugin_alias, [])
                # Only show shared params for core MATB tasks
                show_shared = plugin_alias in ("sysmon", "track", "communications", "resman")
                render_plugin_section(
                    plugin_alias,
                    params,
                    shared_params if show_shared else None,
                )

        # Show any plugins not in categories
        categorized = set()
        for plugins in PLUGIN_CATEGORIES.values():
            categorized.update(plugins)

        uncategorized = [p for p in plugin_params if p not in categorized and p != "_shared"]
        if uncategorized:
            st.subheader("📂 Other Plugins")
            for plugin_alias in sorted(uncategorized):
                params = plugin_params.get(plugin_alias, [])
                render_plugin_section(plugin_alias, params)

    # ---------------------------------------------------------------------------
    # Tab 3: Config Preview
    # ---------------------------------------------------------------------------
    with tab_preview:
        st.header("Current config.ini")
        st.code(config_text, language="ini")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reload from disk"):
                st.rerun()
        with col2:
            st.download_button(
                "📥 Download config.ini",
                data=config_text,
                file_name="config.ini",
                mime="text/plain",
            )

    # ---------------------------------------------------------------------------
    # Tab 4: Scenario Helper
    # ---------------------------------------------------------------------------
    with tab_scenario:
        st.header("Scenario Command Helper")
        st.markdown(
            "Generate scenario commands for plugin parameters. "
            "Copy and paste these into your scenario files."
        )

        selected_plugin = st.selectbox(
            "Select Plugin",
            options=sorted(plugin_params.keys()),
            format_func=lambda x: x if x != "_shared" else "(shared task parameters)",
        )

        if selected_plugin and selected_plugin in plugin_params:
            params = plugin_params[selected_plugin]

            st.markdown(f"### Commands for `{selected_plugin}`")

            for param in params:
                default_display = param.default if param.default != "(empty)" else '""'
                command = f"0:00:00;{selected_plugin};{param.variable};{default_display}"

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.code(command, language="text")
                with col2:
                    st.caption(param.description[:50] + "..." if len(param.description) > 50 else param.description)

            st.markdown("---")
            st.markdown("### Example: Start and configure plugin")
            st.code(
                f"# Start {selected_plugin}\n"
                f"0:00:00;{selected_plugin};start\n"
                f"\n"
                f"# Configure parameters\n"
                + "\n".join(
                    f"0:00:00;{selected_plugin};{p.variable};{p.default if p.default != '(empty)' else ''}"
                    for p in params[:5]
                )
                + f"\n\n# Stop {selected_plugin}\n"
                f"0:05:00;{selected_plugin};stop",
                language="text",
            )


if __name__ == "__main__":
    main()
