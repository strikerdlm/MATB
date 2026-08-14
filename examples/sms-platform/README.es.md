# Recorrido de capacidades del SMS FAC ISR

[English](README.md)

Este recorrido ejecutable usa los límites públicos y compilados de los paquetes FAC ISR SMS con datos sintéticos. Imprime un único documento JSON determinista. No inicia un servicio, no comanda una aeronave, no aprueba una misión, no registra una decisión institucional ni establece alistamiento operacional. El requisito duro deliberadamente incompleto mantiene `safetyKernel.status` bloqueado y el evento de investigación permanece no despachable.

## Prerrequisitos e inicio rápido

Use Node.js 22.x y el archivo de bloqueo `SMS/package-lock.json`. En una estación de desarrollo con red, `npm ci` puede descargar las dependencias fijadas; en una estación aislada solo funcionará si la caché de npm ya está poblada. Después de instalar dependencias y compilar los paquetes, el recorrido solo lee archivos locales y no usa la red.

Linux o WSL:

```bash
./examples/sms-platform/run.sh
```

Windows nativo con PowerShell 7+:

```powershell
./examples/sms-platform/run.ps1
```

Los lanzadores cambian a `SMS/`, ejecutan `npm ci`, compilan todos los paquetes y luego ejecutan `node ../examples/sms-platform/package-tour.mjs`. Repita el último comando para confirmar una salida idéntica. Los árboles generados `SMS/packages/*/dist` y `SMS/node_modules` son productos locales y no deben confirmarse en Git.

## Qué demuestra el resultado

Los nueve objetos superiores corresponden a los nueve paquetes. Evidence calcula el hash de un archivo local controlado. Energy calcula la reserva con la forma completa del modelo de desempeño aprobado. Fleet evalúa una capacidad VLOS calificada frente a evidencia aceptada. Geo crea un segmento estable. Telemetry reproduce un evento fijo y demorado como dato de solo lectura. Safety Kernel rechaza un requisito duro sin evidencia fuente aceptada. SMS promueve un peligro sintético y evalúa un SPI, mientras auditoría, CAPA, ERP y gestión del cambio quedan bloqueados o incompletos al faltar evidencia responsable. Human Performance aplica una política explícita. Research abre una sesión seudonimizada con consentimiento, adapta un evento MATB y exporta un registro desidentificado sin identidad operacional ni campos de liberación.

Los resultados favorables de energía o flota son resultados de componentes, no autorizaciones de vuelo. El resumen no contiene aceptación humana, material de firma, credenciales ni decisiones de liberación de misión.

## Función de cada espacio de trabajo

| Espacio | Función y límite |
| --- | --- |
| `SMS/packages/evidence/` | JSON canónico, hashes, registro de fuentes, afirmaciones, manifiestos, rechazo de retroceso y verificación de paquetes. |
| `SMS/packages/energy/` | Baterías/segmentos con unidades y evaluación determinista de energía y reservas con un modelo respaldado por evidencia. |
| `SMS/packages/fleet/` | Configuración de aeronaves, evidencia de capacidades, mantenimiento y calificación de tripulación. |
| `SMS/packages/geo/` | Coordenadas, paquetes geográficos fuera de línea, terreno, visibilidad, rutas, espacio aéreo, meteorología y borradores no transmisores. |
| `SMS/packages/telemetry/` | Normalización estricta de telemetría de solo lectura, demoras/pérdidas, reproducción y retención; no tiene ruta de mando. |
| `SMS/packages/safety-kernel/` | Aplicabilidad, vigencia, datos de flota/energía, riesgo, ciclo de vida, compuertas y auditoría deterministas; la evidencia dura desconocida bloquea. |
| `SMS/packages/sms/` | Peligros organizacionales, indicadores, auditorías, CAPA, preparación ERP y gestión del cambio. |
| `SMS/packages/human-performance/` | Servicio/calificación/fatiga, carga de trabajo, carga de alertas y límites CRM. |
| `SMS/packages/research/` | Protocolo, ética/consentimiento, instrumentos, adaptadores MATB/sensores, reproducción, agregación y exportación separada de operaciones. |
| `SMS/apps/edge-api/` | API Fastify local, base de datos/auditoría, ingreso seguro de paquetes y límites sin C2. |
| `SMS/apps/console/` | Consola React para revisión y pruebas de accesibilidad/extremo a extremo. |
| `SMS/tools/map-packager/` | Inspección, construcción, firma controlada y verificación de manifiestos geográficos fuera de línea. |
| `SMS/tools/research/` | Adquisición/copia, extracción, verificación de hashes/evidencia, registro de consultas y escaneo sin C2. |

