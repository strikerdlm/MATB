# Bilingual COMM verification — 2026-09-30

The existing English and Spanish WAV banks were intact; no audio files were regenerated or replaced. Fixes address Spanish catalog selection, non-serializable radio widgets entering scientific logs, prompt preparation time being counted as playback, frame-throttled completion checks, and native audio shutdown.

## Native Windows smoke tests

Five synthetic 70-second practice runs used the real scheduler, XAudio2 media backend, scientific writer, and built-in automatic solver. Each completed with an own-call HIT, a distractor correct rejection, no invalidated COMM opportunity, and process exit 0 without fatal diagnostics.

| Profile | Audio | Screenshots |
| --- | --- | --- |
| OpenMATB classic | English, male | [Playing](classic-en_EN-male/own-playing.png), [response](classic-en_EN-male/own-response.png), [distractor](classic-en_EN-male/other-playing.png), [rejection](classic-en_EN-male/other-response.png) |
| OpenMATB classic | Spanish, female | [Playing](classic-es_CO-female/own-playing.png), [response](classic-es_CO-female/own-response.png), [distractor](classic-es_CO-female/other-playing.png), [rejection](classic-es_CO-female/other-response.png) |
| MATB-FAC modern | English, male | [Playing](fac_modern-en_EN-male/own-playing.png), [response](fac_modern-en_EN-male/own-response.png), [distractor](fac_modern-en_EN-male/other-playing.png), [rejection](fac_modern-en_EN-male/other-response.png) |
| MATB-FAC modern | Spanish, female | [Playing](fac_modern-es_CO-female/own-playing.png), [response](fac_modern-es_CO-female/own-response.png), [distractor](fac_modern-es_CO-female/other-playing.png), [rejection](fac_modern-es_CO-female/other-response.png) |
| MATB-FAC modern | Spanish, male | [Playing](fac_modern-es_CO-male/own-playing.png), [response](fac_modern-es_CO-male/own-response.png), [distractor](fac_modern-es_CO-male/other-playing.png), [rejection](fac_modern-es_CO-male/other-response.png) |

These are application framebuffer captures, not evidence of human intelligibility or measured physical speaker onset. The smoke scenarios explicitly selected audio language and voice; existing research scenarios retain their pinned English audio independently of UI language.

## Validation scope

Fresh isolated delivery-worktree runs passed **920 OpenMATB tests** and **115 audio-profile/scenario tests**. Commands: `python -m pytest -q -p no:cacheprovider` from `openmatb`, and the same command with `tests/test_communications_profile.py tests/test_scenario_builder.py tests/test_experiment_compiler.py` from the repository root. Both used fresh explicit `--basetemp` directories because the default Windows pytest temporary directory returned Access Denied on the first attempt; no code changes were required for that environment issue.

Original working-tree validation: 897 OpenMATB tests and 115 audio-profile/scenario tests passed. Backend coverage totaled 542 passes and one POSIX-only skip across a full run and a targeted rerun: five tests initially failed because offline calculator wheels were missing, then all five passed after wheel preparation. This was not a single uninterrupted clean backend run.

The repaired console environment passed dependency checks. A live isolated backend passed health, capability, native readiness, preview launch, and preview abort checks. Preview abort intentionally terminates the preview process; it is separate from the five normally completed native runs.

The native run source hashes (SHA-256, original Windows file bytes) were:

```text
openmatb/main.py: a9ed0362e88cd519365565f505dec3d1d3ae427ddc7bba08adbcfcdf276ee22d
openmatb/plugins/communications.py: fb9c4b8547c1fd0fffae472926f7860c833e9e99c9a34b66aae4de580a442a32
openmatb/core/scheduler.py: 23c04b00faba7044b930555490516da61948a398253e71008f6347fb774791fb
```

The native and backend checks ran in the original working tree before PR isolation. This delivery is based on `d3f150c`, which already includes the logger/provenance/pause fixes. Unrelated local changes, environments, raw session logs, and databases are excluded. Screenshots contain synthetic practice data only.
