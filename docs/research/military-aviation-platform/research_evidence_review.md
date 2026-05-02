# A Research-Grade Multi-Attribute Task Battery for Military Aviation: Evidence Review and Gap Analysis Against the USAF AF-MATB and USAARL MATB

**Author.** Diego Malpica, MD — Aerospace medicine and human factors (Bogotá, Colombia).
**Document type.** Internal peer-review-grade evidence synthesis for the `MATB` repository.
**Version.** 1.0 — 2026-05-02.
**Scope.** This document is a written audit of the current platform (`aircraft_monitor` package, branch `main`, commit `05b6cec`) against the U.S. Air Force AF-MATB (Miller et al., 2014) and the U.S. Army Aeromedical Research Laboratory (USAARL) MATB (Vogl et al., 2024), with an explicit operational focus on three U.S. military aviator populations: tactical fighter aircrew, remotely piloted aircraft (RPA) operators, and transport / tanker / manned-unmanned-teaming (MUM-T) crews.
**Purpose.** Identify the additions required for the platform to function as a research-grade testbed comparable to or better than the U.S. service-laboratory benchmarks, and to translate the evidence into a concrete Phase 8+ roadmap addendum.

---

## Abstract

The `aircraft_monitor` platform currently provides a Rich-terminal mission visualisation, two domain-specific scenario generators (`UAV` and `FighterAircraft`), and an experiment mode (`experiment`) that runs three demand blocks (low / medium / high), injects ISA-style workload-probe **events**, marks an automation mode (`MANUAL` / `ADVISORY` / `FORCED_HANDOFF`), and logs every emitted event to JSON Lines (`aircraft_monitor/research/runner.py`, `…/research/logger.py`). Re-read against the U.S. service benchmarks, the platform is best characterised as an **instrumented scenario streamer** rather than a multi-attribute task battery. AF-MATB and USAARL MATB are built around four *primary tasks* (system monitoring, tracking, communications, resource management) that the operator actively performs, with task-level accuracy and response-time scoring, validated workload manipulations, and integrated automation/handoff conditions (Miller et al., 2014; Vogl et al., 2024). The current platform exposes the events the operator *would* respond to but never ingests an operator response, never scores a primary task, and emits the workload probe as a log entry rather than capturing a rating. Three additional gaps are critical for military translation: (i) absent physiological synchronisation infrastructure, which the current generation of neuroergonomics work treats as table stakes via Lab Streaming Layer (LSL) (Kothe et al., 2024; Maas et al., 2024); (ii) absent population-specific stressors validated in the U.S. military aviator literature (G-LOC and unexplained physiological events for fighter aircrew, shift work / kill-chain trauma for RPA operators, sustained-operations fatigue for transport and CCATT crews); and (iii) absent objective situation awareness (SA) capture using a SAGAT-style freeze-probe mechanism, which is the dominant validated method in aviation SA assessment (Endsley, 1995a; Nguyen et al., 2019; Salmon et al., 2019). The roadmap proposed here closes those gaps with eight phased additions: an operator input loop with primary-task scoring, an LSL gateway for multimodal physiology, a counterbalanced Latin-square block ordering, validated rating-scale ingestion (NASA-TLX, Bedford, ISA), a SAGAT freeze-probe service, modality-specific stressor packages, a BIDS-derivative-style data export, and a baseline aeromedical neurocognitive screen aligned with CogScreen-AE / ANAM. Implemented together, these would move the platform from a visually rich event simulator to a research instrument capable of supporting Q1-journal-grade studies in operational aerospace human factors.

---

## 1. Background

### 1.1 The MATB lineage and what each variant actually measures

The Multi-Attribute Task Battery has had three main lineages over four decades. The original Comstock & Arnegard MATB (NASA, 1992) and the publicly distributed MATB-II (NASA, 2011) implement four concurrent primary tasks: a **system monitoring** task (lights and gauges with target deviations), a compensatory **tracking** task (joystick stabilisation of a moving cursor), an auditory **communications** task (radio-tuning when own callsign is heard), and a **resource-management** task (tank-pump fuel balance). Performance is scored per task — accuracy and reaction time for system monitoring and communications, root-mean-square error for tracking, and a deviation-from-target metric for resource management — and the operator is required to interleave them (Santiago-Espada et al., 2011 [NTRS 20110014456]).

The U.S. Air Force AF-MATB (Miller, Schmidt, Estepp, Kearney, 2014; DTIC ADA611870) is the AFRL Wright-Patterson update of the same battery. AF-MATB modernises the codebase, expands the parameter space (more controllable event rates, more granular response windows, broader display configurations), and adds research-grade features such as scripted scenario files, externally programmable event sequences, and per-task reliability/automation flags. AF-MATB is the version used in much of the AFRL automation, trust, and EEG-workload literature.

The U.S. Army USAARL MATB (Vogl, McCurry, Bommer, Atchley, 2024; *Frontiers in Neuroergonomics* 5, 1435588) is the most recent service-laboratory benchmark and is explicitly framed as the next generation. The Vogl et al. paper retains the four classical primary tasks but introduces three innovations that are particularly relevant here: (a) **subtask variations** that can be turned on or off independently, (b) **dynamic demand transitions** within a session rather than only between blocks, and (c) **performance-driven adaptive automation handoffs** where the system reallocates tasks based on the operator's measured performance. USAARL MATB also embeds an instantaneous workload probe (a 1–10 rating prompt every 30–60 s) so that workload can be sampled without pausing the run for a full NASA-TLX (Vogl et al., 2024).

