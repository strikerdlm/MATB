# MATB — Investigación de factores humanos y aseguramiento de la seguridad operacional aeronáutica

[English](README.md) | [Español](README.es.md)

> Software exclusivo para investigación y aseguramiento de la seguridad. MATB
> no es un dispositivo clínico, un sistema operacional certificado, un canal de
> control de aeronaves, un sistema de armas ni un sustituto de la aprobación
> humana responsable.

MATB reúne flujos relacionados e independientes para medicina aeroespacial,
factores humanos, seguridad aeronáutica e investigación de supervisión de sUAS.
No es necesario instalar todos los flujos.

## Empiece aquí: elija un flujo

| Objetivo | Comience con | Resultado |
| --- | --- | --- |
| Diseñar bloques de carga, ejecutar sesiones MATB, convertir registros o ajustar modelos DEPDF | `matb_integration/` y `openmatb/` | Escenarios contrabalanceados, manifiestos, métricas y JSONL listo para analizar |
| Dar seguimiento a participantes y visitas, visualizar datos, ejecutar estadísticas y exportar un estudio | `webui/` | Consola local FastAPI/Next.js con procedencia respaldada por SQLite |
| Ejecutar un estudio sUAS supervisivo determinista y no cinético | `matb_integration/suas/` y `webui/` | Sesiones de navegador, ISA/SAGAT/TLX/Bedford, reproducción verificada y artefactos sellados |
| Evaluar contratos sin conexión de seguridad operacional, evidencia, telemetría y separación de investigación | `SMS/` | Paquetes TypeScript, consola local, comprobaciones deterministas y herramientas de verificación sin conexión |
| Explorar las demostraciones originales de terminal | `aircraft_monitor/` | Demostraciones con semilla de UAV, caza, modo combinado y experimento inspirado en MATB |

