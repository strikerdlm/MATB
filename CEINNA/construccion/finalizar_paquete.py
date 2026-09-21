"""Consolida los artefactos CEINNA y verifica el paquete local final."""
from pathlib import Path
import csv
import hashlib
import json
import posixpath
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'entregables'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'dc': 'http://purl.org/dc/elements/1.1/'}

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

slides = read_json(ROOT / 'construccion/diapositivas_texto.json')
notes = read_json(ROOT / 'guion/notas_data.json')
refs = read_json(ROOT / 'construccion/referencias_slide.json')
geometry = read_json(ROOT / 'revision/geometria_texto.json')
assert len(slides) == len(notes) == 16
assert sum(s['seconds'] for s in slides) == sum(n['seconds'] for n in notes) == 690
assert not any(s['overflow'] for s in geometry)
for source in read_json(ROOT / 'fuentes/manifest.json'):
    assert sha(ROOT / source['copia']) == source['sha256']

pptx = OUT / 'ASTRA_MATB_III_CEINNA_es.pptx'
missing = []
with zipfile.ZipFile(pptx) as archive:
    members = set(archive.namelist())
    slide_names = [n for n in members if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
    note_names = [n for n in members if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', n)]
    assert len(slide_names) == len(note_names) == 16
    visible = '\n'.join(' '.join(t.text or '' for t in ET.fromstring(archive.read(n)).findall('.//a:t', NS)) for n in slide_names)
    embedded_notes = '\n'.join(' '.join(t.text or '' for t in ET.fromstring(archive.read(n)).findall('.//a:t', NS)) for n in note_names)
    assert 'SMSM DIEGO L MALPICA' in visible
    for banned in ['Título ponencia o conferencia', 'Describa brevemente', 'Listado de actividades', 'pendiente la calibración']:
        assert banned.casefold() not in visible.casefold(), banned
    for note in notes:
        if note['spoken']:
            assert note['spoken'] in embedded_notes, f"Notas distintas en lámina {note['slide']}"
    core = ET.fromstring(archive.read('docProps/core.xml'))
    assert core.find('dc:creator', NS).text == 'SMSM DIEGO L MALPICA'
    for name in members:
        if not name.endswith('.rels'):
            continue
        rels = ET.fromstring(archive.read(name))
        base = '' if name == '_rels/.rels' else posixpath.dirname(name).removesuffix('/_rels')
        for rel in rels:
            if rel.get('TargetMode') == 'External':
                continue
            target = rel.get('Target', '')
            resolved = posixpath.normpath(posixpath.join(base, target)).lstrip('/')
            if resolved not in members:
                missing.append((name, target))
    assert not missing, missing

pdf_text = (ROOT / 'revision/texto_pdf.txt').read_text(encoding='utf-8')
assert pdf_text.count('\f') == 16
assert 'SMSM DIEGO L MALPICA' in pdf_text
for ref in refs:
    doi = re.search(r'https://doi.org/\S+', ref['full'])[0]
    assert doi in embedded_notes, doi
assert len(refs) == 6
assert all(2020 <= int(re.search(r'\((20\d{2})\)', ref['full'])[1]) <= 2025 for ref in refs)

speech_rows = []
import wave
for rec in read_json(ROOT / 'revision/lectura_sintetica/manifest.json'):
    with wave.open(rec['path'], 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    speech_rows.append({**rec, 'measured_seconds': round(duration, 2), 'fits_allocated': duration <= rec['allocated_seconds']})
assert all(r['fits_allocated'] for r in speech_rows)
(ROOT / 'revision/lectura_sintetica/duraciones.json').write_text(json.dumps(speech_rows, ensure_ascii=False, indent=2), encoding='utf-8')

for source, target in [
    ('guion/notas_del_ponente.md', 'Notas_del_ponente_es.md'),
    ('guion/preguntas_comite.md', 'Preguntas_y_respuestas_del_comite.md'),
    ('evidencia/referencias_apa.md', 'Referencias_APA.md'),
    ('guion/glosario.md', 'Glosario.md'),
]:
    shutil.copyfile(ROOT / source, OUT / target)

with (ROOT / 'guion/mapa_diapositivas.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(['diapositiva', 'titulo', 'plantilla_base', 'segundos', 'recurso', 'fuente'])
    for s in slides:
        source = 'Plantilla original' if s['slide'] in (1, 16) else 'Matriz de afirmaciones, notas y bibliografía por lámina'
        resource = 'Texto y formas editables'
        if s['slide'] == 5: resource = 'Ilustración conceptual imagegen'
        if s['slide'] == 7: resource = 'Captura documental OpenMATB'
        writer.writerow([s['slide'], s['title'], s['template_slide'], s['seconds'], resource, source])

text_md = '# Texto final de diapositivas\n\nExportado del PPTX mediante PowerPoint; tiempos de exposición planificados.\n\n'
for s in slides:
    text_md += f"## {s['slide']}. {s['title']}\n\nTiempo: {s['seconds']} s. Plantilla base: {s['template_slide']}.\n\n{s['text']}\n\n"
(ROOT / 'guion/diapositivas.md').write_text(text_md.rstrip() + '\n', encoding='utf-8')

with (ROOT / 'visuales/registro_activos.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(['activo', 'metodo', 'procedencia', 'diapositiva', 'rotulo', 'sha256'])
    for relative, method, origin, slide, label in [
        ('fuentes/Plantilla_III_CEINNA.pptx', 'Plantilla original', 'Adjunto del investigador; manifest.json', '1–16', 'Identidad institucional original'),
        ('visuales/imagegen/habitat_estacion_conceptual.png', 'imagegen integrado', 'PROMPTS_IMAGEGEN.md', '5', 'Ilustración conceptual generada con IA; no fotografía de ASTRA.'),
        ('visuales/capturas_tecnicas/openmatb_captura_documentacion.png', 'Copia sin modificación', 'openmatb/.img/capture.png; commit 9b57a226f21b7046ce4d85556c9b71607a95bfea', '7', 'Captura documental de OpenMATB; interfaz original en francés'),
        ('construccion/build_presentation.ps1', 'Formas y texto nativos editables', 'Código local; cronología y auditoría técnica', '3,4,6,8–13', 'Diagramas metodológicos; no gráficas de resultados humanos'),
    ]:
        writer.writerow([relative, method, origin, slide, label, sha(ROOT / relative)])

word_count = sum(len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ−′]+(?:[’'’-][\wÁÉÍÓÚÜÑáéíóúüñ]+)*\b", n['spoken'])) for n in notes)
summary = {
    'fecha': '2026-09-21', 'diapositivas_pptx': 16, 'paginas_pdf': 16,
    'notas_embebidas': 16, 'exposicion_programada_segundos': 690,
    'limite_exposicion_segundos': 720, 'preguntas_comentarios_segundos': 180,
    'referencias_2020_2025': 6, 'desbordamientos_detectados': 0,
    'relaciones_internas_rotas': 0, 'copias_originales_sha256': f"{len(read_json(ROOT / 'fuentes/manifest.json'))} coinciden",
    'palabras_guion_oral': word_count,
    'voz_lectura_sintetica': speech_rows[0]['voice'],
    'lectura_sintetica_sin_pausas_segundos': round(sum(r['measured_seconds'] for r in speech_rows), 2),
    'lecturas_sinteticas_dentro_de_ventana': len(speech_rows),
    'ensayo_humano_realizado': False,
    'pptx_sha256': sha(pptx), 'pdf_sha256': sha(OUT / 'ASTRA_MATB_III_CEINNA_es.pdf'),
}
(ROOT / 'revision/verificacion_final.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