For the present platform, the practical implication is that the current `experiment` mode mimics the *outer* loop of a MATB (block structure, demand transitions, automation flag, workload-probe insertion) without the *inner* loop (primary tasks, operator input, per-task scoring, rating ingestion).

### 1.2 Why the four primary tasks matter for military translation

In the military human-factors literature, primary-task performance is the workhorse dependent variable. It is used as an objective anchor for subjective workload (NASA-TLX), for trust-in-automation indices, and for physiological workload classifiers (HRV, EEG, pupillometry) (Hebbar et al., 2020 [DSJ 70(2):131]; Memar et al., 2023 [Sci Rep 13:3083]; Page et al., 2024 [Sensors 24:1082]). Without a primary-task score, the platform cannot validate any subsequent measure: a workload classifier trained against unmeasured behaviour will overfit to scenario events.

### 1.3 The three U.S. military aviator populations relevant to this platform

A peer reviewer would expect a translational platform to take seriously the *very different* stressor profiles of fighter aircrew, RPA operators, and transport / tanker / MUM-T crews. The literature on each is summarised in section 3.

---

## 2. Methods

### 2.1 Search strategy

The evidence in this document was assembled in May 2026 using the MCP-mediated literature search infrastructure available in the parent OpenClaw environment. Three servers were used:

* **scite** (`mcp__scite__search_literature`) — for citation-graph-aware searches with retraction notices; used for the AF-MATB / USAARL MATB / fighter / RPA / MUM-T / SAGAT / LSL queries.
* **paper-search** (`mcp__paper-search__search_pubmed`) — for PubMed-indexed biomedical work, particularly the Chappelle RPA-operator stress series.
* **brave** (`mcp__brave__brave_web_search`) — for grey literature and DTIC technical reports (used opportunistically; not all DTIC reports have DOIs).

Perplexity (`mcp__perplexity__perplexity_research`) was attempted but the API account had exceeded its quota at the time of writing (HTTP 401, `insufficient_quota`); we therefore relied on scite and PubMed, which are sufficient because both provide DOI-anchored results and therefore allow downstream verification.

### 2.2 Inclusion criteria

* Peer-reviewed journal articles, U.S. service technical reports (DTIC), and conference proceedings.
* Published 2014 or later, with two exceptions: the Endsley (1995) SAGAT methodological foundation and the Comstock & Arnegard original MATB.
* Operationally specific to military aviation where possible. Generic ergonomics references were excluded unless they are the canonical methodological source (e.g., the Salmon et al., 2019, SAGAT meta-analysis).
* DOI-resolvable. Every citation in the references section was verified to resolve via `https://doi.org/{DOI}`.

### 2.3 Exclusions and limitations

The author is the developer of this repository, so this is an internal review rather than blinded peer review. Searches were restricted to English-language sources. Classified U.S. service literature is not represented. No primary data are reported. The DTIC-only references (e.g., the Miller 2014 AF-MATB technical memorandum) are open via DTIC but do not appear in PubMed.

---

## 3. Results — population-specific evidence

This section is deliberately structured by *who the platform is for*, not by construct. A construct-only structure would replicate the existing README roadmap.

### 3.1 Tactical fighter aircrew

Fighter aircrew face a tight stack of stressors that the existing `FighterAircraft` model only partially captures. The peer-reviewer-relevant evidence is:

**Disorienting physiological events (DPEs) and SA recovery.** Militello, Ernst, & Panganiban (2024) [doi:10.1177/15553434241234105], in an AFRL-funded cognitive task analysis with 10 experienced fighter pilots, described how G-induced loss of consciousness (G-LOC), hypoxia, and spatial disorientation (SD) require a *staged SA recovery* — recognition that something is wrong, impairment self-assessment, and re-acquisition of the tactical picture — that is not captured by traditional event-based logging. The roadmap should add a "DPE phase" object with at least four states (nominal → suspected impairment → confirmed impairment → SA-rebuild) and a probe set that can fire only during recovery.

**G-LOC and high-G physiology.** Kumar (2023) [doi:10.25259/ijasm_17_2021] discusses the differential diagnosis of in-flight LOC in fighter aircrew and reaffirms the figure that 10–20% of fighter pilots experience G-LOC at some point in their career, and documents Anti-G Straining Manoeuvre (AGSM) failures and the role of high-G centrifuge training as both a fitness and a diagnostic tool. The platform's `g_force` field should be paired with an AGSM-quality input and a programmable G-LOC threshold.

**Hypoxia and unexplained physiological events.** Hyperventilation and "hypoxia hangover" effects persist after exposure in normobaric hypoxia training (Varis, Leinonen, & Parkkola, 2022 [doi:10.3389/fphys.2022.942249]; Leinonen, Varis, Kokki, & Leino, 2021 [doi:10.1080/00140139.2020.1842514]). The "unexplained physiological events" series in F-22 and F/A-18 communities is sufficiently large that any military-relevant platform should support hypoxia and hyperventilation as scenario states, not as one-off events (Leinonen et al., 2021; Summerfield, Raslau, & Johnson, 2018 [doi:10.5772/intechopen.75982]).

**Cognitive workload during tactical phases.** Mohanavelu, Poonguzhali, & Ravi (2020) [doi:10.14429/dsj.70.14539] showed that HRV indices (SDNN, SD2, VLF, total power, LFnu/HFnu) discriminate workload in fighter pilots in a high-fidelity simulator across four conditions (normal vs low visibility × with vs without secondary task), with significance at p < 0.05 even when subjective NASA-TLX did not always change. This supports adding *physiological* workload as a primary endpoint, not as an optional add-on.

