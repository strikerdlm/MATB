# MATB timing qualification protocol

## Objective

Quantify, for each supported laboratory rig, the uncertainty between scheduled
events, software dispatch, physical visual/audio onset, participant input, log
timestamps, and LSL markers. Internal timestamps alone do not qualify physical onset.

## Equipment and configuration

- Photodiode attached to a high-contrast display patch and an independent acquisition channel.
- Audio loopback or microphone/acoustic coupler recorded by the same acquisition system.
- Electrical or mechanical input actuator for the keyboard/joystick under test.
- LabRecorder or equivalent LSL capture, with clock-offset information retained.
- Fixed computer, display, refresh rate, audio device, input device, OS, Python/OpenMATB
  version, git commit, power mode, and background-process policy.

## Procedure

1. Record the hardware/environment manifest and calibrate acquisition clocks.
2. Run at least 200 isolated visual events at each supported refresh rate.
3. Run at least 200 isolated auditory events for each supported output device.
4. Run at least 200 actuated inputs for every authorized response device.
5. Run a representative full MATB block while recording photodiode, audio, input,
   JSONL events, timing QC, and XDF/LSL output.
6. Repeat after restart and on at least three separate runs per configuration.
7. Match events by immutable ID; exclude no observation silently. Record unmatched,
   duplicate, dropped, and ambiguous events separately.

## Derived quantities

- scheduled scenario time to software dispatch;
- software dispatch to physical visual or auditory onset;
- physical onset to LSL marker;
- physical input to MATB response timestamp;
- LSL clock offset/drift;
- update-loop stalls, event lateness, and dropped/unmatched events.

For every quantity report n, median, interquartile range, 95th percentile, 99th
percentile, maximum, and the signed direction of latency. Stratify by hardware,
refresh rate, modality, and run. Do not pool configurations that differ materially.

## Acceptance and reporting

Acceptance limits must be preregistered for the intended scientific use. ERP studies
require tighter limits than block-level workload studies. A configuration fails closed
when physical onset was not measured, event matching is ambiguous, clock drift is
unresolved, or a preregistered limit is exceeded. The signed report must include raw
captures, matching code, exclusions, hashes, software commit, and the generated
`timing_qc.json`; it must never replace session-specific QC.
