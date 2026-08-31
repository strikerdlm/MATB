"""Tests for core.scenario - Scenario parsing and validation logic."""

from hashlib import sha256
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.event import Event
from core.scenario import Scenario


class TestScenarioProvenance:
    def test_source_digest_covers_the_complete_scenario_text(self):
        contents = ["# protocol\n", "0:00:00;sysmon;start\n", "0:01:00;sysmon;stop\n"]

        assert Scenario.source_sha256(contents) == sha256("".join(contents).encode("utf-8")).hexdigest()

    def test_source_digest_changes_when_an_experimental_command_changes(self):
        first = ["0:00:10;sysmon;alerttimeout;10000\n"]
        second = ["0:00:10;sysmon;alerttimeout;12000\n"]

        assert Scenario.source_sha256(first) != Scenario.source_sha256(second)

    def test_source_digest_preserves_programmatic_line_boundaries(self):
        assert Scenario.source_sha256(["a", "bc"]) != Scenario.source_sha256(["ab", "c"])

    @pytest.mark.parametrize("level", ["low", "medium", "high"])
    def test_committed_reference_scenarios_parse_with_the_tracked_event_parser(
        self, level
    ):
        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "scenarios" / "military_aviation" / f"{level}_workload.txt"
        )

        contents = scenario_path.read_text(encoding="utf-8").splitlines()
        events = [
            Event.parse_from_string(line_number, line)
            for line_number, line in enumerate(contents, start=1)
            if line.strip() and not line.startswith("#")
        ]
        scenario = _make_scenario(events=events)

        assert scenario.events
        assert scenario.get_plugins_name_list() == (
            "sysmon", "track", "resman", "communications", "genericscales"
        )
        assert all(event.time_sec >= 0 for event in events)


def _make_scenario(**kwargs):
    """Create a Scenario object bypassing __init__ to avoid file I/O."""
    s = object.__new__(Scenario)
    s.events = []
    s.plugins = {}
    s.__dict__.update(kwargs)
    return s