## Compilación, pruebas, tipos y lint

Ejecute las compuertas desde `SMS/`:

```bash
cd SMS
npm run build
npm test
npm run typecheck
npm run lint
```

`npm run build` compila paquetes, herramientas, API y consola. `npm test` compila primero y luego ejecuta el espacio Vitest. Typecheck usa el proyecto TypeScript raíz y lint la configuración ESLint raíz. Cada espacio expone `build`, `test` y `typecheck`; por ejemplo, `npm test --workspace @fac-isr/sms`. La consola también tiene `test:e2e` y `test:a11y`, que requieren los navegadores de Playwright instalados.

## Aplicaciones de desarrollo local

El paquete edge API no tiene script `dev`. Compílelo e inicie explícitamente su servidor exportado solo para desarrollo. Este comando usa base en memoria, internet deshabilitado, sin TLS y el puerto loopback del manifiesto de despliegue; no lo exponga fuera de la estación:

```bash
cd SMS
npm run build --workspace @fac-isr/edge-api
node --input-type=module -e 'import("./apps/edge-api/dist/server.js").then(async ({buildServer}) => { const app = await buildServer({bindAddress:"127.0.0.1", port:8443, databaseUrl:":memory:", packageDirectory:"./data/packages", internet:"disabled"}); await app.listen({host:"127.0.0.1", port:8443}); })'
```

El endpoint es HTTP de desarrollo en `http://127.0.0.1:8443/healthz`; la preparación normalmente permanece incompleta porque faltan paquetes controlados y configuración institucional.

Para el servidor de desarrollo de la consola:

```bash
cd SMS/apps/console
npm run dev
```

Vite normalmente selecciona el puerto loopback 5173. La vista previa controlada del paquete enlaza `127.0.0.1:4173`, también usado por el manifiesto Playwright:

```bash
cd SMS/apps/console
npm run preview:test
```

Compile antes de `preview:test` si no se ejecutó mediante su pre-script. Iniciar aplicaciones demuestra desarrollo, no aceptación.

## Despliegue edge fuera de línea

`SMS/Dockerfile` produce un contenedor Linux `linux/amd64` fijado. `SMS/docker/compose.edge.yml` enlaza solo al loopback del host, `127.0.0.1:8443` por defecto, y usa una red Docker interna. Windows nativo puede ejecutar Node/npm/PowerShell, pero el contenedor requiere Docker Desktop u otro runtime de contenedores Linux; el entrypoint usa herramientas y permisos POSIX y no es un servicio nativo de Windows.

Compose requiere tres ubicaciones institucionalmente controladas: `SMS_DATA_DIR` para el volumen SQLite cifrado y escribible, `SMS_PACKAGE_DIR` para paquetes verificados de solo lectura y `SMS_TLS_DIR` para el certificado y el material TLS privado con permisos restrictivos. `SMS_EDGE_PORT` solo puede cambiar el puerto loopback del host. Dentro del contenedor la base está en `/var/lib/fac-isr/data/edge.sqlite`, los paquetes en `/opt/sms/packages` y TLS es obligatorio. El runtime deshabilita internet, usa UID/GID 10001, elimina capacidades, monta un sistema de solo lectura y expone únicamente HTTPS.

No coloque material TLS o de liberación controlado en este ejemplo ni en el repositorio. La institución receptora debe suministrarlo mediante custodia y almacenamiento cifrado aprobados.

El ciclo fuera de línea usa:

```bash
cd SMS
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
```

`build:offline` compila/prueba el espacio y la imagen Linux, y reúne OCI, SBOM, evidencia de aceptación e inventarios en un paquete transferible. Requiere un daemon Docker, dependencias fijadas y la imagen base disponibles durante la construcción; “fuera de línea” describe el runtime/traspaso producido, no promete que la construcción carezca de insumos previamente preparados. `verify:offline` valida estructura, hashes, imagen, flujo de aceptación y contrato sin red. `verify:evidence-offline` requiere un valor UTC explícito y determinista en `SMS_EVIDENCE_VERIFY_AS_OF`. Las verificaciones sin C2 y de separación no conceden alistamiento.

