# FAC ISR Safety Management and Human Performance Suite

## Approved Product Design

**Date:** 2026-08-08

**Author:** Dr Diego Malpica — Aerospace Medicine and Human Performance — Subdirectorate of Aerospace Sciences — Colombian Aerospace Force

**Status:** Approved conversational design consolidated for written review

**Primary authority profile:** Colombian State Aviation, FAC ISR, under AAAES and RACAE

**Future profiles, in order:** Private Certified Operator, then Civil Public Entity

## 1. Executive decision

The product is an offline-first, bilingual Safety Decision Support System for Colombian Aerospace Force ISR UAS and RPAS operations. It supports the complete safety lifecycle before, during, and after flight for unarmed ISR and support configurations in every RACAE aircraft class. It creates an evidence-backed mission safety case, applies class- and operation-specific requirements, monitors read-only telemetry, manages the four-gate release process, preserves an immutable audit trail, and feeds organizational safety assurance and human-factors research.

The product is not a ground control station. It cannot arm, launch, command, redirect, or recover an aircraft. It does not store ISR imagery, intelligence products, weapons data, or classified information. The approved GCS remains the only system with a command path to the aircraft.

True one-to-many swarm control is not dispatchable under the initial operational profile. RACAE 94 section 94.201(a) requires one operator or remote pilot per aircraft, and section 94.250 is reserved. Operational missions may coordinate one, two, three, or more aircraft only when each aircraft has an assigned qualified operator or remote pilot. A separate research mode may model swarm concepts but must label every such scenario non-dispatchable.

## 2. Product purpose

The suite has five connected purposes:

1. Help FAC ISR personnel establish whether a proposed mission satisfies the applicable regulatory, technical, operational, environmental, and human-performance conditions.
2. Make the evidence, assumptions, residual risks, approvals, and limitations behind every release decision visible and auditable.
3. Support safe read-only monitoring of active missions without creating a flight-command dependency.
4. Convert mission experience, telemetry review, occurrences, hazards, corrective actions, and lessons learned into organizational SMS assurance.
5. Provide a separately governed human-factors research environment for workload, fatigue, situation awareness, automation, alerting, CRM, and human–multi-UAS studies.

The suite does not itself constitute authorization from AAAES, FAC, ATC, UAEAC, or another competent authority. Operational reliance requires verification and acceptance by qualified FAC personnel and the competent institutional authorities.

## 3. Success criteria

The design is successful when:

- A mission cannot be labelled ready unless every applicable hard requirement has a valid result, current evidence, and required approval.
- Every rule result traces to an authoritative source, edition, section, effective date, and approved normalized interpretation.
- All supported unarmed RACAE class configurations activate the correct aircraft, airspace, crew, airworthiness, VFR or IFR, communications, and flight-plan requirements.
- A material mission change invalidates precisely the approvals and calculations affected by that change.
- The edge node can plan, review, monitor, debrief, and export a mission with no internet connection.
- The interface clearly distinguishes ready, conditional, degraded, blocked, suspended, aborted, and closed states without relying on colour alone.
- The product cannot transmit C2 commands through any supported interface.
- Operational and research identities and records remain physically and logically separated.
- Spanish and English interfaces use the same stable concepts and cannot produce different rule behaviour.
- Golden blocked cases never produce a release-ready result.
- A complete mission package can be independently reconstructed from its snapshots, hashes, evidence, decisions, and event ledger.

## 4. Non-goals and prohibited scope

The first product and its future operator profiles do not:

- Control aircraft, payloads, launchers, recovery systems, or GCS functions.
- Design weapons, targeting systems, kinetic effects, or offensive tactics.
- Release an armed, strike, weapon-carrying, or weapon-employment configuration; those configurations remain blocked and outside the product safety case even when the aircraft weight falls within a supported RACAE class.
- Store or process EO, IR, multispectral, SAR, or other ISR imagery.
- Store intelligence assessments, target products, or classified mission content.
- Replace approved flight, maintenance, emergency, training, or command manuals.
- Generate an aeromedical diagnosis, medical clearance, or automated fitness-to-fly determination.
- Treat open-source aeronautical data as authoritative when approved official data is required.
- Treat a simulation or research result as operational proof of safety.
- Treat an AI-generated interpretation as an approved regulatory rule.

The application will display an unclassified controlled-data banner and instruct users not to enter classified content.

## 5. Regulatory and safety basis

### 5.1 Authority hierarchy

When requirements conflict, the system applies this hierarchy:

1. Colombian law, binding AAAES resolutions, and current RACAE.
2. Approved FAC doctrine, orders, manuals, modes of employment, and unit standards.
3. RAC and UAEAC requirements applicable to civil-airspace integration and coordination.
4. ICAO, NATO, JARUS, and recognized aviation or system-safety standards adopted or accepted for the intended use.
5. Approved manufacturer flight, operation, maintenance, and airworthiness material.
6. Peer-reviewed scientific evidence.
7. Internal research syntheses and Obsidian knowledge notes.

A lower-ranked source may add a more conservative control when it does not conflict with a higher-ranked authority. An unresolved conflict or absent authority results in an unverified requirement and blocks any decision that depends on it.

### 5.2 Core Colombian State Aviation corpus

The initial regulatory register will evaluate and normalize at least:

