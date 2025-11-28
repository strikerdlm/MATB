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


def generate_hrv_combat(duration: int, profile: DifficultyProfile) -> List[str]:
    """Generate a combat scenario with HRV integration and adaptive automation.
    
    This template implements the RT-HRV combat integration roadmap from Manual.md
    Section 18, including:
    - Baseline HRV calibration phase
    - Progressive workload ladder (fighter + UAV)
    - HRV-triggered automation rules
    - Overload detection and response
    
    Args:
        duration: Total scenario duration in seconds.
        profile: Difficulty profile for workload scaling.
        
    Returns:
        List of scenario event strings.
    """
    duration = max(duration, 600)  # Minimum 10 minutes for proper HRV assessment
    baseline_duration = 120  # 2 minutes for baseline calibration
    
    events: List[str] = [
        '# HRV Combat Integration Scenario',
        f'# Difficulty Level: {profile.level}/10',
        f'# Duration: {duration}s (includes {baseline_duration}s baseline)',
        f'# Event Interval: {profile.event_interval}s',
        f'# Deadline Factor: {profile.deadline_factor:.1f}',
        '#',
        '# Research Reference: Manual.md Section 18',
        '# - Durantin et al. 2014: Overload detection via LF/HF reversal',
        '# - Koskelo et al. 2024: Military flight HRV patterns',
        '',
        '# ============================================',
        '# PHASE 1: BASELINE CALIBRATION (0-2 min)',
        '# ============================================',
        '# Low workload period for HRV baseline collection',
        '',
        '# Start physiological monitoring first',
        '0:00:00;polarrlink;start',
        '0:00:01;physiomonitor;start',
        '0:00:02;physiomonitor;baseline;start',
        '',
        '# Start basic MATB tasks at low difficulty',
        '0:00:05;sysmon;start',
        '0:00:05;track;start',
        '0:00:05;resman;start',
        '0:00:05;communications;start',
        '',
        '# Minimal events during baseline',
        '0:00:30;communications;radioprompt;OWN,118.0,1',
        '0:01:00;sysmon;automaticsolver;True',
        '0:01:30;communications;radioprompt;OWN,124.5,1',
        '',
        '# End baseline collection',
        f'{format_time(baseline_duration)};physiomonitor;baseline;stop',
        '',
        '# ============================================',
        '# PHASE 2: COMBAT SYSTEMS ACTIVATION',
        '# ============================================',
        '',
        f'{format_time(baseline_duration + 5)};sysmon;automaticsolver;False',
        f'{format_time(baseline_duration + 5)};energymanager;start',
        f'{format_time(baseline_duration + 5)};threatboard;start',
        f'{format_time(baseline_duration + 5)};weaponsinventory;start',
        f'{format_time(baseline_duration + 5)};missiondirector;start',
        f'{format_time(baseline_duration + 5)};senseandavoid;start',
        f'{format_time(baseline_duration + 5)};datalink;start',
        f'{format_time(baseline_duration + 5)};emergencystack;start',
        f'{format_time(baseline_duration + 5)};compositescore;start',
        f'{format_time(baseline_duration + 5)};automationhooks;start',
        '',
        '# Initialize weapons loadout',
        f'{format_time(baseline_duration + 10)};weaponsinventory;load;AIM9,4',
        f'{format_time(baseline_duration + 10)};weaponsinventory;load;AIM120,6',
        f'{format_time(baseline_duration + 10)};threatboard;countermeasure;chaff,20',
        f'{format_time(baseline_duration + 10)};threatboard;countermeasure;flare,20',
        '',
        '# ============================================',
        '# HRV-TRIGGERED AUTOMATION RULES',
        '# ============================================',
        '# These rules implement adaptive automation based on physiological state',
        '',
        '# Rule 1: When RMSSD z-score drops below -1.5 (high workload)',
        '# -> Enable Mission Director auto mode to reduce cognitive load',
        f'{format_time(baseline_duration + 15)};automationhooks;rule;'
        'physiomonitor,hrv_rmssd_zscore,lt,-1.5,AUTO,target=missiondirector,command=automation,payload=uav1,auto,cooldown=30',
        '',
        '# Rule 2: When LF/HF ratio exceeds baseline + 50%',
        '# -> Extend datalink deadlines',
        f'{format_time(baseline_duration + 15)};automationhooks;rule;'
        'physiomonitor,hrv_lf_hf,gt,2.5,EXTEND,target=datalink,command=deadline_multiplier,payload=1.5,cooldown=60',
        '',
        '# Rule 3: When overload is detected (LF/HF reversal pattern)',
        '# -> Pause non-critical tasks',
        f'{format_time(baseline_duration + 15)};automationhooks;rule;'
        'physiomonitor,hrv_workload,eq,overload,PAUSE,target=payloadmanager,command=standby,payload=all,cooldown=45',
        '',
        '# Enable automation hooks',
        f'{format_time(baseline_duration + 20)};automationhooks;enable;1',
        '',
    ]
    
    # Generate progressive workload phases
    timeline = baseline_duration + 30
    phase_duration = (duration - baseline_duration - 60) // 4
    
    # PHASE 3: LOW WORKLOAD
    events.extend([
        '# ============================================',
        f'# PHASE 3: LOW WORKLOAD ({format_time(timeline)} - {format_time(timeline + phase_duration)})',
        '# Expected HRV: RMSSD stable, LF/HF ~1.0',
        '# ============================================',
        '',
    ])
    
    # Low workload events
    g_event = 3.0 + (profile.level * 0.1)
    events.append(f'{format_time(timeline)};energymanager;event;PATROL,{g_event:.1f},30')
    events.append(f'{format_time(timeline + 15)};missiondirector;assign;UAV1,Surveillance,180')
    events.append(f'{format_time(timeline + 30)};datalink;message;MSG1,ATC,NORM,Radar contact 12 o clock,45')
    
    timeline += phase_duration
    
    # PHASE 4: MEDIUM WORKLOAD
    events.extend([
        '',
        '# ============================================',
        f'# PHASE 4: MEDIUM WORKLOAD ({format_time(timeline)} - {format_time(timeline + phase_duration)})',
        '# Expected HRV: RMSSD -10-15%, LF/HF ~1.5',
        '# ============================================',
        '',
    ])
    
    # Medium workload events
    g_event = 4.5 + (profile.level * 0.15)
    tti = int(40 * profile.deadline_factor)
    events.append(f'{format_time(timeline)};energymanager;event;INTERCEPT,{g_event:.1f},35')
    events.append(f'{format_time(timeline + 10)};threatboard;spawn;TH1,045,12,R73,{tti}')
    events.append(f'{format_time(timeline + 15)};missiondirector;assign;UAV2,Strike,120')
    events.append(f'{format_time(timeline + 20)};datalink;message;MSG2,AWACS,PRIO,Bandit 2 o clock high,30')
    events.append(f'{format_time(timeline + 25)};senseandavoid;spawn;INT1,090,1.5,200,35')
    events.append(f'{format_time(timeline + 35)};threatboard;engage;TH1,FOX3')
    events.append(f'{format_time(timeline + 45)};threatboard;resolve;TH1,SPLASH')
    events.append(f'{format_time(timeline + 50)};senseandavoid;resolve;INT1,turn right 15')
    
    timeline += phase_duration
    
    # PHASE 5: HIGH WORKLOAD
    events.extend([
        '',
        '# ============================================',
        f'# PHASE 5: HIGH WORKLOAD ({format_time(timeline)} - {format_time(timeline + phase_duration)})',
        '# Expected HRV: RMSSD -20-25%, LF/HF ~2.5',
        '# ============================================',
        '',
    ])
    
    # High workload events - multiple concurrent tasks
    g_event = 5.5 + (profile.level * 0.2)
    tti = int(35 * profile.deadline_factor)
    events.append(f'{format_time(timeline)};energymanager;event;ENGAGE,{g_event:.1f},40')
    events.append(f'{format_time(timeline + 5)};threatboard;spawn;TH2,315,8,AIM9,{tti}')
    events.append(f'{format_time(timeline + 8)};threatboard;spawn;TH3,045,10,R77,{tti + 5}')
    events.append(f'{format_time(timeline + 10)};missiondirector;conflict;UAV1,airspace')
    events.append(f'{format_time(timeline + 12)};datalink;message;MSG3,AWACS,CRIT,Multiple contacts,20')
    events.append(f'{format_time(timeline + 15)};senseandavoid;spawn;INT2,270,1.0,100,25')
    events.append(f'{format_time(timeline + 18)};weaponsinventory;expend;AIM120,1')
    events.append(f'{format_time(timeline + 20)};threatboard;engage;TH2,FOX2')
    events.append(f'{format_time(timeline + 22)};threatboard;countermeasure;chaff,2')
    events.append(f'{format_time(timeline + 25)};missiondirector;assign;UAV3,CSAR,90')
    events.append(f'{format_time(timeline + 28)};threatboard;engage;TH3,FOX3')
    events.append(f'{format_time(timeline + 30)};emergencystack;trigger;WARN1,FUEL LOW,Check tanks|Transfer fuel')
    events.append(f'{format_time(timeline + 35)};threatboard;resolve;TH2,SPLASH')
    events.append(f'{format_time(timeline + 40)};threatboard;resolve;TH3,MISS')
    events.append(f'{format_time(timeline + 45)};missiondirector;clearconflict;UAV1')
    events.append(f'{format_time(timeline + 50)};emergencystack;resolve;WARN1')
    
    timeline += phase_duration
    
    # PHASE 6: OVERLOAD INDUCTION (if high difficulty)
    if profile.level >= 6:
        events.extend([
            '',
            '# ============================================',
            f'# PHASE 6: OVERLOAD INDUCTION ({format_time(timeline)} - {format_time(timeline + phase_duration)})',
            '# Expected HRV: RMSSD -30%+, LF/HF may DECREASE (Durantin overload)',
            '# ============================================',
            '',
        ])
        
        # Overload events - simultaneous high-stress tasks
        g_event = 6.5 + (profile.level * 0.2)
        events.append(f'{format_time(timeline)};energymanager;event;DEFENSIVE,{g_event:.1f},45')
        events.append(f'{format_time(timeline + 2)};energymanager;overg;{g_event + 0.5:.1f}')
        events.append(f'{format_time(timeline + 5)};threatboard;spawn;TH4,180,5,GUN,20')
        events.append(f'{format_time(timeline + 7)};threatboard;spawn;TH5,200,6,R73,22')
        events.append(f'{format_time(timeline + 10)};emergencystack;trigger;HYD1,HYD PRESS LOW,Switch pumps|Check breakers|Monitor temps')
        events.append(f'{format_time(timeline + 12)};missiondirector;conflict;UAV2,lost_link')
        events.append(f'{format_time(timeline + 15)};datalink;message;MSG4,AWACS,CRIT,SAM LAUNCH,15')
        events.append(f'{format_time(timeline + 17)};threatboard;countermeasure;flare,4')
        events.append(f'{format_time(timeline + 20)};senseandavoid;spawn;INT3,045,0.5,50,15')
        events.append(f'{format_time(timeline + 22)};weaponsinventory;expend;AIM9,2')
        events.append(f'{format_time(timeline + 25)};threatboard;engage;TH4,GUN')
        events.append(f'{format_time(timeline + 28)};threatboard;engage;TH5,FOX2')
        events.append(f'{format_time(timeline + 30)};physiooverlay;apply;#000000AA,5')
        events.append(f'{format_time(timeline + 35)};threatboard;resolve;TH4,SPLASH')
        events.append(f'{format_time(timeline + 38)};threatboard;resolve;TH5,SPLASH')
        events.append(f'{format_time(timeline + 40)};emergencystack;resolve;HYD1')
        events.append(f'{format_time(timeline + 45)};missiondirector;clearconflict;UAV2')
    else:
        # Recovery phase for lower difficulties
        events.extend([
            '',
            '# ============================================',
            f'# PHASE 6: RECOVERY ({format_time(timeline)} - {format_time(timeline + phase_duration)})',
            '# Expected HRV: Gradual RMSSD recovery',
            '# ============================================',
            '',
        ])
        events.append(f'{format_time(timeline)};energymanager;event;EGRESS,3.0,30')
        events.append(f'{format_time(timeline + 30)};missiondirector;complete;UAV1')
    
    # Cleanup and stop
    end_time = duration
    events.extend([
        '',
        '# ============================================',
        '# SCENARIO END',
        '# ============================================',
        '',
        f'{format_time(end_time - 10)};automationhooks;disable;1',
        f'{format_time(end_time - 5)};physiomonitor;export;',
        '',
        f'{format_time(end_time)};compositescore;stop',
        f'{format_time(end_time)};automationhooks;stop',
        f'{format_time(end_time)};emergencystack;stop',
        f'{format_time(end_time)};senseandavoid;stop',
        f'{format_time(end_time)};missiondirector;stop',
        f'{format_time(end_time)};weaponsinventory;stop',
        f'{format_time(end_time)};threatboard;stop',
        f'{format_time(end_time)};energymanager;stop',
        f'{format_time(end_time)};datalink;stop',
        f'{format_time(end_time)};communications;stop',
        f'{format_time(end_time)};resman;stop',
        f'{format_time(end_time)};track;stop',
        f'{format_time(end_time)};sysmon;stop',
        f'{format_time(end_time)};physiomonitor;stop',
        f'{format_time(end_time)};polarrlink;stop',
    ])
    
    return events


