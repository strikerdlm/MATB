# Copyright 2025, by OpenMATB contributors.
# Utility script to emit reference scenarios.

import argparse
from pathlib import Path


def format_time(seconds: int) -> str:
    minutes, sec = divmod(max(0, seconds), 60)
    return f'{minutes:02d}:{sec:02d}'


def generate_uas_bvlos(duration: int) -> list[str]:
    duration = max(duration, 60 * 5)
    events = [
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
    ]
    timeline = 5
    mission_index = 1
    while timeline < duration - 60:
        events.append(f'{format_time(timeline)};missiondirector;assign;UAV{mission_index},Task-{mission_index},{180 + mission_index*30}')
        events.append(f'{format_time(timeline + 10)};payloadmanager;activate;CamA,Target-{mission_index},18')
        events.append(f'{format_time(timeline + 25)};senseandavoid;spawn;INT{mission_index},090,2.0,150,35')
        mission_index = (mission_index % 3) + 1
        timeline += 60
    end = format_time(duration)
    events.extend([
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


def generate_hpa_overlay(duration: int) -> list[str]:
    duration = max(duration, 180)
    events = [
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
    ]
    events.append('0:00:30;failureinjector;schedule;emergencystack,trigger,HYD1|HYD PRESS LOW|Switch pumps|Check breakers,10')
    events.append('0:00:45;failureinjector;schedule;physiooverlay,apply,#000000AA|8,0')
    events.append('0:00:50;failureinjector;schedule;threatboard,spawn,TH1|035|14|R73|45,0')
    events.append('0:01:10;failureinjector;schedule;threatboard,engage,TH1|FOX3,0')
    events.append('0:01:25;failureinjector;schedule;threatboard,resolve,TH1|SPLASH,0')
    end = format_time(duration)
    events.extend([
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


def write_scenario(path: Path, events: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as handle:
        handle.write("# Generated template\n")
        for line in events:
            handle.write(f'{line}\n')


def main():
    parser = argparse.ArgumentParser(description='Generate predefined scenario templates.')
    parser.add_argument('--template', choices=['uas_bvlos', 'hpa_overlay'], required=True)
    parser.add_argument('--duration', type=int, default=300, help='Scenario duration in seconds')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    if args.template == 'uas_bvlos':
        events = generate_uas_bvlos(args.duration)
    else:
        events = generate_hpa_overlay(args.duration)
    write_scenario(args.output, events)
    print(f'Scenario written to {args.output}')


if __name__ == '__main__':
    main()