- RACAE 94, Rules of Flight and Operation for UAS and RPAS, Amendment 2.
- RACAE 219, Safety Management System.
- Applicable provisions of RACAE 91, 20, 21, 43, 61, 63, 65, 67, 114, 120, 141, 142, 145, 160, 203, 204, 210, 211, and 215.
- AAAES resolutions, regulatory circulars, safety bulletins, informational circulars, manuals, guides, and current official aeronautical information.
- RAC 100 and related RAC provisions when civil airspace, civil infrastructure, or UAEAC coordination makes them applicable.

The applicable subset is determined by mission, aircraft class, airspace, crew, operating authority, and approved FAC doctrine. Inclusion in the source register does not mean that every provision applies to every mission.

### 5.3 SMS model

The organizational SMS follows the RACAE 219 structure:

1. Safety policy and objectives.
2. Safety risk management.
3. Safety assurance.
4. Safety promotion.

Mission safety cases provide structured inputs to the SMS, including hazards, residual risks, exceptions, occurrences, telemetry reviews, corrective actions, audit findings, management-of-change triggers, and lessons learned.

The risk engine supports an approved probability-and-severity matrix, NASO thresholds, and risk-acceptance authorities configured from controlled FAC policy. The product ships with no invented institutional risk-acceptance authority. Operational release remains unavailable until the approved matrix, acceptance levels, and responsible roles have been configured and signed into the active policy package.

## 6. Research and evidence phase

### 6.1 Research workstreams

Before operational implementation, the evidence phase covers:

1. Current Colombian State Aviation regulation and AAAES source history.
2. RACAE 219 SMS implementation requirements and FAC organizational responsibilities.
3. RACAE class, flight-rule, airspace, crew, airworthiness, maintenance, and occurrence requirements.
4. International SMS, UAS risk, human-factors, and system-safety practices that can add defensible controls without conflicting with RACAE.
5. Publicly documented, non-weaponized UAS capability baselines for procurement and fleet gap analysis.
6. Offline mapping, terrain, weather, NOTAM, AIP, telemetry, cybersecurity, and software-supply-chain practices.
7. Human performance evidence for fatigue, screen exposure, workload, situation awareness, automation supervision, CRM, alarm design, and multi-UAS operations.

### 6.2 Search method

Tavily, Brave, and Firecrawl will be used as complementary research channels:

- Tavily performs bounded discovery and cross-domain recall.
- Brave independently verifies discovery and surfaces alternative official locations.
- Firecrawl extracts selected pages into clean Markdown and captures source metadata.
- Direct official downloads preserve original PDFs and other primary files.
- Academic databases are used for peer-reviewed human-factors and safety evidence.

Discovery results are not evidence by themselves. Claims must be connected to the underlying official or scholarly source. Each research summary will identify query, method, extracted findings, inference, evidence quality, sources, and unresolved gaps.

### 6.3 Evidence library

The SMS/docs evidence library uses:

    docs/
    ├── source-register/
    ├── regulations/original/
    ├── regulations/extracted/
    ├── regulations/normalized/
    ├── fac-doctrine/
    ├── international-standards/
    ├── manufacturer-evidence/
    ├── research/
    ├── obsidian-imports/
    ├── translations/
    └── provenance/

Every acquired file has:

- Stable source identifier.
- Original title and filename.
- Authority and authority rank.
- Canonical URL or controlled internal origin.
- Retrieval date.
- Publication, amendment, and effective dates.
- File size, media type, and cryptographic checksum.
- Language.
- License or use restriction.
- Sensitivity marking.
- Extraction method and extraction checksum.
- Review state and reviewer identity.
- Superseded-by relationship when applicable.

Originals are immutable. Normalized requirements, translations, and interpretations are separate versioned artifacts.

### 6.4 Obsidian imports

Relevant material will be copied, not moved, from the Obsidian vault. Each copy retains its original vault path and checksum. The first candidate set includes:

- Private Pilot & UAS School/Reglamentos Aeronáuticos de Colombia RAC 100.md
- Private Pilot & UAS School/UAS Notes.md
- Research/Drone and Health/rac100_vs_faa_comparison.md
- Research/Drone and Health/FAA_vs_RAC100_sUAS_comparison.md
- AI Projects/SMS/Components.md

These notes provide context and discovery assistance but do not outrank current official publications. A detected discrepancy, such as a note referencing a different RAC 100 amendment than the copied regulation, is recorded and resolved against the official source before normalization.

### 6.5 Preliminary official source verification

The initial discovery pass confirmed the official AAAES RACAE library and RACAE 94 Amendment 2. A direct copy of RACAE 94 downloaded on 2026-08-08 produced SHA-256:

312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976

The production evidence phase must download the official file into SMS/docs, recompute its checksum, and register the acquisition rather than relying on the temporary discovery copy.

## 7. Operator profiles

The safety kernel is profile-driven.

### 7.1 State Aviation profile

The first profile is FAC ISR under AAAES and RACAE. It covers unarmed ISR and support configurations in every RACAE class and uses FAC-approved doctrine and role definitions. It supports routine, training, research, and other authorized mission contexts without encoding classified mission content. Selection of an armed or strike configuration is a hard out-of-scope blocker rather than a configurable exception.

### 7.2 Future profiles

The next profiles are implemented in this order:

1. Private Certified Operator under RAC 100.
2. Civil Public Entity under RAC 100 and its special mission provisions.

The user selects the profile when creating an organization or mission. A profile determines terminology, authority hierarchy, rule packages, approval roles, required documents, risk method, and export format. A mission cannot change profiles after its first approval; it must be cloned into a new mission under the other profile.

