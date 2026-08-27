"""The stable v1 samples/trials field contract and generated dictionary."""

from __future__ import annotations

from dataclasses import asdict, dataclass


BUNDLE_SCHEMA_VERSION = "matb-scientific-bundle-v1"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    dtype: str
    unit: str
    nullable: bool
    description: str
    direction: str = "not_applicable"


def _field(
    name: str,
    dtype: str,
    unit: str,
    description: str,
    *,
    nullable: bool = False,
    direction: str = "not_applicable",
) -> FieldSpec:
    return FieldSpec(name, dtype, unit, nullable, description, direction)


SAMPLE_FIELDS: tuple[FieldSpec, ...] = (
    _field("schema_version", "string", "1", "Scientific bundle schema identifier."),
    _field("session_id", "string", "1", "Pseudonymous runtime session identifier."),
    _field("sample_index", "int64", "1", "Sequential observed sample index."),
    _field("scheduled_monotonic_ns", "int64", "ns", "Most recent elapsed sampling deadline."),
    _field("observed_monotonic_ns", "int64", "ns", "Actual state observation timestamp."),
    _field("utc_ns", "int64", "ns", "UTC timestamp derived from the monotonic session origin."),
    _field("scenario_time_s", "float64", "s", "OpenMATB scenario clock."),
    _field("interval_ms", "float64", "ms", "Interval from the previous observed sample.", nullable=True),
    _field("lateness_ms", "float64", "ms", "Observation lateness relative to its deadline."),
    _field("missed_ticks", "int64", "1", "Elapsed deadlines not populated with synthetic observations."),
    _field("scenario_paused", "bool", "1", "Whether scenario time was paused."),
    _field("event_sequence", "int64", "1", "Latest legacy/event sequence visible to this sample."),
    _field("sysmon_alive", "bool", "1", "Systems-monitoring task active state."),
    _field("communications_alive", "bool", "1", "Communications task active state."),
    _field("tracking_alive", "bool", "1", "Tracking task active state."),
    _field("resman_alive", "bool", "1", "Resource-management task active state."),
    _field("workload_alive", "bool", "1", "Concurrent workload prompt active state."),
    _field("automation_sysmon", "bool", "1", "Systems-monitoring automation state."),
    _field("automation_communications", "bool", "1", "Communications automation state."),
    _field("automation_tracking", "bool", "1", "Tracking automation state."),
    _field("automation_resman", "bool", "1", "Resource-management automation state."),
    _field("load_sysmon", "bool", "1", "At least one sysmon response pending."),
    _field("load_communications", "bool", "1", "At least one communications response pending."),
    _field("load_workload", "bool", "1", "A workload response is pending."),
    _field("discrete_load_count", "int64", "tasks", "Number of pending discrete task classes."),
    _field("sysmon_pending_ids_json", "json", "1", "Stable identifiers for pending alerts."),
    _field("communications_pending_ids_json", "json", "1", "Stable identifiers for pending prompts."),
    _field("tracking_cursor_x", "float64", "proportion", "Horizontal cursor position.", nullable=True),
    _field("tracking_cursor_y", "float64", "proportion", "Vertical cursor position.", nullable=True),
    _field("tracking_deviation", "float64", "graph_unit", "Cursor distance from target centre.", nullable=True, direction="lower_is_better"),
    _field("tracking_in_target", "bool", "1", "Cursor inside target.", nullable=True, direction="higher_is_better"),
    _field("tank_a_level", "float64", "tank_unit", "Tank A level.", nullable=True),
    _field("tank_a_target", "float64", "tank_unit", "Tank A target.", nullable=True),
    _field("tank_a_deviation", "float64", "tank_unit", "Signed Tank A target deviation.", nullable=True),
    _field("tank_a_in_tolerance", "bool", "1", "Tank A inside tolerance.", nullable=True, direction="higher_is_better"),
    _field("tank_b_level", "float64", "tank_unit", "Tank B level.", nullable=True),
    _field("tank_b_target", "float64", "tank_unit", "Tank B target.", nullable=True),
    _field("tank_b_deviation", "float64", "tank_unit", "Signed Tank B target deviation.", nullable=True),
    _field("tank_b_in_tolerance", "bool", "1", "Tank B inside tolerance.", nullable=True, direction="higher_is_better"),
    _field("pump_states_json", "json", "1", "Resource-management pump states."),
    _field("workload_prompt_id", "string", "1", "Active workload prompt identifier.", nullable=True),
)