Si es nuevo en el repositorio, lea el inicio rápido del flujo que necesita y
empiece con datos sintéticos o seudónimos. Las guías especializadas están en
[Referencias y guías detalladas](#referencias-y-guías-detalladas).

## Seguridad, privacidad y límites de investigación

- Los flujos OpenMATB y MATB son instrumentos de investigación. NASA-TLX, ISA,
  Bedford, SAGAT, detección de señales, resultados neurocognitivos, estadísticas
  y resultados DEPDF no son hallazgos clínicos, determinaciones de aptitud,
  conclusiones de aeronavegabilidad ni autorizaciones operacionales.
- El simulador sUAS nativo es sintético y no cinético. No contiene aeronaves
  reales, armas, selección de blancos, mapas del mundo real, telemetría externa,
  despacho autónomo ni una ruta de mando y control.
- El espacio de trabajo `SMS/` es un sistema sin conexión para aseguramiento y
  evidencia de seguridad. Una prueba, compilación, matriz de evidencia o
  compuerta aprobada no equivale a aprobación operacional institucional. El
  estado actual permanece no operacional hasta que revisores humanos
  calificados cierren los alcances de aceptación requeridos.
- Mantenga las claves de vinculación de participantes, consentimientos,
  información de salud, evidencia controlada, material de firma, claves TLS,
  arrendamientos de controladores y decisiones institucionales fuera del
  repositorio y bajo custodia de la institución propietaria.
- Use identificadores seudónimos como `P01` o `SYNTH-P01`. Nunca coloque un
  arrendamiento de controlador en una URL, registro, captura de pantalla o
  exportación de investigación.

## Arquitectura y flujo de datos

```text
Sesión de tareas OpenMATB
        │ CSV + manifiesto del escenario
        ▼
matb_integration.log_converter ──► métricas JSONL ──► DEPDF/estadística Suhir
                                                              │
                                                              ▼
                                                   Consola de Investigación/exportación

YAML sintético ──► motor sUAS determinista ──► estado seguro para observadores
                                                    │
                                                    ▼
                                             artefactos de reproducción/debrief

Evidencia local firmada + telemetría de solo lectura ──► API edge/núcleo SMS
                                                            │
                                                            ▼
                                                     consola/auditoría/verificación
```

```text
MATB/
├── matb_integration/       Bibliotecas de escenarios, conversión, análisis, screen y sUAS
├── openmatb/               Entorno OpenMATB y plugins versionados en el repositorio
├── scenarios/              Escenarios de aviación militar y sUAS sintético
├── webui/                  Backend FastAPI y Consola de Investigación Next.js
├── SMS/                    Monorepo de seguridad operacional Node/TypeScript
├── aircraft_monitor/       Demostraciones Rich de terminal conservadas
├── scripts/                Ayudas de instalación, lanzamiento y pruebas sin conexión
├── tests/                  Pruebas Python, integración, sUAS y aplicaciones
└── docs/                   Detalle científico, de implementación, diseño y verificación
```

La base de datos de investigación y el dominio operacional del SMS son
responsabilidades separadas. El paquete de investigación del SMS tiene
comprobaciones explícitas de límites de datos, y las superficies sUAS/telemetría
nativas son deliberadamente de solo lectura respecto de aeronaves reales.

## Requisitos previos

Instale solamente las dependencias del flujo que vaya a utilizar.

| Dependencia | La usan | Versión o nota |
| --- | --- | --- |
| Git | Todos los flujos | Necesario para clonar el repositorio |
| Python | MATB, OpenMATB, Consola de Investigación, sUAS y monitor heredado | Python 3.12+ es la base soportada |
| Node.js y npm | Frontend de la Consola, lanzador sUAS y SMS | Node 20+ para `webui/` y sUAS; Node 22.x para `SMS/` |
| Xvfb | OpenMATB en Linux sin interfaz gráfica | Solo para ejecutar el entorno de tareas Pyglet sin pantalla |
| Navegador | Consola de Investigación y sUAS | Navegador local compatible; Chromium/Playwright además es necesario para compuertas de navegador |
| Docker | Imagen/paquete SMS sin conexión | Se necesitan contenedores Linux e insumos controlados por la institución |

Clone el repositorio:

```bash
git clone https://github.com/strikerdlm/MATB.git
cd MATB
```

En Windows, los ejemplos de Python y Node pueden ejecutarse de forma nativa.
Los lanzadores POSIX, puntos de entrada de contenedores Linux, comprobaciones de
permisos Unix y procedimientos Xvfb requieren Linux, macOS o WSL2.

## Inicio rápido: flujo de investigación MATB/OpenMATB

Este es el flujo principal para un estudio de factores humanos. Produce
escenarios y análisis sintético sin requerir participantes. El directorio
versionado `openmatb/` está disponible para desarrollo local; `install_to_openmatb.py`
también puede copiar los escenarios y cuestionarios del repositorio a otro
checkout compatible de OpenMATB.

### 1. Cree el entorno Python

```bash
python3 -m venv .venv-matb
.venv-matb/bin/python -m pip install --upgrade pip
.venv-matb/bin/python -m pip install -r requirements-dev.txt
.venv-matb/bin/python -m pip install -r openmatb/requirements.txt
```

`requirements-dev.txt` incluye las dependencias Python de análisis y backend.
Los requisitos de OpenMATB agregan sus paquetes específicos de ejecución.

### 2. Instale escenarios y cuestionarios versionados

```bash
.venv-matb/bin/python install_to_openmatb.py "$PWD/openmatb"
```

Esto copia los escenarios de aviación militar y los cuestionarios del repositorio
a `openmatb/includes/`. Para usar otro checkout, reemplace `"$PWD/openmatb"`
por su ruta; debe contener un directorio `includes/`.

### 3. Genere un nuevo conjunto de carga cuando sea necesario

El generador crea bloques LOW, MEDIUM y HIGH junto con manifiestos deterministas.
Use un directorio de salida dedicado para no sobrescribir los escenarios
versionados:

```bash
mkdir -p exports
.venv-matb/bin/python -m matb_integration.scenario_builder \
  --output-dir exports/military-aviation \
  --block-duration 900 \
  --seed 42
```

Los archivos generados son `low_workload.txt`, `medium_workload.txt` y
`high_workload.txt`. Los manifiestos guardan la semilla, duración, nivel de
carga, hash del escenario, sondas esperadas y configuración de cuestionarios.

### 4. Configure y ejecute un bloque OpenMATB

Edite [`openmatb/config.ini`](openmatb/config.ini) y comience con:

```ini
language=en_EN
fullscreen=False
scenario_path=military_aviation/low_workload.txt
display_session_number=True
```

Ejecute en un equipo con escritorio:

```bash
cd openmatb
../.venv-matb/bin/python main.py
```

Ejecute en Linux sin interfaz gráfica con Xvfb:

```bash
Xvfb :100 -screen 0 1920x1080x24 &
cd openmatb
DISPLAY=:100 ../.venv-matb/bin/python main.py
```

OpenMATB escribe un CSV con marca de tiempo debajo de `openmatb/sessions/`.
Cambie `scenario_path` a `military_aviation/medium_workload.txt` o
`military_aviation/high_workload.txt` para las otras condiciones. Empiece en
modo ventana; active pantalla completa solamente después de estabilizar el
equipo de destino.

### 5. Convierta un CSV de sesión en métricas

```bash
cd ..
.venv-matb/bin/python -m matb_integration.log_converter \
  openmatb/sessions/<session>.csv \
  --participant P01 \
  --level LOW \
  --block low_workload \
  --output exports/P01_low.jsonl
```

El conversor registra detección de señales SYSMON y COMM, tiempos de reacción,
NASA-TLX, Bedford, ISA y SAGAT cuando están presentes. Escribe un registro JSONL
estructurado y utiliza una corrección log-lineal para d-prime.

### 6. Ajuste el DEPDF de Suhir con tres niveles de una visita

```bash
.venv-matb/bin/python -m matb_integration.suhir.cli fit \
  --participant P01 \
  --low LOW.csv \
  --medium MEDIUM.csv \
  --high HIGH.csv \
  --source raw_tlx \
  --out exports/P01_suhir.json
```

El ajuste estima `G0`, `P0` y `tau0` a partir de los tres registros de carga.
Lea la [guía DEPDF](matb_integration/suhir/README.md) antes de citar el modelo:
es comparativo e intraparticipante, y tres niveles identifican exactamente los
parámetros sin grados de libertad para bondad de ajuste.

### 7. Ejecute la CLI estadística independiente cuando sea necesario

La CLI acepta los arreglos JSON devueltos por los endpoints `/metrics/long` y
`/fits` de la Consola de Investigación:

```bash
.venv-matb/bin/python -m matb_integration.analysis.stats.cli run \
  --metrics-json metrics.json \
  --fits-json fits.json \
  --output exports/frequentist.json

.venv-matb/bin/python -m matb_integration.analysis.stats.cli bayes \
  --metrics-json metrics.json \
  --fits-json fits.json \
  --output exports/bayesian.json \
  --seed 20260604 \
  --draws 1000 \
  --tune 1000 \
  --chains 4
```

El motor frecuentista ofrece efectos de carga MixedLM, trayectorias por visita,
correlación de medidas repetidas, deriva de parámetros DEPDF, multiplicidad,
tamaños de efecto, intervalos de confianza y procedencia. El comando bayesiano
es un artefacto de sensibilidad separado; revise R-hat, tamaño de muestra
efectivo y divergencias antes de interpretarlo.

## Inicio rápido: Consola de Investigación MATB

La Consola administra participantes seudónimos, seguimiento de seis visitas,
ingesta CSV/manifiesto, visualización descriptiva, estadística, evaluación
neurocognitiva y exportaciones reproducibles.

### 1. Instale backend y frontend

```bash
python3 -m venv .venv-webui
.venv-webui/bin/python -m pip install --upgrade pip
.venv-webui/bin/python -m pip install -r requirements-dev.txt

cd webui/frontend
npm ci
cd ../..
mkdir -p exports/research-console
```

### 2. Inicie el backend

En la terminal 1:

```bash
cd webui/backend
MATB_DB_PATH="$PWD/../../exports/research-console/matb.db" \
MATB_FRONTEND_ORIGINS="http://127.0.0.1:3100" \
../../.venv-webui/bin/python -m uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8000
```

Compruebe que funciona:

```bash
curl --fail http://127.0.0.1:8000/health
```

### 3. Inicie el frontend

En la terminal 2:

```bash
cd webui/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Abra <http://127.0.0.1:3100/>.

### 4. Siga la primera secuencia de uso

1. Abra `Participants` y cree un participante seudónimo como `P01`.
2. Abra `Upload` e ingrese los CSV LOW, MEDIUM y HIGH de la misma visita.
   Adjunte el manifiesto de cada escenario cuando esté disponible.
3. Abra `Tracker` y confirme que la celda de la visita está completa.
4. Abra `Visualization` para trayectorias, comparaciones por carga, curvas
   DEPDF y resúmenes grupales.
5. Abra `Analysis` para ejecutar el artefacto frecuentista y, cuando corresponda,
   el análisis bayesiano de sensibilidad asíncrono.
6. Abra `Screen` para administrar la batería exploratoria de cuatro subpruebas:
   Simple RT, Choice RT, 2-back y seguimiento de persecución. El texto para
   participantes está en español colombiano (`es-CO`).
7. Use Research Bundle para exportar participantes, visitas, métricas tidy,
   ajustes, artefactos de análisis, procedencia, advertencias, manifiestos y
   opciones de figuras.

Endpoints backend importantes:

| Endpoint | Propósito |
| --- | --- |
| `GET /health` | Salud del servicio |
| `POST /participants` y `GET /participants` | Preparación de participantes |
| `POST /ingest` | Ingesta CSV y manifiesto opcional |
| `GET /tracker`, `GET /block` | Integridad y detalle del bloque |
| `GET /metrics/long`, `GET /fits` | Entradas de análisis y curvas DEPDF |
| `POST /analysis/run`, `POST /analysis/bayes/run` | Análisis frecuentista y bayesiano |
| `POST /screen`, `GET /screen` | Puntuación de pantalla y resumen HCF de cohorte |
| `GET /exports/research-context`, `POST /exports/research-bundle` | Exportaciones reproducibles |

Consulte la [guía del backend](webui/backend/README.md) y la [guía del frontend](webui/frontend/README.md)
para los contratos completos de API y de la pantalla.

## Inicio rápido: simulador sUAS sintético nativo

Es un simulador de investigación basado en navegador, orientado a Linux y sin
interfaz gráfica. Es determinista y no cinético, y está diseñado para estudiar
carga supervisiva, conciencia situacional, comunicación, recuperación y
reproducción.

### 1. Instale el lanzador sin conexión

El lanzador soportado requiere Python 3.12+, Node 20+ y npm:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
```

El instalador construye el frontend y ejecuta las compuertas nativas de sUAS y
backend. La primera instalación puede necesitar red; el runtime instalado está
diseñado para funcionar sin Docker, X11, GPU ni Internet.

### 2. Inicie la consola

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

Abra <http://127.0.0.1:3100/mission/setup>. El estado del backend está en
<http://127.0.0.1:8000/health>. El lanzador usa loopback por defecto y escribe
datos con permisos exclusivos del propietario bajo `var/suas/`. Use
`--data-dir`, `--backend-port` y `--frontend-port` para una ejecución dedicada.

### 3. Use el protocolo del navegador

1. Seleccione un escenario YAML validado y el idioma de sesión (`en` o `es-CO`).
2. Introduzca el participante y la visita seudónimos.
3. Prepare e inicie el bloque de práctica o investigación.
4. Use los controles supervisivos para gestionar flota sintética, contactos,
   alertas, enlaces, energía, separación y acciones requeridas.
5. Complete las sondas ISA/SAGAT y los controles NASA-TLX/Bedford posteriores.
6. Finalice el bloque, revise el debrief y descargue los artefactos sellados.
7. Si se desconecta el controlador, reconecte explícitamente; la sesión se
   pausa y nunca se reanuda por sí sola.

### 4. Ejecute una comprobación CLI determinista pequeña

```bash
.venv-suas/bin/python -m matb_integration.suas.cli validate \
  scenarios/suas/reference_area_search.yaml

.venv-suas/bin/python -m matb_integration.suas.cli record \
  scenarios/suas/reference_area_search.yaml \
  --block PRACTICE \
  --ticks 10 \
  --session-id SYNTH-SUAS-01 \
  --output exports/suas-demo

.venv-suas/bin/python -m matb_integration.suas.cli verify exports/suas-demo
```

El directorio grabado contiene manifiesto, eventos ordenados, checkpoints,
métricas, debrief, verificación de reproducción y `checksums.sha256`. Una
reproducción coincidente confirma el determinismo interno; no valida el vuelo
en el mundo real.

La API nativa expone validación de escenarios, ciclo de vida de sesiones,
comandos no cinéticos, estado de observador redactado, resincronización WebSocket
ordenada, arrendamientos de controlador, recuperación explícita, debrief y
descarga de artefactos. Nunca envíe el arrendamiento a un observador ni lo
coloque en una URL.

## Inicio rápido: espacio de trabajo SMS FAC ISR

`SMS/` es un espacio Node/TypeScript separado para seguridad operacional y
aseguramiento de evidencia sin conexión. Su dominio de investigación está
separado deliberadamente del dominio operacional y el runtime no tiene ruta C2.

### 1. Instale y construya el espacio de trabajo

Use Node 22.x:

```bash
cd SMS
npm ci
npm run build
```

### 2. Ejecute las compuertas técnicas de verificación

```bash
npm test
npm run typecheck
npm run lint
npm run verify:no-c2
npm run verify:data-separation
```

También existen `build:offline`, `verify:offline`, verificación de evidencia,
comandos SBOM/manifiesto de release, generación de matriz de verificación y
herramientas controladas para paquetes de aceptación. No ejecute
`acceptance:record` con datos inventados: es una acción separada de ingreso de
decisiones institucionales para custodios humanos autorizados.

### 3. Explore la consola y los paquetes

La consola puede iniciarse para desarrollo local de UI con:

```bash
npm run dev --workspace @fac-isr/console
```

El espacio de trabajo incluye:

- `apps/edge-api/`: API Fastify local para misiones, compuertas, posvuelo,
  ingesta de paquetes, auditoría, reproducción de telemetría, modo seguro y
  límites de datos.
- `apps/console/`: consola React bilingüe para revisión de evidencia, riesgo,
  telemetría, listas de verificación, investigación y debrief.
- `packages/evidence/`: JSON canónico, hashes, registros de fuentes,
  manifiestos y controles contra alteración o downgrade.
- `packages/safety-kernel/`: aplicabilidad, vigencia, dependencias, riesgo,
  ciclo de vida, compuertas y decisiones de auditoría deterministas.
- `packages/energy/`, `packages/fleet/` y `packages/geo/`: energía/reserva,
  configuración/calificación y lógica de coordenadas/rutas/espacio aéreo/terreno.
- `packages/human-performance/`: evaluaciones acotadas de servicio, fatiga,
  carga, alertas y CRM; no es diagnóstico médico ni certificación de aptitud.
- `packages/research/`: protocolo, ética/consentimiento, adaptadores MATB y
  sensores, instrumentos, reproducción, agregación y exportación desidentificada.
- `packages/sms/` y `packages/telemetry/`: registros SMS y canonicalización/
  reproducción de telemetría de solo lectura.

Para despliegue controlado sin conexión, TLS, custodia de paquetes, vigencia de
evidencia y aceptación institucional, use la [lista de aceptación SMS](SMS/docs/release/state-aviation-acceptance-checklist.md),
la [matriz de verificación](SMS/docs/release/verification-matrix.md) y las [limitaciones conocidas](SMS/docs/release/known-limitations.md).

## Inicio rápido: demostraciones heredadas de monitor aeronáutico

El paquete `aircraft_monitor/` se conserva como demostración determinista de
terminal, no como superficie activa de investigación:

```bash
python3 -m venv .venv-legacy
.venv-legacy/bin/python -m pip install -r requirements.txt

.venv-legacy/bin/python -m aircraft_monitor
.venv-legacy/bin/python -m aircraft_monitor.demo_uav
.venv-legacy/bin/python -m aircraft_monitor.demo_fighter
.venv-legacy/bin/python -m aircraft_monitor experiment \
  --headless --research-modality uas --seed 42
```

La salida de investigación se crea por defecto en `./exports/`; use un
directorio dedicado e identificadores seudónimos para cualquier experimento.

## Capacidades

### Investigación MATB y OpenMATB

- Flujo OpenMATB de cuatro tareas: monitoreo de sistemas, seguimiento,
  comunicaciones y gestión de recursos.
- Bloques LOW/MEDIUM/HIGH con generación de eventos con semilla y apoyo para
  contrabalanceo.
- Manifiestos deterministas con procedencia SHA-256, sondas esperadas,
  metadatos de cuestionarios y validadores.
- Cuestionarios en inglés y español para NASA-TLX, ISA, Bedford y SAGAT, con
  las limitaciones de validación documentadas en las guías de escalas.
- Métricas estructuradas de desempeño: d-prime, aciertos, omisiones, falsas
  alarmas, rechazos correctos, tiempo de reacción, TLX, Bedford, ISA y SAGAT.
- Soporte opcional de plugin OpenMATB compatible con LSL para futuros flujos de
  fisiología sincronizada; un estudio fisiológico completo todavía necesita un
  protocolo validado de adquisición y sincronización.

### Modelado y estadística

- Cálculos DEPDF de no fallo humano y resultado de misión de Suhir,
  degradación Weibull, calibración FOAT, normalización MWL, entradas HCF e
  informes.
- Análisis frecuentista Q1–Q4: efectos de carga, trayectorias por visita,
  correlación de medidas repetidas, deriva DEPDF, controles de multiplicidad,
  tamaños de efecto, intervalos de confianza y sensibilidad de casos completos.
- Reajustes bayesianos de sensibilidad con PyMC, intervalos posteriores, R-hat,
  tamaño de muestra efectivo, divergencias, semillas y procedencia del sampler.
- Estados explícitos `ok`, `insufficient_data` y `not_estimable` para que los
  datos faltantes no se conviertan silenciosamente en conclusiones.

### Consola de Investigación

- Seguimiento seudónimo de participantes y seis visitas con una cuadrícula de
  completitud derivada.
- Ingesta CSV con controles de duplicados, celdas ocupadas, ausencia de SYSMON,
  sobrescritura y validación de manifiestos.
- Trayectorias descriptivas, gráficos por nivel de carga, curvas DEPDF, vistas
  grupales, exportación PNG y JSON de opciones ECharts para figuras.
- Ajuste DEPDF automático cuando están presentes los tres niveles de una visita.
- Batería de pantalla de Simple RT, Choice RT, 2-back y seguimiento de
  persecución; puntuación server-side desde trials sin procesar y mapeo HCF
  exploratorio de cohorte.
- Exportaciones JSON de contexto y ZIP reproducible con métricas, ajustes,
  artefactos estadísticos, manifiestos, advertencias y procedencia.

### Simulador sUAS sintético nativo

- Flota, rutas, sectores, contactos, alertas, sensores, enlaces, energía,
  separación, perfiles de carga y comandos supervisivos sintéticos deterministas.
- Bloques de práctica/LOW/MEDIUM/HIGH con compuertas ISA, SAGAT, NASA-TLX y
  Bedford.
- Preparación de participante/visita seudónimos, aislamiento por arrendamiento
  de controlador, modo observador, sondas privadas redactadas, pausa al perder
  conexión y recuperación explícita.
- Grabación de eventos append-only, checkpoints, debrief sellado, rutas de
  artefacto relativas, sumas SHA-256 y reproducción determinista.
- Funcionamiento Linux/sin interfaz gráfica sin X11, Docker, GPU, telemetría
  externa ni integración con aeronaves reales.

### Espacio de aseguramiento SMS FAC ISR

- Registros de fuentes/evidencia, JSON canónico, hashes, manifiestos, firmas,
  vigencia y detección de downgrade o alteración.
- Núcleo de seguridad determinista con resultados pass/blocked/unknown y
  comportamiento fail-closed ante evidencia crítica.
- Planificación/revisión de misiones, compuertas, listas de verificación,
  registros posvuelo, auditoría, modo seguro e ingesta local de paquetes firmados.
- Reproducción de telemetría de solo lectura, procedencia de retención,
  comprobaciones de flota/configuración/mantenimiento/calificación de tripulación,
  energía/reserva y lógica geoespacial sin conexión.
- Políticas de desempeño humano, protocolos de investigación, consentimiento,
  adaptadores MATB/HRV/sensores, instrumentos, reproducción, agregación y
  exportaciones desidentificadas no despachables.
- Scripts de verificación de ausencia de C2 y separación investigación/operación.

## Potencial de investigación

### Preguntas que admite la plataforma actual

1. **Dosis-respuesta de carga:** ¿Los eventos y tareas concurrentes cambian la
   detección, el tiempo de respuesta, NASA-TLX, ISA, Bedford o seguimiento?
2. **Conciencia situacional:** ¿Cómo cambian percepción, comprensión y
   proyección en sondas de congelamiento bajo carga, pérdida de enlace,
   incertidumbre de contactos o conflicto supervisivo?
3. **Aprendizaje y fatiga:** ¿Cambian desempeño, carga, conciencia situacional o
   parámetros DEPDF en visitas repetidas o bloques prolongados?
4. **No fallo humano y resultado de misión:** ¿Cómo modifican la carga y los
   registros de fallos los parámetros DEPDF y las estimaciones comparativas de
   resultado de misión?
5. **Operación sUAS supervisiva:** ¿Cómo afectan el tamaño de flota, alertas,
   separación, energía, pérdida de enlace y reportes requeridos las decisiones
   y métricas de debrief?
6. **Aseguramiento centrado en las personas:** ¿Cómo deben presentarse y
   revisarse la vigencia de evidencia, las compuertas, la telemetría de solo
   lectura, los controles de fatiga/carga y la separación de datos?

### Extensiones futuras

Estas son oportunidades de investigación, no afirmaciones de que cada capacidad
esté implementada o validada:

- Sincronización de marcadores LSL y streams fisiológicos para HRV, ECG, EEG,
  eye-tracking y otras señales alineadas en el tiempo.
- Derivados tipo BIDS y paquetes longitudinales portables.
- Manipulaciones controladas de confiabilidad de automatización, handoffs
  adaptativos, transparencia y confianza en automatización.
- Paquetes de estresores para caza, RPA, transporte/ISR, MUM-T, rotorcraft y
  robótica espacial con validación específica de protocolo.
- Integración de eye-tracking/pupillometría y modelos multimodales de carga.
- Clasificadores de carga en línea específicos por participante, con
  incertidumbre y barreras explícitas contra uso operacional.
- Generación de informes Markdown/Quarto con procedencia, faltantes, tamaños de
  efecto y advertencias analíticas.

La [revisión de evidencia y hoja de ruta](docs/research/military-aviation-platform/2026-06-10_current_state_and_capability_roadmap.md)
describe la base científica y las limitaciones pendientes.

## Verificación y operaciones

Ejecute solamente las suites correspondientes al flujo que cambió. Use un
entorno y un directorio de salida dedicados para cada estudio o demostración.

```bash
# Contrato de documentación
pytest tests/test_readme_documentation.py -q

# Puente MATB, DEPDF, estadística, screen e integración
.venv-matb/bin/python -m pytest tests/test_scenario_builder.py \
  tests/test_scenario_manifest.py tests/test_log_converter.py \
  tests/analysis_stats tests/suhir tests/screen -q

# Pruebas del sUAS nativo
.venv-suas/bin/python -m pytest tests/suas -q

# Backend de la Consola de Investigación
cd webui/backend
../../.venv-webui/bin/python -m pytest -q

# Frontend de la Consola de Investigación
cd ../frontend
npm test -- --run
npm run typecheck
npm run build

# Espacio de trabajo SMS
cd ../../SMS
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

Las pruebas E2E/accesibilidad del navegador necesitan además Chromium o el
recurso Playwright aprobado. La verificación de la imagen SMS sin conexión
necesita Docker, insumos de compilación fijados y evidencia/paquetes controlados.

Límites locales predeterminados:

| Servicio | Predeterminado | Límite |
| --- | --- | --- |
| FastAPI de investigación/sUAS | `127.0.0.1:8000` | Loopback; salud en `/health` |
| Next.js de investigación/sUAS | `127.0.0.1:3100` | UI local de navegador |
| Consola SMS de desarrollo | Puerto predeterminado de Vite | Solo UI de desarrollo/revisión |
| Despliegue edge SMS | HTTPS controlado | Requiere TLS, paquetes y custodia institucionales |

Mantenga los valores loopback. Un enlace no local requiere orígenes de navegador,
autenticación, privacidad, red y controles de amenazas explícitos más allá de
estos lanzadores.

## Solución de problemas

| Síntoma | Respuesta segura |
| --- | --- |
| Falta un módulo Python | Confirme el intérprete con `python -c "import sys; print(sys.executable)"` e instale los requisitos del flujo; no instale globalmente para ocultar el problema. |
| OpenMATB no encuentra un escenario | Ejecute `install_to_openmatb.py` contra el checkout correcto y verifique `includes/scenarios/military_aviation/`. |
| OpenMATB parpadea o falla Pyglet | Comience en modo ventana, verifique el entorno virtual de OpenMATB y, en Linux sin pantalla, Xvfb y `DISPLAY`. La UI sUAS nativa no necesita X11. |
| La Consola no conecta | Confirme `/health`, `NEXT_PUBLIC_API_URL`, `MATB_FRONTEND_ORIGINS` y que los puertos 8000/3100 estén disponibles. |
| La ingesta devuelve 409 | El hash del archivo o la celda participante/visita/carga ya existe. Use una base dedicada nueva o el flujo de sobrescritura documentado después de revisar la procedencia. |
| La grabación sUAS rechaza la salida | El directorio debe estar ausente o vacío. Elija uno nuevo; no borre un artefacto de estudio para ejecutar una demostración. |
| Se desconecta el controlador sUAS | Reconecte explícitamente con el arrendamiento. Una desconexión válida pausa la sesión y nunca la reanuda automáticamente. |
| SMS informa evidencia faltante, vencida o alterada | Detenga el flujo, conserve el diagnóstico y obtenga evidencia autorizada vigente mediante custodia. Nunca desactive controles de vigencia, autoridad, firma o hash. |
| Las pruebas pasan pero SMS continúa bloqueado | Es esperado hasta que las revisiones institucionales y decisiones humanas autorizadas estén vigentes. La verificación técnica no es autorización operacional. |

## Mapa del repositorio

| Ruta | Función |
| --- | --- |
| `matb_integration/` | Generación de escenarios, conversión, cuestionarios, DEPDF, estadística, screen y bibliotecas sUAS deterministas |
| `openmatb/` | Runtime OpenMATB versionado, plugins, escenarios y reproducción |
| `scenarios/military_aviation/` | Escenarios de estudio compatibles con OpenMATB |
| `scenarios/suas/` | Escenarios YAML sUAS sintéticos |
| `webui/backend/` | Servicio FastAPI de investigación/sUAS, persistencia, análisis y exportaciones |
| `webui/frontend/` | Seguimiento/análisis de investigación y consola sUAS de navegador |
| `SMS/apps/` | API edge SMS y consola de revisión bilingüe |
| `SMS/packages/` | Dominios de evidencia, safety-kernel, energía, flota, geo, desempeño humano, investigación, SMS y telemetría |
| `SMS/tools/` | Adquisición de evidencia, empaquetado de mapas, compilación sin conexión, release y aceptación |
| `aircraft_monitor/` | Demostraciones sintéticas de terminal conservadas |
| `tests/` | Pruebas Python, integración, sUAS, aplicación y documentación |
| `docs/` y `SMS/docs/` | Evidencia científica, implementación, verificación, release y gobernanza |

## Referencias y guías detalladas

- [Guía del runtime OpenMATB](openmatb/README.md)
- [Descripción de la Consola](webui/README.md), [API backend](webui/backend/README.md) y [pantallas frontend](webui/frontend/README.md)
- [Guía DEPDF de Suhir](matb_integration/suhir/README.md)
- [Validación de escalas en español](docs/research/scales/scale_validation_es.md) y [validación SAGAT](docs/research/scales/sagat_validation.md)
- [Hoja de ruta de capacidades](docs/research/military-aviation-platform/2026-06-10_current_state_and_capability_roadmap.md)
- [Informe de verificación sUAS](docs/implementation/suas-c2-v1-verification.md)
- [Diccionario de datos de investigación SMS](SMS/docs/provenance/research-data-dictionary.md)
- [Matriz de verificación SMS](SMS/docs/release/verification-matrix.md), [limitaciones conocidas](SMS/docs/release/known-limitations.md) y [lista de aceptación](SMS/docs/release/state-aviation-acceptance-checklist.md)
- [Changelog](CHANGELOG.md)

## Glosario

| Término | Significado en este repositorio |
| --- | --- |
| MATB | Paradigma Multi-Attribute Task Battery de factores humanos |
| OpenMATB | Runtime de escritorio de código abierto para presentar las cuatro tareas MATB |
| DEPDF | Función de distribución de probabilidad doble exponencial para modelado comparativo de no fallo humano |
| HCF / F/F0 | Mapeo exploratorio del factor de capacidad humana desde la pantalla de investigación |
| SAGAT | Situation Awareness Global Assessment Technique, método de sondas de congelamiento |
| sUAS | Sistema de aeronaves pequeñas no tripuladas; aquí, simulador sintético de supervisión |
| SMS | Safety Management System; aquí, el espacio de aseguramiento `SMS/` |
| No despachable | Dato o resultado de investigación que no puede entrar en una decisión de release operacional |

## Licencia

MATB se distribuye bajo la [Licencia MIT](LICENSE). La licencia no certifica
aptitud para uso clínico, de vuelo, defensa, seguridad crítica u operación y no
reemplaza la ley aplicable, la gobernanza institucional, la revisión ética ni la
aceptación humana.
