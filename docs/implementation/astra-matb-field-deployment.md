# Aplicación MATB en ASTRA-1 y ASTRA-2

Entrada de operación: `http://127.0.0.1:3100/astra`.

1. En una base nueva, usar **Cargar ASTRA-1 (5) y ASTRA-2 (7)**.
2. Una vez por base, revisar las políticas de registro, escribir el investigador
   responsable y activar el protocolo. La aplicación conserva su identidad y
   la versión de las reglas. Una base con otro estudio activo no se sustituye.
3. Seleccionar misión, indicativo, visita y pantalla. Comprobar identidad,
   audio, controles y pantalla. En V0, realizar la familiarización de 5 min.
4. Aplicar la visita. El recorrido usa el entorno nativo, reconocimiento de
   controles, tres bloques de 15 min, valoraciones tras cada bloque y dos
   pausas registradas de 3 min. Las pausas se controlan en el mismo recorrido.
5. Documentar consentimiento, reposo pre-tarea de 5 min y KSS antes de cada
   bloque en la hoja de campo; el panel no acredita estos registros externos.

## Grupos y calendario

| Misión | Indicativos |
| --- | --- |
| ASTRA-1 | CUELLAR, ICEMAN, COLORADO, WHITE, PIRATA |
| ASTRA-2 | BART, CHUCKY, VOLCANO, ALFA-1, ALFA-2, ALFA-3, ALFA-4 |

V0 PRE; V1 DM2; V2 DM4; V3 DM7; V4 DM10; V5 DM13; V6 DM15; V7 POST D+1.
Fechas y turnos son **planificados**. No se crean resultados, basales completados
ni fechas reales de adquisición. Los códigos P se asignan sin sobrescribir
identidades existentes y mantienen el mismo orden de bloques en las ocho visitas.
Si existen basales externos, revisar su correspondencia antes de adquirir datos.

Las fuentes son el registro de candidatos actualizado el 29 de septiembre de
2026, la guía y hoja de campo v2 de esa fecha y el Manual de Operaciones ASTRA
2026, sección 4.7.6. Solo se incorporan indicativo, grado, unidad, función y
franja de edad disponibles. Los datos no disponibles de ALFA-1 a ALFA-4 quedan
vacíos. Las políticas descriptivas y de repetición técnica se muestran para
su revisión explícita al activar; no constituyen un resultado de validación.

## Participantes y sesiones pendientes

**Gestionar participantes** permite añadir indicativos y retirar/restaurar
personas. Retirar conserva identidad, visitas y resultados y bloquea nuevas
adquisiciones. No se permite retirar a alguien con una evaluación activa.

Un 409 por sesión existente muestra su participante y permite retomarla. Si
todavía no comenzó, también permite cerrarla y liberar el puesto. Recuperar una
pestaña perdida rota las credenciales solo de sesiones INSTRUCTIONS/READY sin
inicio ni proceso nativo. Una tarea iniciada conserva sus controles originales.

La carga inicial es idempotente: no duplica participantes ni reactiva retirados.
Las rutas ASTRA se registran con el componente opcional OpenMATB y no cambian
el calendario del protocolo legado `astra-2026`.