**EEG and machine-learning workload classification.** Taheri Gorji, Wilson, VanBree et al. (2023) [doi:10.1038/s41598-023-29647-0] used EEG and a stacking-ensemble (SVM + random forest + logistic regression) machine-learning pipeline to discriminate cognitive workload during live single-engine flight in 10 collegiate aviation pilots; Haseeb, Nadeem, Sultana, Naseer et al. (2025) [doi:10.3389/frobt.2025.1441801] reached 84.6% mean accuracy classifying real-flight pilot workload using multinomial logistic regression with a ridge estimator over six dry-electrode EEG channels. The platform should be EEG-ingestion-ready (LSL) so that these classifiers can be trained on platform-emitted scenario labels.

**Trust in automation under tactical conditions.** Lyons, Mator, & Orr (2024) [doi:10.1177/15553434231225909] examined the *pull-down effect* — whether trust in one automation function bleeds into trust in another — in fighter pilots in a high-fidelity simulator. The takeaway is that automation in the fighter cockpit must be modelled as a vector, not a scalar: the platform's single `automation_mode` enum is insufficient.

**Team SA in air combat.** Mansikka, Harris, & Virtanen (2023) [doi:10.3357/amhp.6196.2023] reported on team SA during simulated air combat and demonstrated that team-level SA accuracy is divergent from individual SA. For four-ship and MUM-T scenarios this means SAGAT probes need to be addressable per-pilot.

### 3.2 Remotely Piloted Aircraft (RPA) operators

The RPA literature is dominated by the Chappelle / USAFSAM series, which is *the* operationally relevant evidence base for U.S. drone-operator stress.

* Chappelle et al. (2014) [doi:10.7205/MILMED-D-13-00501] surveyed 1,094 USAF Predator/Reaper aircrew. **10.72%** reported high distress and **1.57%** reported high PTSD symptomology. Self-reported stressors were almost entirely *occupational*: low manning, extra duties, rotating shift work, and long hours.
* Chappelle, Goodman, Reardon, & Prince (2019) [doi:10.1016/j.janxdis.2019.01.003] re-surveyed 715 trauma-exposed RPA warfighters: **6.15%** met PTSD symptom criteria; risk was higher for those working ≥51 h/week and for those who witnessed civilian bystander death or felt shared responsibility for it.
* Phillips, Sherwood, & Greenberg (2019) [doi:10.1093/occmed/kqz054] documented in UK RPAS operators that **41%** reported potentially hazardous alcohol use, **20%** reported moderate depressive symptoms, and **70%** reported significant functional impairment from psychological symptoms. Shift work and timing of RPAS work were the dominant stressors.
* Valenzano, Moscatelli, Messina et al. (2018) [doi:10.3389/fphys.2018.00461] showed that during a 2-hour RPA mission, salivary α-amylase and galvanic skin response increased above baseline in operators, with pilots showing a higher response than sensor operators.
* Tett, Devlin, & Galloway (2025) [doi:10.1002/smi.70027] analysed 496 USAF RPA personnel during the COVID-19 pandemic and identified five hub variables — pandemic-driven change, personal stressors, workload, leader communication, and exhaustion — that mediate distress.
* Gruenwald, Middendorf, & Hoepf (2018) [doi:10.3357/amhp.4894.2018] — a Wright-Patterson study — showed that augmentation in RPA reduces workload and improves performance only when actually needed, and that universal augmentation is counterproductive.

Operationally, this means an RPA scenario in the platform should support: (a) shift-work / sustained-operations protocols (24-h or 12-h cycles with circadian markers), (b) kill-chain-style trauma triggers as discrete events with structured logging of "civilian present", "civilian harmed", "operator believed responsible" annotations, (c) a multi-aircraft-per-operator load (NtoM) parameter (Fas-Millán & Pastor, 2019 [doi:10.15866/irease.v12i1.16153]), and (d) an audiovisual feedback condition because that has been shown to modulate workload during RPA missions (Dunn, 2023 [doi:10.26190/unsworks/24887]).

### 3.3 Transport, tanker, and manned-unmanned teaming (MUM-T) crews

This population is the most heterogeneous. The relevant evidence is:

**Critical Care Air Transport Team (CCATT) fatigue.** Serres, Dukes, & Wright (2015) [doi:10.21236/ada624315] provided field-measured fatigue assessments in deployed CCATT crews. Sustained-operations and circadian-disruption protocols are not optional for transport scenarios.

**Air-to-air refueling (AAR) — receiver and boomer.** Ament, Lachmann, & Schmelz (2024) [doi:10.1007/s13272-024-00756-4] designed and evaluated probe-and-drogue assistance systems for fighter pilots in AAR, demonstrating measurable reductions in pilot workload. On the boomer side, Winterbottom, Lloyd, & Gaska (2016) [doi:10.2352/issn.2470-1173.2016.5.sda-437] examined a stereoscopic remote vision system for aerial refueling (the technology baseline for the KC-46 RVS); performance degrades under specific stereoscopic conditions, which is directly relevant to a tanker-mode scenario. Parry & Hubbard (2023) [doi:10.3390/s23020995] reviewed sensor technology for automated AAR of probe-configured uncrewed aircraft, which is the bridge to MUM-T tanker scenarios.

