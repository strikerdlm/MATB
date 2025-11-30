"""Streamlit UI for editing config.ini, plugin parameters, and scenarios.

The UI exposes:
1. [Openmatb] and [User] sections from config.ini
2. All plugin parameters from parameters.csv with type-aware widgets
3. Scenario Designer for creating/editing/validating scenario files
4. Launch control for running OpenMATB scenarios
5. Sidebar guidance based on Docs/Manual.md
6. Voice Generator for ATC-style communications using OpenAI TTS

Run with: streamlit run tools/config_portal.py
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from collections import defaultdict
from configparser import ConfigParser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

import streamlit as st

# Import voice generator (optional - may not be available if openai not installed)
try:
    from tools.voice_generator import (
        ATCVoiceGenerator,
        VoiceConfig,
        AVAILABLE_VOICES,
        VOICE_DESCRIPTIONS,
        VOICE_PRESETS,
        AUDIO_FORMATS,
        load_api_key,
        generate_matb_voice_files,
        render_voice_generator_tab,
    )
    VOICE_GENERATOR_AVAILABLE = True
except ImportError:
    VOICE_GENERATOR_AVAILABLE = False

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
SPANISH_INSTRUCTIONS_DIR: Final[Path] = PROJECT_ROOT / "includes" / "instructions" / "spanish"
QUESTIONNAIRES_DIR: Final[Path] = PROJECT_ROOT / "includes" / "questionnaires"
MANUAL_REF: Final[str] = "Docs/Manual.md"

# Scenario to instructions mapping by language
# Spanish instructions
SCENARIO_INSTRUCTIONS_ES: Final[dict[str, list[str]]] = {
    # UAS Scenarios
    "uas_basic.txt": [
        "spanish/uas/uas_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/uas/uas_basic_intro.txt",
    ],
    "uas_bvlos.txt": [
        "spanish/uas/uas_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/uas/uas_bvlos_intro.txt",
    ],
    "uas_military_ex.txt": [
        "spanish/uas/uas_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/mumt/operatorcapacity.txt",
        "spanish/mumt/vtolmanager.txt",
        "spanish/uas/uas_military_intro.txt",
    ],
    # HPA Scenarios
    "hpa_overlay.txt": [
        "spanish/hpa/hpa_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/hpa/emergencystack.txt",
        "spanish/uas/datalink.txt",
        "spanish/hpa/hpa_overlay_intro.txt",
    ],
    "hpa_qra_ex.txt": [
        "spanish/hpa/hpa_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/hpa/weaponsinventory.txt",
        "spanish/hpa/emergencystack.txt",
        "spanish/uas/datalink.txt",
        "spanish/hpa/hpa_qra_intro.txt",
    ],
    # MUM-T Scenarios
    "mumt_ramp_lvl1.txt": [
        "spanish/mumt/mumt_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/hpa/weaponsinventory.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/mumt/operatorcapacity.txt",
        "spanish/mumt/vtolmanager.txt",
        "spanish/mumt/mumt_lvl1_intro.txt",
    ],
    "mumt_ramp_lvl2.txt": [
        "spanish/mumt/mumt_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/hpa/weaponsinventory.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/mumt/operatorcapacity.txt",
        "spanish/mumt/vtolmanager.txt",
        "spanish/mumt/mumt_lvl2_intro.txt",
    ],
    "mumt_ramp_lvl3.txt": [
        "spanish/mumt/mumt_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/hpa/weaponsinventory.txt",
        "spanish/uas/missiondirector.txt",
        "spanish/uas/senseandavoid.txt",
        "spanish/uas/payloadmanager.txt",
        "spanish/uas/datalink.txt",
        "spanish/mumt/operatorcapacity.txt",
        "spanish/mumt/vtolmanager.txt",
        "spanish/mumt/physiomonitor.txt",
        "spanish/mumt/mumt_lvl3_intro.txt",
    ],
    # Default/Basic Scenarios
    "default.txt": [
        "spanish/default/bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/default/completo.txt",
    ],
    "basic.txt": [
        "spanish/default/bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/default/completo.txt",
    ],
    "hrv_combat_demo.txt": [
        "spanish/mumt/mumt_bienvenida.txt",
        "spanish/default/sysmon.txt",
        "spanish/default/track.txt",
        "spanish/default/communications.txt",
        "spanish/default/resman.txt",
        "spanish/hpa/energymanager.txt",
        "spanish/hpa/threatboard.txt",
        "spanish/mumt/physiomonitor.txt",
        "spanish/default/completo.txt",
    ],
}

# English instructions (using default/ folder)
SCENARIO_INSTRUCTIONS_EN: Final[dict[str, list[str]]] = {
    # Default/Basic Scenarios - English
    "default.txt": [
        "default/welcome_screen.txt",
        "default/sysmon.txt",
        "default/track.txt",
        "default/communications.txt",
        "default/resman.txt",
        "default/full.txt",
    ],
    "basic.txt": [
        "default/welcome_screen.txt",
        "default/sysmon.txt",
        "default/track.txt",
        "default/communications.txt",
        "default/resman.txt",
        "default/full.txt",
    ],
}

# Combined mapping for backwards compatibility
SCENARIO_INSTRUCTIONS: Final[dict[str, list[str]]] = SCENARIO_INSTRUCTIONS_ES

# Generated audio cache directory
GENERATED_AUDIO_DIR: Final[Path] = PROJECT_ROOT / "includes" / "sounds" / "generated" / "instructions"

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

# Scenario templates for quick generation
SCENARIO_TEMPLATES: Final[dict[str, dict[str, str | int | list[str]]]] = {
    "Basic MATB (5 min)": {
        "description": "Core MATB tasks only - sysmon, track, resman, communications",
        "duration": 300,
        "difficulty": 5,
        "plugins": ["sysmon", "track", "resman", "communications", "scheduling"],
    },
    "UAS Basic (5 min)": {
        "description": "UAS operator scenario with mission director, sense & avoid, payloads",
        "duration": 300,
        "difficulty": 5,
        "plugins": ["sysmon", "track", "resman", "communications", "missiondirector",
                    "senseandavoid", "payloadmanager", "datalink", "physiomonitor"],
    },
    "Fighter HPA (3 min)": {
        "description": "Fighter pilot scenario with energy management, threats, weapons",
        "duration": 180,
        "difficulty": 6,
        "plugins": ["sysmon", "track", "resman", "communications", "energymanager",
                    "threatboard", "weaponsinventory", "datalink", "physiomonitor"],
    },
    "HRV Combat (10 min)": {
        "description": "Full combat scenario with HRV baseline, progressive workload phases",
        "duration": 600,
        "difficulty": 7,
        "plugins": ["polarrlink", "physiomonitor", "sysmon", "track", "resman",
                    "communications", "energymanager", "threatboard", "weaponsinventory",
                    "missiondirector", "senseandavoid", "datalink", "emergencystack",
                    "compositescore", "automationhooks"],
    },
    "MUM-T Coordination (7 min)": {
        "description": "Manned-Unmanned Teaming with fighter + dual-UAV coordination",
        "duration": 420,
        "difficulty": 4,
        "plugins": ["sysmon", "track", "resman", "communications", "physiomonitor",
                    "missiondirector", "senseandavoid", "payloadmanager", "datalink",
                    "operatorcapacity", "platformprofile", "energymanager", "threatboard",
                    "weaponsinventory", "vtolmanager", "launchrecovery", "mumtcoordination"],
    },
    "BVLOS Training (5 min)": {
        "description": "Beyond Visual Line of Sight with control transfer and UTM",
        "duration": 300,
        "difficulty": 5,
        "plugins": ["sysmon", "track", "resman", "communications", "missiondirector",
                    "senseandavoid", "payloadmanager", "datalink", "bvlossensory",
                    "controltransfer", "utmintegration", "physiomonitor"],
    },
    "Baseline Calibration (5 min)": {
        "description": "Low-workload baseline for HRV calibration before assessment",
        "duration": 300,
        "difficulty": 2,
        "plugins": ["polarrlink", "physiomonitor", "sysmon", "track", "resman",
                    "communications"],
    },
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
        # Check pump_state BEFORE on_off since "`on` or `off`" is a substring of
        # "`on` or `off` or `failure`" - checking on_off first would misclassify pumps
        if "`on` or `off` or `failure`" in pv:
            return "pump_state"
        if "`on` or `off`" in pv:
            return "on_off"
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
    """Settings stored under the [Openmatb] section of config.ini.

    The fields here are intentionally limited to configuration values that
    influence timing, layout, or visual accessibility; workload metrics
    remain defined entirely by scenarios and plugin logic.
    """

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
    ui_scale: float
    colorblind_mode: bool


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
        ui_scale=float(openmatb_section.get("ui_scale", "1.0")),
        colorblind_mode=openmatb_section.get("colorblind_mode", "False").lower() == "true",
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


def load_instruction_content(instruction_path: str) -> str:
    """Load instruction file content from the instructions directory."""
    full_path = INSTRUCTIONS_DIR / instruction_path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8")
    return f"<p><em>Archivo no encontrado: {instruction_path}</em></p>"


def get_instructions_for_scenario(scenario_name: str, language: str = "es") -> list[str]:
    """Get the list of instruction files for a given scenario and language.
    
    Args:
        scenario_name: Name of the scenario file
        language: Language code ('es' for Spanish, 'en' for English)
        
    Returns:
        List of instruction file paths relative to INSTRUCTIONS_DIR
    """
    # Extract just the filename from the path
    scenario_file = Path(scenario_name).name
    
    # Select appropriate mapping based on language
    if language == "en":
        instructions_map = SCENARIO_INSTRUCTIONS_EN
        default_instructions = [
            "default/welcome_screen.txt",
            "default/sysmon.txt",
            "default/track.txt",
            "default/communications.txt",
            "default/resman.txt",
            "default/full.txt",
        ]
    else:  # Default to Spanish
        instructions_map = SCENARIO_INSTRUCTIONS_ES
        default_instructions = [
            "spanish/default/bienvenida.txt",
            "spanish/default/sysmon.txt",
            "spanish/default/track.txt",
            "spanish/default/communications.txt",
            "spanish/default/resman.txt",
            "spanish/default/completo.txt",
        ]
    
    # Check if we have specific instructions for this scenario
    if scenario_file in instructions_map:
        return instructions_map[scenario_file]
    
    # For English, if no specific mapping, fall back to Spanish with a note
    # (Spanish instructions are more complete)
    if language == "en" and scenario_file in SCENARIO_INSTRUCTIONS_ES:
        # Return Spanish instructions as fallback (better than nothing)
        return SCENARIO_INSTRUCTIONS_ES[scenario_file]
    
    # Default fallback
    return default_instructions


def get_cached_audio_path(scenario_name: str, language: str, voice_preset: str) -> Path:
    """Get the path for cached audio file.
    
    Args:
        scenario_name: Name of the scenario
        language: Language code ('es' or 'en')
        voice_preset: Voice preset name
        
    Returns:
        Path to the cached audio file
    """
    GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    scenario_base = Path(scenario_name).stem
    filename = f"{scenario_base}_{language}_{voice_preset}.mp3"
    return GENERATED_AUDIO_DIR / filename


def check_cached_audio(scenario_name: str, language: str, voice_preset: str) -> Path | None:
    """Check if cached audio exists for the given parameters.
    
    Args:
        scenario_name: Name of the scenario
        language: Language code ('es' or 'en')
        voice_preset: Voice preset name
        
    Returns:
        Path to cached audio if exists, None otherwise
    """
    cache_path = get_cached_audio_path(scenario_name, language, voice_preset)
    if cache_path.exists():
        return cache_path
    return None


def render_spanish_instructions(scenario_path: str) -> None:
    """Render all Spanish instructions for a scenario."""
    instruction_files = get_instructions_for_scenario(scenario_path)
    
    st.markdown("### 📖 Instrucciones del Escenario en Español")
    st.markdown(f"**Escenario seleccionado:** `{scenario_path}`")
    st.markdown("---")
    
    # Progress tracking
    total_pages = len(instruction_files)
    
    # Initialize page state and track scenario changes
    if "instruction_page" not in st.session_state:
        st.session_state["instruction_page"] = 0
    if "instruction_scenario_last" not in st.session_state:
        st.session_state["instruction_scenario_last"] = ""
    
    # Reset page to 0 when scenario changes
    if st.session_state["instruction_scenario_last"] != scenario_path:
        st.session_state["instruction_page"] = 0
        st.session_state["instruction_scenario_last"] = scenario_path
    
    # Clamp current page to valid bounds (safety check)
    current_page = st.session_state["instruction_page"]
    if current_page >= total_pages:
        current_page = max(0, total_pages - 1)
        st.session_state["instruction_page"] = current_page
    
    # Navigation
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("⬅️ Anterior", disabled=current_page == 0):
            st.session_state["instruction_page"] = max(0, current_page - 1)
            st.rerun()
    with col2:
        st.progress((current_page + 1) / total_pages)
        st.caption(f"Página {current_page + 1} de {total_pages}")
    with col3:
        if st.button("Siguiente ➡️", disabled=current_page >= total_pages - 1):
            st.session_state["instruction_page"] = min(total_pages - 1, current_page + 1)
            st.rerun()
    
    st.markdown("---")
    
    # Display current instruction page
    if current_page < len(instruction_files):
        instruction_file = instruction_files[current_page]
        content = load_instruction_content(instruction_file)
        
        # Render HTML content
        st.markdown(content, unsafe_allow_html=True)
        
        # Show file info
        with st.expander("ℹ️ Información del archivo"):
            st.caption(f"Archivo: `{instruction_file}`")
    
    st.markdown("---")
    
    # Quick navigation
    st.markdown("### 📑 Navegación Rápida")
    cols = st.columns(4)
    for idx, instr_file in enumerate(instruction_files):
        col_idx = idx % 4
        with cols[col_idx]:
            # Extract a short name from the file path
            short_name = Path(instr_file).stem.replace("_", " ").title()
            is_current = idx == current_page
            if st.button(
                f"{'→ ' if is_current else ''}{short_name}",
                key=f"nav_{idx}",
                use_container_width=True,
            ):
                st.session_state["instruction_page"] = idx
                st.rerun()
    
    # Reset button
    st.markdown("---")
    if st.button("🔄 Reiniciar a la primera página"):
        st.session_state["instruction_page"] = 0
        st.rerun()


def render_all_instructions_printable(scenario_path: str) -> str:
    """Generate a printable version of all instructions."""
    instruction_files = get_instructions_for_scenario(scenario_path)
    
    all_content = []
    all_content.append(f"<h1>Instrucciones: {scenario_path}</h1>")
    all_content.append("<hr>")
    
    for idx, instr_file in enumerate(instruction_files, 1):
        content = load_instruction_content(instr_file)
        all_content.append(f"<h2>Sección {idx}</h2>")
        all_content.append(content)
        all_content.append("<hr>")
    
    return "\n".join(all_content)


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
# Scenario Designer Functions
# ---------------------------------------------------------------------------
def format_timestamp(seconds: int) -> str:
    """Convert seconds to H:MM:SS format."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:02d}"


