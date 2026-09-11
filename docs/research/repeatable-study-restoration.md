# Repeatable study operation and restoration

This is a local research workspace. The researcher authors and freezes the study,
analysis plan, instrument bindings, preparation rules, recovery intervals and
eligibility policy before assignment. Review the rehearsal, assign participants,
and complete the prescribed preparation through **Study → Participant**. Native
preflight holds the actual process until its resolved controls are accepted.
Run the assigned visit; record interruption causes and create explicit repeats.
Keep all original attempts. Amend only future assignments. Retrospective purpose
classification is an auditable correction, never a replacement of source data.

After collection closes, select exact attempts and native metric derivations in
**Study → Analysis**, freeze that selection and request descriptive execution.
Saved results are bounded reads; refresh and execution are explicit station jobs.
The frozen cutoff preserves what was selected even when later evidence,
classifications or assignments change. Descriptive results do not automatically
run a confirmatory model or promote an instrument's qualification.

## Consistent backup

Close the visit and its recording processes. In **Station**, enter exclusive
maintenance with a named researcher and reason. Wait until no live reservation,
resource lane or running/uncertain writer remains. Open **Study → Restore** (also
linked from Station), record the researcher and reason, and download a verified
whole-study ZIP. The equivalent local command is:

```sh
python tools/study_workspace.py backup /absolute/study.sqlite3 /separate/whole-study.zip
```

SQLite's exclusive writer reservation covers the consistent DB copy, raw-file
inventory and copying. The bundle includes all tables, immutable evidence and
qualification blobs, preparation admissions and their exact event frontiers,
HCF/analysis snapshots, pinned source/wheel kits, station job responses and
configured/persisted native, H10, Liftoff and mission artifact roots. Original
scientific file bytes and manifests are unchanged. Missing required sources,
recorded checksum failures, active writers and an output inside a source root
fail the backup. Incomplete recordings remain explicitly incomplete.

Operational credentials, controller leases, active reservations and queued work
are retired in the backup DB. They are not reusable authority. The source station
and its original database are not modified by this retirement.

## Empty-workspace restore

Use the matching software checkout and a stopped destination backend. The
archive checksum inventory detects modification; it is not a signature proving
who supplied the archive. Restore into an absent or empty directory:

```sh
python tools/study_workspace.py restore /separate/whole-study.zip '/new/station ñ' --study-id researcher-study
```

The CLI verifies archive paths, inventory, hashes, SQLite integrity/foreign keys,
frozen study/plan identities, preparation admissions and analysis fingerprints.
It rejects a different study identity, nonempty destination or missing required
component implementation. It stages extraction before activating the directory.
Core packages preserve historical native evidence; a full study requiring an
omitted Liftoff or mission implementation cannot silently lose that component.

`restore-report.json` gives the exact `environment` values for the new backend.
Set those variables in the launcher environment, including `MATB_DB_PATH`,
`MATB_ARTIFACT_RELOCATION` and `MATB_API_TOKEN_FILE`, plus any relocated instrument
roots. For example, in PowerShell, using the actual report location:

```powershell
$r = Get-Content 'C:\new\station ñ\restore-report.json' -Raw | ConvertFrom-Json
$r.environment.PSObject.Properties | ForEach-Object {
  [Environment]::SetEnvironmentVariable($_.Name, [string]$_.Value, 'Process')
}
```

On POSIX shells, export the report's values before starting the backend. The
new `.station-secret` is local operational authority; do not copy a previous
station token over it. `relocation.json` resolves original recorded paths to
restored files; original manifests remain byte-identical. A restored workspace
never falls back to an unavailable original absolute artifact path. Keep
`original-manifest.json` and both reports with the restored workspace.

The restored station starts in maintenance, with no resumed acquisition or
queued job. Verify its history and files, then leave maintenance explicitly.
Continuation of collection requires a new, explicit attempt and fresh controller
admission. Restoring an old simulation checkpoint into active acquisition is not
part of this release.

## Actual offline descriptive reproduction

Before freezing results, prepare the matching Python/platform wheel kit with
`tools/prepare_study_wheels.py` and `MATB_DESCRIPTIVE_WHEELHOUSE`. Each frozen
analysis carries the exact selected raw observations, calculator source,
dependency versions, wheels, checksums, selection/plan identities and figure.
Run:

```sh
python tools/study_workspace.py reproduce '/new/station ñ' '/separate/offline-proof ñ'
```