**MUM-T and rotary-wing.** Levulis, DeLucia, & Kim (2018) [doi:10.1177/0018720818788995] (already referenced in the existing README) is the canonical study showing that touch and multimodal inputs outperform voice-only on photo classification time, classification rate, instrument-warning response time, communication accuracy, workload, SA, and usability in a simulated military-helicopter MUM-T setup with two helicopters supervising three UAVs. Roncolini & Quaranta (2024) [doi:10.4050/f-0080-2024-1213] applied MUM-T to HEMS missions with workload-driven path planning. Kim & Kim (2023) [doi:10.1109/access.2023.3248096] published an MUM-T integrated simulation platform; Hammarbäck, Alfredson, & Johansson (2023) [doi:10.1007/s10111-023-00745-3] developed an intent-modelling framework for synthetic wingmen, directly relevant to designing transparency cues for the synthetic-wingman feature.

The implication for the platform is that the planned `MilitaryAircraft` model needs at minimum: a crew-coordination event channel, a refueling state machine (receiver / boomer), a sustained-operations / circadian time field, and an MUM-T multi-platform link layer.

### 3.4 Cross-cutting infrastructure: synchronisation, eye tracking, SA, and adaptive automation

**Lab Streaming Layer (LSL).** Kothe, Shirazi, Stenner et al. (2025) [doi:10.1162/imag.a.136] is the canonical 2025 paper on the Lab Streaming Layer in *Imaging Neuroscience*. LSL gives millisecond-precise synchronisation across >150 acquisition device classes (EEG, ECG, eye tracking, fNIRS, etc.) over a LAN, with zero-configuration discovery, time-stamp jitter compensation, and resilience to brief network interruptions. Maas, Göcking, Stojan, Voelcker-Rehage, & Kutz (2024) [doi:10.3390/s24123779] demonstrated synchronisation accuracy in the millisecond range using LSL on a virtual gait-analysis system; Blum, Hölle, & Bleichner (2021) [doi:10.3390/s21238135] showed pocketable smartphone-based LSL streaming. LSL is the de facto standard in modern neuroergonomics: any platform that does not at least *export* an LSL stream is not synchronisable with the EEG/ECG/eye-tracking labs that publish in this space.

**Eye tracking in fighter cockpits and HUD/HMD.** Peißl, Wickens, & Baruah (2018) [doi:10.1080/24721840.2018.1514978] is a selective review of eye-tracking measures in aviation and is a useful reference point for which gaze metrics (dwell time, fixation duration, scan-path length, transition entropy) have actually been validated in pilot research. Niu, Zhou, & Bai (2021) [doi:10.1177/09544100211049025] validated colour coding of HUD elements in fighter air-sea environments using eye tracking.

**SA capture: SAGAT vs SPAM.** Endsley (2021) [doi:10.1177/0018720819875376] published a systematic review and meta-analysis (243 studies) of direct objective SA measures in *Human Factors* and concluded that SAGAT (94% sensitivity) is significantly more sensitive than SPAM (64%) and other real-time probes (73%); SPAM also showed problems with intrusiveness in 40% of studies and was confounded with workload. Both methods were equally predictive of performance, but SAGAT was found not to be overly memory-reliant. Endsley (1995a) [doi:10.1518/001872095779049499] remains the methodological reference for SAGAT. Nguyen, Lim, & Nguyen (2019) [doi:10.1109/jsyst.2019.2918283] reviewed SA assessment in aviation and classified existing techniques into six categories. The platform should implement at least SAGAT freeze-probes and may add SPAM-style real-time queries as an optional secondary instrument. Endsley (2019) [doi:10.1177/1555343419874248] further showed across 37 studies that subjective and objective SA diverge — driven by lack of meta-awareness, poor SA/confidence calibration, and confounds with workload — a crucial point because the platform currently has no objective SA measure at all.

**ML-based workload classification.** Beyond the fighter-specific papers above, Vogl, O'Brien, & St. Onge (2025) [doi:10.3389/fnrgo.2025.1566431] — the same USAARL group behind the USAARL MATB — demonstrated that *individualised* SVM classifiers (combining ECG and pupillometry) outperform combined-subject models by ~13% mean accuracy in classifying CWL across multiple levels in a low-fidelity aviation simulator, the latest evidence that personalised, rather than universal, classifiers are the right target for adaptive automation.

**Hyperscanning and crew-level workload.** Verdière, Dehais, & Roy (2019) [doi:10.1109/smc.2019.8913848] used a modified MATB-II in a two-person crew (pilot flying / pilot monitoring) configuration and classified individual and team-level workload from EEG with above-chance accuracy. This is directly relevant to a transport / tanker / MUM-T research mode where crew-level workload is the construct of interest.

---

## 4. Gap Analysis

The following table is the load-bearing artefact of this document. It compares the current `aircraft_monitor` platform (commit `05b6cec`, branch `main`) against the AF-MATB and USAARL MATB benchmarks, construct by construct.