def parse_timestamp(ts: str) -> int:
    """Parse H:MM:SS or M:SS to seconds."""
    parts = ts.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0])


def validate_scenario(content: str, available_plugins: list[str]) -> list[str]:
    """Validate scenario content and return list of errors."""
    errors: list[str] = []
    lines = content.strip().split("\n")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(";")
        if len(parts) < 3:
            errors.append(f"Line {line_num}: Invalid format - need at least timestamp;plugin;command")
            continue

        # Validate timestamp
        ts = parts[0]
        if not re.match(r"^\d+:\d{2}:\d{2}$", ts):
            errors.append(f"Line {line_num}: Invalid timestamp format '{ts}' - use H:MM:SS")

        # Validate plugin
        plugin = parts[1].lower()
        if plugin not in available_plugins and plugin not in ("instructions", "genericscales"):
            errors.append(f"Line {line_num}: Unknown plugin '{plugin}'")

    return errors


def generate_scenario_from_template(
    template_name: str,
    duration_override: int | None = None,
    difficulty_override: int | None = None,
) -> str:
    """Generate a scenario file from a template."""
    template = SCENARIO_TEMPLATES.get(template_name)
    if not template:
        return ""

    duration = duration_override or int(template["duration"])
    difficulty = difficulty_override or int(template["difficulty"])
    plugins = list(template["plugins"])
    description = str(template["description"])

    lines: list[str] = []

    # Header
    lines.append(f"# {template_name}")
    lines.append(f"# {description}")
    lines.append(f"# Duration: {duration}s | Difficulty: {difficulty}/10")
    lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Determine phases based on difficulty
    event_interval = max(15, 60 - (difficulty * 5))  # Higher difficulty = more frequent events
    automation_level = max(0.0, 1.0 - (difficulty * 0.1))  # Higher difficulty = less automation

    # Phase 1: Startup
    lines.append("# ============================================")
    lines.append("# PHASE 1: STARTUP")
    lines.append("# ============================================")
    lines.append("")

    # Start core MATB tasks
    core_plugins = ["sysmon", "track", "resman", "communications"]
    for plugin in core_plugins:
        if plugin in plugins:
            lines.append(f"0:00:00;{plugin};start")

    # Start advanced plugins with slight delay
    advanced_start = 2
    for plugin in plugins:
        if plugin not in core_plugins:
            lines.append(f"0:00:{advanced_start:02d};{plugin};start")
            advanced_start += 1

    lines.append("")

    # Phase 2: Low workload / Baseline
    if "physiomonitor" in plugins:
        lines.append("# ============================================")
        lines.append("# PHASE 2: BASELINE CALIBRATION")
        lines.append("# ============================================")
        lines.append("")
        lines.append("0:00:10;physiomonitor;baseline;start")
        baseline_end = min(120, duration // 5)
        lines.append(f"{format_timestamp(baseline_end)};physiomonitor;baseline;stop")
        lines.append("")

    # Phase 3: Main workload
    lines.append("# ============================================")
    lines.append("# PHASE 3: MAIN WORKLOAD")
    lines.append("# ============================================")
    lines.append("")

    # Generate events based on plugins
    current_time = 30 if "physiomonitor" not in plugins else 130
    stop_time = duration - 10

    while current_time < stop_time:
        # Add events based on available plugins
        if "missiondirector" in plugins and current_time % (event_interval * 2) == 0:
            uav_id = f"UAV{(current_time // 60) % 3 + 1}"
            missions = ["Surveillance", "Strike", "Relay", "CSAR", "Patrol"]
            mission = missions[(current_time // event_interval) % len(missions)]
            lines.append(f"{format_timestamp(current_time)};missiondirector;assign;{uav_id},{mission},{event_interval * 3}")

        if "senseandavoid" in plugins and (current_time + 15) % (event_interval * 3) == 0:
            intr_id = f"INTR{(current_time // 60) % 5 + 1}"
            bearing = ((current_time * 17) % 360)
            lines.append(f"{format_timestamp(current_time)};senseandavoid;spawn;{intr_id},{bearing:03d},2.0,200,{event_interval}")

        if "threatboard" in plugins and (current_time + 30) % (event_interval * 2) == 0:
            th_id = f"TH{(current_time // 60) % 4 + 1}"
            bearing = ((current_time * 23) % 360)
            weapons = ["R73", "AIM9", "GUN", "R77"]
            weapon = weapons[(current_time // event_interval) % len(weapons)]
            lines.append(f"{format_timestamp(current_time)};threatboard;spawn;{th_id},{bearing:03d},{(current_time % 15) + 5},{weapon},{event_interval}")

        if "energymanager" in plugins and current_time % (event_interval * 2) == 0:
            events = ["PATROL", "INTERCEPT", "ENGAGE", "DEFENSIVE", "EGRESS"]
            event = events[(current_time // event_interval) % len(events)]
            g_load = 3.0 + (difficulty * 0.4)
            lines.append(f"{format_timestamp(current_time)};energymanager;event;{event},{g_load:.1f},{event_interval}")

        if "datalink" in plugins and (current_time + 10) % event_interval == 0:
            msg_id = f"MSG{(current_time // 30) % 10 + 1}"
            senders = ["ATC", "AWACS", "UAVOPS", "PILOT"]
            sender = senders[(current_time // event_interval) % len(senders)]
            priorities = ["NORM", "PRIO", "CRIT"]
            priority = priorities[min(2, difficulty // 4)]
            lines.append(f"{format_timestamp(current_time)};datalink;message;{msg_id},{sender},{priority},Update received,{event_interval}")

        if "payloadmanager" in plugins and (current_time + 20) % (event_interval * 2) == 0:
            sensors = ["CamA", "IRST", "Radar", "EO"]
            sensor = sensors[(current_time // event_interval) % len(sensors)]
            target = f"Target-{chr(65 + (current_time // 60) % 5)}"
            lines.append(f"{format_timestamp(current_time)};payloadmanager;activate;{sensor},{target},{event_interval}")

        if "communications" in plugins and current_time % (event_interval * 2) == 0:
            prompt_type = "own" if (current_time // event_interval) % 3 != 0 else "other"
            lines.append(f"{format_timestamp(current_time)};communications;radioprompt;{prompt_type}")

        if "sysmon" in plugins and (current_time + 5) % event_interval == 0:
            scale = ((current_time // 15) % 4) + 1
            side = [-1, 0, 1][(current_time // event_interval) % 3]
            lines.append(f"{format_timestamp(current_time)};sysmon;scales-{scale}-failure;True")

        current_time += event_interval

    lines.append("")

    # Phase 4: Shutdown
    lines.append("# ============================================")
    lines.append("# PHASE 4: SHUTDOWN")
    lines.append("# ============================================")
    lines.append("")

    # Clear active elements
    if "datalink" in plugins:
        lines.append(f"{format_timestamp(duration - 15)};datalink;clear;*")
    if "threatboard" in plugins:
        lines.append(f"{format_timestamp(duration - 15)};threatboard;clear;*")

    # Stop all plugins in reverse order
    lines.append("")
    for plugin in reversed(plugins):
        lines.append(f"{format_timestamp(duration)};{plugin};stop")

    lines.append("")
    return "\n".join(lines)


def render_scenario_editor(scenario_options: list[str], available_plugins: list[str]) -> None:
    """Render the scenario editor interface."""
    st.subheader("Edit Existing Scenario")

    selected_scenario = st.selectbox(
        "Select scenario to edit",
        options=scenario_options,
        key="edit_scenario_select",
    )

    if selected_scenario:
        scenario_path = SCENARIO_DIR / selected_scenario
        if scenario_path.exists():
            content = scenario_path.read_text(encoding="utf-8")

            edited_content = st.text_area(
                "Scenario content",
                value=content,
                height=400,
                key="scenario_editor",
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("✅ Validate"):
                    errors = validate_scenario(edited_content, available_plugins)
                    if errors:
                        for error in errors:
                            st.error(error)
                    else:
                        st.success("✅ Scenario is valid!")

            with col2:
                if st.button("💾 Save Changes"):
                    # Backup first
                    backup_path = scenario_path.with_suffix(".txt.bak")
                    backup_path.write_text(content, encoding="utf-8")
                    # Write new content
                    scenario_path.write_text(edited_content, encoding="utf-8")
                    st.success(f"Saved! Backup at {backup_path.name}")

            with col3:
                st.download_button(
                    "📥 Download",
                    data=edited_content,
                    file_name=selected_scenario.replace("/", "_"),
                    mime="text/plain",
                )

            # Show scenario stats
            with st.expander("📊 Scenario Statistics"):
                lines = [l for l in edited_content.split("\n") if l.strip() and not l.strip().startswith("#")]
                plugins_used = set()
                timestamps: list[int] = []
                for line in lines:
                    parts = line.split(";")
                    if len(parts) >= 2:
                        plugins_used.add(parts[1])
                        try:
                            timestamps.append(parse_timestamp(parts[0]))
                        except (ValueError, IndexError):
                            pass

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Commands", len(lines))
                with col2:
                    st.metric("Plugins", len(plugins_used))
                with col3:
                    if timestamps:
                        duration = max(timestamps)
                        st.metric("Duration", f"{duration // 60}m {duration % 60}s")

                st.write("**Plugins used:**", ", ".join(sorted(plugins_used)))


def render_template_generator(available_plugins: list[str]) -> None:
    """Render the template-based scenario generator."""
    st.subheader("Create from Template")

    template_name = st.selectbox(
        "Select template",
        options=list(SCENARIO_TEMPLATES.keys()),
        key="template_select",
    )

    if template_name:
        template = SCENARIO_TEMPLATES[template_name]
        st.info(f"**{template_name}**: {template['description']}")

        col1, col2 = st.columns(2)
        with col1:
            duration = st.number_input(
                "Duration (seconds)",
                min_value=60,
                max_value=3600,
                value=int(template["duration"]),
                step=30,
            )
        with col2:
            difficulty = st.slider(
                "Difficulty (1-10)",
                min_value=1,
                max_value=10,
                value=int(template["difficulty"]),
            )

        st.write("**Plugins included:**")
        plugins_list = list(template["plugins"])
        cols = st.columns(4)
        for idx, plugin in enumerate(plugins_list):
            with cols[idx % 4]:
                st.write(f"• {plugin}")

        if st.button("🎲 Generate Scenario"):
            generated = generate_scenario_from_template(template_name, duration, difficulty)
            st.session_state["generated_scenario"] = generated
            st.session_state["generated_template"] = template_name

        if "generated_scenario" in st.session_state:
            st.text_area(
                "Generated scenario",
                value=st.session_state["generated_scenario"],
                height=400,
                key="generated_preview",
            )

            col1, col2 = st.columns(2)
            with col1:
                filename = st.text_input(
                    "Filename",
                    value=f"{template_name.lower().replace(' ', '_')}_{datetime.now().strftime('%d%m%Y_%H%M%S')}.txt",
                )
            with col2:
                if st.button("💾 Save to scenarios/"):
                    save_path = SCENARIO_DIR / filename
                    save_path.write_text(st.session_state["generated_scenario"], encoding="utf-8")
                    st.success(f"Saved to includes/scenarios/{filename}")

            st.download_button(
                "📥 Download",
                data=st.session_state["generated_scenario"],
                file_name=filename,
                mime="text/plain",
            )


def render_custom_builder(
    available_plugins: list[str],
    plugin_params: dict[str, list[PluginParameter]],
) -> None:
    """Render the custom scenario builder."""
    st.subheader("Build Custom Scenario")

    # Initialize session state
    if "custom_events" not in st.session_state:
        st.session_state["custom_events"] = []

    col1, col2 = st.columns(2)
    with col1:
        scenario_name = st.text_input("Scenario name", value="custom_scenario")
        scenario_duration = st.number_input("Duration (seconds)", min_value=60, max_value=3600, value=300, step=30)
    with col2:
        scenario_difficulty = st.slider("Difficulty", min_value=1, max_value=10, value=5)
        scenario_description = st.text_input("Description", value="Custom scenario")

    st.markdown("---")

    # Plugin selection
    st.subheader("1. Select Plugins")
    selected_plugins: list[str] = []

    for category, plugins in PLUGIN_CATEGORIES.items():
        with st.expander(category, expanded=category == "Core MATB Tasks"):
            cols = st.columns(3)
            for idx, plugin in enumerate(plugins):
                if plugin in available_plugins:
                    with cols[idx % 3]:
                        if st.checkbox(plugin, key=f"plugin_{plugin}"):
                            selected_plugins.append(plugin)

    st.markdown("---")

    # Event builder
    st.subheader("2. Add Events")

    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    with col1:
        event_time = st.number_input("Time (s)", min_value=0, max_value=3600, value=0, step=5, key="event_time")
    with col2:
        event_plugin = st.selectbox("Plugin", options=selected_plugins or ["(select plugins first)"], key="event_plugin")
    with col3:
        common_commands = ["start", "stop", "show", "hide", "pause", "resume", "automaticsolver;True", "automaticsolver;False"]
        event_command = st.selectbox("Command", options=common_commands + ["(custom)"], key="event_command")
        if event_command == "(custom)":
            event_command = st.text_input("Custom command", key="custom_command")
    with col4:
        event_value = st.text_input("Value", key="event_value")

    if st.button("➕ Add Event"):
        if event_plugin and event_plugin != "(select plugins first)" and event_command:
            cmd = f"{event_command};{event_value}" if event_value else event_command
            st.session_state["custom_events"].append({
                "time": event_time,
                "plugin": event_plugin,
                "command": cmd,
            })
            st.rerun()

    # Show current events
    if st.session_state["custom_events"]:
        st.markdown("**Current Events:**")
        events_sorted = sorted(st.session_state["custom_events"], key=lambda x: x["time"])
        for idx, event in enumerate(events_sorted):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.code(f"{format_timestamp(event['time'])};{event['plugin']};{event['command']}")
            with col2:
                if st.button("🗑️", key=f"del_{idx}"):
                    st.session_state["custom_events"].remove(event)
                    st.rerun()

    st.markdown("---")

    # Generate and preview
    st.subheader("3. Generate Scenario")

    if st.button("🔨 Build Scenario"):
        lines = [
            f"# {scenario_name}",
            f"# {scenario_description}",
            f"# Duration: {scenario_duration}s | Difficulty: {scenario_difficulty}/10",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "# Start plugins",
        ]

        # Add start commands
        for plugin in selected_plugins:
            lines.append(f"0:00:00;{plugin};start")

        lines.append("")
        lines.append("# Events")

        # Add custom events
        for event in sorted(st.session_state["custom_events"], key=lambda x: x["time"]):
            lines.append(f"{format_timestamp(event['time'])};{event['plugin']};{event['command']}")

        lines.append("")
        lines.append("# Stop plugins")

        # Add stop commands
        for plugin in reversed(selected_plugins):
            lines.append(f"{format_timestamp(scenario_duration)};{plugin};stop")

        st.session_state["built_scenario"] = "\n".join(lines)

    if "built_scenario" in st.session_state:
        st.text_area("Preview", value=st.session_state["built_scenario"], height=300)

        col1, col2 = st.columns(2)
        with col1:
            filename = f"{scenario_name}_{datetime.now().strftime('%d%m%Y_%H%M%S')}.txt"
            if st.button("💾 Save"):
                save_path = SCENARIO_DIR / filename
                save_path.write_text(st.session_state["built_scenario"], encoding="utf-8")
                st.success(f"Saved to includes/scenarios/{filename}")
        with col2:
            st.download_button(
                "📥 Download",
                data=st.session_state["built_scenario"],
                file_name=filename,
                mime="text/plain",
            )

    # Clear button
    if st.button("🧹 Clear All Events"):
        st.session_state["custom_events"] = []
        if "built_scenario" in st.session_state:
            del st.session_state["built_scenario"]
        st.rerun()


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
    st.info(
        "Controls such as **UI Scale** and **Colorblind-Friendly Status Palette** affect only the 2D "
        "presentation (font size, spacing, symbology). Scenario timing, task logic, and workload "
        "metrics remain unchanged, so MATB / military aircrew assessment validity is preserved."
    )

    # Tabs for different sections
    if VOICE_GENERATOR_AVAILABLE:
        tab_core, tab_plugins, tab_instructions, tab_voice, tab_designer, tab_launch, tab_preview, tab_scenario = st.tabs(
            ["⚙️ Core Settings", "🔌 Plugin Parameters", "📖 Instrucciones", "🎙️ Voice Generator",
             "🎬 Scenario Designer", "🚀 Launch", "📄 Config Preview", "📋 Scenario Helper"]
        )
    else:
        tab_core, tab_plugins, tab_instructions, tab_designer, tab_launch, tab_preview, tab_scenario = st.tabs(
            ["⚙️ Core Settings", "🔌 Plugin Parameters", "📖 Instrucciones",
             "🎬 Scenario Designer", "🚀 Launch", "📄 Config Preview", "📋 Scenario Helper"]
        )
        tab_voice = None

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

                ui_scale = st.slider(
                    "UI Scale",
                    min_value=0.5,
                    max_value=2.0,
                    value=float(openmatb.ui_scale),
                    step=0.05,
                    help=(
                        "Global scale factor for on-screen fonts and spacing. "
                        "Use 1.0 for nominal layouts; adjust only for readability on specific displays."
                    ),
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

                colorblind_mode = st.checkbox(
                    "Colorblind-Friendly Status Palette",
                    value=openmatb.colorblind_mode,
                    help=(
                        "Use aeronautical status colors and symbols that remain legible "
                        "without relying solely on red/green discrimination."
                    ),
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
                    ui_scale=float(ui_scale),
                    colorblind_mode=colorblind_mode,
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
                            "ui_scale": _format_float(new_openmatb.ui_scale),
                            "colorblind_mode": str(new_openmatb.colorblind_mode),
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
    # Tab 3: Spanish Instructions
    # ---------------------------------------------------------------------------
    with tab_instructions:
        st.header("📖 Instrucciones del Escenario")
        st.markdown(
            "Lea las instrucciones en español antes de iniciar el escenario. "
            "Estas instrucciones explican paso a paso cada tarea del test."
        )
        st.markdown("---")
        
        # Scenario selection for instructions
        st.subheader("Seleccione el Escenario")
        
        # Get current scenario from config
        current_scenario = openmatb.scenario_path
        
        # Allow selecting a different scenario for instructions
        instruction_scenario = st.selectbox(
            "Escenario para ver instrucciones",
            options=scenario_options,
            index=scenario_options.index(current_scenario) if current_scenario in scenario_options else 0,
            key="instruction_scenario_select",
            help="Seleccione el escenario para ver sus instrucciones en español",
        )
        
        # Check if instructions exist for this scenario
        scenario_file = Path(instruction_scenario).name
        has_instructions = scenario_file in SCENARIO_INSTRUCTIONS
        
        if not has_instructions:
            st.warning(
                f"⚠️ No hay instrucciones específicas para `{instruction_scenario}`. "
                "Se mostrarán las instrucciones predeterminadas del MATB básico."
            )
        else:
            st.success(f"✅ Instrucciones disponibles para `{instruction_scenario}`")
        
        st.markdown("---")
        
        # Display instructions
        render_spanish_instructions(instruction_scenario)
        
        # Printable version
        st.markdown("---")
        st.subheader("📄 Versión para Imprimir")
        
        col1, col2 = st.columns(2)
        with col1:
            printable_content = render_all_instructions_printable(instruction_scenario)
            st.download_button(
                "📥 Descargar Instrucciones (HTML)",
                data=printable_content,
                file_name=f"instrucciones_{scenario_file.replace('.txt', '')}.html",
                mime="text/html",
                use_container_width=True,
            )
        with col2:
            # Generate plain text version
            instruction_files = get_instructions_for_scenario(instruction_scenario)
            plain_text = []
            plain_text.append(f"INSTRUCCIONES: {instruction_scenario}")
            plain_text.append("=" * 50)
            plain_text.append("")
            for idx, instr_file in enumerate(instruction_files, 1):
                content = load_instruction_content(instr_file)
                # Strip HTML tags for plain text
                text_only = re.sub(r'<[^>]+>', '', content)
                text_only = re.sub(r'\s+', ' ', text_only).strip()
                plain_text.append(f"SECCIÓN {idx}")
                plain_text.append("-" * 30)
                plain_text.append(text_only)
                plain_text.append("")
            
            st.download_button(
                "📥 Descargar Instrucciones (TXT)",
                data="\n".join(plain_text),
                file_name=f"instrucciones_{scenario_file.replace('.txt', '')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        
        # Generate spoken instructions (if voice generator available)
        if VOICE_GENERATOR_AVAILABLE:
            st.markdown("---")
            st.subheader("🎙️ Instrucciones Habladas")
            st.markdown(
                "Genere una versión de audio de las instrucciones usando OpenAI TTS. "
                "Esto es útil para participantes que prefieren escuchar las instrucciones."
            )
            
            # Language selection - this determines BOTH text and voice language
            voice_lang = st.selectbox(
                "Idioma de las Instrucciones",
                options=["es", "en"],
                format_func=lambda x: "Español" if x == "es" else "English",
                key="instruction_voice_lang",
                help="Selecciona el idioma del texto y la voz. El texto y la voz siempre coinciden.",
            )
            
            # Voice presets filtered by language
            if voice_lang == "es":
                preset_options = [
                    "briefing_instructor_es",
                    "atc_male_es",
                    "atc_female_es",
                ]
                preset_labels = {
                    "briefing_instructor_es": "🎓 Instructor (Español)",
                    "atc_male_es": "👨‍✈️ ATC Masculino (Español)",
                    "atc_female_es": "👩‍✈️ ATC Femenino (Español)",
                }
            else:
                preset_options = [
                    "briefing_instructor_en",
                    "atc_male_en",
                    "atc_female_en",
                ]
                preset_labels = {
                    "briefing_instructor_en": "🎓 Instructor (English)",
                    "atc_male_en": "👨‍✈️ ATC Male (English)",
                    "atc_female_en": "👩‍✈️ ATC Female (English)",
                }
            
            voice_preset = st.selectbox(
                "Preset de Voz",
                options=preset_options,
                format_func=lambda x: preset_labels.get(x, x.replace("_", " ").title()),
                key=f"instruction_voice_preset_{voice_lang}",
                help="Selecciona el estilo de voz para las instrucciones.",
            )
            
            # Check for cached audio
            cached_audio = check_cached_audio(instruction_scenario, voice_lang, voice_preset)
            
            if cached_audio:
                st.success(f"✅ Audio en caché disponible")
                st.audio(str(cached_audio))
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Regenerar Audio", key="regenerate_audio"):
                        # Delete cached file and regenerate
                        cached_audio.unlink(missing_ok=True)
                        st.rerun()
                with col2:
                    st.download_button(
                        "📥 Descargar Audio",
                        data=cached_audio.read_bytes(),
                        file_name=cached_audio.name,
                        mime="audio/mpeg",
                    )
            else:
                # Check for English instructions availability
                if voice_lang == "en":
                    scenario_file = Path(instruction_scenario).name
                    if scenario_file not in SCENARIO_INSTRUCTIONS_EN:
                        st.warning(
                            "⚠️ No hay instrucciones en inglés para este escenario. "
                            "Se usarán las instrucciones en español con voz en inglés."
                        )
                
                if st.button("🎤 Generar Audio de Instrucciones", key="gen_instruction_audio"):
                    api_key = load_api_key()
                    if not api_key:
                        st.error(
                            "⚠️ Se requiere una clave API de OpenAI. "
                            "Configure la variable de entorno `OPENAI_API_KEY` o agréguela a `.env`."
                        )
                    else:
                        with st.spinner("Generando audio de instrucciones..."):
                            # Collect all instruction text in the selected language
                            instruction_files = get_instructions_for_scenario(
                                instruction_scenario, voice_lang
                            )
                            all_text = []
                            for instr_file in instruction_files:
                                content = load_instruction_content(instr_file)
                                # Strip HTML tags
                                text_only = re.sub(r'<[^>]+>', '', content)
                                text_only = re.sub(r'\s+', ' ', text_only).strip()
                                all_text.append(text_only)
                            
                            full_text = " ... ".join(all_text)
                            
                            # Limit text length for API
                            if len(full_text) > 4000:
                                full_text = full_text[:4000] + "..."
                            
                            try:
                                preset = VOICE_PRESETS.get(voice_preset)
                                if preset:
                                    config = VoiceConfig(
                                        voice=preset.voice,
                                        speed=preset.speed,
                                        instructions=preset.instructions,
                                        language=voice_lang,
                                    )
                                else:
                                    config = VoiceConfig(language=voice_lang)
                                
                                generator = ATCVoiceGenerator(config=config, api_key=api_key)
                                
                                # Use cached path for output
                                output_path = get_cached_audio_path(
                                    instruction_scenario, voice_lang, voice_preset
                                )
                                
                                result = generator.generate_communication(
                                    full_text, output_path, config
                                )
                                
                                if result.success:
                                    st.success(f"✅ Audio generado y guardado en caché")
                                    st.audio(str(result.file_path))
                                    st.rerun()  # Refresh to show cached audio UI
                                else:
                                    st.error(f"❌ Error: {result.error_message}")
                            except Exception as exc:
                                st.error(f"❌ Error al generar audio: {exc}")

        # Instructions checklist
        st.markdown("---")
        st.subheader("✅ Lista de Verificación Pre-Test")
        st.markdown(
            """
            Antes de iniciar el test, asegúrese de:
            
            1. ☐ **Leer todas las instrucciones** - Use las flechas para navegar por todas las páginas
            2. ☐ **Entender cada tarea** - Pregunte si tiene dudas sobre alguna tarea
            3. ☐ **Verificar el equipo** - Joystick conectado (si aplica), audio funcionando
            4. ☐ **Sensor Polar H10** - Si el escenario incluye HRV, verificar conexión Bluetooth
            5. ☐ **Ambiente adecuado** - Iluminación, temperatura, ruido controlados
            6. ☐ **Descanso previo** - Mínimo 6 horas de sueño, sin cafeína reciente
            
            Cuando esté listo, vaya a la pestaña **🚀 Launch** para iniciar el escenario.
            """
        )

    # ---------------------------------------------------------------------------
    # Tab 4: Voice Generator (if available)
    # ---------------------------------------------------------------------------
    if VOICE_GENERATOR_AVAILABLE and tab_voice is not None:
        with tab_voice:
            render_voice_generator_tab()

    # ---------------------------------------------------------------------------
    # Tab 5: Scenario Designer
    # ---------------------------------------------------------------------------
    with tab_designer:
        st.header("🎬 Scenario Designer")
        st.markdown(
            "Create, edit, and validate scenario files. Use templates for quick starts "
            "or build custom scenarios from scratch."
        )

        designer_mode = st.radio(
            "Mode",
            options=["📝 Edit Existing", "✨ Create from Template", "🔧 Build Custom"],
            horizontal=True,
        )

        if designer_mode == "📝 Edit Existing":
            render_scenario_editor(scenario_options, available_plugins)

        elif designer_mode == "✨ Create from Template":
            render_template_generator(available_plugins)

        else:  # Build Custom
            render_custom_builder(available_plugins, plugin_params)

    # ---------------------------------------------------------------------------
    # Tab 5: Launch OpenMATB
    # ---------------------------------------------------------------------------
    with tab_launch:
        st.header("🚀 Launch OpenMATB")
        st.markdown(
            "Launch the OpenMATB application with your current configuration. "
            "Make sure to save your config.ini changes before launching."
        )

        # Display current configuration summary
        st.subheader("📋 Current Configuration Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Scenario", openmatb.scenario_path)
        with col2:
            st.metric("Language", openmatb.language)
        with col3:
            st.metric("Participant", user.participant_id)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Fullscreen", "Yes" if openmatb.fullscreen else "No")
        with col2:
            st.metric("Screen Index", openmatb.screen_index)
        with col3:
            st.metric("Clock Speed", f"{openmatb.clock_speed}x")

        # Check scenario validity
        scenario_file = SCENARIO_DIR / openmatb.scenario_path
        scenario_valid = scenario_file.exists()

        st.markdown("---")

        if not scenario_valid:
            st.error(
                f"⚠️ **Scenario file not found**: `{openmatb.scenario_path}`\n\n"
                "Please select a valid scenario in the Core Settings tab or create one in the Scenario Designer."
            )

        # Scenario preview
        if scenario_valid:
            with st.expander("📄 Preview Scenario", expanded=False):
                scenario_content = scenario_file.read_text(encoding="utf-8")
                lines = [l for l in scenario_content.split("\n") if l.strip() and not l.strip().startswith("#")]
                st.caption(f"{len(lines)} commands in scenario")
                st.code(scenario_content[:2000] + ("..." if len(scenario_content) > 2000 else ""), language="text")

        st.markdown("---")
        st.subheader("🎮 Launch Controls")

        # Initialize session state for process tracking
        if "matb_process" not in st.session_state:
            st.session_state["matb_process"] = None
        if "launch_log" not in st.session_state:
            st.session_state["launch_log"] = []

        # Check if process is running
        process_running = False
        if st.session_state["matb_process"] is not None:
            poll_result = st.session_state["matb_process"].poll()
            if poll_result is None:
                process_running = True
            else:
                # Process finished
                st.session_state["launch_log"].append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] OpenMATB exited with code {poll_result}"
                )
                st.session_state["matb_process"] = None

        if process_running:
            st.warning("⏳ **OpenMATB is currently running**")
            if st.button("🛑 Stop OpenMATB", type="secondary", use_container_width=True):
                if st.session_state["matb_process"]:
                    st.session_state["matb_process"].terminate()
                    st.session_state["launch_log"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] OpenMATB terminated by user"
                    )
                    st.session_state["matb_process"] = None
                    st.rerun()
        else:
            # Launch button
            col1, col2 = st.columns(2)
            with col1:
                launch_btn = st.button(
                    "🚀 Launch OpenMATB",
                    type="primary",
                    use_container_width=True,
                    disabled=not scenario_valid,
                    help="Start the OpenMATB application with current config.ini settings",
                )
            with col2:
                launch_windowed = st.checkbox(
                    "Override fullscreen (launch windowed)",
                    value=False,
                    help="Temporarily launch in windowed mode for testing",
                )

            if launch_btn:
                try:
                    # Determine Python executable
                    python_exe = sys.executable
                    # On Windows, check for Python313 as fallback
                    if sys.platform == "win32" and not Path(python_exe).exists():
                        for py_path in [r"C:\Python313\python.exe", r"C:\Python312\python.exe", r"C:\Python311\python.exe"]:
                            if Path(py_path).exists():
                                python_exe = py_path
                                break

                    # Prepare environment
                    env = os.environ.copy()

                    # If windowed override, temporarily modify config
                    if launch_windowed and openmatb.fullscreen:
                        # Read current config
                        temp_config = CONFIG_PATH.read_text(encoding="utf-8")
                        # Replace fullscreen=True with fullscreen=False
                        temp_config = re.sub(
                            r"fullscreen\s*=\s*True",
                            "fullscreen=False",
                            temp_config,
                            flags=re.IGNORECASE,
                        )
                        CONFIG_PATH.write_text(temp_config, encoding="utf-8")
                        st.session_state["launch_log"].append(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Temporarily set fullscreen=False"
                        )

                    # Launch OpenMATB
                    main_py = PROJECT_ROOT / "main.py"
                    st.session_state["launch_log"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Launching: {python_exe} {main_py}"
                    )

                    process = subprocess.Popen(
                        [python_exe, str(main_py)],
                        cwd=str(PROJECT_ROOT),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                    )

                    st.session_state["matb_process"] = process
                    st.session_state["launch_log"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] OpenMATB started (PID: {process.pid})"
                    )

                    st.success(f"✅ OpenMATB launched! (PID: {process.pid})")
                    st.rerun()

                except FileNotFoundError as e:
                    st.error(f"❌ Failed to launch: {e}")
                    st.session_state["launch_log"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {e}"
                    )
                except OSError as e:
                    st.error(f"❌ OS Error: {e}")
                    st.session_state["launch_log"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {e}"
                    )

        # Launch log
        if st.session_state["launch_log"]:
            with st.expander("📜 Launch Log", expanded=True):
                for entry in st.session_state["launch_log"][-10:]:  # Show last 10 entries
                    st.text(entry)
                if st.button("🧹 Clear Log"):
                    st.session_state["launch_log"] = []
                    st.rerun()

        # Quick actions
        st.markdown("---")
        st.subheader("⚡ Quick Actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📂 Open Sessions Folder", use_container_width=True):
                sessions_dir = PROJECT_ROOT / "sessions"
                sessions_dir.mkdir(exist_ok=True)
                if sys.platform == "win32":
                    os.startfile(str(sessions_dir))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(sessions_dir)], check=False, timeout=5)
                else:
                    subprocess.run(["xdg-open", str(sessions_dir)], check=False, timeout=5)
        with col2:
            if st.button("📂 Open Scenarios Folder", use_container_width=True):
                if sys.platform == "win32":
                    os.startfile(str(SCENARIO_DIR))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(SCENARIO_DIR)], check=False, timeout=5)
                else:
                    subprocess.run(["xdg-open", str(SCENARIO_DIR)], check=False, timeout=5)
        with col3:
            if st.button("📂 Open Project Folder", use_container_width=True):
                if sys.platform == "win32":
                    os.startfile(str(PROJECT_ROOT))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(PROJECT_ROOT)], check=False, timeout=5)
                else:
                    subprocess.run(["xdg-open", str(PROJECT_ROOT)], check=False, timeout=5)

    # ---------------------------------------------------------------------------
    # Tab 6: Config Preview
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
    # Tab 7: Scenario Helper
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
