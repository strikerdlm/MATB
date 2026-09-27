"""Check the exported EMAVI PPTX/PDF against the authored sources.

Uses Python's standard library and the installed Poppler tools. PowerPoint COM
performs the separate native typography, geometry and contain checks.
"""
from pathlib import Path
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import unicodedata
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def norm(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())

def texts(node):
    return '\n'.join(''.join(t.text or '' for t in p.findall('.//a:t', NS))
                     for p in node.findall('.//a:p', NS))

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    manifest=json.loads((ROOT/'fuentes/manifest.json').read_text(encoding='utf-8-sig'))
    notes=json.loads((ROOT/'fuentes/notas.json').read_text(encoding='utf-8-sig'))
    pptx=ROOT/'entregables/ASTRA_MATB_EMAVI_es_ampliada.pptx'
    pdf=pptx.with_suffix('.pdf')
    check(len(notes)==40, 'Expected 40 authored notes')
    check(sum(n['seconds'] for n in notes)==1740, 'Expected 29:00 scheduled speech')
    check(sha(ROOT/'fuentes/FAC-template.pptx')=='147312eaac5e5c164b9433b072c36c104be8f8e090405539bb4e0bdbf4fc6959', 'Template changed')
    report={'date':'2026-09-27','slides':40,'notes':40,'scheduled_seconds':1740,
            'spoken_words':sum(len(n['oral'].split()) for n in notes),
            'human_rehearsal':False,'images':[],'tables':[]}
    with ZipFile(pptx) as z:
        check(z.testzip() is None, 'ZIP integrity failure')
        names=set(z.namelist())
        slideparts=sorted(n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
        noteparts=sorted(n for n in names if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml',n))
        check(len(slideparts)==40 and len(noteparts)==40,'Incorrect native slide/note count')
        broken=[]
        for part in names:
            if not part.endswith('.rels'):
                continue
            base=part.split('/_rels/')[0] if '/_rels/' in part else ''
            for rel in ET.fromstring(z.read(part)):
                if rel.get('TargetMode')=='External':
                    continue
                target=unquote(rel.get('Target','').split('#')[0])
                resolved=posixpath.normpath(posixpath.join(base,target)).lstrip('/')
                if resolved not in names:
                    broken.append([part,target,resolved])
        check(not broken, f'Broken package relationships: {broken}')
        report['internal_relationships']='passed'
        visible=[]
        for i in range(1,41):
            xml=ET.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
            st=texts(xml)
            matches=re.findall(r'P[úu]blico\s+Clasificado',st,re.I)
            visible.extend([i]*len(matches))
            check(not re.search(r'OPCI[ÓO]N\s*0?[12]|Esta\s+plantilla|\bX{4,}\b',st,re.I),f'Placeholder slide {i}')
            rels=ET.fromstring(z.read(f'ppt/slides/_rels/slide{i}.xml.rels'))
            note_rel=next(r for r in rels if r.get('Type','').endswith('/notesSlide'))
            note_part=posixpath.normpath(posixpath.join('ppt/slides',note_rel.get('Target')))
            nt=texts(ET.fromstring(z.read(note_part)))
            check(norm(notes[i-1]['oral']) in norm(nt),f'Oral note mismatch slide {i}')
            check(norm(notes[i-1]['sources']) in norm(nt),f'Source note mismatch slide {i}')
            check(f"GUION ORAL ({notes[i-1]['seconds']} s)" in nt,f'Time mismatch slide {i}')
            if not 5<=i<=39:
                continue
            item=manifest['content'][i-5]
            check(norm(item['title']) in norm(st),f'Title mismatch slide {i}')
            if item['type']=='text':
                for bullet in item['bullets']:
                    check(norm(bullet) in norm(st),f'Bullet mismatch slide {i}: {bullet}')
            elif item['type']=='table':
                tables=xml.findall('.//a:tbl',NS)
                check(len(tables)==1,f'Native editable table absent slide {i}')
                actual=[[texts(cell) for cell in row.findall('a:tc',NS)]
                        for row in tables[0].findall('a:tr',NS)]
                check(actual==[item['columns']]+item['rows'],f'Table content mismatch slide {i}')
                report['tables'].append(i)
            elif item['type']=='image_text':
                check(norm(item['body']) in norm(st),f'Image body mismatch slide {i}')
                pic=next(p for p in xml.findall('.//p:pic',NS)
                         if p.find('p:nvPicPr/p:cNvPr',NS).get('name')=='FAC_IMAGE_SLOT')
                rid=pic.find('.//a:blip',NS).get('{'+NS['r']+'}embed')
                image_rel=next(r for r in rels if r.get('Id')==rid)
                image_part=posixpath.normpath(posixpath.join('ppt/slides',image_rel.get('Target')))
                local=(ROOT/'fuentes'/item['image']['path']).resolve()
                check(hashlib.sha256(z.read(image_part)).hexdigest()==sha(local),f'Image bytes changed slide {i}')
                report['images'].append({'slide':i,'file':str(local.relative_to(ROOT)),'sha256':sha(local)})
        check(visible==[2],f'Classification visible on {visible}; expected one occurrence on slide 2')
        report['classification_visible_slides']=visible
    pdfinfo=shutil.which('pdfinfo')
    pdftotext=shutil.which('pdftotext')
    check(pdfinfo and pdftotext,'Poppler not installed')
    info=subprocess.run([pdfinfo,str(pdf)],check=True,capture_output=True).stdout.decode('utf-8','replace')
    check(re.search(r'^Pages:[ \t]+40\s*$',info,re.M) is not None,'PDF does not have 40 pages')
    check('Microsoft' in info and 'PowerPoint' in info,'PDF was not exported natively with PowerPoint')
    raw=subprocess.run([pdftotext,'-enc','UTF-8','-raw',str(pdf),'-'],check=True,capture_output=True,encoding='utf-8').stdout
    pages=raw.split('\f')
    if raw.endswith('\f'):
        pages.pop()
    check(len(pages)==40,'Incorrect PDF text page count')
    occurrences=[i+1 for i,p in enumerate(pages) for _ in re.finditer(r'P[úu]blico\s+Clasificado',p,re.I)]
    check(occurrences==[2],f'PDF classification appears on {occurrences}')
    for i,item in enumerate(manifest['content'],5):
        check(norm(item['title']) in norm(pages[i-1]),f'PDF title not selectable slide {i}')
    report['pdf']={'pages':40,'native_export':True,'text_selectable':True,'classification_visible_pages':occurrences}
    report['artifacts']=[{'file':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in [pptx,pdf]]
    native_path=ROOT/'revision/verificacion_fac_ampliada.json'
    native=json.loads(native_path.read_text(encoding='utf-8-sig'))
    check(native['result']=='passed' and native['deck_sha256']==sha(pptx),'Native validation does not match final PPTX')
    check(native['slides']==40 and native['classification_visible_slides']==[2],'Native validation scope mismatch')
    report['native_layout_validation']={'result':'passed','record':str(native_path.relative_to(ROOT)),
                                        'checked_at':native['checked_at'],'deck_sha256':native['deck_sha256']}
    report['result']='passed'
    out=ROOT/'revision/verificacion_ampliada.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Passed: 40 slides/pages; 40 notes; {len(report["tables"])} editable tables; {len(report["images"])} exact embedded images; single classification notice')

if __name__=='__main__':
    main()