## 8. System boundary and deployment

### 8.1 Deployment topology

The system runs on a deployable edge node: a rugged laptop or compact server connected to an isolated local Ethernet or approved wireless network. Role workstations and tablets use a local web interface. The same package can run in standalone mode on one laptop.

The edge node requires no internet connection for:

- Authentication against its local identity store.
- Mission planning and map display.
- Rule evaluation and calculations.
- Four-gate review.
- Read-only monitoring.
- Debrief and occurrence capture.
- Audit and export.
- Research sessions configured for offline use.

### 8.2 Connected staging workstation

A separate connected staging utility:

- Retrieves approved public and institutional updates.
- Validates source identity, schema, license, and integrity.
- Scans packages for malware.
- Produces a signed, versioned update bundle and manifest.
- Writes the bundle to controlled transfer media.
- Records the transfer and intended recipient.

The edge node never needs direct internet access. It verifies every bundle before import and quarantines invalid, unexpected, downgraded, or unsigned packages.

### 8.3 System flow

    Connected staging station
             |
             | signed update package
             v
    Tactical edge node
      - regulatory registry
      - safety kernel
      - mission workflow
      - maps and data packages
      - operational database
      - research database
      - audit ledger
             ^
             |
             | authenticated local clients
             |
      commander, safety, operators, maintenance

    Approved GCS -- one-way telemetry --> telemetry gateway --> edge node
    Edge node --------------- no command path ----------------> GCS

## 9. Logical components

The isolated SMS TypeScript workspace contains:

- Tactical web application: planning, monitoring, SMS, research, and administration interface.
- Edge API: authentication, mission workflow, data access, audit, and local integrations.
- Safety kernel: deterministic applicability, rule, gate, and calculation engine.
- Regulatory registry: sources, normalized rules, translations, effective dates, and review status.
- Geospatial engine: offline maps, route geometry, terrain, airspace, weather, and NOTAM matching.
- Performance engine: aircraft, payload, battery, endurance, reserve, and uncertainty models.
- Telemetry gateway: read-only vendor adapters and a canonical status model.
- Fleet and maintenance module: aircraft, payload, battery, configuration, discrepancy, and release records.
- SMS assurance module: hazards, risks, occurrences, CAPA, audits, SPI, and management of change.
- Human-performance module: operational duty and workload controls.
- Research laboratory: consented, pseudonymous protocols and experimental sessions.
- Export service: bilingual human-readable packages and machine-readable archives.
- Staging utility: connected acquisition, validation, packaging, and signing.

Safety rules, terminology, calculations, and schemas are reusable TypeScript packages with no dependency on the visual interface.

## 10. Core data model

### 10.1 Regulatory entities

- RegulatorySource
- SourceEdition
- NormalizedRequirement
- RequirementTranslation
- ApplicabilityPredicate
- RuleEvaluation
- EvidenceReference
- PolicyPackage

### 10.2 Organization and personnel entities

- Organization
- Unit
- Role
- User
- CrewMember
- Qualification
- RecencyRecord
- DutyPeriod
- Assignment

Operational personnel records retain only the minimum data needed for identity, qualification, assignment, duty, and safety status.

### 10.3 Fleet entities

- UASSystem
- Aircraft
- GroundControlStation
- PayloadConfiguration
- Battery
- AirworthinessRecord
- MaintenanceProgram
- Discrepancy
- MaintenanceAction
- MaintenanceRelease
- CapabilityClaim
- CapabilityEvidence

### 10.4 Mission and SMS entities

- Mission
- MissionRevision
- Route
- Waypoint
- FlightRule
- VisualCondition
- AirspaceRequirement
- DataSnapshot
- Checklist
- ChecklistResponse
- Hazard
- RiskAssessment
- Mitigation
- ResidualRisk
- GateApproval
- OperationalException
- FlightEvent
- TelemetrySegment
- Debrief
- Occurrence
- CorrectiveAction
- AuditFinding
- SafetyPerformanceIndicator
- ManagementOfChangeCase

### 10.5 Research entities

Research entities live in the research database:

- Protocol
- EthicsApproval
- ConsentRecord
- ParticipantCode
- ResearchSession
- ConditionAssignment
- InstrumentDefinition
- InstrumentResponse
- ResearchEvent
- DeidentifiedExport

Operational identity is not stored in the research database. A separately protected linkage mechanism is permitted only when required by an approved protocol.

## 11. Safety kernel

The safety kernel consumes:

- Active operator profile and policy package.
- Mission revision.
- Aircraft class, configuration, and capability evidence.
- Crew roles, qualifications, recency, duty, and safety status.
- Route, terrain, airspace, flight rule, and visual condition.
- Weather, NOTAM, AIP, and local observation snapshots.
- Maintenance, battery, and payload status.
- Risk assessment, mitigations, residual risk, and acceptance authority.
- Gate approvals and operational exceptions.

It produces:

- Applicable and non-applicable requirements with reasons.
- Pass, fail, unknown, expired, or not-reviewed results.
- Release gate status.
- Blocking conditions and required evidence.
- Calculation results with inputs, units, uncertainty, and model version.
- Human-readable explanations in Spanish and English.
- Exact citations to the approved source package.

The kernel is deterministic for a fixed mission, policy, evidence, and data snapshot. Display values never feed back into authoritative calculations.

## 12. Mission lifecycle