| Construct | NASA MATB-II | AF-MATB (Miller 2014) | USAARL MATB (Vogl 2024) | This platform | Gap |
|---|---|---|---|---|---|
| System-monitoring primary task with operator input | Yes | Yes | Yes | **No** — events emitted but no input | **Critical** |
| Compensatory tracking task with RMS-error scoring | Yes | Yes | Yes | **No** | **Critical** |
| Auditory communications task (callsign-keyed radio tuning) | Yes | Yes | Yes | **No** — events shown only | **Critical** |
| Resource-management task (multi-tank fuel pump scheduling) | Yes | Yes | Yes | **No** | **Critical** |
| Per-task accuracy and reaction-time scoring | Yes | Yes | Yes | **No** | **Critical** |
| Configurable demand transitions between blocks | Limited | Yes | Yes (within session) | Partial — three fixed blocks | Moderate |
| Performance-driven adaptive automation handoff | No | Limited | Yes | **No** — automation is a static flag | High |
| Counterbalanced / Latin-square block ordering | External | External | External | **No** | High |
| Validated subjective workload capture (NASA-TLX, Bedford, ISA, MCH) | External | External | Yes (instantaneous probe ingested) | **Partial** — probe emitted, rating not captured | High |
| Objective SA capture (SAGAT freeze-probe, SPAM queries) | No | No (external) | No (external) | **No** | High |
| Trust-in-automation scale ingestion | No | External | External | **No** | High |
| Multimodal physiology synchronisation (EEG, ECG, eye tracking, fNIRS, GSR) | No | No | LSL-compatible | **No** | High |
| Standardised data export (BIDS-derivative or analogue) | No | No | No | **No** (custom JSONL) | Medium |
| Counterbalanced training trials and practice criterion | External | Yes | Yes | **No** | Medium |
| Population-specific stressor packs (fighter / RPA / transport) | No | No | Generic | **Partial** — UAV vs Fighter scenarios but not stressors | High |
| G-LOC, hypoxia, AGSM-failure events as scenario states | No | No | No | **No** | High (fighter) |
| Lost-link, kill-chain trauma, multi-RPA load | No | No | No | **No** | High (RPA) |
| Sustained-operations / circadian / fatigue protocol | No | No | Limited | **No** | High (transport) |
| MUM-T / synthetic-wingman / multi-platform link layer | No | No | No | **No** | High |
| Reproducibility infrastructure (seed, scenario manifest, version pinning) | Limited | Yes | Yes | **Partial** — seed only | Medium |
| Open-source distribution and modifiability | Yes (NASA) | DoD only | Limited (USAARL) | Yes (MIT) | **Strength** |

The platform's only pure strengths over the U.S. service benchmarks are its open licence, its modern Python toolchain, and its terminal-first operability in headless / CI environments. Every other row is a deficit relative to USAARL MATB and most are deficits relative to AF-MATB.

The single most important gap, as the table shows, is the *absence of an operator input loop*. Until that is added, no other addition (LSL, SAGAT, NASA-TLX) has anything to attach to.

---

## 5. Proposed Additions

The following additions are derived directly from sections 3–4. They are sorted by precedence: each item presupposes the items above it.

### 5.1 Operator input loop with primary-task scoring (Phase 8)

* Implement a foreground input thread that captures keyboard / mouse / controller events with monotonic timestamps and binds them to the active primary task.
* Re-implement the four canonical MATB primary tasks as Python objects with a uniform `Task` interface (`render`, `tick`, `accept_input`, `score`).
* Score per-task accuracy and reaction time on every event; emit `task_score` records into the JSONL alongside `event` records.
* Acceptance criterion: a healthy adult participant should be able to complete all four tasks concurrently and produce a per-task scoring file that tracks within ±5% of an external reference (run a head-to-head against MATB-II to validate).

### 5.2 Validated rating-scale ingestion (Phase 8)

* When the runner emits an `ISA WORKLOAD PROBE`, synchronously block until the operator returns a 1–10 rating (or the response window expires). Add a `rating` record with `scale`, `value`, `latency_sec`, and `block` fields.
* Add post-block NASA-TLX (six-item) capture and the Bedford workload scale; both are validated and short. NASA-TLX is the de facto reference and Bedford is preferred in fast-paced cockpit contexts.
* Add a Single Ease Question / Mission Awareness Rating Scale (MARS) variant for SA debrief.

### 5.3 SAGAT freeze-probe service (Phase 8)

* Implement a freeze mechanism that pauses the scenario at scripted points (or randomly within an interval), blanks the displays for a configurable duration, prompts the operator with perception / comprehension / projection questions, and resumes.
* Score each probe as correct / partial / incorrect against the ground-truth scenario state at freeze time. Persist as `sagat_probe` records.
* Endsley (1995a) is the methodological reference; Endsley (2021) [doi:10.1177/0018720819875376] is the meta-analytic implementation reference.

### 5.4 LSL gateway for multimodal physiology (Phase 9)

* Add a `pylsl`-backed outlet that publishes scenario events, automation state, demand-block markers, and operator inputs as an LSL stream of type `Markers`.
* Add an LSL inlet wrapper that subscribes to physiological streams (EEG, ECG, GSR, eye tracking) and writes one `physiology.jsonl` per stream into the run directory, with monotonic-aligned timestamps.
* Use the canonical Kothe et al. (2025) implementation. The platform does *not* need to ship hardware drivers — LSL handles those.

### 5.5 Counterbalanced Latin-square block ordering and training trials (Phase 9)

* Replace the fixed `low → medium → high` order with a Latin-square or Williams-square assignment based on participant ID.
* Add a configurable practice block with a performance criterion (e.g., system-monitoring accuracy ≥0.85, tracking RMSE below threshold) before the experimental blocks begin. Persist a `practice_pass` flag.

### 5.6 Population-specific stressor packs (Phase 10)

