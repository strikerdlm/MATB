"""Research experiment runner built on the existing dashboard."""

from __future__ import annotations

import os
import time
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path
from typing import Final

from rich.console import Console

from aircraft_monitor.events.base import Event, EventCategory, EventSeverity, create_event
from aircraft_monitor.events.fighter_events import FighterEventGenerator
from aircraft_monitor.events.uav_events import UAVEventGenerator
from aircraft_monitor.models.fighter import FighterAircraft, FighterType
from aircraft_monitor.models.uav import UAV, UAVMission, UAVType
from aircraft_monitor.research.logger import ResearchLogger, ResearchRunPaths
from aircraft_monitor.research.protocol import (
    AutomationMode,
    DemandBlock,
    ResearchModality,
    ResearchProtocol,
    WorkloadLevel,
)
from aircraft_monitor.visualization.dashboard import MonitoringDashboard

DEFAULT_RESEARCH_OUTPUT_DIR: Final[Path] = Path(
    os.environ.get("AIRCRAFT_MONITOR_OUTPUT_DIR", "/root/.openclaw/workspace/exports")
)


class ResearchExperimentRunner:
    """Run deterministic MATB-inspired aircraft monitoring experiments."""

    def __init__(
        self,
        *,
        event_delay: float,
        headless: bool | None,
        output_dir: Path = DEFAULT_RESEARCH_OUTPUT_DIR,
        console: Console | None = None,
    ) -> None:
        """Initialize the runner.

        Raises:
            ValueError: If event_delay is negative.
        """
        if event_delay < 0.0:
            raise ValueError("event_delay must be non-negative.")
        self._event_delay = event_delay
        self._headless = headless
        self._output_dir = output_dir
        self._console = console if console is not None else Console()

    def run_default_protocol(
        self,
        *,
        participant_id: str,
        session_id: str,
        modality: ResearchModality,
        seed: int,
    ) -> ResearchRunPaths:
        """Run the default low/medium/high research protocol."""
        protocol = ResearchProtocol.default(modality=modality, seed=seed)
        return self.run_protocol(
            participant_id=participant_id,
            session_id=session_id,
            protocol=protocol,
        )

    def run_protocol(
        self,
        *,
        participant_id: str,
        session_id: str,
        protocol: ResearchProtocol,
    ) -> ResearchRunPaths:
        """Run a protocol and write JSONL/summary outputs."""
        with ResearchLogger(
            output_dir=self._output_dir,
            participant_id=participant_id,
            session_id=session_id,
            protocol=protocol,
        ) as logger:
            for block_index, block in enumerate(protocol.blocks):
                self._console.print(
                    f"\n[bold cyan]Research block:[/bold cyan] {block.name} "
                    f"({block.workload.value}, automation={block.automation_mode.value})"
                )
                dashboard, events = self._build_dashboard_and_events(
                    modality=protocol.modality,
                    seed=protocol.seed + block_index,
                )
                instrumented_events = self._instrument_events(
                    block=block,
                    events=events,
                    logger=logger,
                )
                self._run_dashboard(
                    dashboard=dashboard,
                    modality=protocol.modality,
                    events=instrumented_events,
                )
            logger.write_summary()
            paths = logger.paths

        self._console.print(f"\n[green]Research events:[/green] {paths.events_jsonl}")
        self._console.print(f"[green]Research summary:[/green] {paths.summary_json}\n")
        return paths

    def _build_dashboard_and_events(
        self,
        *,
        modality: ResearchModality,
        seed: int,
    ) -> tuple[MonitoringDashboard, Generator[Event, None, None] | tuple[Generator[Event, None, None], Generator[Event, None, None]]]:
        """Create scenario state and event generators for one block."""
        dashboard = MonitoringDashboard(event_delay=self._event_delay, headless=self._headless)

        if modality == ResearchModality.UAS:
            uav = UAV(
                callsign="RESEARCH-UAS",
                uav_type=UAVType.RECONNAISSANCE,
                mission=UAVMission.ISR,
            )
            dashboard.set_uav(uav)
            return dashboard, UAVEventGenerator(uav, seed=seed).generate_full_mission()

        if modality == ResearchModality.FIGHTER:
            fighter = FighterAircraft(
                callsign="RESEARCH-FTR",
                tail_number="AF-R001",
                fighter_type=FighterType.MULTIROLE,
            )
            dashboard.set_fighter(fighter)
            return dashboard, FighterEventGenerator(fighter, seed=seed).generate_full_mission()

        uav = UAV(
            callsign="RESEARCH-UAS",
            uav_type=UAVType.RECONNAISSANCE,
            mission=UAVMission.ISR,
        )
        fighter = FighterAircraft(
            callsign="RESEARCH-FTR",
            tail_number="AF-R001",
            fighter_type=FighterType.MULTIROLE,
        )
        dashboard.set_uav(uav)
        dashboard.set_fighter(fighter)
        return (
            dashboard,
            (
                UAVEventGenerator(uav, seed=seed).generate_full_mission(),
                FighterEventGenerator(fighter, seed=seed + 10_000).generate_full_mission(),
            ),
        )

    def _run_dashboard(
        self,
        *,
        dashboard: MonitoringDashboard,
        modality: ResearchModality,
        events: Generator[Event, None, None] | tuple[Generator[Event, None, None], Generator[Event, None, None]],
    ) -> None:
        """Run the existing dashboard for one research block."""
        if modality == ResearchModality.UAS:
            if isinstance(events, tuple):
                raise TypeError("UAS modality expects one event stream.")
            dashboard.run_uav_simulation(events)
            return
        if modality == ResearchModality.FIGHTER:
            if isinstance(events, tuple):
                raise TypeError("Fighter modality expects one event stream.")
            dashboard.run_fighter_simulation(events)
            return
        if not isinstance(events, tuple):
            raise TypeError("Combined modality expects two event streams.")
        dashboard.run_combined_simulation(events[0], events[1])

    def _instrument_events(
        self,
        *,
        block: DemandBlock,
        events: Generator[Event, None, None] | tuple[Generator[Event, None, None], Generator[Event, None, None]],
        logger: ResearchLogger,
    ) -> Generator[Event, None, None] | tuple[Generator[Event, None, None], Generator[Event, None, None]]:
        """Wrap one or two event streams with research events and logging."""
        if isinstance(events, tuple):
            return (
                self._instrument_single_stream(
                    block=block,
                    events=events[0],
                    logger=logger,
                    stream_label="uas",
                ),
                self._instrument_single_stream(
                    block=block,
                    events=events[1],
                    logger=logger,
                    stream_label="fighter",
                ),
            )
        return self._instrument_single_stream(
            block=block,
            events=events,
            logger=logger,
            stream_label="primary",
        )

    def _instrument_single_stream(
        self,
        *,
        block: DemandBlock,
        events: Iterable[Event],
        logger: ResearchLogger,
        stream_label: str,
    ) -> Generator[Event, None, None]:
        """Inject MATB-style research events and log every emitted event."""
        start = time.monotonic()
        event_index = 0
        source_event_count = 0

        for startup_event in self._startup_events(block=block, stream_label=stream_label):
            event_index += 1
            logger.record_event(
                block=block,
                event=startup_event,
                event_index=event_index,
                monotonic_sec=time.monotonic() - start,
            )
            yield startup_event

        for source_event in self._take_bounded(events, limit=block.max_events):
            event_index += 1
            source_event_count += 1
            logger.record_event(
                block=block,
                event=source_event,
                event_index=event_index,
                monotonic_sec=time.monotonic() - start,
            )
            yield source_event

            if source_event_count % block.workload_probe_interval_events == 0:
                probe = self._workload_probe(block=block, stream_label=stream_label)
                event_index += 1
                logger.record_event(
                    block=block,
                    event=probe,
                    event_index=event_index,
                    monotonic_sec=time.monotonic() - start,
                )
                yield probe

        end_event = create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "RESEARCH BLOCK COMPLETE",
            f"{block.name} completed for stream {stream_label}",
            "RESEARCH",
            {
                "block": block.name,
                "stream": stream_label,
                "workload": block.workload.value,
            },
        )
        event_index += 1
        logger.record_event(
            block=block,
            event=end_event,
            event_index=event_index,
            monotonic_sec=time.monotonic() - start,
        )
        yield end_event

    @staticmethod
    def _take_bounded(events: Iterable[Event], *, limit: int) -> Iterator[Event]:
        """Yield no more than limit events."""
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        count = 0
        for event in events:
            yield event
            count += 1
            if count >= limit:
                return

    @staticmethod
    def _startup_events(block: DemandBlock, stream_label: str) -> tuple[Event, ...]:
        """Create block metadata events."""
        demand = create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "DEMAND BLOCK START",
            f"{block.name}: workload={block.workload.value}, response window={block.response_window_sec:.1f}s",
            "RESEARCH",
            {
                "block": block.name,
                "stream": stream_label,
                "workload": block.workload.value,
                "max_events": block.max_events,
                "probe_interval_events": block.workload_probe_interval_events,
            },
        )
        automation = create_event(
            EventSeverity.WARNING if block.automation_mode != AutomationMode.MANUAL else EventSeverity.INFO,
            EventCategory.SYSTEM,
            "AUTOMATION STATE",
            (
                f"mode={block.automation_mode.value}, "
                f"reliability={block.automation_reliability:.2f}"
            ),
            "RESEARCH",
            {
                "block": block.name,
                "stream": stream_label,
                "automation_mode": block.automation_mode.value,
                "automation_reliability": block.automation_reliability,
            },
        )
        return (demand, automation)

    @staticmethod
    def _workload_probe(block: DemandBlock, stream_label: str) -> Event:
        """Create an instantaneous workload assessment prompt event."""
        expected = {
            WorkloadLevel.LOW: 3,
            WorkloadLevel.MEDIUM: 6,
            WorkloadLevel.HIGH: 8,
        }[block.workload]
        return create_event(
            EventSeverity.WARNING,
            EventCategory.PILOT,
            "ISA WORKLOAD PROBE",
            (
                "Prompt operator for instantaneous workload rating "
                f"1-10 within {block.response_window_sec:.1f}s"
            ),
            "RESEARCH",
            {
                "block": block.name,
                "stream": stream_label,
                "scale": "ISA_1_10",
                "response_window_sec": block.response_window_sec,
                "expected_anchor": expected,
            },
        )