The authoritative mission states are:

    Draft
      -> Planned
      -> Under Review
      -> Ready for Release
      -> Released
      -> Active
      -> Completed | Suspended | Aborted
      -> Post-flight Review
      -> Closed

A blocked mission remains in Planned or Under Review with explicit blockers. A material change creates a new MissionRevision and invalidates affected calculations and approvals.

Material changes include:

- Aircraft, GCS, payload, battery, or software configuration.
- Assigned operator, pilot, observer, maintainer, safety officer, or commander.
- Route, altitude, flight rule, visual condition, area, schedule, or mission duration.
- Weather, NOTAM, airspace, or aeronautical-data snapshot.
- Hazard, mitigation, residual-risk level, or exception.
- Approved manufacturer or regulatory baseline.

The dependency graph records which gates and evaluations each field affects.

## 13. Four-gate release

### 13.1 Maintenance release

An authorized maintainer confirms:

- Aircraft identity and configuration.
- Airworthiness and inspection status.
- Open discrepancies and deferrals.
- Required maintenance and minimum equipment.
- Battery and payload condition.
- Firmware, software, and approved configuration.
- Return-to-service authority.

### 13.2 Operator acceptance

Every assigned operator or remote pilot confirms:

- Correct aircraft assignment.
- Qualification and recency.
- Mission and route understanding.
- Airspace, weather, NOTAM, communication, and emergency briefing.
- Automation and lost-link behaviour.
- Duty, fatigue, and personal ability to perform the assigned function.
- Final go/no-go authority and abort criteria.

One qualified operator or remote pilot is required for every active aircraft under the State Aviation profile unless a future authoritative rule package explicitly permits another arrangement.

### 13.3 Safety acceptance or escalation

The safety officer confirms:

- Hazard completeness.
- Risk-method correctness.
- Mitigation ownership and verification.
- Residual-risk level.
- Correct acceptance authority.
- Data freshness and controlled exceptions.
- ERP readiness.

The safety officer may block or escalate but cannot replace the operator’s flight responsibility.

### 13.4 Command authorization

The mission commander confirms:

- Valid mission authority and order.
- Resources and organizational readiness.
- Required coordination and airspace approval.
- Acceptance of residual risk within delegated authority.
- Compliance with unresolved restrictions and limitations.

Command authorization does not remove the operator or remote pilot’s final go/no-go and abort authority.

## 14. Before-flight workflow

The applicability engine assembles checklists from:

- RACAE class and aircraft type.
- VFR or IFR.
- VLOS, EVLOS, BVLOS, or other authorized visual condition.
- Mission environment and airspace.
- Day or night.
- Number of coordinated aircraft.
- Payload and configuration.
- Crew and support roles.
- Unit doctrine and manufacturer procedures.

The before-flight safety case includes:

- Mission authority and order of flight.
- Aircraft, GCS, payload, and battery configuration.
- Registration, airworthiness, maintenance, and minimum equipment.
- Crew assignment, qualifications, recency, medical status, duty, rest, and fatigue.
- AIP, airspace, aerodrome, heliport, MOA, restricted, prohibited, danger, and ZNVD review.
- ATC, DINAV, UAEAC, and inter-unit coordination where applicable.
- Flight-plan requirements.
- Weather, visibility, cloud, wind, density altitude, and local observation.
- Terrain, obstacles, population exposure, and emergency recovery sites.
- Weight, balance, performance, energy, return, diversion, and contingency reserves.
- C2, communications, GNSS, DAA, transponder, ADS-B, and lost-link readiness.
- Route, geofence, deviation, and contingency validation.
- Hazard assessment, mitigations, residual risk, ERP, and abort criteria.
- Four-gate approvals.

Checklist responses require accountable identity and timestamp. Evidence is mandatory when the normalized requirement declares it. The interface has no bulk check-all function.

## 15. During-flight workflow

The system receives read-only canonical telemetry:

- Position, altitude or height, heading, groundspeed, and vertical rate.
- Active route leg and route deviation.
- Remaining energy and predicted recovery reserve.
- Battery voltage, current, temperature, cell status, and available health indicators.
- Propulsion and platform health available from the approved adapter.
- C2 link state, latency, and packet-loss indicators.
- GNSS fix, satellite count, integrity indicators, and navigation mode.
- DAA, transponder, or ADS-B status when available and approved.

The monitoring workspace evaluates:

- Route containment and approved operating area.
- Terrain and obstacle clearance.
- Airspace and NOTAM conflicts.
- Aircraft-to-aircraft separation.
- Energy at recovery, diversion, and contingency points.
- Weather deterioration and expiring information.
- Telemetry and C2 degradation.
- Operator workload, duty, and screen-exposure thresholds.
- Active mitigations and abort criteria.

Alerts cite an approved SOP, emergency checklist, or normalized requirement. The product records acknowledgement and action status but does not send an aircraft command.

## 16. After-flight workflow

After-flight processing includes:

- Aircraft recovery, shutdown, and inventory accountability.
- Battery temperature, damage, quarantine, cycle, and storage actions.
- Discrepancy and damage recording.
- Required maintenance and return-to-service status.
- Telemetry acquisition, checksum, preservation, and review status.
- Occurrence screening and reporting deadline.
- Crew and mission debrief.
- Hazard, lesson learned, and corrective-action creation.
- SMS indicator and management-of-change updates.
- Research instruments only under an approved, consented protocol.
- Bilingual signed mission, debrief, and evidence exports.

