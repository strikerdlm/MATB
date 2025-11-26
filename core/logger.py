# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import hashlib
import json
import shutil
import subprocess
from collections import namedtuple
from time import perf_counter
from datetime import datetime
from csv import DictWriter
from pathlib import Path
from typing import Any, Dict, Optional
from core.constants import PATHS, REPLAY_MODE
from core.utils import find_the_first_available_session_number
from core.performance_summary import PerformanceAggregator

class Logger:
    def __init__(self):
        self.datetime = datetime.now()
        self.fields_list = ['logtime', 'scenario_time', 'type', 'module', 'address', 'value']
        self.slot = namedtuple('Row', self.fields_list)
        self.maxfloats = 6  # Time logged at microsecond precision
        self.session_id = None
        self.lsl = None

        self.session_id = find_the_first_available_session_number()
        self.mode = 'w'

        self.scenario_time = 0  # Updated by the scheduler class

        self.file = None
        self.writer = None
        self.queue = list()
        self.path: Optional[Path] = None
        self.summary_path: Optional[Path] = None
        self.markdown_path: Optional[Path] = None
        self.session_dir: Optional[Path] = None
        self.performance_summary = PerformanceAggregator()
        self._artifacts_captured = False
        self.provenance_info: Dict[str, Optional[str]] = {}
        self._provenance_version = 0

        if not REPLAY_MODE:
            self.session_dir = PATHS['SESSIONS'].joinpath(
                self.datetime.strftime("%Y-%m-%d"),
                f'{self.session_id}_{self.datetime.strftime("%y%m%d_%H%M%S")}',
            )
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.path = self.session_dir / 'events.csv'
            self.summary_path = self.session_dir / 'summary.json'
            self.markdown_path = self.session_dir / 'summary.md'
            self.open()

    # TODO: see if we can/should merge record_* methods into one
    def record_event(self, event):
        if len(event.command) == 1:
            adress = 'self'
            value = event.command[0]
        elif len(event.command) == 2:
            adress = event.command[0]
            value = event.command[1]
        slot = [perf_counter(), self.scenario_time, 'event', event.plugin, adress, value]
        self.write_single_slot(slot)


    def record_input(self, module, key, state):
        slot = [perf_counter(), self.scenario_time, 'input', module, key, state]
        self.write_single_slot(slot)


    def record_aoi(self, container, name):
        plugin = name.split('_')[0]
        widget = '_'.join(name.split('_')[1:])
        slot = [perf_counter(), self.scenario_time, 'aoi', plugin, widget, container.get_x1y1x2y2()]
        self.write_single_slot(slot)


    def record_state(self, graph_name, attribute, value):
        module = graph_name.split('_')[0]
        graph_name = '_'.join(graph_name.split('_')[1:])
        address = f'{graph_name}, {attribute}'
        slot = [perf_counter(), self.scenario_time, 'state', module, address, value]
        self.write_single_slot(slot)


    def record_parameter(self, plugin, address, value):
        slot = [perf_counter(), self.scenario_time, 'parameter', plugin, address, value]
        self.write_single_slot(slot)

    def record_scenario_version(self, scenario_path: str, version_hash: str) -> None:
        """Record scenario file version for experiment reproducibility."""
        slot = [perf_counter(), self.scenario_time, 'version', 'scenario', scenario_path, version_hash]
        self.write_single_slot(slot)

    def record_config_snapshot(self, plugin: str, config: Dict[str, Any]) -> None:
        """Record a plugin's full configuration snapshot."""
        config_str = json.dumps(config, default=str, sort_keys=True)
        slot = [perf_counter(), self.scenario_time, 'config', plugin, 'snapshot', config_str]
        self.write_single_slot(slot)

    def capture_run_artifacts(self, scenario_path: Optional[Path]) -> None:
        """Persist scenario/config snapshots and plugin versions for reproducibility."""
        if self.session_dir is None or self._artifacts_captured:
            return

        scenario_hash_value: Optional[str] = None
        scenario_name = 'n/a'
        scenario_path_obj = Path(scenario_path) if scenario_path is not None else None

        if scenario_path_obj is not None and scenario_path_obj.exists():
            dest = self.session_dir.joinpath('scenario_snapshot.txt')
            shutil.copy2(scenario_path_obj, dest)
            scenario_hash_value = self._hash_file(scenario_path_obj)
            hash_path = self.session_dir.joinpath('scenario_hash.txt')
            hash_path.write_text(f'{scenario_hash_value}\n', encoding='utf-8')
            self.record_scenario_version(str(scenario_path_obj), scenario_hash_value)
            scenario_name = scenario_path_obj.name

        config_path = PATHS['PLUGINS'].parent.joinpath('config.ini')
        config_snapshot_path: Optional[Path] = None
        if config_path.exists():
            config_snapshot_path = self.session_dir.joinpath('config_snapshot.ini')
            shutil.copy2(config_path, config_snapshot_path)

        plugin_versions_path = self.session_dir.joinpath('plugin_versions.json')
        self._write_plugin_versions(plugin_versions_path)
        self._artifacts_captured = True

        self.provenance_info = {
            'scenario': scenario_name,
            'scenario_hash': scenario_hash_value,
            'session_dir': str(self.session_dir) if self.session_dir else None,
            'config_snapshot': str(config_snapshot_path) if config_snapshot_path else None,
            'plugin_versions': str(plugin_versions_path),
            'summary_json': str(self.summary_path) if self.summary_path else None,
            'summary_markdown': str(self.markdown_path) if self.markdown_path else None,
        }
        self._provenance_version += 1


    def log_performance(self, module, metric, value):
        slot = [perf_counter(), self.scenario_time, 'performance', module, metric, value]
        self.write_single_slot(slot)
        self.performance_summary.record(module, metric, value)


    def record_a_pseudorandom_value(self, module, seed, output):
        slot = [perf_counter(), self.scenario_time, 'seed_value', module, '', seed]
        self.write_single_slot(slot)
        slot = [perf_counter(), self.scenario_time, 'seed_output', module, '', output]
        self.write_single_slot(slot)


    def log_manual_entry(self, entry, key='manual'):
        slot = [perf_counter(), self.scenario_time, key, '', '', entry]
        self.write_single_slot(slot)


    def __enter__(self):
        self.open()
        return self


    def __exit__(self, type, value, traceback):
        self.file.close()


    def open(self):
        create_header = False if self.path.exists() and self.mode == 'a' else True
        self.file = open(str(self.path), self.mode, newline = '')
        self.writer = DictWriter(self.file, fieldnames=self.fields_list)
        if create_header:
            self.writer.writeheader()


    def close(self):
        self.file.close()


    def add_row_to_queue(self, row):
        self.queue.append(row)


    def empty_queue(self):
        self.queue = list()


    def round_row(self, row):
        new_list = list()
        for col in row:
            new_value = round(col, self.maxfloats) if isinstance(col, float) or isinstance(col, int) else col
            new_list.append(new_value)
        return self.slot(*new_list)


    def write_row_queue(self, change_dict=None):
        if not REPLAY_MODE:
            if len(self.queue) == 0:
                print(_('Warning, queue is empty'))
            else:
                for this_row in self.queue:
                    row_dict = self.round_row(this_row)._asdict()
                    if change_dict is not None:
                        for k,v in change_dict.items():
                            row_dict[k] = v
                    self.writer.writerow(row_dict)
                    if self.lsl is not None:
                        self.lsl.push(';'.join([str(r) for r in row_dict.values()]))
                self.empty_queue()


    def write_single_slot(self, values):
        row = self.slot(*values)
        self.add_row_to_queue(row)
        self.write_row_queue()


    def set_totaltime(self, totaltime):
        self.totaltime = totaltime


    def set_scenario_time(self, scenario_time):
        self.scenario_time = scenario_time
        self.performance_summary.update_scenario_time(scenario_time)


    def start_performance_summary(
        self,
        scenario_label: Optional[str] = None,
        scenario_version: Optional[str] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise performance summary with optional versioning and config snapshot.

        Args:
            scenario_label: Human-readable scenario name.
            scenario_version: Semantic version or hash of the scenario file.
            config_snapshot: Dictionary of plugin configurations for reproducibility.
        """
        metadata: Dict[str, Any] = {'session_id': self.session_id}
        if scenario_label:
            metadata['scenario'] = scenario_label
        if scenario_version:
            metadata['scenario_version'] = scenario_version
        if config_snapshot:
            metadata['config_snapshot'] = config_snapshot
        if self.path is not None:
            metadata['log_path'] = str(self.path)
        self.performance_summary.reset(metadata)


    def finalize_performance_summary(self) -> None:
        if self.summary_path is None:
            return
        try:
            self.performance_summary.export(self.summary_path)
            if self.markdown_path is not None:
                self.performance_summary.export_markdown(self.markdown_path)
        except OSError as exc:
            self.log_manual_entry(f'Unable to write performance summary: {exc}', key='error')

    def persist_scenario_contents(self, contents) -> Optional[Path]:
        """Persist inline scenario contents so artifacts can be captured."""
        if self.session_dir is None or contents is None:
            return None
        scenario_file = self.session_dir.joinpath('scenario_inline.txt')
        if isinstance(contents, str):
            text = contents
        else:
            text = ''.join(contents)
        scenario_file.write_text(text, encoding='utf-8')
        return scenario_file

    def get_provenance_snapshot(self) -> tuple[Dict[str, Optional[str]], int]:
        """Expose current provenance info and version counter."""
        return dict(self.provenance_info), self._provenance_version

    def _write_plugin_versions(self, target: Path) -> None:
        versions: Dict[str, str] = {}
        plugins_dir = PATHS.get('PLUGINS')
        if plugins_dir and plugins_dir.exists():
            for plugin_file in sorted(plugins_dir.glob('*.py')):
                if plugin_file.name.startswith('__'):
                    continue
                versions[plugin_file.stem] = self._git_revision_for(plugin_file)
        target.write_text(json.dumps(versions, indent=2, sort_keys=True), encoding='utf-8')

    @staticmethod
    def _hash_file(source: Path) -> str:
        digest = hashlib.sha256()
        with source.open('rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _git_revision_for(path: Path) -> str:
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--pretty=%H', '--', str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            revision = result.stdout.strip()
            return revision or 'unknown'
        except (subprocess.SubprocessError, FileNotFoundError):
            return 'unknown'


logger = Logger()