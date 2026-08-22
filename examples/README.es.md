# Ejemplos de MATB

[English](README.md) | [Español](README.es.md)

Elija únicamente el flujo que necesita. Todos los recursos confirmados en el repositorio son sintéticos
y seudónimos; ningún ejemplo contiene datos reales de participantes, telemetría operacional,
credenciales, claves privadas, arrendamientos del controlador, firmas ni decisiones institucionales.
Los ejemplos escriben solo en su directorio de salida predeterminado documentado o en el seleccionado
por quien los ejecuta. Detenga cualquier servicio antes de limpiar y elimine solo esa salida dedicada
del ejemplo; nunca un almacén compartido de estudio, evidencia, liberación o aceptación.

| Flujo | Guía | Velocidad y conectividad | Entorno adicional |
| --- | --- | --- | --- |
| Investigación OpenMATB | [Generar, convertir y ajustar](openmatb-research/README.es.md) | Rápido y sin conexión después de instalar las dependencias Python; el recorrido no inicia OpenMATB | Solo se necesita un entorno OpenMATB externo independiente para presentar tareas |
| Consola de Investigación | [Recorrido local de API/navegador](research-console/README.es.md) | Procedimiento de servicio; local y capaz de funcionar sin conexión después de instalar Python/npm y compilar el frontend | FastAPI en 8000, UI del navegador en 3100 |
| sUAS sintético | [Recorrido de CLI y ciclo de vida](suas-simulator/README.es.md) | La CLI es rápida/sin conexión; el procedimiento de servicio es local y capaz de funcionar sin conexión tras la instalación | El servicio de navegador usa el lanzador Linux/WSL2; Windows nativo puede ejecutar la CLI/llamar al servicio WSL2 |
| SMS FAC ISR | [Recorrido de capacidades de paquetes](sms-platform/README.es.md) | El recorrido de paquetes es rápido/sin conexión después de instalar/compilar | Docker/contenedores Linux solo para procedimientos de imagen/paquete sin conexión |
| Monitor heredado | [Cuatro modos de terminal](legacy-monitor/README.es.md) | Simulación de terminal sin conexión | Sin navegador ni servicio; el modo experimento escribe artefactos seleccionados |

Las palabras *pass*, *blocked* o *verified* en la salida del ejemplo describen únicamente el contrato
del componente sintético probado. No establecen validez clínica, aeronavegabilidad, autoridad de
despacho, preparación operacional ni aceptación institucional. No debilite las comprobaciones de
evidencia, vigencia, hash, firma, privacidad, ausencia de C2 o separación cuando se bloquee un ejemplo
diseñado deliberadamente para producir un bloqueo seguro.

Desde la raíz del repositorio, valide sin conexión la documentación, los pares de puntos de entrada
de plataforma, los enlaces, la seguridad operacional de los recursos y los contratos de comandos:

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Esas comprobaciones ligeras en dependencias se ejecutan desde un checkout limpio;
las pruebas de humo de compilación del SMS se omiten con un mensaje accionable cuando
faltan sus dependencias preparadas. Para incluir el objetivo específico de humo de
compilación y recorrido de paquetes del SMS, prepárelo explícitamente:

```bash
cd SMS
npm ci
npm run build:packages
cd ..
python -m pytest tests/documentation/test_documentation.py -q -k sms_package
```

La secuencia completa de instalación/configuración/ejecución/verificación/limpieza para cada flujo está
en la guía enlazada. El [README](../README.es.md) raíz incluye la matriz de prerrequisitos, los límites
entre Windows nativo y WSL2, el catálogo completo de módulos, operaciones, solución de problemas y
restricciones de gobernanza.