TRIAL_FIELDS: tuple[FieldSpec, ...] = (
    _field("schema_version", "string", "1", "Scientific bundle schema identifier."),
    _field("session_id", "string", "1", "Pseudonymous runtime session identifier."),
    _field("trial_id", "string", "1", "Stable session-local trial identifier."),
    _field("task", "string", "1", "Task alias."),
    _field("trial_type", "string", "1", "Stimulus or response class."),
    _field("stimulus_id", "string", "1", "Stable stimulus identifier.", nullable=True),
    _field("onset_s", "float64", "s", "Stimulus or prompt onset."),
    _field("deadline_s", "float64", "s", "Response deadline.", nullable=True),
    _field("response_s", "float64", "s", "Response timestamp.", nullable=True),
    _field("rt_ms", "float64", "ms", "Response time.", nullable=True, direction="lower_is_better"),
    _field("outcome", "string", "1", "HIT, MISS, FA, timeout, or task-specific outcome."),
    _field("correct", "bool", "1", "Whether the response was correct.", nullable=True, direction="higher_is_better"),
    _field("timeout", "bool", "1", "Whether the trial ended at its deadline."),
    _field("actor", "string", "1", "manual or automation."),
    _field("automation_active", "bool", "1", "Automation state at outcome."),
    _field("target_json", "json", "1", "Task-specific target."),
    _field("response_json", "json", "1", "Task-specific response."),
    _field("elements_available", "int64", "elements", "Scorable response elements.", nullable=True),
    _field("elements_correct", "int64", "elements", "Correct response elements.", nullable=True),
    _field("raw_value", "float64", "instrument_unit", "Questionnaire or task raw value.", nullable=True),
    _field("raw_unit", "string", "1", "Unit for raw_value.", nullable=True),
    _field("event_sequence_start", "int64", "1", "First linked event sequence.", nullable=True),
    _field("event_sequence_end", "int64", "1", "Last linked event sequence.", nullable=True),
)


def data_dictionary() -> dict[str, object]:
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "raw_data_authority": (
            "events.csv, samples.csv, and trials.csv are authoritative; "
            "summary scores are deterministic derived values"
        ),
        "tables": {
            "samples": [asdict(field) for field in SAMPLE_FIELDS],
            "trials": [asdict(field) for field in TRIAL_FIELDS],
        },
        "score_definitions": {
            "rt-efficiency-v1": {
                "formula": "clamp(100 * (timeout_ms - rt_ms) / timeout_ms, 0, 100); miss_or_timeout=0",
                "unit": "percent",
                "direction": "higher_is_better",
            },
            "tracking-performance-v1": {
                "formula": "100 - clamp(100 * mean_deviation / tracking_range, 0, 100)",
                "unit": "percent",
                "direction": "higher_is_better",
            },
            "usaarl-tracking-scaled-error-v1": {
                "formula": "clamp(100 * mean_deviation / tracking_range, 0, 100)",
                "unit": "percent",
                "direction": "lower_is_better",
            },
            "resource-performance-v1": {
                "formula": "100 - clamp(100 * mean_absolute_deviation / resource_range, 0, 100)",
                "unit": "percent",
                "direction": "higher_is_better",
            },
            "usaarl-resource-signed-v1": {
                "formula": "100 * (mean_level - 2000) / resource_range",
                "unit": "percent",
                "direction": "target_is_better",
            },
            "communication-element-accuracy-v1": {
                "formula": "100 * elements_correct / elements_available",
                "unit": "percent",
                "direction": "higher_is_better",
            },
        },
        "compatibility_notes": {
            "communications_elements_available": 2,
            "usaarl_communications_elements_required": 3,
            "usaarl_resource_target_required": 2000,
            "experimenter_ranges": "Scores remain null when a required range is absent.",
        },
    }


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "FieldSpec",
    "SAMPLE_FIELDS",
    "TRIAL_FIELDS",
    "data_dictionary",
]