* **Fighter pack.** G-LOC threshold and recovery, AGSM-quality input, hypoxia onset / hypoxia hangover state, SD events, missile-warning time-to-impact, ROE ambiguity. Reference: Militello et al. (2024); Mohanavelu et al. (2020); Leinonen et al. (2021); Lyons et al. (2024).
* **RPA pack.** 12/24-hour shift-work timeline with circadian markers, kill-chain trauma annotations (civilian present / harmed / operator-believed-responsible), multi-aircraft NtoM load, audiovisual feedback condition, lost-link procedure. Reference: Chappelle et al. (2014, 2019); Phillips et al. (2019); Valenzano et al. (2018); Fas-Millán & Pastor (2019); Tett et al. (2025).
* **Transport / MUM-T pack.** Sustained-operations fatigue protocol, AAR receiver / boomer states (KC-46 RVS heritage), MUM-T multi-platform datalink, crew-coordination channel. Reference: Serres et al. (2015); Ament et al. (2024); Winterbottom et al. (2016); Levulis et al. (2018); Kim & Kim (2023); Hammarbäck et al. (2023); Roncolini & Quaranta (2024).

### 5.7 BIDS-derivative-style data export (Phase 10)

* Adopt a BIDS-Behavioral / BIDS-Derivatives layout: top-level `dataset_description.json`, `participants.tsv`, and per-subject `sub-XX/ses-YY/beh/` (and `eeg/`, `physio/` if LSL was used). Each scenario block produces a `*_events.tsv` and a sidecar `*_events.json` with column descriptions.
* Aim for compatibility with the BIDS-Behavioral extension and with EEG-BIDS for any LSL-captured EEG streams.

### 5.8 Aeromedical baseline neurocognitive screen (Phase 10)

* Run a brief baseline at the start of each session, modelled on CogScreen-AE / ANAM (reaction time, working memory, divided attention, tracking). This yields a within-subject anchor against which subsequent task scores can be normalised, removes a confound for hypoxia / fatigue conditions, and aligns the platform with FAA / DoD aeromedical screening practice.

---

## 6. Roadmap addendum

The phases below extend the existing seven-phase roadmap in the project README. They are explicitly Phase 8+; Phases 1–7 should not be re-numbered.

| Phase | Goal | Key deliverable |
|---|---|---|
| 8 | Operator input + primary-task scoring + validated rating capture + SAGAT freeze | A real MATB inner loop. Acceptance: head-to-head with MATB-II within ±5% per-task. |
| 9 | LSL gateway + counterbalancing + practice criterion | Reproducible multimodal sessions; physiology synchronisable with EEG / ECG / eye tracking. |
| 10 | Population-specific stressor packs (fighter / RPA / transport-MUM-T) + BIDS-derivative export + aeromedical baseline | Population-validated experimental sessions exportable to community-standard formats. |
| 11 | Adaptive automation engine driven by performance and physiology | Performance- and physiology-driven dynamic handoffs in the spirit of USAARL MATB §3 (Vogl 2024). |
| 12 | Web / TSX operator interface (optional) | Browser-based station; not required for research-grade status, but useful for multi-station crew studies. |

---

## 7. Conclusion

The current `aircraft_monitor` platform is an excellent scenario engine and a credible terminal-based mission visualiser, but it is not yet a multi-attribute task battery: it lacks an operator input loop, primary-task scoring, validated rating ingestion, objective SA capture, and physiology synchronisation. The U.S. service benchmarks — AF-MATB (Miller et al., 2014) and USAARL MATB (Vogl et al., 2024) — supply a clear template for the inner loop. The military-aviator literature, particularly the Chappelle RPA series for drone operators and the Militello / Mohanavelu / Taheri Gorji / Haseeb fighter literature, supplies concrete population-specific stressors and physiological endpoints that should be parameterised, not narrated. Adding (i) the inner loop, (ii) LSL physiology synchronisation, (iii) SAGAT freeze-probe SA capture, (iv) NASA-TLX / Bedford / ISA rating ingestion, (v) population-specific stressor packs, (vi) BIDS-derivative data export, (vii) Latin-square counterbalancing with a practice criterion, and (viii) an aeromedical baseline screen would move the platform across the threshold from event simulator to research instrument, and would put it in a position to publish operationally relevant findings in *Aerospace Medicine and Human Performance*, *Human Factors*, *Frontiers in Neuroergonomics*, *Applied Ergonomics*, and *IEEE Transactions on Human-Machine Systems*.

---

## References

Author lists for each entry below were verified against either Crossref (`https://api.crossref.org/works/{DOI}`) or scite metadata captured during the literature search. Where Crossref returned only a partial author list within the truncated response window, attribution defaulted to the scite/PubMed snippet and "et al." is used to acknowledge that not every co-author is listed; readers should consult the DOI directly for the canonical author list. Endsley (1995a/b), Wickens (2002), NASA MATB-II (Santiago-Espada et al., 2011), Onnasch et al. (2014), Levulis et al. (2018), Pontiggia et al. (2024), Vogl et al. (2024), Bjurling (2025), Walker et al. (2013), Waraich et al. (2013), Cummings & Mitchell (2007), Hoff & Bashir (2015), Aweiss et al. (2018), Cahill et al. (2018), Prinet et al. (2012), and FAA (2016) are already cited in the project README and are not duplicated here unless load-bearing in the gap analysis.