def generate_hrv_mumt(duration: int, profile: DifficultyProfile) -> List[str]:
    """Generate a hybrid MUM-T scenario with HRV monitoring.
    
    Combines fighter pilot tasks with UAV supervision to induce
    dual-task interference detectable via HRV.
    
    Args:
        duration: Total scenario duration in seconds.
        profile: Difficulty profile for workload scaling.
        
    Returns:
        List of scenario event strings.
    """
    duration = max(duration, 720)  # Minimum 12 minutes
    baseline_duration = 120
    
    events: List[str] = [
        '# MUM-T HRV Integration Scenario',
        f'# Difficulty Level: {profile.level}/10',
        f'# Duration: {duration}s',
        '# Hybrid manned-unmanned teaming with HRV monitoring',
        '#',
        '# Research Reference: Manual.md Section 18.3.3',
        '# Expected: Dual-task interference detectable via HRV',
        '',
        '# Start physiological monitoring',
        '0:00:00;polarrlink;start',
        '0:00:01;physiomonitor;start',
        '0:00:02;physiomonitor;baseline;start',
        '',
        '# Start all systems',
        '0:00:05;sysmon;start',
        '0:00:05;track;start',
        '0:00:05;resman;start',
        '0:00:05;communications;start',
        '',
        f'{format_time(baseline_duration)};physiomonitor;baseline;stop',
        '',
        '# Activate fighter systems',
        f'{format_time(baseline_duration + 5)};energymanager;start',
        f'{format_time(baseline_duration + 5)};threatboard;start',
        f'{format_time(baseline_duration + 5)};weaponsinventory;start',
        f'{format_time(baseline_duration + 5)};emergencystack;start',
        '',
        '# Activate UAV systems',
        f'{format_time(baseline_duration + 5)};missiondirector;start',
        f'{format_time(baseline_duration + 5)};senseandavoid;start',
        f'{format_time(baseline_duration + 5)};payloadmanager;start',
        f'{format_time(baseline_duration + 5)};operatorcapacity;start',
        '',
        f'{format_time(baseline_duration + 5)};datalink;start',
        f'{format_time(baseline_duration + 5)};compositescore;start',
        f'{format_time(baseline_duration + 5)};automationhooks;start',
        '',
        '# Initialize loadout',
        f'{format_time(baseline_duration + 10)};weaponsinventory;load;AIM9,4',
        f'{format_time(baseline_duration + 10)};weaponsinventory;load;AIM120,4',
        '',
        '# Set operator capacity limits',
        f'{format_time(baseline_duration + 10)};operatorcapacity;set;active,3',
        f'{format_time(baseline_duration + 10)};operatorcapacity;set;supervisory,5',
        '',
        '# HRV automation rules for MUM-T',
        f'{format_time(baseline_duration + 15)};automationhooks;rule;'
        'physiomonitor,hrv_workload,eq,high,AUTO,target=missiondirector,command=automation,payload=uav1,auto,cooldown=45',
        f'{format_time(baseline_duration + 15)};automationhooks;enable;1',
        '',
    ]
    
    # Generate MUM-T workload events
    timeline = baseline_duration + 30
    uav_idx = 1
    threat_idx = 1
    
    while timeline < duration - 90:
        # Fighter task
        g_event = 4.0 + (profile.level * 0.15)
        events.append(f'{format_time(timeline)};energymanager;event;BFM{threat_idx},{g_event:.1f},25')
        
        # UAV supervision task (concurrent)
        events.append(f'{format_time(timeline + 5)};missiondirector;assign;UAV{uav_idx},ISR,120')
        
        # Threat engagement
        tti = int(40 * profile.deadline_factor)
        events.append(f'{format_time(timeline + 10)};threatboard;spawn;TH{threat_idx},045,10,R73,{tti}')
        
        # UAV sensor task
        events.append(f'{format_time(timeline + 15)};payloadmanager;activate;Cam{uav_idx},Target-{threat_idx},15')
        
        # Datalink from both domains
        events.append(f'{format_time(timeline + 20)};datalink;message;FTR{threat_idx},AWACS,PRIO,Bandit,25')
        events.append(f'{format_time(timeline + 22)};datalink;message;UAV{uav_idx},GCS,NORM,Target acquired,30')
        
        # Resolution
        events.append(f'{format_time(timeline + 30)};threatboard;engage;TH{threat_idx},FOX3')
        events.append(f'{format_time(timeline + 40)};threatboard;resolve;TH{threat_idx},SPLASH')
        
        # Add conflicts at higher difficulties
        if profile.level >= 5 and threat_idx % 2 == 0:
            events.append(f'{format_time(timeline + 25)};senseandavoid;spawn;INT{threat_idx},270,1.0,150,30')
            events.append(f'{format_time(timeline + 35)};missiondirector;conflict;UAV{uav_idx},deconflict')
            events.append(f'{format_time(timeline + 50)};missiondirector;clearconflict;UAV{uav_idx}')
        
        uav_idx = (uav_idx % 3) + 1
        threat_idx += 1
        timeline += profile.event_interval + 20
    
    # Cleanup
    end_time = duration
    events.extend([
        '',
        f'{format_time(end_time - 10)};automationhooks;disable;1',
        f'{format_time(end_time - 5)};physiomonitor;export;',
        '',
        f'{format_time(end_time)};compositescore;stop',
        f'{format_time(end_time)};automationhooks;stop',
        f'{format_time(end_time)};operatorcapacity;stop',
        f'{format_time(end_time)};payloadmanager;stop',
        f'{format_time(end_time)};senseandavoid;stop',
        f'{format_time(end_time)};missiondirector;stop',
        f'{format_time(end_time)};emergencystack;stop',
        f'{format_time(end_time)};weaponsinventory;stop',
        f'{format_time(end_time)};threatboard;stop',
        f'{format_time(end_time)};energymanager;stop',
        f'{format_time(end_time)};datalink;stop',
        f'{format_time(end_time)};communications;stop',
        f'{format_time(end_time)};resman;stop',
        f'{format_time(end_time)};track;stop',
        f'{format_time(end_time)};sysmon;stop',
        f'{format_time(end_time)};physiomonitor;stop',
        f'{format_time(end_time)};polarrlink;stop',
    ])
    
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
    python scenario_templates.py --template hrv_combat --difficulty 7 --duration 600 --output hrv_combat.txt
    python scenario_templates.py --template hrv_mumt --difficulty 6 --duration 720 --output hrv_mumt.txt
        """
    )
    parser.add_argument(
        '--template',
        choices=['uas_bvlos', 'hpa_overlay', 'training', 'hrv_combat', 'hrv_mumt'],
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
    elif args.template == 'hrv_combat':
        events = generate_hrv_combat(args.duration, profile)
    elif args.template == 'hrv_mumt':
        events = generate_hrv_mumt(args.duration, profile)
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
