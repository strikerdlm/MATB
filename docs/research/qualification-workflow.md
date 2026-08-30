# MATB v1 qualification workflow

The repository implements four independent evidence classes. A pass in one class
never upgrades another:

1. **Software conformance** — deterministic scenarios, state transitions, metrics,
   schemas, replay and golden checks.
2. **Physical timing** — rig-specific photodiode, audio-loopback and actuated-input
   measurements analyzed with `python -m matb_integration.qualification.cli timing`.
3. **Human calibration and reliability** — preregistered LOW/MEDIUM/HIGH dose response
   and repeated sessions in the intended military-aviation population.
4. **Cross-implementation characterization** — direct NASA MATB-II and upstream
   OpenMATB comparisons using preregistered equivalence margins.

## Commands

```powershell
python -m matb_integration.qualification.cli profiles
python -m matb_integration.qualification.cli profiles openmatb-1.4.5-derived
python -m matb_integration.qualification.cli golden --source-commit COMMIT --output golden-conformance.json
python -m matb_integration.qualification.cli conformance openmatb-1.4.5-derived checks.json --source-commit COMMIT --output conformance.json
python -m matb_integration.qualification.cli timing matched-events.csv --rig-json rig.json --limits-json limits.json --use-tier block_plus_physiology --source-commit COMMIT --representative-full-block --output timing-qualification.json
python -m matb_integration.qualification.cli release-status qualification-input.json --output scientific-qualification.json
python -m matb_integration.qualification.cli bids-events session.events.jsonl events.tsv events.json --profile-id MATB-EXTENDED-2.0 --scenario-sha256 HASH --source-commit COMMIT
python -m matb_integration.qualification.cli reference-session metadata.json session-root session-root/session.events.jsonl session-root/metrics.json --output reference-session.json
python -m matb_integration.qualification.cli calibration-manifest scenario-hashes.json --source-commit COMMIT --profile-id MATB-EXTENDED-2.0 --locale es-CO --output calibration-study-manifest.json
```

Timing CSV columns are `event_id`, `modality`, `device_id`, `run_id`, and the
applicable clock fields: `dispatch_s`, `physical_s`, `lsl_s`,
`physical_input_s`, and `response_s`. Every planned event must remain in the
file. Missing, duplicate or ambiguous matches fail closed.

The initial public target is `block_plus_physiology`. ERP/event-related EEG is
always a separate rig-specific qualification and is not implied by this tier.

## Release rule

`v1.0.0` is eligible only when the machine-readable scientific qualification
returns `PASS`. Null or unfavorable empirical findings must be retained. Scenario
profiles are revised under new identifiers rather than retroactively relabeled.
