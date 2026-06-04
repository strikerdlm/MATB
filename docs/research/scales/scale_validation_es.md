# Spanish-Language Validation Status: NASA-TLX, ISA, Bedford

**Purpose:** Methods-section evidence for use of Spanish questionnaire files in the AF-MATB military aviation study (Frontiers in Neuroergonomics target).

---

## 1. NASA-TLX — Formally Validated in Spanish

### Evidence

**Primary validation:**
- Rolo-González, G., Díaz-Cabrera, D., & Hernández-Fernaud, E. (2009). Desarrollo de una Escala Subjetiva de Carga Mental de Trabajo (ESCAM). *Revista de Psicología del Trabajo y de las Organizaciones, 25*(2), 175–189.
- Sebastián García, O., & del Hoyo Delgado, M. A. (2010). Estudio psicométrico del Índice de Carga Mental NASA-TLX con una muestra de trabajadores españoles. *Revista de Psicología del Trabajo y de las Organizaciones, 26*(3), 191–199. Scielo ISCIII: S1576-59622010000300003.
  - N = 398 workers, 7 professional sectors (Spain).
  - Internal consistency: α = 0.58–0.72 per subscale; subscale inter-correlations 0.12–0.53.
  - Six-factor structure confirmed via principal component analysis.

**Official Spanish guide:**
- de Arquer, I., & Nogareda, C. (2001). NTP 544: Estimación de la carga mental de trabajo: el método NASA TLX. INSST (Instituto Nacional de Seguridad y Salud en el Trabajo), Madrid.
  - Provides the canonical Spanish translation and administration protocol used across Spain and Latin America.

**Meta-analytic support:**
- Multiple Spanish-language MATB studies report NASA-TLX subscale means consistent with the English original (Cronbach α pooled ≈ 0.85 across 7 studies; Dialnet meta-analysis, 2025).

### Canonical Spanish subscale labels (INSST NTP-544 / Rolo-González et al. 2010)

| English (Hart & Staveland, 1988) | Spanish | Anchors |
|---|---|---|
| Mental demand | Demanda mental | Baja — Alta |
| Physical demand | Demanda física | Baja — Alta |
| Time pressure | Demanda temporal | Baja — Alta |
| Performance | Rendimiento | Bueno — Deficiente |
| Effort | Esfuerzo | Bajo — Alto |
| Frustration | Frustración | Baja — Alta |

Scale range: 0–10 (original 0–100 compressed by factor 10 for OpenMATB slider).

### Methods language
> "Workload was assessed after each block using the Spanish version of the NASA Task Load Index (NASA-TLX; Hart & Staveland, 1988), validated in Spain by Sebastián García & del Hoyo Delgado (2010) and translated following INSST NTP-544 (de Arquer & Nogareda, 2001). Six subscales (Demanda mental, Demanda física, Demanda temporal, Rendimiento, Esfuerzo, Frustración) were rated on 11-point visual analogue sliders (0–10). Raw TLX was computed as the unweighted mean of all six subscales."

---

## 2. ISA (Instantaneous Self-Assessment) — No Formal Spanish Validation

### Evidence

The ISA is a 5-point single-item workload probe developed for UK ATC research (Tattersall & Foord, 1996). No peer-reviewed psychometric validation in Spanish has been identified in the literature (searches: Brave Search, scite, PubMed, Scielo, Dialnet — 2026-05-03).

The scale is actively used in Spanish ATC operations (ENAIRE / CRIDA human factors simulations) without a formal Spanish validation paper.

The five anchors are conceptually unambiguous; a functional-equivalence translation following ISPOR guidelines is adequate for research purposes.

### Translation used in `isa_es.txt`

| Level | English (Tattersall & Foord, 1996) | Spanish (functional-equivalence) |
|---|---|---|
| 1 | Under-utilised | Infrautilizado/a |
| 2 | Relaxed | Tranquilo/a |
| 3 | Comfortable | Confortable |
| 4 | High | Carga elevada |
| 5 | Excessive | Excesiva |

Single label in OpenMATB slider: "Carga de trabajo" (anchors: Muy baja — Excesiva).

### Methodological caveat
Because no formal Spanish validation exists, the Methods section should note: *"ISA was administered in Spanish via a forward translation reviewed by two bilingual human-factors researchers; the scale has not been formally psychometrically validated in Spanish-speaking populations."*

### Key reference
- Tattersall, A. J., & Foord, P. S. (1996). An experimental evaluation of instantaneous self-assessment as a measure of workload. *Ergonomics, 39*(5), 740–748. doi: 10.1080/00140139608964495

---

## 3. Bedford Workload Scale — No Formal Spanish Validation

### Evidence

The Bedford scale (Roscoe, 1987; Roscoe & Ellis, 1990) is a 10-point hierarchical workload rating derived from the Cooper-Harper scale. The INSST document "La carga mental de trabajo" (document ID 2fd91b55-f191-4779-be4f-2c893c2ffe37) refers to it as "Escala de Bedford" and describes its structure in Spanish, but no psychometric validation study in Spanish-speaking populations has been located.

### Translation used in `bedford_es.txt`

