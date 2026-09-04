"""Canonical OpenMATB visual-profile contract shared by console and runtime.

The contract contains presentation data only. Scenario state, scheduling,
geometry, hit areas, scoring, automation, and response timing are deliberately
outside this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "openmatb-visual-profile-v1"
GEOMETRY_POLICY = "preserve_openmatb_v1"
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

PALETTE_KEYS = frozenset(
    {
        "app_background",
        "panel_background",
        "instrument_background",
        "panel_header",
        "panel_header_text",
        "control_background",
        "control_foreground",
        "text",
        "muted_text",
        "border",
        "grid",
        "accent",
        "safe",
        "warning",
        "critical",
        "disabled",
    }
)

MODULE_KEYS: dict[str, frozenset[str]] = {
    "tracking": frozenset(
        {
            "panel",
            "axis",
            "grid",
            "target",
            "target_fill",
            "cursor",
            "cursor_outside",
            "show_panel",
            "show_grid",
            "closed_target_border",
        }
    ),
    "system_monitoring": frozenset(
        {
            "panel",
            "lamp_1",
            "lamp_2",
            "lamp_3",
            "lamp_4",
            "lamp_off",
            "lamp_border",
            "lamp_shape",
            "scale",
            "pointer",
            "feedback_positive",
            "feedback_negative",
        }
    ),
    "communications": frozenset(
        {
            "panel",
            "display_background",
            "display_border",
            "active",
            "inactive",
            "positive",
            "negative",
            "show_display_bezel",
        }
    ),
    "resource_management": frozenset(
        {
            "panel",
            "tank_1",
            "tank_2",
            "tank_3",
            "tank_4",
            "tank_5",
            "tank_6",
            "fluid",
            "pipe_on",
            "pipe_off",
            "pump_on",
            "pump_off",
            "pump_failure",
            "tolerance",
            "meter",
            "show_pump_ring",
        }
    ),
    "workload": frozenset({"panel", "scale", "marker"}),
}

DOCUMENT_KEYS = frozenset(
    {"schema_version", "profile_id", "version", "label", "geometry_policy", "palette", "metrics", "modules"}
)
METRIC_KEYS = frozenset({"line_width", "panel_radius", "corner_mark_ratio"})
BOOLEAN_PATHS = frozenset(
    {
        ("tracking", "show_panel"),
        ("tracking", "show_grid"),
        ("tracking", "closed_target_border"),
        ("communications", "show_display_bezel"),
        ("resource_management", "show_pump_ring"),
    }
)
ENUM_PATHS = {("system_monitoring", "lamp_shape"): frozenset({"rectangle", "circle"})}


class VisualProfileValidationError(ValueError):
    """Raised when a visual profile violates the closed v1 contract."""

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


def canonical_json(value: object) -> str:
    """Serialize without formatting or key-order ambiguity."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def profile_sha256(profile: dict[str, Any]) -> str:
    """Hash the normalized document rather than caller formatting."""

    normalized = validate_visual_profile(profile)
    return hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()


def _check_exact_keys(value: object, expected: frozenset[str], path: str, issues: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return None
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        issues.append(f"{path} missing fields: {', '.join(missing)}")
    if unknown:
        issues.append(f"{path} has unknown fields: {', '.join(unknown)}")
    return value


def _normalize_color(value: object, path: str, issues: list[str]) -> str:
    if not isinstance(value, str) or HEX_COLOR_PATTERN.fullmatch(value) is None:
        issues.append(f"{path} must be a #RRGGBB color")
        return "#000000"
    return value.upper()


def validate_visual_profile(value: object) -> dict[str, Any]:
    """Validate and normalize a strict ``openmatb-visual-profile-v1`` document."""

    issues: list[str] = []
    document = _check_exact_keys(value, DOCUMENT_KEYS, "$", issues)
    if document is None:
        raise VisualProfileValidationError(issues)

    schema_version = document.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        issues.append(f"schema_version must equal {SCHEMA_VERSION}")
    profile_id = document.get("profile_id")
    if not isinstance(profile_id, str) or PROFILE_ID_PATTERN.fullmatch(profile_id) is None:
        issues.append("profile_id must contain 3..64 lowercase letters, numbers, or hyphens")
    version = document.get("version")
    if not isinstance(version, str) or SEMVER_PATTERN.fullmatch(version) is None:
        issues.append("version must be a three-part semantic version")
    label = document.get("label")
    if not isinstance(label, str) or not 3 <= len(label.strip()) <= 100:
        issues.append("label must contain 3..100 characters")
    if document.get("geometry_policy") != GEOMETRY_POLICY:
        issues.append(f"geometry_policy must equal {GEOMETRY_POLICY}")

    palette = _check_exact_keys(document.get("palette"), PALETTE_KEYS, "palette", issues)
    normalized_palette: dict[str, str] = {}
    if palette is not None:
        for key in sorted(PALETTE_KEYS):
            normalized_palette[key] = _normalize_color(palette.get(key), f"palette.{key}", issues)

    metrics = _check_exact_keys(document.get("metrics"), METRIC_KEYS, "metrics", issues)
    normalized_metrics: dict[str, float] = {}
    metric_bounds = {
        "line_width": (1.0, 6.0),
        "panel_radius": (0.0, 24.0),
        "corner_mark_ratio": (0.0, 0.20),
    }
    if metrics is not None:
        for key, (minimum, maximum) in metric_bounds.items():
            candidate = metrics.get(key)
            if isinstance(candidate, bool) or not isinstance(candidate, (int, float)) or not math.isfinite(float(candidate)):
                issues.append(f"metrics.{key} must be a finite number")
                continue
            numeric = float(candidate)
            if not minimum <= numeric <= maximum:
                issues.append(f"metrics.{key} must be between {minimum:g} and {maximum:g}")
            normalized_metrics[key] = numeric

    modules = _check_exact_keys(document.get("modules"), frozenset(MODULE_KEYS), "modules", issues)
    normalized_modules: dict[str, dict[str, Any]] = {}
    if modules is not None:
        for module_name, expected_keys in MODULE_KEYS.items():
            module = _check_exact_keys(modules.get(module_name), expected_keys, f"modules.{module_name}", issues)
            if module is None:
                continue
            normalized_module: dict[str, Any] = {}
            for key in sorted(expected_keys):
                candidate = module.get(key)
                path = (module_name, key)
                if path in BOOLEAN_PATHS:
                    if not isinstance(candidate, bool):
                        issues.append(f"modules.{module_name}.{key} must be a boolean")
                    normalized_module[key] = candidate
                elif path in ENUM_PATHS:
                    if candidate not in ENUM_PATHS[path]:
                        allowed = ", ".join(sorted(ENUM_PATHS[path]))
                        issues.append(f"modules.{module_name}.{key} must be one of: {allowed}")
                    normalized_module[key] = candidate
                else:
                    normalized_module[key] = _normalize_color(
                        candidate, f"modules.{module_name}.{key}", issues
                    )
            normalized_modules[module_name] = normalized_module

    if issues:
        raise VisualProfileValidationError(issues)
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "version": version,
        "label": label.strip(),
        "geometry_policy": GEOMETRY_POLICY,
        "palette": normalized_palette,
        "metrics": normalized_metrics,
        "modules": normalized_modules,
    }