Telemetry retention must meet the current RACAE minimum and any longer approved FAC retention schedule. RACAE 94 section 94.705 establishes a minimum one-year period for applicable flight telemetry. Other retention periods use the greater of the regulatory floor and the active approved institutional policy.

## 17. Coordinated aircraft and swarm research

Operational mode supports coordinated missions with one or more aircraft. It requires:

- One qualified operator or remote pilot per active aircraft.
- Unique aircraft, battery, payload, and GCS assignment.
- Defined command hierarchy and communication plan.
- Separation criteria.
- Contingency behaviour for partial mission failure.
- Crew and alert workload analysis.
- Individual acceptance by every assigned operator.

Swarm research mode:

- Is isolated from operational mission release.
- Uses synthetic or approved research data.
- May model one-to-many supervision, emergent coordination, workload, and automation.
- Displays a persistent non-dispatchable label.
- Cannot be converted directly to an operational mission.
- Requires an approved research protocol for human-subject data.

## 18. Offline mapping and flight planning

### 18.1 Geospatial stack

The selected open-source foundation is:

- MapLibre GL JS for the interactive map.
- PMTiles for portable vector, raster, and terrain archives.
- OpenStreetMap-derived vectors using an OpenMapTiles-compatible schema.
- Copernicus or NASA elevation sources with documented provenance.
- Open-source styles, glyphs, and sprites stored locally.

No map view depends on a commercial token or online tile service.

### 18.2 Package strategy

The edge node stores:

- A Colombia-wide vector and medium-resolution terrain baseline.
- Mission-area packages with higher-resolution terrain, obstacles, approved imagery, and operational overlays.
- Signed official aeronautical packages.

Supported controlled imports include PMTiles, MBTiles, GeoTIFF, Cloud Optimized GeoTIFF, GeoJSON, KML, KMZ, and GPX. Every layer displays source, edition, effective period, authority, and freshness.

### 18.3 Operational layers

The map supports:

- Terrain, contours, hillshade, and 3D terrain.
- Roads, hydrography, settlements, administrative boundaries, and land cover.
- Aerodromes, heliports, navigation features, obstacles, and emergency sites.
- Airspace classes, MOA, and prohibited, restricted, danger, training, and no-drone zones.
- AIP, NOTAM, weather, communication, and approved operational-area overlays.
- VLOS and EVLOS terrain viewsheds.
- C2 line-of-sight and coverage-risk overlays.
- Population and third-party exposure layers when approved data is available.

Open-source aeronautical data is supplemental. It cannot satisfy an official-data gate unless the competent authority has approved it for that purpose.

### 18.4 Coordinate and unit handling

The interface supports WGS 84 and approved MAGNA-SIRGAS transformations, plus:

- Decimal degrees.
- Degrees, minutes, seconds.
- UTM.
- MGRS.

The authoritative stored geometry uses WGS 84 coordinates with explicit datum metadata. Aviation calculations use approved aviation units, distinguish altitude MSL from height AGL, and retain unrounded values internally.

### 18.5 Planning tools

Planning supports:

- Waypoints and route legs.
- Corridors.
- Holds and orbits.
- Area-search patterns.
- Altitude profiles.
- Emergency, alternate, and forced-recovery locations.
- Terrain and obstacle clearance.
- Route-airspace and route-NOTAM intersection.
- Day, night, and sun-position assessment.
- VFR or IFR selection gated by RACAE class and approved aircraft capability.
- BVLOS planning gated by applicable authority, airspace, DAA, C2, crew, and contingency evidence.
- Draft ICAO or FAC flight-plan data without transmission.

Exports include PDF, JSON, GeoJSON, KML or KMZ, and GPX. Exports are planning artifacts and do not create a command path to the GCS.

## 19. Weather, NOTAM, and data freshness

The system supports:

- METAR and TAF decoding in Spanish and English.
- SIGMET and winds-aloft packages.
- Local manual weather observations with observer identity and time.
- Visibility and cloud-clearance validation.
- Wind, crosswind, density-altitude, temperature, and precipitation limits.
- Spatial and temporal matching of NOTAMs.

Critical datasets have policy-defined maximum ages. Expired data creates a hard release gate.

A controlled degraded-data exception requires:

- Identification of the stale or missing dataset.
- Alternate verified source.
- Operational consequence.
- Mitigation.
- Defined validity period.
- Safety review.
- Acceptance by the correct risk authority.
- Operator acknowledgement.

An exception is visible throughout the mission and cannot be copied automatically to a new mission.

## 20. Aircraft capability and procurement baseline

The product maintains a vendor-neutral, non-weaponized capability model covering:

- Aircraft class, MTOW, dimensions, and configuration.
- Endurance and range under stated conditions.
- Propulsion and energy architecture.
- Environmental envelope and ingress protection.
- Wind, precipitation, temperature, and altitude limitations.
- Navigation, GNSS, inertial, and integrity capabilities.
- C2 bands, redundancy, latency, range, and approved resilience evidence.
- DAA, ADS-B, transponder, remote identification, and airspace-integration capabilities.
- EO, IR, multispectral, mapping, and other payload metadata without imagery.
- Payload mass, power, thermal, stabilization, and interface requirements.
- Cybersecurity, firmware provenance, secure boot, update, logging, and supply-chain evidence.
- Maintenance, spares, battery, training, GCS, and lifecycle support.
- Human-system interface, staffing, workload, alarm, and training characteristics.

