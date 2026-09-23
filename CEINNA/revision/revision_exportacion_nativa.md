# Revisión de exportación nativa — CEINNA

23-09-2026. Exportación mediante Microsoft PowerPoint 16.0 / Microsoft 365 en Windows.

Se revisaron las 17 láminas mediante hojas de contacto y ampliaciones focales por un revisor independiente. No se encontraron recortes de texto, superposiciones, glifos ausentes ni contenido en blanco. Se conservó el diseño institucional. Los PDF contienen texto seleccionable; las notas incrustadas coinciden con el guion vigente. Las huellas SHA-256 están en `verificacion_exportacion_nativa.json`.

Cero cuadros con desbordamiento en la medición de PowerPoint. Los pies bibliográficos permanecen pequeños pero íntegros. Duración programada: 720 segundos; sin ensayo humano nuevo ni margen adicional.

El manual ASTRA de fuentes tiene una huella distinta de la registrada en el manifiesto original. La diferencia precede a esta exportación (modificación en commit `467e7d4`); se conserva y declara, sin afirmar que todas las fuentes coinciden con las copias originales. La plantilla PPTX sí coincide. El paquete original de 16 láminas y sus informes históricos permanecen separados.

Verificación reproducible desde la raíz del repositorio: `python CEINNA/construccion/verificar_exportaciones_nativas.py` (requiere PyMuPDF). Las hojas `exportacion_nativa_*.jpg` documentan la revisión.
