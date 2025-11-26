# Copyright 2025, by OpenMATB contributors.
# Utility script to emit reference scenarios with configurable difficulty.

"""Scenario Template Generator

This module generates predefined scenario templates for UAS and HPA use cases.
It supports configurable difficulty levels (1-10) that adjust:
- Event frequency
- Time pressure (deadlines)
- Number of concurrent tasks
- Failure injection rates

Usage:
    python scenario_templates.py --template uas_bvlos --difficulty 5 --duration 300 --output scenario.txt
    python scenario_templates.py --template hpa_overlay --difficulty 8 --duration 180 --output scenario.txt
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class DifficultyProfile:
    """Encapsulates difficulty-dependent parameters."""

    level: int  # 1-10
    event_interval: int  # seconds between events
    deadline_factor: float  # multiplier for time limits (lower = harder)
    concurrent_tasks: int  # max simultaneous tasks
    failure_rate: float  # probability of failure injection per minute

    @classmethod
    def from_level(cls, level: int) -> 'DifficultyProfile':
        """Create a profile from a 1-10 difficulty level."""
        level = max(1, min(10, level))
        # Level 1: easy (long intervals, generous deadlines)
        # Level 10: hard (short intervals, tight deadlines)
        event_interval = max(20, 90 - (level * 7))
        deadline_factor = 1.5 - (level * 0.1)  # 1.4 at level 1, 0.5 at level 10
        concurrent_tasks = min(6, 2 + (level // 2))
        failure_rate = level * 0.1  # 0.1 at level 1, 1.0 at level 10
        return cls(
            level=level,
            event_interval=event_interval,
            deadline_factor=max(0.3, deadline_factor),
            concurrent_tasks=concurrent_tasks,
            failure_rate=failure_rate,
        )


def format_time(seconds: int) -> str:
    """Format seconds as H:MM:SS."""
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, sec = divmod(remainder, 60)
    return f'{hours}:{minutes:02d}:{sec:02d}'


def generate_uas_bvlos(duration: int, profile: DifficultyProfile) -> List[str]:
    """Generate a UAS BVLOS scenario with difficulty scaling."""
    duration = max(duration, 60 * 5)
    events: List[str] = [
        '# UAS BVLOS Scenario',
        f'# Difficulty Level: {profile.level}/10',
        f'# Event Interval: {profile.event_interval}s',
        f'# Deadline Factor: {profile.deadline_factor:.1f}',
        '',
        '0:00:00;sysmon;start',
        '0:00:00;track;start',
        '0:00:00;resman;start',
        '0:00:00;communications;start',
        '0:00:02;missiondirector;start',
        '0:00:02;senseandavoid;start',
        '0:00:02;payloadmanager;start',
        '0:00:02;datalink;start',
        '0:00:02;physiomonitor;start',
        '0:00:02;polarrlink;start',
        '0:00:02;compositescore;start',
    ]

    timeline = 5
    mission_index = 1
    intruder_index = 1
    message_index = 1

    while timeline < duration - 60:
        # Mission assignment
        mission_duration = int(180 * profile.deadline_factor + mission_index * 30)
        events.append(
            f'{format_time(timeline)};missiondirector;assign;UAV{(mission_index % 4) + 1},'
            f'Task-{mission_index},{mission_duration}'
        )

        # Payload activation
        payload_deadline = int(18 * profile.deadline_factor)
        events.append(
            f'{format_time(timeline + 10)};payloadmanager;activate;CamA,Target-{mission_index},{payload_deadline}'
        )

        # Sense and avoid intruder
        tti = int(35 * profile.deadline_factor)
        events.append(
            f'{format_time(timeline + 20)};senseandavoid;spawn;INT{intruder_index},090,2.0,150,{tti}'
        )

        # Datalink message with difficulty-scaled deadline
        msg_deadline = int(30 * profile.deadline_factor)
        events.append(
            f'{format_time(timeline + 25)};datalink;message;MSG{message_index},ATC,PRIO,'
            f'Acknowledge waypoint {mission_index},{msg_deadline}'
        )

        # Conflict injection at higher difficulties
        if profile.level >= 5 and mission_index % 2 == 0:
            events.append(
                f'{format_time(timeline + 30)};missiondirector;conflict;UAV{(mission_index % 4) + 1},airspace'
            )
            events.append(
                f'{format_time(timeline + 45)};missiondirector;clearconflict;UAV{(mission_index % 4) + 1}'
            )

        mission_index += 1
        intruder_index += 1
        message_index += 1
        timeline += profile.event_interval

    # Cleanup and stop
    end = format_time(duration)
    events.extend([
        '',
        f'# Scenario End',
        f'{end};compositescore;stop',
        f'{end};polarrlink;stop',
        f'{end};physiomonitor;stop',
        f'{end};datalink;stop',
        f'{end};payloadmanager;stop',
        f'{end};senseandavoid;stop',
        f'{end};missiondirector;stop',
        f'{end};communications;stop',
        f'{end};resman;stop',
        f'{end};track;stop',
        f'{end};sysmon;stop',
    ])
    return events


def generate_hpa_overlay(duration: int, profile: DifficultyProfile) -> List[str]:
    """Generate an HPA overlay scenario with difficulty scaling."""
    duration = max(duration, 180)
    events: List[str] = [
        '# HPA Overlay Scenario',
        f'# Difficulty Level: {profile.level}/10',
        f'# Event Interval: {profile.event_interval}s',
        f'# Deadline Factor: {profile.deadline_factor:.1f}',
        '',
        '0:00:00;sysmon;start',
        '0:00:00;track;start',
        '0:00:00;resman;start',
        '0:00:00;communications;start',
        '0:00:02;energymanager;start',
        '0:00:02;threatboard;start',
        '0:00:02;datalink;start',
        '0:00:02;physiomonitor;start',
        '0:00:02;physiooverlay;start',
        '0:00:02;emergencystack;start',
        '0:00:02;failureinjector;start',
        '0:00:02;compositescore;start',
    ]

    # Schedule emergency based on difficulty
    if profile.level >= 3:
        events.append(
            f'0:00:30;failureinjector;schedule;emergencystack,trigger,'
            f'HYD1|HYD PRESS LOW|Switch pumps|Check breakers,{int(10 * profile.deadline_factor)}'
        )

    # Energy events with difficulty-scaled G-loads
    timeline = 5
    event_names = ['ENTRY', 'SETUP', 'ENGAGE', 'REPOSITION', 'DEFENSIVE', 'EGRESS']
    g_loads = [3.5, 4.2, 5.5, 2.8, 6.0, 3.0]
    event_idx = 0
    threat_idx = 1
    msg_idx = 1

    while timeline < duration - 30:
        if event_idx < len(event_names):
            g_load = g_loads[event_idx] + (profile.level * 0.1)
            event_duration = int(30 * profile.deadline_factor)
            events.append(
                f'{format_time(timeline)};energymanager;event;{event_names[event_idx]},{g_load:.1f},{event_duration}'
            )
            event_idx += 1

        # Threat spawning
        tti = int(45 * profile.deadline_factor)
        weapons = ['R73', 'AIM9', 'GUN', 'R77', 'AIM120']
        weapon = weapons[threat_idx % len(weapons)]
        events.append(
            f'{format_time(timeline + 10)};threatboard;spawn;TH{threat_idx},'
            f'{(threat_idx * 45) % 360:03d},{14 - threat_idx},{weapon},{tti}'
        )

        # Datalink message
        msg_deadline = int(25 * profile.deadline_factor)
        events.append(
            f'{format_time(timeline + 15)};datalink;message;HPA{msg_idx},AWACS,PRIO,'
            f'Bandit {threat_idx} o clock,{msg_deadline}'
        )

        # Engage and resolve threat
        events.append(f'{format_time(timeline + 20)};threatboard;engage;TH{threat_idx},FOX3')
        events.append(f'{format_time(timeline + 30)};threatboard;resolve;TH{threat_idx},SPLASH')

        # Over-G warning at higher difficulties
        if profile.level >= 6 and threat_idx % 2 == 0:
            events.append(f'{format_time(timeline + 25)};energymanager;overg;{6.0 + profile.level * 0.2:.1f}')

        # Physio overlay stress effect at high difficulties
        if profile.level >= 7 and threat_idx % 3 == 0:
            overlay_duration = int(8 * profile.deadline_factor)
            events.append(
                f'{format_time(timeline + 22)};physiooverlay;apply;#000000AA,{overlay_duration}'
            )

        threat_idx += 1
        msg_idx += 1
        timeline += profile.event_interval

    # Cleanup
    end = format_time(duration)
    events.extend([
        '',
        f'{end};compositescore;stop',
        f'{end};failureinjector;stop',
        f'{end};physiooverlay;stop',
        f'{end};emergencystack;stop',
        f'{end};physiomonitor;stop',
        f'{end};datalink;stop',
        f'{end};threatboard;stop',
        f'{end};energymanager;stop',
        f'{end};communications;stop',
        f'{end};resman;stop',
        f'{end};track;stop',
        f'{end};sysmon;stop',
    ])
    return events


def generate_training(duration: int, profile: DifficultyProfile) -> List[str]:
    """Generate an automated training scenario."""
    duration = max(duration, 420)  # Minimum 7 minutes
    events: List[str] = [
        '# Automated Training Scenario',
        f'# Duration: {duration}s',
        '',
        '0:00:00;autotraining;start',
    ]

    phase_duration = duration // 5
    events.append(f'0:00:05;autotraining;phase;tracking')
    events.append(f'{format_time(phase_duration)};autotraining;phase;sysmon')
    events.append(f'{format_time(phase_duration * 2)};autotraining;phase;communications')
    events.append(f'{format_time(phase_duration * 3)};autotraining;phase;resman')
    events.append(f'{format_time(phase_duration * 4)};autotraining;phase;combined')

    end = format_time(duration)
    events.append(f'{end};autotraining;stop')
    return events


def write_scenario(path: Path, events: List[str]) -> None:
    """Write scenario events to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for line in events:
            handle.write(f'{line}\n')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate predefined scenario templates with difficulty scaling.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scenario_templates.py --template uas_bvlos --difficulty 5 --duration 300 --output uas_med.txt
    python scenario_templates.py --template hpa_overlay --difficulty 8 --duration 180 --output hpa_hard.txt
    python scenario_templates.py --template training --duration 420 --output training.txt
        """
    )
    parser.add_argument(
        '--template',
        choices=['uas_bvlos', 'hpa_overlay', 'training'],
        required=True,
        help='Scenario template type'
    )
    parser.add_argument(
        '--difficulty',
        type=int,
        default=5,
        help='Difficulty level (1-10, default: 5)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=300,
        help='Scenario duration in seconds (default: 300)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output file path'
    )
    args = parser.parse_args()

    profile = DifficultyProfile.from_level(args.difficulty)

    if args.template == 'uas_bvlos':
        events = generate_uas_bvlos(args.duration, profile)
    elif args.template == 'hpa_overlay':
        events = generate_hpa_overlay(args.duration, profile)
    else:
        events = generate_training(args.duration, profile)

    write_scenario(args.output, events)
    print(f'Scenario written to {args.output}')
    print(f'  Template: {args.template}')
    print(f'  Difficulty: {profile.level}/10')
    print(f'  Duration: {args.duration}s')
    print(f'  Event interval: {profile.event_interval}s')
    print(f'  Deadline factor: {profile.deadline_factor:.1f}')


if __name__ == '__main__':
    main()