Capability claims require evidence and confidence. Marketing material alone is identified as vendor-claimed and cannot satisfy an airworthiness or release requirement.

Publicly documented DJI Enterprise and non-weaponized military UAS may be used as comparison references. The suite does not reproduce protected specifications without attribution and does not design weapons or offensive capabilities.

## 21. Energy and battery management

Battery records include:

- Serial number and aircraft compatibility.
- Chemistry and nominal capacity.
- Cycles and age.
- Cell voltage and imbalance.
- Internal resistance when available.
- Temperature history.
- State of charge and state of health.
- Storage, charging, maintenance, damage, and quarantine status.

Mission energy models account for:

- Aircraft and payload configuration.
- Manufacturer performance evidence.
- Wind and expected groundspeed.
- Temperature and density altitude.
- Climb, cruise, work, hold, return, diversion, and contingency segments.
- Battery health and model uncertainty.

The result provides predicted energy at every waypoint, recovery reserve, diversion reserve, contingency reserve, uncertainty, and the limiting assumption. In-flight estimates update from read-only telemetry without changing the approved minimum reserve.

## 22. Human factors and operational performance

### 22.1 Operational controls

The operational module covers:

- Qualification, recency, and role coverage.
- Duty, rest, cumulative workload, and screen exposure.
- Privacy-preserving fit or unfit self-declaration.
- CRM briefing and communication plan.
- Transfer-of-control and incapacitation readiness.
- Workload by mission phase.
- Operator-to-aircraft and operator-to-alert demand.
- Automation-mode awareness.
- Alert acknowledgement and escalation.
- Alarm-flood detection.
- Structured human-factors debrief.
- Training and recurrent-check tracking.

RACAE 94 fatigue and screen-exposure requirements and approved FAC policy are represented as versioned controls.

Command personnel see only the minimum operational status needed for assignment. Medical details, diagnoses, and clinical reasoning remain outside the operational interface.

### 22.2 Research laboratory

The research environment supports:

- Protocol and ethics-approval registration.
- Informed consent.
- Pseudonymous participant codes.
- Condition assignment and block scheduling.
- SAGAT, NASA-TLX, ISA, Bedford workload, SART, and controlled custom instruments.
- MATB simulator integration through an explicitly labelled research adapter.
- Synchronized mission and research events.
- Workload, situation awareness, automation trust, CRM, alert, and human–multi-UAS studies.
- Optional research-only HRV, eye-tracking, and psychomotor adapters.
- Deterministic session replay.
- Deidentified CSV, JSON, and Parquet exports.

Operational and research databases use different access controls and encryption keys. Research results cannot automatically change a person’s operational qualification, assignment, medical status, or release eligibility. Only approved deidentified aggregate findings may inform SMS assurance, training design, or interface changes.

## 23. SMS assurance functions

The organizational SMS module includes:

- Safety policy and accountable-executive records.
- Roles, responsibilities, and delegated risk authorities.
- Hazard register.
- Mission and systemic risk assessments.
- Safety-performance indicators and alert levels.
- Occurrence intake and regulatory reporting workflow.
- Corrective and preventive actions.
- Audit and inspection findings.
- Management of change.
- ERP ownership, exercises, review dates, and lessons.
- Training, communication, and safety promotion.
- Regulatory amendment impact analysis.

Mission hazards may be promoted into the organizational hazard register. Corrective actions retain owner, due date, evidence, verification, effectiveness review, and closure authority.

## 24. Controlled bilingual terminology

Every operational concept has:

- Stable term identifier.
- Official Spanish label.
- Standard English equivalent.
- Approved acronym.
- Definition.
- Source.
- Applicability.
- Effective version.
- Deprecated or prohibited informal synonyms.

Examples include:

| Spanish | English |
| --- | --- |
| Sistema aéreo no tripulado (UAS) | Unmanned aircraft system (UAS) |
| Aeronave pilotada a distancia (RPA) | Remotely piloted aircraft (RPA) |
| Piloto remoto | Remote pilot |
| Operador UAS | UAS operator |
| Seguridad operacional | Aviation safety |
| Seguridad de la aviación | Aviation security |
| Altura AGL | Height above ground level |
| Altitud MSL | Altitude above mean sea level |
| Estación de control en tierra | Ground control station (GCS) |
| Pérdida del enlace C2 | C2 link loss |
| Plan de respuesta a emergencias | Emergency response plan |

Rules:

- Drone appears only in explanatory or source-specific contexts.
- VLOS, EVLOS, BVLOS, VFR, IFR, METAR, TAF, SIGMET, NOTAM, AGL, MSL, C2, DAA, ADS-B, and UTC retain standard meanings.
- UTC is authoritative for operations; America/Bogota local time is supplementary.
- Regulatory quotations remain in the source language.
- English regulatory renderings are labelled controlled translations.
- Changing interface language cannot change stored meaning, units, calculations, or rule behaviour.
- Exports may present Spanish and English side by side.

## 25. Visual and interaction design

### 25.1 Subject and interface purpose

The interface is a deployable FAC ISR mission-safety workstation. It must help commanders, safety officers, maintainers, operators, and researchers understand mission state without presenting a fictional weapon-system aesthetic.

### 25.2 Palette

- Night base: #081B25
- Day chart: #E6EEF0
- Navigation cyan: #44B8C7
- Normal green: #4FA878
- Caution amber: #F2AA3C
- Warning red: #D64E4B

