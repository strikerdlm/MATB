# OpenMATB visual profile v1

## Purpose and scientific boundary

`openmatb-visual-profile-v1` is the closed, presentation-only contract between
the MATB Research Console and the native Python/Pyglet participant runtime. It
controls semantic colors, line width, panel radius, corner marks, and a small
set of renderer options for TRACK, SYSMON, COMM, RESMAN, and subjective
workload. It cannot contain scenario events, task activation, automation,
failures, workload, response windows, geometry, hit areas, scoring, audio, or
participant color-vision simulation.

The authoritative validator is
`matb_integration/openmatb_visual_profiles.py`. Every object is closed: missing
and unknown fields are rejected, colors use only `#RRGGBB`, numbers must be
finite and bounded, and the only geometry policy is
`preserve_openmatb_v1`. The bundled
[`fac_modern`](../../openmatb/themes/fac_modern.json),
[`classic`](../../openmatb/themes/classic.json), and
[`cockpit`](../../openmatb/themes/cockpit.json) documents are complete examples.

## Identity, lifecycle, and integrity

A profile is identified by `profile_id` plus a three-part semantic `version`.
The console stores drafts and immutable published versions. Published profiles
cannot be edited; a new draft must be cloned. Validation blocks publication for
essential text/control contrast errors. Lower stimulus-separation contrast is
reported separately and requires explicit acknowledgement because changing a
stimulus can itself change experimental demand.

The API supports list/get, clone, draft update, validate, publish, import,
export, and isolated native preview operations under
`/openmatb/visual-profiles`. Import accepts the profile document only and always
creates a draft; an existing identity with different content fails closed.
Export returns the strict document without database lifecycle fields.

The SHA-256 is computed from normalized UTF-8 JSON with sorted keys and compact
separators. Session preparation writes one canonical `visual-profile.json`
inside `exports/openmatb-controlled/<session-id>/`, records its ID, version,
schema version, and hash in the session and each scenario manifest, and passes
the absolute file using `--theme-file`. The backend verifies the artifact path,
schema, identity, and hash immediately before every block launch. Legacy
sessions without profile provenance continue to use their frozen
`--visual-theme` value.

## Researcher workbench and preview

The Next.js workbench is available at `/openmatb/appearance` from OpenMATB
settings. It uses CSS custom properties and SVG previews, supports strict JSON
import/export, and does not add participant-task traffic to the browser. The
native preview launches the synthetic `fac_visual_preview.txt` scenario under
an isolated `openmatb-preview/<uuid>/` artifact root. It carries no participant
or visit identity, is mutually exclusive with controlled OpenMATB processes,
and is never ingested as study data.

The browser-only color-vision-deficiency preview uses the severity matrices of
Machado, Oliveira, and Fernandes (2009), *IEEE Transactions on Visualization
and Computer Graphics*, https://doi.org/10.1109/TVCG.2009.113. It is never
written to the participant profile or applied by the native runtime.

Software invariance and matching hashes do not establish perceptual,
psychometric, workload, clinical, aeromedical, or operational equivalence.
Treat each appearance as an experimental condition until equivalence has been
demonstrated under a preregistered protocol.

---

# Perfil visual OpenMATB v1

## Propósito y límite científico

`openmatb-visual-profile-v1` es el contrato cerrado y exclusivo de presentación
entre la Consola de Investigación MATB y el entorno nativo Python/Pyglet que ve
el participante. Controla colores semánticos, grosor de línea, radio de panel,
marcas de esquina y algunas opciones de renderizado para TRACK, SYSMON, COMM,
RESMAN y carga subjetiva. No puede contener eventos, activación, automatización,
fallas, carga de trabajo, ventanas de respuesta, geometría, áreas activas,
puntuación, audio ni simulación de visión cromática para el participante.

El validador autoritativo está en
`matb_integration/openmatb_visual_profiles.py`. Todos los objetos son cerrados:
se rechazan campos faltantes o desconocidos, los colores usan únicamente
`#RRGGBB`, los números deben ser finitos y acotados y la única política de
geometría es `preserve_openmatb_v1`. Los tres JSON distribuidos enlazados en la
sección inglesa son ejemplos completos.

## Identidad, ciclo de vida e integridad

Un perfil se identifica mediante `profile_id` y una `version` semántica de tres
partes. La consola almacena borradores y versiones publicadas inmutables. Una
versión publicada no se edita: se clona para crear otro borrador. Los errores de
contraste esencial impiden publicar. Los contrastes bajos entre estímulos se
presentan por separado y exigen reconocimiento explícito, porque modificar el
estímulo puede modificar la demanda experimental.

La preparación de sesión escribe un `visual-profile.json` canónico en
`exports/openmatb-controlled/<session-id>/`, registra identidad, versión,
esquema y hash en la sesión y los manifiestos, y transmite la ruta absoluta con
`--theme-file`. Antes de cada bloque, el backend vuelve a verificar ruta,
esquema, identidad y hash. Las sesiones heredadas sin procedencia de perfil
continúan usando su valor `--visual-theme` congelado.

## Banco de trabajo y vista previa

El banco Next.js está disponible en `/openmatb/appearance`. La vista nativa usa
un escenario sintético bajo `openmatb-preview/<uuid>/`, no contiene identidad de
participante o visita, es mutuamente excluyente con procesos controlados y nunca
se incorpora a los datos del estudio. La simulación de deficiencia de visión
cromática solo modifica la previsualización del navegador y nunca el perfil ni
el entorno nativo.

La invariancia del software y la coincidencia de hashes no demuestran
equivalencia perceptual, psicométrica, de carga, clínica, aeromédica u
operacional. Cada apariencia debe tratarse como condición experimental hasta
demostrar equivalencia mediante un protocolo prerregistrado.
