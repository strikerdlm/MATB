# Revisión de exportación nativa — EMAVI

23-09-2026. Exportación mediante Microsoft PowerPoint 16.0 / Microsoft 365 en Windows.

Se revisaron las 24 láminas mediante hojas de contacto y ampliaciones focales por un revisor independiente. No se encontraron recortes de texto, superposiciones, glifos ausentes ni contenido en blanco. Se conservó el diseño institucional. Los PDF contienen texto seleccionable; las notas incrustadas coinciden con el guion vigente. Las huellas SHA-256 están en `verificacion_exportacion_nativa.json`.

La validación FAC comprobó avisos, clasificación, geometría, tipografía e imágenes PNG incrustadas. Se abreviaron dos títulos para ajustarlos a los espacios de la plantilla. Se corrigió la escritura de metadatos para PowerShell 7 mediante XML del paquete.

Observaciones menores: texto central pequeño y espaciado justificado amplio en 6–8 y 18–22; detalles finos de las capturas 11–17, especialmente 12 y 16, requieren ampliación para lectura durante proyección.

Verificación reproducible desde la raíz del repositorio: `python CEINNA/construccion/verificar_exportaciones_nativas.py` (requiere PyMuPDF). Las hojas `exportacion_nativa_*.jpg` documentan la revisión.
