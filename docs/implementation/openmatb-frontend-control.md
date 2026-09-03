# Control de OpenMATB desde MATB-FAC

## Alcance

La consola web local controla la suite clásica de OpenMATB sin sustituir su ventana Pyglet. El investigador prepara la visita, abre la pantalla del participante y controla inicio, pausa, reanudación, repetición de práctica y aborto. El participante lee las instrucciones y responde las escalas; no recibe la credencial de control.

La secuencia es `PRACTICE` seguida de `LOW`, `MEDIUM` y `HIGH` en uno de los seis órdenes de contrabalanceo. Antes de cada bloque se requiere una acción explícita del investigador. Una sesión ya creada conserva los SHA-256 del preset y de las instrucciones publicados.

## Preparación de la estación

1. Instale las dependencias Python de OpenMATB y las dependencias del backend y frontend.
2. Defina `MATB_OPENMATB_PYTHON` con el ejecutable Python que contiene Pyglet cuando el backend use otro entorno.
3. En Linux, inicie la sesión desde un escritorio con `DISPLAY` o `WAYLAND_DISPLAY` disponible. En Windows, la consola asigna el proceso nativo a un Job Object para cerrar también sus procesos descendientes al abortar o apagar el backend.
4. Inicie backend y frontend con los lanzadores del repositorio.
5. Abra **OpenMATB → Suite clásica**, seleccione participante, visita, preset, instrucciones y pantalla, y confirme la comprobación física de audio y controles.
6. Pulse **Preparar y abrir pantalla del participante**. El token del participante se transfiere una sola vez mediante el fragmento local de la URL y luego se elimina de la barra de direcciones.
7. El participante confirma las instrucciones. El investigador inicia cada bloque con un clic desde su panel.

Los artefactos controlados se guardan en `exports/openmatb-controlled/` de forma predeterminada. Puede cambiarse con `MATB_OPENMATB_OUTPUT_DIR`. La configuración es local: no expone control remoto ni publica datos.

## Presets e instrucciones

Las configuraciones publicadas son inmutables. Para modificar una, abra **Configurar presets e instrucciones**, clone una versión, edite el borrador y publíquelo. Los presets incluyen duración, dificultad, objetivo TRACK, pérdida RESMAN e intervalo ISA para los cuatro perfiles. Las instrucciones contienen pasos generales, texto por tarea y texto específico para T0, DM8 y DM15; otras visitas usan la entrada `DEFAULT`.

Los rótulos LOW/MEDIUM/HIGH describen presets de ingeniería. No demuestran por sí mismos separación psicométrica, calibración humana ni validez operacional; esa evidencia debe analizarse de manera independiente.

## Escalas de carga de trabajo

- **Raw NASA-TLX** es la medida subjetiva principal posbloque: seis dimensiones mostradas en español, 0–100 en pasos de 5. La adaptación estudiada en España mostró consistencia interna aceptable en 398 trabajadores, pero esto no constituye validación colombiana o latinoamericana automática (Díaz Ramiro et al., 2010, <https://scielo.isciii.es/scielo.php?pid=S1576-59622010000300003&script=sci_abstract>).
- **ISA** se presenta durante OpenMATB en español con cinco niveles. Puede ser sensible a la dificultad, pero su propia solicitud puede afectar el rendimiento de tracking; por ello se registra como medición concurrente potencialmente reactiva (Tattersall & Foord, 1996, <https://pubmed.ncbi.nlm.nih.gov/8635447/>).
- **Bedford** se presenta como escala secundaria 1–10 con descripciones de capacidad sobrante. La interfaz la marca como traducción exploratoria no validada localmente. La escala original tiene estructura de árbol de decisión y sus valores no deben asumirse equidistantes (NASA, 2010, <https://matb-files.larc.nasa.gov/Workload_Primer_TM_Final.pdf>).

La suite no convierte una traducción en una validación. Para uso confirmatorio, el protocolo debe preespecificar versión, población, administración, hipótesis y tratamiento estadístico de cada escala.

## Recuperación

- Si el backend reinicia durante una ejecución, la sesión se marca `INTERRUPTED`; no se infiere continuidad temporal.
- Si OpenMATB no informa que está listo en 20 segundos, la sesión falla y el proceso se termina.
- **Abortar** es terminal y conserva la razón y los artefactos ya escritos.
- **Repetir práctica** sólo está disponible inmediatamente después de la práctica y antes del primer bloque medido.
