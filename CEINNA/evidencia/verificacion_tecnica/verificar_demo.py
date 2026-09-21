"""Verificación focal CEINNA: exclusivamente artefactos sintéticos locales."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from matb_integration.scenario_builder import build_block_scenario, WorkloadLevel
from matb_integration.log_converter import convert_session

OUT = Path(__file__).resolve().parent
results = []
metrics = []
for i, level in enumerate(WorkloadLevel):
    path = OUT / 'escenarios' / f'{level.value}_workload.txt'
    manifest = json.loads(path.with_suffix('.txt.manifest.json').read_text(encoding='utf-8'))
    expected = build_block_scenario(level=level, block_duration_sec=900, seed=42+i)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == manifest['scenario']['sha256']
    assert path.read_text(encoding='utf-8') == expected
    assert expected == build_block_scenario(level=level, block_duration_sec=900, seed=42+i)
    record = convert_session(ROOT / 'examples/openmatb-research/fixtures' / f'{level.value}.csv', participant_id='SYNTH-CEINNA-01', block_name='synthetic_'+level.value, workload_level=level.name)
    metrics.append(record)
    results.append(dict(condicion=level.name, duracion_escenario_s=900, semilla=42+i, sha256=digest, hash_verificado=True, reproduccion_identica=True, parametros=manifest['parameters'], eventos_previstos=manifest['expected']))
(OUT/'metricas_sinteticas.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
summary = dict(fecha='2026-09-21', commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), python=sys.version, tipo='Demostración técnica sintética; no datos humanos ni ejecución de la interfaz', escenarios=results, archivos_convertidos=len(metrics), limitacion='La conversión de CSV y la generación de escenarios no demuestran adquisición ni elegibilidad confirmatoria.')
(OUT/'resultado_verificacion.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('PASS: 3 escenarios con hash SHA-256 correcto, regeneración idéntica y 3 CSV sintéticos convertidos.')
for row in results:
    e=row['eventos_previstos']
    print(row['condicion'], 'SYSMON objetivo',e['sysmon_target_opportunities'],'no objetivo',e['sysmon_nontarget_opportunities'],'COMM',e['comm_events'])