Panels and text colours derive from these tokens with tested contrast. Colour is never the only status carrier.

### 25.3 Typography

- Archivo Narrow for headings, mission identifiers, and compact operational labels.
- Atkinson Hyperlegible for instructions, checklists, and bilingual prose.
- IBM Plex Mono for coordinates, UTC time, telemetry, aircraft identifiers, and citations.

Font files and licenses are stored locally.

### 25.4 Map-first layout

The workstation layout is:

    Mission Safety Strip: phase, class, flight rules, four gates, blockers
    ----------------------------------------------------------------------
    Mission plan       | Terrain and route map | Risks, aircraft, alerts
    Requirements       |                       | Weather, crew, reserves
    ----------------------------------------------------------------------
    Event, telemetry, and decision timeline

The map remains dominant during planning and monitoring. Tablets support briefing, checklist, review, and approval. Detailed route construction is workstation-optimized.

### 25.5 Signature interaction

The persistent Mission Safety Strip is inspired by ATC flight-progress strips. It displays:

- Mission phase.
- Aircraft and RACAE class.
- Flight rules and visual condition.
- Four gate states.
- Highest unresolved hazard.
- Critical data freshness.
- Operator go/no-go state.

Selecting a segment opens the evidence and governing requirement. The strip is structural navigation and audit context, not decoration.

### 25.6 Accessibility and motion

- Keyboard access and visible focus.
- Large touch targets.
- High-contrast day and night modes.
- Text, icon, and shape status redundancy.
- Reduced-motion support.
- Motion restricted to meaningful state transitions and one alert pulse.
- No decorative radar sweep, neon glow, glassmorphism, or non-functional animation.

## 26. Security model

The first release handles unclassified controlled safety data.

Controls include:

- Persistent classification banner and content warning.
- Local role-based access with least privilege.
- Separate gate permissions.
- Authenticated local clients and TLS on the tactical network.
- Encrypted system disk, databases, backups, and exports.
- Separate operational and research databases and keys.
- Signed software, policy, regulatory, map, and data packages.
- Append-only decision and audit ledger.
- Automatic session locking.
- Controlled emergency access with enhanced audit.
- Malware scanning and quarantine on staging.
- Software bill of materials.
- Third-party license and provenance register.

The telemetry gateway has a read-only canonical adapter contract. No adapter method, message, route, or interface may represent a command to the aircraft or GCS.

## 27. Safe failure and error handling

The system fails visibly and conservatively:

- Unknown or conflicting regulation: dependent release decision blocked.
- Invalid or expired critical data: release blocked or controlled exception required.
- Database write failure: read-only safe mode and approvals disabled.
- Clock inconsistency: signatures, deadlines, and expiry checks blocked.
- Missing map or terrain package: affected checks unavailable and mission re-evaluated.
- Telemetry loss: monitoring marked degraded and approved procedure displayed.
- Corrupt or unsigned import: package quarantined.
- Safety-kernel failure: no ready result produced.
- Material mission change: affected approvals invalidated.
- Translation missing: authoritative source-language term displayed.
- Export failure: mission state unchanged and failure audited.

Recovery cannot silently recreate an approval. An approval is valid only when its signed record and dependencies remain valid.

## 28. Data freshness and rollback protection

Every package declares:

- Package type and schema.
- Issuer.
- Version.
- Issue and effective time.
- Expiry or maximum age.
- Geographic scope.
- Dependencies.
- Superseded versions.
- Signature.
- Content hashes.

The edge node rejects unauthorized downgrades. Historical missions retain their original package snapshot even after a newer package is installed.

## 29. Export and session portability

A mission export contains:

- Mission and revision identifiers.
- Operator profile and policy package.
- Aircraft, payload, battery, GCS, and crew assignments.
- Route and map-package references.
- Regulatory and data snapshots.
- Rule evaluations.
- Checklists and evidence.
- Hazards, mitigations, residual risks, and exceptions.
- Four gate approvals.
- Event and telemetry indexes.
- Debrief, occurrences, and corrective actions.
- Audit manifest and hashes.

Human-readable exports are bilingual PDF or archival HTML. Machine-readable exports use versioned JSON plus referenced files. Research exports are separate, deidentified packages.

Import verifies schema, signatures, hashes, source profile, and classification. Imported missions default to read-only review until explicitly cloned into the local organization.

## 30. Verification strategy

### 30.1 Automated verification

- Unit tests for normalized rules and calculations.
- Property-based tests for units, geometry, time, energy, and state transitions.
- Golden cases for every RACAE class.
- Golden blocked cases for missing crew, stale data, airspace conflict, insufficient reserve, expired qualification, invalid maintenance release, and unacceptable residual risk.
- Dependency tests proving correct gate invalidation after material changes.
- Bilingual terminology and export equivalence.
- Map projection, datum, terrain, obstacle, and airspace-intersection tests.
- Battery and endurance model tests against approved evidence.
- Data-package tamper, expiry, downgrade, and partial-import tests.
- Telemetry delay, dropout, duplication, ordering, and malformed-message tests.
- Offline cold-start and disconnected-operation tests.
- Multi-user concurrency and four-gate separation tests.
- Accessibility, keyboard, daylight, night, tablet, and reduced-motion tests.
- Long-duration and multi-aircraft performance tests.
- Research and operational data-separation tests.
- Negative tests proving no C2 command interface exists.

