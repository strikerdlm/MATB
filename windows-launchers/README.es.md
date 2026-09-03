# Lanzadores de MATB UAS para Windows

Estos accesos ejecutan la consola sUAS y las simulaciones técnicas desde el
Explorador de archivos sin modificar los escenarios del estudio. Requieren
PowerShell 7, Python 3.12 o posterior, Node.js 20 o posterior y npm.

## Primer uso

1. Ejecute `01 - Abrir consola UAS.cmd`. Este acceso comprueba el entorno,
   instala dependencias faltantes, actualiza la compilación si es necesario,
   inicia los servicios locales y abre la guía paso a paso en
   `http://127.0.0.1:3100/start`.
2. Use `00 - Preparar MATB UAS.cmd` solamente si desea preparar el equipo y
   ejecutar las pruebas focalizadas sin abrir la consola.
3. Mantenga abierta la ventana supervisora. Presione `Ctrl+C` allí o ejecute
   `99 - Detener MATB UAS.cmd` para finalizar los procesos registrados.

`02 - Diagnosticar MATB UAS.cmd` revisa, sin modificar datos, las versiones de
Python y Node, dependencias, compilación, escenario, puertos, procesos
registrados, salud HTTP y la última ejecución sellada. Una consola detenida con
los puertos libres se considera un estado normal.

La consola se enlaza únicamente a loopback. Los datos, registros y estados de
proceso se guardan bajo `exports/windows-suas/service/`, una ruta ignorada por
Git. No use identidades personales; la consola acepta participantes
seudonimizados como `P01`.

## Simulaciones por perfil

Los accesos `10` a `13` validan `reference_area_search`, ejecutan la duración
completa configurada del perfil, graban artefactos en una carpeta nueva y
verifican replay y sumas de comprobación. Los resultados se escriben en:

```text
exports/windows-suas/runs/<fecha>-reference_area_search-<perfil>/
```

Estas ejecuciones son simulaciones técnicas sin interacción humana. No son
sesiones experimentales válidas y no sustituyen el protocolo interactivo, que
siempre comienza con `PRACTICE` y aplica el orden contrabalanceado del
participante.

`90 - Verificar ultima simulacion.cmd` vuelve a verificar el directorio técnico
más reciente sin modificarlo.

`91 - Abrir resultados MATB UAS.cmd` abre en el Explorador la ejecución técnica
sellada más reciente y, si existe, la carpeta de logs del servicio. Solo abre
rutas bajo `exports/windows-suas/`; use el acceso `90` para recalcular la
verificación criptográfica y el replay.

## Escenarios adicionales

Los scripts internos aceptan cualquier archivo YAML válido colocado
directamente en `scenarios/suas/`. El nombre del archivo y `scenario_id` deben
coincidir. Por ejemplo:

```powershell
pwsh -NoProfile -File .\scripts\Invoke-MatbUasProfile.ps1 `
  -Scenario otro_escenario -WorkloadProfile LOW
```

Cada escenario debe conservar los bloques `PRACTICE`, `LOW`, `MEDIUM` y
`HIGH`. Los rótulos de carga son preajustes de ingeniería pendientes de
calibración humana.

## Seguridad y solución de problemas

- El lanzador no cambia la política de ejecución de PowerShell.
- Los accesos de simulación funcionan aunque el Explorador de archivos los
  inicie desde un directorio distinto al repositorio.
- La consola detecta el commit Git y el estado del árbol antes de iniciar el
  backend. En un clon limpio, el diseñador registra procedencia `complete`. La
  advertencia provisional permanece deliberadamente si el árbol tiene cambios,
  Git no puede comprobarlo o el código proviene de un ZIP sin metadatos Git.
  Reinicie la consola con el acceso `99` y luego `01` después de actualizar los
  lanzadores para que el nuevo proceso reciba esta información.
- Si los puertos 8000 o 3100 pertenecen a otro programa, el inicio se detiene.
- El acceso de detención comprueba PID, ejecutable exacto y hora de inicio;
  cuando Windows permite consultar esa información, también valida la línea
  de comando. No detiene procesos Python o Node no registrados.
- Si una simulación técnica falla, conserve su carpeta y revise el mensaje en
  la ventana. Para la consola, revise `exports/windows-suas/service/logs/`.
- Un directorio de ejecución nunca se reutiliza ni se sobrescribe.
