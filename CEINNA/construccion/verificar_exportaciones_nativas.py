"""Verify native EMAVI/CEINNA exports; requires PyMuPDF (fitz)."""
from pathlib import Path
import hashlib
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

import fitz

ROOT = Path(__file__).resolve().parents[2]
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(project, stem, expected, note_path, note_field):
    folder = ROOT / project
    pptx = folder / 'entregables' / (stem + '.pptx')
    pdf = pptx.with_suffix('.pdf')
    notes = read_json(folder / note_path)
    assert len(notes) == expected
    with zipfile.ZipFile(pptx) as archive:
        assert archive.testzip() is None
        members = set(archive.namelist())
        slides = sorted((n for n in members if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
                        key=lambda n: int(re.search(r'slide(\d+)', n)[1]))
        note_parts = [n for n in members if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', n)]
        assert len(slides) == len(note_parts) == expected
        def text(name):
            return '\n'.join(t.text or '' for t in ET.fromstring(archive.read(name)).findall('.//a:t', NS))
        for i, slide in enumerate(slides):
            rel = ET.fromstring(archive.read(slide.replace('/slides/', '/slides/_rels/') + '.rels'))
            target = next(r.get('Target') for r in rel if r.get('Type', '').endswith('/notesSlide'))
            note_text = text(posixpath.normpath(posixpath.join('ppt/slides', target)))
            normalize = lambda value: ' '.join(value.split())
            assert normalize(notes[i][note_field]) in normalize(note_text), (project, i + 1, 'notes')
        visible = '\n'.join(text(s) for s in slides)
        for banned in ['Título ponencia o conferencia', 'Describa brevemente', 'XXXX', 'Esta plantilla']:
            assert banned.casefold() not in visible.casefold(), banned
        for name in members:
            if not name.endswith('.rels'):
                continue
            base = '' if name == '_rels/.rels' else posixpath.dirname(name).removesuffix('/_rels')
            for rel in ET.fromstring(archive.read(name)):
                if rel.get('TargetMode') != 'External':
                    target = posixpath.normpath(posixpath.join(base, rel.get('Target', ''))).lstrip('/')
                    assert target in members, (name, target)
        if project == 'EMAVI':
            assert read_json(folder / 'fuentes/aprobacion_politica.json')['approved'] is True
            for i in range(1, expected - 1):
                assert 'Público Clasificado' in text(slides[i]), i + 1
        core = ET.fromstring(archive.read('docProps/core.xml'))
        assert core.find('{http://purl.org/dc/elements/1.1/}creator').text == 'SMSM DIEGO L MALPICA'
    with fitz.open(pdf) as doc:
        assert len(doc) == expected
        assert 'PowerPoint' in doc.metadata.get('producer', '')
        pages = [page.get_text() for page in doc]
        # Institutional opening/closing slides may be entirely graphical.
        assert all(len(t.strip()) > 20 for t in pages[1:-1])
        if project == 'EMAVI':
            assert all('Público Clasificado' in t for t in pages[1:-1])
        extracted = '\f'.join('\n'.join(line.rstrip(' \t\r') for line in page.split('\n')) for page in pages) + '\f'
        (folder / 'revision/texto_pdf_nativo.txt').write_text(extracted, encoding='utf-8')
        producer = doc.metadata['producer']
    source_hash_mismatches = []
    if project == 'CEINNA':
        assert not any(r['overflow'] for r in read_json(folder / 'revision/geometria_texto.json'))
        assert sum(n['seconds'] for n in notes) == 720
        for source in read_json(folder / 'fuentes/manifest.json'):
            if sha(folder / source['copia']) != source['sha256']:
                source_hash_mismatches.append(source['copia'])
                assert not source['copia'].endswith('.pptx'), 'Template hash changed'
    else:
        assert sha(folder / 'fuentes/FAC-template.pptx') == '147312eaac5e5c164b9433b072c36c104be8f8e090405539bb4e0bdbf4fc6959'
    report = {
        'date': '2026-09-23', 'export_engine': producer,
        'pptx_slides': expected, 'pdf_pages': expected, 'embedded_notes_verified': expected,
        'native_pdf_text_verified': True, 'broken_internal_relationships': 0,
        'planned_seconds': sum(n['seconds'] for n in notes),
        'human_rehearsal_performed': False,
        'source_manifest_hash_mismatches': source_hash_mismatches,
        'pptx_sha256': sha(pptx), 'pdf_sha256': sha(pdf),
    }
    (folder / 'revision/verificacion_exportacion_nativa.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(project, json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    verify('CEINNA', 'ASTRA_MATB_III_CEINNA_es_visual', 17, 'guion/notas_data.json', 'spoken')
    verify('EMAVI', 'ASTRA_MATB_EMAVI_es', 24, 'fuentes/notas.json', 'oral')