## Herramientas de mapas e investigación

Compile las herramientas con `npm run build:tools` desde `SMS/`. El parser de mapas admite:

- `inspect`, con `--directory` obligatorio y `--manifest` opcional;
- `build-manifest`, con `--directory`, `--metadata` y `--output` opcional;
- `sign`, con `--directory`, una ruta externa controlada para la entrada de firma y `--manifest` opcional;
- `verify`, con `--directory`, entrada pública controlada de verificación, `--as-of` y `--manifest` opcional.

Invóquelo como `node tools/map-packager/dist/cli.js <comando>`. Un comando ausente o desconocido muestra el uso vigente y termina con error. La firma es una actividad controlada; el recorrido no la ejecuta ni suministra material.

El parser de investigación admite `record-query`, `acquire`, `copy-obsidian`, `extract`, `verify`, `verify-offline` y `verify-no-c2`. `record-query` requiere `--tool` y `--query`; su estado es `pending`, `executed` o `unverified-lead`, y `executed` exige un artefacto de evidencia. `acquire` registra una fuente oficial con metadatos de fuente/título/autoridad/URI/destino y hash esperado o archivo de preparación opcionales. `copy-obsidian` importa una nota con procedencia. `extract` recibe fuente y destino. `verify` recibe una fuente y SHA-256 esperado. Los comandos offline y sin C2 usan registros y árboles locales controlados. Invóquelo como `node tools/research/dist/cli.js <comando>` desde `SMS/`; nunca adivina un comando faltante.

## Verificación, liberación y aceptación institucional

El inventario completo de comandos de `SMS/package.json` es:

```bash
cd SMS
npm run build
npm test
npm run typecheck
npm run lint
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
npm run release:manifest
npm run release:sign
npm run release:verify
npm run verify:matrix
npm run acceptance:packets
npm run verify:acceptance
npm run verify:all
```

La lista identifica los scripts; los flujos parametrizados aún requieren argumentos. `release:manifest` requiere `-- --version <x.y.z>` igual a `SMS/package.json` y genera SBOM, escaneo de seguridad e informe de pruebas antes del manifiesto canónico. `release:sign` requiere un identificador institucional y una entrada de firma externa; solo el custodio autorizado debe ejecutarlo. `release:verify` comprueba integridad y reporta el alistamiento por separado. Nunca cree material de demostración ni confirme material controlado.

`verify:matrix` ejecuta la matriz de evidencia y escribe deliberadamente un informe cuyo alistamiento permanece falso aunque pasen todos los requisitos técnicos. `acceptance:packets` requiere `-- --output <directorio-vacío> --as-of <UTC-exacto>` y opcionalmente un `--scope` aprobado; genera paquetes deterministas no firmados fuera de `SMS/docs/release`. Esos paquetes no son decisiones.

`acceptance:record` se omite deliberadamente del bloque masivo porque no es una verificación automatizada rutinaria. Su simulación requiere un paquete vigente y una decisión institucional controlada suministrada por una persona; aplicar el registro es una acción mutante separada. Nunca rellene una plantilla con revisores, aprobaciones, tiempos, evidencia o resultados inventados. Revisores institucionales calificados deben resolver los ámbitos RACAE/traducción, lista operacional, autoridad de riesgo, emergencias, ciberseguridad/despliegue, datos geográficos oficiales, factores humanos, separación de investigación y formación/promoción de seguridad.

`verify:acceptance` valida la evidencia registrada a una fecha UTC explícita; `--require-ready` es una compuerta estricta opcional. `verify:all` combina tipos, lint, matriz y aceptación. Una compilación, pruebas, matriz, integridad de liberación o generación de paquetes satisfactoria puede coexistir con alistamiento falso. Solo el flujo institucional humano controlado puede cambiar ese estado.

## Interpretación de seguridad

Este recorrido es educación sintética para revisores. “Pass” solo indica que un contrato determinista aceptó sus hechos sintéticos. “Blocked”, “unknown”, “expired” e “incomplete” son resultados esperados cuando faltan evidencia, vigencia, autoridad o aceptación humana. Nada del JSON es instrucción de despacho, ruta C2, hallazgo de aeronavegabilidad, hallazgo médico ni autorización de vuelo.
