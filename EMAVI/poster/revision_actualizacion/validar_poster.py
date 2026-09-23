"""Validate the poster package and compare its editable text with the PDF export."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import posixpath
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PPTX = ROOT / 'EMAVI_2026_poster_Malpica_actualizado.pptx'
PDF = PPTX.with_suffix('.pdf')
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}

def norm(s):
    return re.sub(r'\s+', '', s).casefold()

# Raw extraction preserves shape order; layout extraction interleaves the two columns.
pdf_text = subprocess.check_output(['pdftotext', '-raw', str(PDF), '-']).decode('utf-8')
native = json.loads((HERE / 'verificacion_powerpoint.json').read_text(encoding='utf-8-sig'))
checks = {'original_unchanged': native['source_unchanged'],
          'no_text_overflow': not any(t['overflow'] for t in native['text_checks'])}
with ZipFile(PPTX) as z:
    checks['zip_crc_ok'] = z.testzip() is None
    names = set(z.namelist())
    slides = [n for n in names if re.fullmatch(r'ppt/slides/slide\d+.xml', n)]
    checks['single_slide'] = len(slides) == 1
    pres = ET.fromstring(z.read('ppt/presentation.xml'))
    size = pres.find('p:sldSz', NS)
    dims = [int(size.attrib[k]) / 360000 for k in ('cx', 'cy')]
    checks['dimensions_80x120cm'] = all(abs(a-b) < .01 for a,b in zip(dims,[80,120]))
    paragraphs = []
    for name in slides:
        xml = ET.fromstring(z.read(name))
        for p in xml.findall('.//a:p', NS):
            value = ''.join(t.text or '' for t in p.findall('.//a:t', NS))
            if value.strip():
                paragraphs.append(value)
    missing = [p for p in paragraphs if norm(p) not in norm(pdf_text)]
    checks['all_editable_paragraphs_in_pdf'] = not missing
    # Include speaker notes and document properties when checking superseded content.
    package_text = '\n'.join(z.read(n).decode('utf-8') for n in names
                             if n.endswith('.xml') and (n.startswith('ppt/slides/')
                             or n.startswith('ppt/notesSlides/') or n.startswith('docProps/')))
    checks['no_superseded_claims_or_commercial_name'] = not any(
        s.casefold() in package_text.casefold() for s in
        ['Liftoff', 'd9f0882c6ef6', '57 pruebas', '61,2', 'VISITAS PROPUESTAS'])
    broken = []
    for name in names:
        if not name.endswith('.rels'):
            continue
        base = posixpath.dirname(posixpath.dirname(name))
        for rel in ET.fromstring(z.read(name)):
            if rel.attrib.get('TargetMode') == 'External':
                continue
            target = rel.attrib['Target']
            resolved = posixpath.normpath(posixpath.join(base, target)).lstrip('/')
            if resolved not in names:
                broken.append([name, target])
    checks['internal_relationships_resolve'] = not broken

info = subprocess.check_output(['pdfinfo', str(PDF)]).decode('utf-8', errors='replace')
checks['pdf_single_page'] = bool(re.search(r'Pages:\s+1\b', info))
checks['pdf_metadata_updated'] = 'MATB-FAC:' in info and 'Liftoff' not in info
page_match = re.search(r'Page size:\s+([\d.]+) x ([\d.]+) pts', info)
checks['pdf_dimensions_match'] = bool(page_match) and all(
    abs(float(value)*2.54/72-expected) < .01
    for value,expected in zip(page_match.groups(), [80,120]))
checks['pdf_has_selectable_text'] = len(pdf_text) > 3500
report = {'date': '2026-09-23', 'checks': checks, 'passed': all(checks.values()),
          'dimensions_cm': dims, 'text_paragraphs': len(paragraphs),
          'missing_pdf_paragraphs': missing, 'broken_relationships': broken,
          'minimum_font_pt': min(t['font_pt'] for t in native['text_checks']),
          'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [PPTX, PDF, ROOT/'EMAVI_2026_poster_Malpica.pptx']}}
(HERE / 'validacion_final.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))
raise SystemExit(0 if report['passed'] else 1)