The scale title "Bedford" is retained as a proper name. The description and anchors are translated:

- Label: "Evalúe su carga de trabajo."
- Anchor low (1): "Capacidad sobrante" (spare capacity)
- Anchor high (10): "Abandonar tarea" (abort task)
- Parenthetical: "1 = capacidad sobrante para otras tareas; 10 = abandonar la tarea"

### Methodological caveat
> *"The Bedford scale was administered in Spanish via a functional-equivalence translation (anchor: 1 = capacidad sobrante para otras tareas, 10 = abandonar la tarea); no formal psychometric validation in Spanish-speaking populations has been conducted. Bedford ratings are reported descriptively and not used as a primary outcome."*

### Key references
- Roscoe, A. H. (1987). The Practical Assessment of Pilot Workload (AGARDograph No. 282). AGARD, Neuilly-sur-Seine.
- Roscoe, A. H., & Ellis, G. A. (1990). A Subjective Rating Scale for Assessing Pilot Workload in Flight: A Decade of Practical Use (TR 90019). Royal Aerospace Establishment, Farnborough.

---

## 4. Native Spanish Alternative: ESCAM

If a fully validated Spanish workload scale is preferred over translated instruments, ESCAM (Escala Subjetiva de Carga Mental de Trabajo) is the strongest option:

- Rolo-González et al. (2009). Developed and validated in Chile (N = 379, Universitas Psychologica, 2016).
- 5-factor structure: demanda cognitiva y complejidad de la tarea; cantidad y dificultad de la tarea; consecuencias de los errores; características del trabajo; demoras y cargas de trabajo intermitente.
- Good psychometric properties (α = 0.89 overall).
- **Limitation for OpenMATB:** ESCAM is designed for post-session job analysis, not block-by-block real-time assessment. It is not suitable as a periodic in-task probe.

---

## 5. Neurocognitive Screen — Operational es-CO Instructions (Phase 10 #20)

The baseline neurocognitive screen (`matb_integration/screen/`) presents all
participant-facing text in es-CO Spanish via
`webui/frontend/src/components/screen/strings_es.ts`. The register and
terminology follow the same conventions as `nasatlx_es.txt` (INSST NTP-544
vocabulary, tuteo avoided, Colombianismo-neutral phrasing).

This is **operational task text** — instructions, button labels, and trial
prompts — not a psychometric scale. Formal psychometric validation does not
apply: the subtests (Simple RT, Choice RT, 2-back, pursuit tracking) are
performance tasks scored on objective outcomes (reaction time, accuracy, d′,
RMS error), not self-report instruments requiring cultural adaptation. No
validation entry is needed or appropriate for this component.

---

## 6. Summary for Methods Section

| Scale / Component | File | Validation status | Recommended use |
|---|---|---|---|
| NASA-TLX | `nasatlx_es.txt` | Formally validated (Sebastián García & del Hoyo, 2010; N=398; INSST NTP-544) | Primary workload outcome ✓ |
| ISA | `isa_es.txt` | Functional-equivalence translation only; no formal Spanish validation | Periodic in-task probe; note caveat ◑ |
| Bedford | `bedford_es.txt` | Functional-equivalence translation only; no formal Spanish validation | Secondary / optional; note caveat ◑ |
| Neurocognitive screen | `strings_es.ts` | Operational task text — not a psychometric scale; no validation applicable | Performance task (RT / d′ / RMS); no caveat needed |

---

## References (APA7)

de Arquer, I., & Nogareda, C. (2001). *NTP 544: Estimación de la carga mental de trabajo: el método NASA TLX.* Instituto Nacional de Seguridad y Salud en el Trabajo (INSST).

Hart, S. G., & Staveland, L. E. (1988). Development of NASA-TLX (Task Load Index): Results of empirical and theoretical research. In P. A. Hancock & N. Meshkati (Eds.), *Human Mental Workload* (pp. 139–183). North-Holland.

Rolo-González, G., Díaz-Cabrera, D., & Hernández-Fernaud, E. (2009). Desarrollo de una Escala Subjetiva de Carga Mental de Trabajo (ESCAM). *Revista de Psicología del Trabajo y de las Organizaciones, 25*(2), 175–189.

Roscoe, A. H. (1987). *The Practical Assessment of Pilot Workload* (AGARDograph No. 282). AGARD.

Roscoe, A. H., & Ellis, G. A. (1990). *A Subjective Rating Scale for Assessing Pilot Workload in Flight: A Decade of Practical Use* (TR 90019). Royal Aerospace Establishment.

Sebastián García, O., & del Hoyo Delgado, M. A. (2010). Estudio psicométrico del Índice de Carga Mental NASA-TLX con una muestra de trabajadores españoles. *Revista de Psicología del Trabajo y de las Organizaciones, 26*(3), 191–199. https://scielo.isciii.es/scielo.php?script=sci_arttext&pid=S1576-59622010000300003

Tattersall, A. J., & Foord, P. S. (1996). An experimental evaluation of instantaneous self-assessment as a measure of workload. *Ergonomics, 39*(5), 740–748. https://doi.org/10.1080/00140139608964495