1. Ament, J., Lachmann, J., & Schmelz, J. (2024). Design and Assessment of Fighter Pilot Assistance Systems for Air-to-Air Refuelling with Probe-and-Drogue-Equipment. *CEAS Aeronautical Journal*, 15(4), 1091–1110. https://doi.org/10.1007/s13272-024-00756-4
2. Blum, S., Hölle, D., & Bleichner, M. G. (2021). Pocketable Labs for Everyone: Synchronized Multi-Sensor Data Streaming and Recording on Smartphones with the Lab Streaming Layer. *Sensors*, 21(23), 8135. https://doi.org/10.3390/s21238135
3. Chappelle, W. L., McDonald, K. D., Prince, L., Goodman, T., Ray-Sannerud, B. N., & Thompson, W. (2014). Symptoms of psychological distress and post-traumatic stress disorder in United States Air Force "drone" operators. *Military Medicine*, 179(8S), 63–70. https://doi.org/10.7205/MILMED-D-13-00501
4. Chappelle, W., Goodman, T., Reardon, L., & Prince, L. (2019). Combat and operational risk factors for post-traumatic stress disorder symptom criteria among United States Air Force remotely piloted aircraft "Drone" warfighters. *Journal of Anxiety Disorders*, 62, 86–93. https://doi.org/10.1016/j.janxdis.2019.01.003
5. Dunn, M. (2023). *Remotely Piloted Aircraft: The impact of audiovisual feedback and workload on operator performance* [Doctoral dissertation, UNSW Sydney]. https://doi.org/10.26190/unsworks/24887
6. Endsley, M. R. (1995a). Measurement of situation awareness in dynamic systems. *Human Factors*, 37(1), 65–84. https://doi.org/10.1518/001872095779049499
7. Endsley, M. R. (2019). The Divergence of Objective and Subjective Situation Awareness: A Meta-Analysis. *Journal of Cognitive Engineering and Decision Making*, 14(1), 34–53. https://doi.org/10.1177/1555343419874248
8. Endsley, M. R. (2021). A Systematic Review and Meta-Analysis of Direct Objective Measures of Situation Awareness: A Comparison of SAGAT and SPAM. *Human Factors*, 63(1), 124–150. https://doi.org/10.1177/0018720819875376
9. Fas-Millán, M. Á., & Pastor, E. (2019). NtoM: A Concept of Operations for Pilots of Multiple Remotely Piloted Aircraft. *International Review of Aerospace Engineering*, 12(1), 12. https://doi.org/10.15866/irease.v12i1.16153
10. Gruenwald, C. M., Middendorf, M. S., & Hoepf, M. R. (2018). Augmenting human performance in remotely piloted aircraft. *Aerospace Medicine and Human Performance*, 89(2), 115–121. https://doi.org/10.3357/amhp.4894.2018
11. Hammarbäck, J., Alfredson, J., & Johansson, B. (2023). My synthetic wingman must understand me: modelling intent for future manned–unmanned teaming. *Cognition, Technology & Work*, 26(1), 107–126. https://doi.org/10.1007/s10111-023-00745-3
12. Haseeb, M., Nadeem, R., Sultana, N., Naseer, N., Nazeer, H., & Dehais, F. (2025). Monitoring pilots' mental workload in real flight conditions using multinomial logistic regression with a ridge estimator. *Frontiers in Robotics and AI*, 12, 1441801. https://doi.org/10.3389/frobt.2025.1441801
13. Kim, S., & Kim, Y. (2023). Development of an MUM-T Integrated Simulation Platform. *IEEE Access*, 11, 21519–21533. https://doi.org/10.1109/ACCESS.2023.3248096
14. Kothe, C., Shirazi, S. Y., Stenner, T., et al. (2025). The Lab Streaming Layer for synchronized multimodal recording. *Imaging Neuroscience*, 3. https://doi.org/10.1162/imag.a.136
15. Kumar, A. (2023). In-flight loss of consciousness in a fighter aircrew — G-LOC or No G-LOC conundrum. *Indian Journal of Aerospace Medicine*, 66, 84–89. https://doi.org/10.25259/ijasm_17_2021
16. Leinonen, A., Varis, N., Kokki, H., & Leino, T. K. (2021). Normobaric hypoxia training in military aviation and subsequent hypoxia symptom recognition. *Ergonomics*, 64(4), 545–552. https://doi.org/10.1080/00140139.2020.1842514
17. Levulis, S. J., DeLucia, P. R., & Kim, S. Y. (2018). Effects of touch, voice, and multimodal input, and task load on multiple-UAV monitoring performance during simulated manned-unmanned teaming in a military helicopter. *Human Factors*, 60(8), 1117–1129. https://doi.org/10.1177/0018720818788995
18. Lyons, J. B., Mator, J. D., & Orr, T. E. (2024). Is the Pull-Down Effect Overstated? An Examination of Trust Propagation Among Fighter Pilots in a High-Fidelity Simulation. *Journal of Cognitive Engineering and Decision Making*, 18(2), 99–113. https://doi.org/10.1177/15553434231225909
19. Maas, S. A., Göcking, T., Stojan, R., Voelcker-Rehage, C., & Kutz, D. F. (2024). Synchronization of Neurophysiological and Biomechanical Data in a Real-Time Virtual Gait Analysis System (GRAIL): A Proof-of-Principle Study. *Sensors*, 24(12), 3779. https://doi.org/10.3390/s24123779
20. Mansikka, H., Harris, D., & Virtanen, K. (2023). Accuracy and Similarity of Team Situation Awareness in Simulated Air Combat. *Aerospace Medicine and Human Performance*, 94(6), 429–436. https://doi.org/10.3357/amhp.6196.2023
21. Militello, L. G., Ernst, K., & Panganiban, A. R. (2024). Get on the Round Dial: Fighter Pilot Strategies for Recovering Situation Awareness After Disorienting Physiological Events. *Journal of Cognitive Engineering and Decision Making*, 18(2), 137–155. https://doi.org/10.1177/15553434241234105
22. Miller, W. D., Schmidt, K. D., & Estepp, K. D. (2014). *An Updated Version of the U.S. Air Force Multi-Attribute Task Battery (AF-MATB)*. Air Force Research Laboratory. DTIC ADA611870. https://doi.org/10.21236/ada611870
23. Mohanavelu, K., Poonguzhali, S., Ravi, D., et al. (2020). Cognitive Workload Analysis of Fighter Aircraft Pilots in Flight Simulator Environment. *Defence Science Journal*, 70(2), 131–139. https://doi.org/10.14429/dsj.70.14539
24. Nguyen, T. T., Lim, C. P., & Nguyen, N. D. (2019). A Review of Situation Awareness Assessment Approaches in Aviation Environments. *IEEE Systems Journal*, 13(3), 3590–3603. https://doi.org/10.1109/JSYST.2019.2918283
25. Niu, Y., Zhou, T., & Bai, L. (2021). Research on color coding of fighter jet head-up display key information elements in air–sea flight environment based on eye-tracking technology. *Proceedings of the Institution of Mechanical Engineers, Part G: Journal of Aerospace Engineering*, 236(10), 2010–2030. https://doi.org/10.1177/09544100211049025
26. Page, C., Liu, C. C., Meltzer, J., & Ghosh Hajra, S. (2024). Blink-Related Oscillations Provide Naturalistic Assessments of Brain Function and Cognitive Workload within Complex Real-World Multitasking Environments. *Sensors*, 24(4), 1082. https://doi.org/10.3390/s24041082
27. Parry, J., & Hubbard, S. (2023). Review of Sensor Technology to Support Automated Air-to-Air Refueling of a Probe Configured Uncrewed Aircraft. *Sensors*, 23(2), 995. https://doi.org/10.3390/s23020995
28. Peißl, S., Wickens, C. D., & Baruah, R. (2018). Eye-Tracking Measures in Aviation: A Selective Literature Review. *International Journal of Aerospace Psychology*, 28(3–4), 98–112. https://doi.org/10.1080/24721840.2018.1514978
29. Phillips, A., Sherwood, D., Greenberg, N., & Jones, N. (2019). Occupational stress in Remotely Piloted Aircraft System operators. *Occupational Medicine*, 69(4), 244–250. https://doi.org/10.1093/occmed/kqz054
30. Roncolini, F., & Quaranta, G. (2024). Manned-Unmanned Teaming Applied To HEMS Missions: A Path Planning Approach Based On The Pilot's Workload Assessment. *Vertical Flight Society 80th Annual Forum*. https://doi.org/10.4050/f-0080-2024-1213
31. Serres, J. L., Dukes, S., & Wright, B. (2015). *Assessment of Fatigue in Deployed Critical Care Air Transport Team Crews*. Defense Technical Information Center, ADA624315. https://doi.org/10.21236/ada624315
32. Summerfield, D. T., Raslau, D., & Johnson, B. (2018). Physiologic Challenges to Pilots of Modern High Performance Aircraft. In S. Stirling (Ed.), *Aircraft Technology*. IntechOpen. https://doi.org/10.5772/intechopen.75982
33. Taheri Gorji, H., Wilson, N., VanBree, J., et al. (2023). Using machine learning methods and EEG to discriminate aircraft pilot cognitive workload during flight. *Scientific Reports*, 13(1), 2507. https://doi.org/10.1038/s41598-023-29647-0
34. Tett, R. P., Devlin, N., & Galloway, K. (2025). Pandemic Concerns, Occupational Stressors, Burnout, and Psychological Distress Among U.S. Air Force Remotely Piloted Aircraft Personnel: A Multidimensional Mediation Model. *Stress and Health*, 41(2). https://doi.org/10.1002/smi.70027
35. Valenzano, A., Moscatelli, F., Messina, A., et al. (2018). Stress Profile in Remotely Piloted Aircraft Crewmembers During 2 h Operating Mission. *Frontiers in Physiology*, 9, 461. https://doi.org/10.3389/fphys.2018.00461
36. Varis, N., Leinonen, A., & Parkkola, K. (2022). Hyperventilation and Hypoxia Hangover During Normobaric Hypoxia Training in Hawk Simulator. *Frontiers in Physiology*, 13, 942249. https://doi.org/10.3389/fphys.2022.942249
37. Verdière, K. J., Dehais, F., & Roy, R. N. (2019). Spectral EEG-based classification for operator dyads' workload and cooperation level estimation. *IEEE International Conference on Systems, Man and Cybernetics (SMC)*, 3919–3924. https://doi.org/10.1109/SMC.2019.8913848
38. Vogl, J., McCurry, C. D., Bommer, S., & Atchley, J. A. (2024). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. *Frontiers in Neuroergonomics*, 5, 1435588. https://doi.org/10.3389/fnrgo.2024.1435588
39. Vogl, J., O'Brien, K., & St. Onge, P. (2025). One size does not fit all: a support vector machine exploration of multiclass cognitive state classifications using physiological measures. *Frontiers in Neuroergonomics*, 6, 1566431. https://doi.org/10.3389/fnrgo.2025.1566431
40. Winterbottom, M., Lloyd, C. J., & Gaska, J. (2016). Stereoscopic Remote Vision System Aerial Refueling Visual Performance. *Electronic Imaging — Stereoscopic Displays and Applications XXVII*, 28(5), 1–10. https://doi.org/10.2352/issn.2470-1173.2016.5.sda-437

---

*Document maintained at `docs/research/military-aviation-platform/research_evidence_review.md`. On every revision, re-extract author lists from Crossref (`https://api.crossref.org/works/{DOI}`) before adding new citations.*