def load_visual_profile(path: Path) -> dict[str, Any]:
    """Read one profile from disk and fail closed on invalid JSON or schema."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualProfileValidationError([f"could not read visual profile {path}: {exc}"]) from exc
    return validate_visual_profile(raw)


def hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    """Convert a validated browser color to the opaque Pyglet tuple."""

    if HEX_COLOR_PATTERN.fullmatch(value) is None:
        raise ValueError("color must use #RRGGBB")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5)) + (255,)


def _relative_luminance(value: str) -> float:
    channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def assess_visual_profile(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return publish-blocking accessibility errors and acknowledged warnings.

    Text and essential control boundaries are blocking. Experimental stimulus
    separability is a warning because changing it can itself alter the task.
    """

    normalized = validate_visual_profile(profile)
    palette = normalized["palette"]
    modules = normalized["modules"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    essential_pairs = (
        ("text-app", palette["text"], palette["app_background"], 4.5, "palette.text", "palette.app_background"),
        ("text-panel", palette["text"], palette["panel_background"], 4.5, "palette.text", "palette.panel_background"),
        ("text-instrument", palette["text"], palette["instrument_background"], 4.5, "palette.text", "palette.instrument_background"),
        ("header-text", palette["panel_header_text"], palette["panel_header"], 4.5, "palette.panel_header_text", "palette.panel_header"),
        ("control-text", palette["control_foreground"], palette["control_background"], 4.5, "palette.control_foreground", "palette.control_background"),
        ("border-panel", palette["border"], palette["panel_background"], 3.0, "palette.border", "palette.panel_background"),
    )
    for code, foreground, background, minimum, foreground_path, background_path in essential_pairs:
        ratio = contrast_ratio(foreground, background)
        if ratio < minimum:
            errors.append(
                {
                    "code": f"contrast-{code}",
                    "message": f"Contrast {ratio:.2f}:1 is below {minimum:.1f}:1",
                    "paths": [foreground_path, background_path],
                    "ratio": round(ratio, 3),
                    "minimum": minimum,
                }
            )

    stimulus_pairs = (
        ("tracking-cursor-target", modules["tracking"]["cursor"], modules["tracking"]["target_fill"], "modules.tracking.cursor", "modules.tracking.target_fill"),
        ("tracking-outside-panel", modules["tracking"]["cursor_outside"], modules["tracking"]["panel"], "modules.tracking.cursor_outside", "modules.tracking.panel"),
        ("sysmon-lamp1-off", modules["system_monitoring"]["lamp_1"], modules["system_monitoring"]["lamp_off"], "modules.system_monitoring.lamp_1", "modules.system_monitoring.lamp_off"),
        ("sysmon-lamp2-off", modules["system_monitoring"]["lamp_2"], modules["system_monitoring"]["lamp_off"], "modules.system_monitoring.lamp_2", "modules.system_monitoring.lamp_off"),
        ("comm-active-inactive", modules["communications"]["active"], modules["communications"]["inactive"], "modules.communications.active", "modules.communications.inactive"),
        ("resman-pump-on-off", modules["resource_management"]["pump_on"], modules["resource_management"]["pump_off"], "modules.resource_management.pump_on", "modules.resource_management.pump_off"),
        ("safety-safe-critical", palette["safe"], palette["critical"], "palette.safe", "palette.critical"),
    )
    for code, first, second, first_path, second_path in stimulus_pairs:
        ratio = contrast_ratio(first, second)
        if ratio < 3.0:
            warnings.append(
                {
                    "code": f"stimulus-{code}",
                    "message": f"Stimulus contrast {ratio:.2f}:1 is below the 3.0:1 review threshold",
                    "paths": [first_path, second_path],
                    "ratio": round(ratio, 3),
                    "minimum": 3.0,
                }
            )
    return {"errors": errors, "warnings": warnings}


def clone_profile_identity(profile: dict[str, Any], *, profile_id: str, version: str, label: str) -> dict[str, Any]:
    """Copy a validated profile while changing only its version identity."""

    cloned = deepcopy(validate_visual_profile(profile))
    cloned.update(profile_id=profile_id, version=version, label=label)
    return validate_visual_profile(cloned)
