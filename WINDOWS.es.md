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
   práctica o la sesión asignada del estudio. Mantenga abierta la ventana supervisora.

| Archivo | Función |
| --- | --- |
| `Install MATB.cmd` | Instalar o reparar la aplicación de investigación |
| `Start MATB.cmd` | Abrir la consola de investigación |
| `Start OpenMATB.cmd` | Abrir OpenMATB en español, en ventana y en la primera pantalla |
| `Diagnose MATB.cmd` | Revisar dependencias, compilación, escenario, procesos, puertos y registros |
| `Stop MATB.cmd` | Detener los servicios registrados de la consola |

Los accesos anteriores de `windows-launchers/` siguen disponibles. Para estudios
controlados, use las sesiones asignadas de la consola; el escritorio directo es
un flujo independiente. La consola instalada y las tareas incluidas funcionan
sin Internet; mapas en línea, tráfico en vivo y proveedores de modelos necesitan
conectividad. Bluetooth necesita hardware compatible.

Los datos se guardan en `exports/windows-suas/`: capturas de escritorio en
`desktop/`; base de datos, capturas de consola, dependencias de exportación y
registros en `service/`. Puede definir `MATB_DATA_ROOT` con una carpeta externa
dedicada. Los registros de instalación están en `exports/windows-install/`.
Conserve los datos al actualizar. Evite Program Files y carpetas sincronizadas.

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
| Puertos 8000 o 3100 ocupados | Detenga el servicio conocido o use `-BackendPort`/`-FrontendPort` en el lanzador PowerShell existente. |
| Faltan dependencias de exportación | Repita setup con la misma carpeta de datos e intérprete que la consola. |
| Movió el repositorio | Detenga la consola anterior y repita setup en la ubicación nueva. |

El trabajo CI de instalación Windows comprueba preparación, aislamiento,
versiones, arranque, reproducción, diagnóstico y cierre con rutas que contienen
espacios y Unicode. Pantalla, audio, controles y Polar H10 deben verificarse en
la estación real.
