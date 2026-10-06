# Instalar MATB en Windows

[English](WINDOWS.md) | [Español](WINDOWS.es.md)

1. Descargue el ZIP y use **Extraer todo**, o clone el repositorio. Use una
   carpeta donde pueda escribir, por ejemplo `C:\Users\SuNombre\MATB`.
2. Abra **Install MATB.cmd** con doble clic. En Windows 10/11 de 64 bits,
   instala los requisitos que falten mediante WinGet: PowerShell 7, Python 3.12
   de 64 bits y Node.js 22. Crea `.venv-suas`, instala versiones fijadas para
   Windows, prepara dependencias de exportación sin conexión, instala y compila
   la interfaz y ejecuta verificaciones. La primera instalación necesita Internet.
   Acepte el aviso de elevación de Windows si un instalador lo solicita.
   Mantenga abierta la ventana hasta que termine.
3. Abra **Start MATB.cmd**. El navegador muestra
   `http://127.0.0.1:3100/start`. Seleccione OpenMATB u otra actividad y elija
   práctica o la sesión asignada del estudio. Al finalizar el arranque puede cerrar
   la ventana del acceso; la aplicación continúa funcionando.

| Archivo | Función |
| --- | --- |
| `Install MATB.cmd` | Instalar o reparar la aplicación de investigación |
| `Start MATB.cmd` | Cerrar la instancia anterior y abrir nuevamente la consola |
| `Start OpenMATB.cmd` | Cerrar la instancia anterior y abrir OpenMATB en español, en ventana y en la primera pantalla |
| `Diagnose MATB.cmd` | Revisar dependencias, compilación, escenario, procesos, puertos y registros |
| `Stop MATB.cmd` | Cerrar la consola y las ventanas nativas, incluso si falta el registro de procesos |

Los accesos anteriores de `windows-launchers/` siguen disponibles. Para estudios
controlados, use las sesiones asignadas de la consola; el escritorio directo es
un flujo independiente. La consola instalada y las tareas incluidas funcionan
sin Internet; mapas en línea, tráfico en vivo y proveedores de modelos necesitan
conectividad. Bluetooth necesita hardware compatible.

Cada inicio libera los puertos de MATB (8000 y 3100 por defecto), cierra sus
procesos secundarios y las ventanas OpenMATB de esta instalación antes de
reparar dependencias o compilar. Esto también cierra cualquier aplicación que
ocupe esos dos puertos: resérvelos para MATB. No cierra otros procesos Python o
Node por su nombre. Si otra instalación necesita esos puertos, use
`-BackendPort` y `-FrontendPort` en los accesos de consola. Una tarea interrumpida
no se marca como completada; conserva los datos ya escritos y requiere un nuevo
intento. Evite reiniciar durante una adquisición que desee conservar activa.

Los datos se guardan en `exports/windows-suas/`: capturas de escritorio en
`desktop/`; base de datos, capturas de consola, dependencias de exportación y
registros en `service/`. Puede definir `MATB_DATA_ROOT` con una carpeta externa
dedicada. Los registros de instalación están en `exports/windows-install/`.
Conserve los datos al actualizar. Evite Program Files y carpetas sincronizadas.

Al abrir sin una carpeta de datos explícita, si existe la base histórica
`webui/backend/matb_webui.db` del arranque manual, se reutiliza para conservar
los participantes y resultados. `MATB_DB_PATH` tiene prioridad; una carpeta
seleccionada con `-DataRoot` o `MATB_DATA_ROOT` usa su propia base. El lanzador
muestra la ruta elegida y la guarda en `service/service-state.json`.

Por defecto se usa un entorno Python local aislado. Si define `MATB_PYTHON` o
`MATB_VENV`, la instalación puede modificar ese entorno seleccionado; quite las
variables para usar el entorno aislado. Windows/Python 3.12 usa
`release/requirements-windows-py312.lock`; otras versiones compatibles elegidas
explícitamente usan los requisitos del código. Windows y WSL necesitan entornos
y compilaciones separados. Los accesos no requieren WSL ni Git cuando usa el
ZIP, cuya procedencia conserva correctamente el estado provisional.

## Solución de problemas

| Síntoma | Acción |
| --- | --- |
| Falta WinGet | Instale/actualice [Microsoft App Installer](https://apps.microsoft.com/detail/9nblggh4nns1) y repita la instalación. |
| La institución bloquea instalaciones | Solicite los requisitos a TI: [PowerShell](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows), [Python 3.12](https://www.python.org/downloads/windows/), [Node.js 22](https://nodejs.org/en/download). |
| PowerShell bloquea scripts | Los accesos usan una política limitada al proceso; no cambian la política del equipo. Las políticas institucionales siguen aplicándose. Consulte a TI. |
| Fallan dependencias o compilación | Repita `Install MATB.cmd` y consulte su registro. |
| npm `EPERM` en `node_modules/.vite/vitest/.../results.json` | Cuando la estación esté inactiva, cierre las pruebas de la interfaz, ejecute `Stop MATB.cmd`, luego `Install MATB.cmd` y `Start MATB.cmd`. La preparación conserva la caché anterior fuera de `node_modules` antes de reinstalar. Para un lanzador anterior, vea abajo. |
| Puertos 8000 o 3100 ocupados o sesión anterior abierta | Repita `Start MATB.cmd`: cierra la instancia anterior y libera los puertos antes de abrir. Si Windows impide cerrar un proceso protegido, el mensaje identifica el proceso y detiene el arranque. |
| `maplibre-gl/package.json` ausente o `next` no reconocido | Use `Start MATB.cmd`; comprueba los paquetes requeridos y repara una instalación incompleta antes de abrir. No necesita ejecutar `npm start` por separado. |
| Parpadeo en OpenMATB nativo a pantalla completa | Actualice y vuelva a abrir MATB. En Windows se usa una ventana sin bordes dentro del área de trabajo, con sincronización explícita del compositor. La comprobación visual de la pantalla sigue siendo necesaria; no se cambian el controlador ni el registro de Windows. |
| Faltan dependencias de exportación | Repita setup con la misma carpeta de datos e intérprete que la consola. |
| Movió el repositorio | Detenga la consola anterior y repita setup en la ubicación nueva. |

Ese `results.json` es una caché de pruebas de software, ajena a los resultados
de participantes. Windows puede impedir borrarla si la creó otra cuenta
(incluida una cuenta de pruebas automáticas) o si un proceso la mantiene abierta.
La preparación la conserva en `webui/frontend/.matb-cache-backup-*`; las nuevas
pruebas usan una caché temporal separada por cuenta y copia del repositorio.
Los datos de participantes permanecen en la carpeta de datos configurada.

Con un lanzador anterior, cierre las pruebas y detenga MATB cuando la estación
esté inactiva. Después ejecute esto en PowerShell desde la carpeta del
repositorio, antes de repetir la instalación:

```powershell
$frontend = (Resolve-Path -LiteralPath '.\webui\frontend').Path
$cache = Join-Path $frontend 'node_modules\.vite'
$backup = Join-Path $frontend ('.matb-cache-backup-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $cache) {
    [System.IO.Directory]::Move($cache, $backup)
}
```

Si tampoco permite moverla, reinicie Windows y repita antes de abrir MATB o las
pruebas. Si persiste el error de acceso, revise los permisos de esa caché
específica. Conserve los datos del estudio y la protección del antivirus.

El trabajo CI de instalación Windows comprueba preparación, aislamiento,
versiones, arranque, reproducción, diagnóstico y cierre con rutas que contienen
espacios y Unicode. Pantalla, audio, controles y Polar H10 deben verificarse en
la estación real.
