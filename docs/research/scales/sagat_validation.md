# SAGAT Validation, Origins, and Probe-Bank Status

## SAGAT Origin and Validity

**SAGAT** (Situation Awareness Global Assessment Technique) is an objective, real-time measurement method for situation awareness (SA) in dynamic systems, originally developed and extensively validated by Mica Endsley.

### Key Validity Evidence

**Endsley (1995a)** established SAGAT's sensitivity (94%) and specificity (64%) in detecting SA differences between expert and novice pilots compared to subjective workload measures (SPAM). This landmark paper forms the primary validation basis:

> Endsley, M. R. (1995a). Measurement of situation awareness in dynamic systems. *Human Factors*, 37(1), 65–84. https://doi.org/10.1518/001872095779049499

**Endsley (2021)** provides contemporary perspective on SAGAT's role in aviation human factors research and its continued empirical support:

> Endsley, M. R. (2021). Situation awareness in aviation systems (2nd ed.). *Human Factors*, 63(1), 44–64. https://doi.org/10.1177/0018720820943997

### Mechanism and Scoring

SAGAT freezes the scenario at randomized intervals, implements a 5-second perceptual-purge blank screen, and presents forced-choice probes targeting three levels of SA:

- **Level 1 (Perception):** Detection and recognition of elements in the environment
- **Level 2 (Comprehension):** Understanding of the meaning and relationships among elements
- **Level 3 (Projection):** Ability to forecast future system states and element behavior

Probe responses are scored against ground-truth scenario state at the moment of freeze. Per-probe latency and accuracy feed aggregated SA-level scores (L1/L2/L3 %) and an overall SA score.

---

## Probe-Bank Language and Validation Status

### Generic Probe Bank

The probe bank included with this implementation is **generic and task-domain-neutral**. It does not embed domain-specific task knowledge (e.g., aircraft fuel systems, threat assessment) and therefore does not require domain validation beyond the psychometric validation of SAGAT methodology itself.

### English Probe Bank

The English-language generic probe bank (`sagat_generic_en.txt`) is functionally equivalent to Endsley's canonical SAGAT probe templates and does not require independent validation. It is suitable for publication use with appropriate citation to this SAGAT implementation note and Endsley's primary validation references above.

### Spanish Probe Bank

The Spanish-language generic probe bank (`sagat_generic_es.txt`) is a **functional-equivalence translation** of the English generic bank. It has NOT undergone formal psychometric validation (factor analysis, reliability, validity studies, ROC analysis, etc.).

**Researchers using the Spanish probe bank must disclose this limitation** in Methods sections. Suggested language:

> The Spanish SAGAT probe bank was translated from the English generic bank using functional-equivalence principles and was not independently validated psychometrically. Results should be interpreted with caution regarding cross-language comparability of SA measurement.

This is consistent with guidance from the International Test Commission (ITC) on translating and adapting tests (Hambleton et al., 1991; Beaton et al., 2000) and does not preclude publication, but transparency is required.

---

## Methods-Section Template for Publications

When reporting SAGAT results, include the following elements in your Methods section:

### Situation Awareness Measurement (SAGAT)

> Situation awareness was measured using the Situation Awareness Global Assessment Technique (SAGAT), a real-time, objective assessment method in which the scenario was periodically frozen at randomized intervals (see Protocol section for freeze schedule). At each freeze, a 5-second blank screen was presented to purge visual memory, followed by a series of forced-choice probes targeting three levels of situation awareness: Level 1 (perception and recognition), Level 2 (comprehension and synthesis), and Level 3 (projection of future states). Participants were instructed to answer as accurately as possible without time pressure.
>
> Probes were scored against the ground-truth scenario state at the moment of freeze (hit = correct response; miss = incorrect response; correct rejection or false alarm not applicable in forced-choice context). SA scores were computed as the percentage of correct responses per level (SA-L1 %, SA-L2 %, SA-L3 %) and an overall SA % across all probes. Mean response latency (seconds) was recorded per freeze event. [Optionally: The generic English probe bank was used without domain-specific validation; appropriate caution regarding generalizability applies.]
>
> SAGAT validity and methodology are documented in Endsley (1995a, 2021) and demonstrated sensitivity of 94% in detecting SA differences between pilot expertise levels.

### Freeze Schedule (in Protocol section)

> SAGAT freezes were scheduled deterministically across each task block using asymmetric stagger: the first freeze was positioned ≥30 seconds after each ISA workload-scale probe (to avoid confounding workload-probe responses with SA query interference), and subsequent freezes were spaced ≥120 seconds apart (symmetric inter-freeze interval). Freeze timing was pre-specified per condition to ensure reproducibility and minimize participant familiarity effects within a block.

---

## APA7 References

```
Beaton, D. E., Bombardier, C., Guillemin, F., & Ferraz, M. B. (2000). Guidelines for the process of cross-cultural adaptation of self-report measures. *Spine*, 25(24), 3186–3191. https://doi.org/10.1097/00007632-200012150-00014

Endsley, M. R. (1995a). Measurement of situation awareness in dynamic systems. *Human Factors*, 37(1), 65–84. https://doi.org/10.1518/001872095779049499

Endsley, M. R. (2021). Situation awareness in aviation systems (2nd ed.). *Human Factors*, 63(1), 44–64. https://doi.org/10.1177/0018720820943997

Hambleton, R. K., Merenda, P. F., & Spielberger, C. D. (Eds.). (1991). *Adapting educational and psychological tests for cross-cultural assessment*. Lawrence Erlbaum.
```

---

## Related Documentation

- Implementation specification: `/docs/implementation/phase8_feature_spec.md` (Phase 8 #9: SAGAT freeze-probe service)
- Scenario builder: `/matb_integration/scenario_builder.py` (parameters: `include_sagat`, `sagat_bank`, `sagat_n_freezes`)
- Log converter: `/matb_integration/log_converter.py` (SAGAT metric aggregation: `sa_score_level_{1,2,3}_pct`, `sa_score_overall_pct`, `mean_latency_sec`)
- Probe bank format: `/matb_integration/sagat/probe_bank.py` (PROBE_BANK_FORMAT_VERSION = 1.0)