class TestGetPluginsNameList:
    def test_unique_names(self):
        """Extracts unique plugin names from events."""
        s = _make_scenario(
            events=[
                Event(1, 0, "sysmon", ["start"]),
                Event(2, 10, "sysmon", ["stop"]),
                Event(3, 0, "track", ["start"]),
            ]
        )
        names = s.get_plugins_name_list()
        assert names == ("sysmon", "track")

    def test_excludes_deprecated(self):
        """Filters out deprecated plugin names."""
        # DEPRECATED = ['pumpstatus', 'end', 'cutofffrequency', 'equalproportions']
        s = _make_scenario(
            events=[
                Event(1, 0, "sysmon", ["start"]),
                Event(2, 0, "pumpstatus", ["start"]),
            ]
        )
        names = s.get_plugins_name_list()
        assert "pumpstatus" not in names
        assert "sysmon" in names

    def test_empty_events(self):
        """Empty event list yields an empty stable sequence."""
        s = _make_scenario(events=[])
        names = s.get_plugins_name_list()
        assert names == ()

    def test_order_is_stable_across_python_hash_seeds(self):
        ordering_path = Path(__file__).resolve().parents[1] / "core" / "ordering.py"
        script = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('openmatb_ordering', {str(ordering_path)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(','.join(module.unique_in_order(['track', 'sysmon', 'track', 'communications'])))
"""
        outputs = []
        for seed in ("1", "777"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            outputs.append(completed.stdout.strip())
        assert outputs == [
            "track,sysmon,communications",
            "track,sysmon,communications",
        ]


class TestGetPluginEvents:
    def test_filters_by_name(self):
        """Returns only events matching the plugin name."""
        events = [
            Event(1, 0, "sysmon", ["start"]),
            Event(2, 10, "track", ["start"]),
            Event(3, 20, "sysmon", ["stop"]),
        ]
        s = _make_scenario(events=events)
        result = s.get_plugin_events("sysmon")
        assert len(result) == 2
        assert all(e.plugin == "sysmon" for e in result)

    def test_empty_for_unknown(self):
        """Unknown plugin returns empty list."""
        s = _make_scenario(events=[Event(1, 0, "sysmon", ["start"])])
        result = s.get_plugin_events("nonexistent")
        assert result == []

    def test_returns_all_matching(self):
        """Returns all events for a given plugin."""
        events = [
            Event(1, 0, "track", ["start"]),
            Event(2, 10, "track", ["stop"]),
        ]
        s = _make_scenario(events=events)
        result = s.get_plugin_events("track")
        assert len(result) == 2


class TestEventsRetrocompatibility:
    def test_normal_event_preserved(self):
        """Non-deprecated events pass through."""
        events = [Event(1, 0, "sysmon", ["start"])]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        assert len(result) == 1
        assert result[0].command == ["start"]

    def test_deprecated_event_removed(self):
        """Deprecated commands are filtered out."""
        events = [
            Event(1, 0, "sysmon", ["pumpstatus"]),  # deprecated command
            Event(2, 10, "sysmon", ["start"]),
        ]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        assert len(result) == 1
        assert result[0].command == ["start"]

    def test_deprecated_event_warns(self, mock_errors):
        """Deprecated events trigger a non-fatal warning via get_errors()."""
        events = [
            Event(1, 0, "sysmon", ["pumpstatus"]),  # deprecated command
            Event(2, 0, "pumpstatus", ["start"]),    # deprecated plugin
        ]
        s = _make_scenario(events=events)
        s.events_retrocompatibility()
        assert mock_errors.add_error.call_count == 2
        for call in mock_errors.add_error.call_args_list:
            assert "deprecated" in call.args[0]
            assert call.kwargs["fatal"] is False

    def test_sysmon_scale_failure_up_splits(self):
        """Scale failure 'up' splits into failure+side events."""
        events = [Event(1, 10, "sysmon", ["scales-scale1-failure", "up"])]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        assert len(result) == 2
        assert result[0].command == ["scales-scale1-failure", "True"]
        assert result[1].command == ["scales-scale1-side", "1"]

    def test_sysmon_scale_failure_down_splits(self):
        """Scale failure 'down' splits into failure+side events."""
        events = [Event(1, 10, "sysmon", ["scales-scale1-failure", "down"])]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        assert len(result) == 2
        assert result[0].command == ["scales-scale1-failure", "True"]
        assert result[1].command == ["scales-scale1-side", "-1"]

    def test_preserves_time_and_plugin(self):
        """Split events keep original line, time, plugin."""
        events = [Event(5, 30, "sysmon", ["scales-s1-failure", "up"])]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        for e in result:
            assert e.line == 5
            assert e.time_sec == 30
            assert e.plugin == "sysmon"

    def test_mixed_events(self):
        """Mixed deprecated/normal/split events processed correctly."""
        events = [
            Event(1, 0, "sysmon", ["start"]),
            Event(2, 5, "sysmon", ["pumpstatus"]),  # deprecated command
            Event(3, 10, "sysmon", ["scales-s1-failure", "up"]),
            Event(4, 20, "track", ["start"]),
        ]
        s = _make_scenario(events=events)
        result = s.events_retrocompatibility()
        # start (kept) + pumpstatus (deprecated, removed) + failure (split to 2) + track (kept)
        assert len(result) == 4
        assert result[0].command == ["start"]
        assert result[1].command == ["scales-s1-failure", "True"]
        assert result[2].command == ["scales-s1-side", "1"]
        assert result[3].command == ["start"]


class TestGetParametersValue:
    def test_simple_parameter(self):
        """Retrieves a top-level parameter value."""
        mock_plugin = MagicMock()
        mock_plugin.parameters = {"title": "Test", "taskupdatetime": 100}
        s = _make_scenario(plugins={"sysmon": mock_plugin})
        val, exists = s.get_parameters_value("sysmon", ["title", "New"])
        assert exists is True
        assert val == "Test"

    def test_nested_parameter(self):
        """Retrieves a nested (dash-separated) parameter."""
        mock_plugin = MagicMock()
        mock_plugin.parameters = {"taskfeedback": {"overdue": {"active": False, "delayms": 2000}}}
        s = _make_scenario(plugins={"sysmon": mock_plugin})
        val, exists = s.get_parameters_value("sysmon", ["taskfeedback-overdue-active", "True"])
        assert exists is True
        assert val is False

    def test_nonexistent_parameter(self):
        """Missing parameter returns (None, False)."""
        mock_plugin = MagicMock()
        mock_plugin.parameters = {"title": "Test"}
        s = _make_scenario(plugins={"sysmon": mock_plugin})
        val, exists = s.get_parameters_value("sysmon", ["nonexistent", "val"])
        assert exists is False
        assert val is None

    def test_nonexistent_nested(self):
        """Missing nested key returns (None, False)."""
        mock_plugin = MagicMock()
        mock_plugin.parameters = {"taskfeedback": {"overdue": {"active": False}}}
        s = _make_scenario(plugins={"sysmon": mock_plugin})
        val, exists = s.get_parameters_value("sysmon", ["taskfeedback-missing-key", "val"])
        assert exists is False
        assert val is None


class TestGetValidationDict:
    def test_does_not_pollute_global_dict(self):
        """Calling get_validation_dict() for a plugin must not mutate the global dict."""
        from core.scenario import global_validation_dict

        original_keys = set(global_validation_dict.keys())

        mock_plugin = MagicMock()
        mock_plugin.validation_dict = {"custom_param": lambda x: (x, None)}
        s = _make_scenario(plugins={"comms": mock_plugin})

        result = s.get_validation_dict("comms")

        # The returned dict should contain the plugin key
        assert "custom_param" in result
        # The global dict must NOT have been mutated
        assert set(global_validation_dict.keys()) == original_keys
        assert "custom_param" not in global_validation_dict

    def test_includes_global_and_plugin_keys(self):
        """Returned dict merges global validators with plugin-specific ones."""
        mock_plugin = MagicMock()
        mock_plugin.validation_dict = {"plugin_key": lambda x: (x, None)}
        s = _make_scenario(plugins={"comms": mock_plugin})

        result = s.get_validation_dict("comms")
        # Should have both global keys (e.g. 'title') and the plugin key
        assert "title" in result
        assert "plugin_key" in result

    def test_no_plugin_validation_dict(self):
        """Plugin with no validation_dict returns only global validators."""
        from core.scenario import global_validation_dict

        mock_plugin = MagicMock(spec=[])  # no attributes at all
        s = _make_scenario(plugins={"track": mock_plugin})

        result = s.get_validation_dict("track")
        assert set(result.keys()) == set(global_validation_dict.keys())


class TestGetPluginMethods:
    def test_returns_callable_names(self):
        """Lists callable method names of a plugin."""
        mock_plugin = MagicMock()
        mock_plugin.start = lambda: None
        mock_plugin.stop = lambda: None
        s = _make_scenario(plugins={"sysmon": mock_plugin})
        methods = s.get_plugin_methods("sysmon")
        assert "start" in methods
        assert "stop" in methods