### 30.2 Human and institutional verification

- Regulatory traceability review by qualified FAC personnel.
- Review of RACAE interpretations and translations.
- Operational checklist validation with representative operators, remote pilots, maintainers, safety officers, and commanders.
- Human-factors usability studies under approved protocols.
- Tabletop and functional ERP exercises.
- Cybersecurity and deployment review.
- Independent acceptance of active risk matrices and delegated authorities.

The product cannot be represented as operationally accepted until the required institutional reviews are complete.

## 31. Version control and release evidence

The SMS workspace uses:

- Auditable Git history.
- Semantic software versions.
- Conventional, scoped commit messages.
- Changelog.
- Signed release manifest.
- Test and verification report.
- Known-limitations register.
- SBOM and license register.
- Regulatory baseline and source checksums.
- Database and package schema versions.

Application metadata, documentation, and mission-package authorship use:

Dr Diego Malpica — Aerospace Medicine and Human Performance — Subdirectorate of Aerospace Sciences — Colombian Aerospace Force

Third-party sources, software, maps, standards, and datasets retain their own required attribution. Sole product authorship does not remove third-party attribution.

## 32. Delivery decomposition

The product is delivered as independently reviewable subprojects:

1. Evidence acquisition, source register, and regulatory corpus.
2. Controlled terminology and normalized rule model.
3. Safety kernel and mission state machine.
4. Identity, roles, audit, and four-gate release.
5. Fleet, maintenance, payload, and battery foundation.
6. Offline mapping, packages, and flight planning.
7. Before-flight safety case.
8. Read-only telemetry and during-flight monitoring.
9. After-flight, occurrence, and debrief workflow.
10. SMS assurance and management of change.
11. Operational human-performance module.
12. Separate human-factors research laboratory and MATB adapter.
13. State Aviation class-complete verification and deployment hardening.
14. Private Certified Operator profile.
15. Civil Public Entity profile.

Each subproject produces working, testable software or a validated evidence artifact. No subproject may bypass an earlier safety or traceability boundary.

## 33. Initial must-have capability list

The State Aviation release must have:

- Unarmed ISR and support configurations across all RACAE aircraft classes.
- Class- and capability-gated VFR and IFR planning.
- VLOS, EVLOS, and authorized BVLOS validation.
- One-operator-per-aircraft operational staffing.
- Non-dispatchable swarm research mode.
- Colombia-wide offline map baseline and mission-area packages.
- Terrain, obstacles, airspace, AIP, NOTAM, and weather review.
- METAR, TAF, SIGMET, local observation, and data-freshness handling.
- Flight-plan drafting without transmission.
- Aircraft, GCS, payload, battery, maintenance, and airworthiness records.
- Energy, reserve, terrain-clearance, and route calculations.
- Hazard, risk, mitigation, exception, and ERP workflows.
- Four-gate release.
- Read-only telemetry monitoring.
- Post-flight, occurrence, telemetry-preservation, and debrief workflows.
- SMS assurance, CAPA, audit, SPI, and management of change.
- Operational human-performance controls.
- Separate research protocols, instruments, replay, and deidentified exports.
- Spanish and English controlled terminology.
- Signed packages, immutable snapshots, audit, and portable mission exports.
- Fully offline tactical operation.

## 34. Design approval record

The conversational design was approved section by section on 2026-08-08 for:

- Colombian State Aviation and FAC ISR primary profile.
- Future Private Certified and Civil Public profiles.
- Safety decision support with no command path.
- Offline-first tactical deployment.
- FAC ISR terminology and workflow.
- Safety metadata only, with no ISR content.
- Operational versus research separation for swarm functions.
- Deployable edge-node topology.
- Four-gate release.
- All RACAE aircraft classes.
- Unclassified controlled safety data.
- National map baseline plus mission-area packages.
- Controlled stale-data exception.
- Connected staging workstation.
- Read-only telemetry.
- Isolated SMS workspace.
- Author attribution.
- Vendor-neutral capability and airworthiness baseline.
- Human-factors operational and research suite.
- Strict operational and research data separation.
- Modular safety-kernel architecture.
- Regulatory evidence and SMS structure.
- Mission lifecycle.
- Mapping and flight-planning design.
- Visual direction.
- Controlled bilingual terminology.
- Safe failure, security, and verification strategy.

This written specification is the review baseline. Implementation planning begins only after the user reviews and approves this file.

## 35. Preliminary source links

- AAAES RACAE library: https://aaaes.fac.mil.co/es/racae
- RACAE 94 Amendment 2: https://aaaes.fac.mil.co/sites/aaaes/files/documentos%20aaaes/racae_94_enmienda_2_reglas_de_vuelo_y_operacion_uasrpas_0.pdf
- RACAE 219: https://aaaes.fac.mil.co/sites/aaaes/files/AAAES/documentos/RACAE/2025/racae_219_sistema_de_gestion_de_seguridad_operacional.pdf
- AAAES normativity: https://aaaes.fac.mil.co/es/normatividad
- Aerocivil RAC collection: https://www.aerocivil.gov.co/documentos/254/reglamentos-aeronauticos-de-colombia-rac/
- Aerocivil resolutions to the RAC: https://www.aerocivil.gov.co/autoridad_aeronautica/normatividad/15-resoluciones-a-los-rac
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js/docs/
- PMTiles for MapLibre: https://docs.protomaps.com/pmtiles/maplibre