Each execution creates a fresh venv without system-site packages, clears inherited
repository/test Python paths, and installs only packaged wheels using isolated
pip with `--no-index`. The packaged calculator runs with Python isolation and
outbound Python sockets denied. This is not an operating-system network sandbox.
It recomputes raw instrument values, eligibility-preserving aggregation and the
figure, checking exact saved results and original figure bytes. Native evidence
uses its frozen execution declaration while checking the actual packaged source
and dependency hashes independently. Original Git/OS metadata remain provenance;
relocation does not fabricate a new original execution identity.

The output retains installation and reproduction logs, frozen artifacts and
`offline-report.json`; the disposable venv is removed after success. An
incompatible/missing wheel, changed source or raw calculation mismatch fails
explicitly. The source workspace can be unavailable throughout reproduction.
The kit is platform/Python specific; prepare and verify a compatible kit for each
station platform before an offline move.

## Verification limits

Synthetic PVT/native/H10 journeys, empty restore, true browser zoom, bilingual
keyboard flows, core packaging and both-OS CI establish software behavior. They
do not establish physical display/input timing, Polar hardware reliability,
human workload calibration, test-retest reliability or translation validity.
The bundled native runtime does not include a SAGAT probe plugin; generated
probe/scenario and synthetic native replay tests are separate from that missing
capability. Public-core publishing remains blocked by the existing scientific,
hardware, licensing and privacy release requirements.

Bayesian calculator version 2.2.1 retains the same priors and scientific model;
its recorded numerical initialization uses `adapt_diag` and the observed mean
for the intercept to avoid unstable far-away starting points. Convergence and
known-effect checks remain unchanged. Descriptive study execution does not run
this model automatically.

# Operación y restauración del estudio

El investigador define y congela el protocolo, el plan de análisis, los
instrumentos, la preparación y los descansos antes de asignar participantes.
Use **Estudio → Participante** para la preparación y la visita. El preflight
nativo mantiene el proceso real detenido hasta aceptar los controles resueltos.
Registre interrupciones, conserve todos los intentos y cree repeticiones
explícitas. Las enmiendas afectan solo asignaciones futuras; la clasificación
retrospectiva conserva la historia original.

Al cerrar la visita, seleccione los intentos y las derivaciones nativas exactas
en **Estudio → Análisis**, congele la selección y solicite el cálculo descriptivo.
Los resultados guardados conservan su selección aunque después aparezcan otras
observaciones o correcciones. No se ejecuta un modelo confirmatorio automático.

Para la copia completa, cierre las grabaciones y active mantenimiento exclusivo
en **Estación**, con investigador y motivo. En **Estudio → Restauración** descargue
la copia verificada. Se conservan la base de datos completa, las fuentes crudas,
los manifiestos originales, la preparación, HCF, los análisis y sus kits offline.
Una fuente obligatoria ausente/corrupta o un escritor activo impide la copia;
una grabación incompleta nunca se convierte en completa.

Con el backend de destino detenido y el software correspondiente, ejecute el
comando `restore` mostrado arriba hacia una carpeta vacía. Use el identificador
real del estudio en `--study-id`. Configure las variables `environment` de
`restore-report.json`; conserve `relocation.json` y `original-manifest.json`.
Los archivos científicos mantienen sus bytes originales. La nueva credencial
`.station-secret` reemplaza la autoridad operativa anterior. La estación queda
en mantenimiento, sin reanudar grabaciones ni trabajos restaurados. Para seguir
recogiendo datos se requiere un intento nuevo y autorización nueva del controlador.

Ejecute `reproduce` hacia otra carpeta vacía para comprobar cada análisis en un
entorno Python nuevo, sin paquetes del sistema, sin rutas Python heredadas y con
instalación `--no-index` desde las ruedas incluidas. Se recalculan las observaciones,
los resultados descriptivos y la figura exacta; se conservan los informes y logs.
El bloqueo de sockets Python no equivale a un aislamiento de red del sistema
operativo. Un kit incompatible, una fuente alterada o una discrepancia falla
explícitamente. Prepare el kit para la versión de Python y el sistema de destino.

Estas pruebas sintéticas verifican software; no validan tiempos físicos, hardware
Polar, carga de trabajo humana, fiabilidad entre sesiones ni traducciones. La
publicación del núcleo continúa sujeta a los requisitos científicos, de hardware,
licencias y privacidad existentes. La ejecución nativa de SAGAT requiere un plugin
que no forma parte del runtime incluido.
