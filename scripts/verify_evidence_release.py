"""Run retained software verification in an already installed isolated environment.

Use a fresh Git checkout (not a source archive), Python 3.12 environment and
Node 22.23.2. Install declared requirements and use --frontend for npm ci,
build and evidence browser acceptance. Output is never qualification of
physical timing or human validity. Each invocation owns its system temp tree.
"""
import argparse
import hashlib
import json
from importlib.metadata import distributions
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tempfile

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--frontend', action='store_true')
p.add_argument('--only', nargs='+')
args = p.parse_args()
root, output = args.source.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
temporary = Path(tempfile.mkdtemp(prefix='matb-verification-'))
env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
           TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary),
           PYTHONPATH=str(root), MATB_SOURCE_COMMIT=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
           MATB_SOURCE_DIRTY=str(bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True).strip())).lower(), MATB_PYTHON=sys.executable)
report = {'source_commit': env['MATB_SOURCE_COMMIT'], 'platform': platform.platform(),
          'python': sys.version, 'executable': sys.executable, 'steps': []}
commands = [
    ('contracts', root, [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider', '--ignore=tests/suas', '--ignore=tests/liftoff', '--ignore=tests/documentation']),
    ('native', root/'openmatb', [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider']),
    ('backend', root/'webui/backend', [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider']),
]
if args.frontend:
    npm = 'npm.cmd' if os.name == 'nt' else 'npm'
    commands += [(name, root/'webui/frontend', [npm, *argv]) for name, argv in [
        ('npm-install', ['ci']), ('frontend', ['test']), ('lint', ['run', 'lint']),
        ('typecheck', ['run', 'typecheck']), ('build', ['run', 'build']),
        ('browser-install', ['exec', '--', 'playwright', 'install', *(['--with-deps'] if os.name != 'nt' else []), 'chromium']),
        ('browser', ['run', 'test:e2e', '--', 'e2e/evidence.spec.ts', '--output=' + str(output/'browser')]),
    ]]
for name, cwd, command in commands:
    if args.only and name not in args.only:
        continue
    if name in {'contracts', 'native', 'backend'}:
        command += ['--junitxml=' + str(output/(name+'.xml')), '--basetemp=' + str(temporary/('pytest-'+name))]
    step_env = dict(env)
    if name == 'backend':
        step_env['PYTHONPATH'] = str(root/'webui/backend') + os.pathsep + str(root)
    print('Starting ' + name, flush=True)
    start = time.perf_counter()
    with (output/(name+'.log')).open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=cwd, env=step_env, stdout=log, stderr=subprocess.STDOUT)
    report['steps'].append({'name': name, 'exit_code': result.returncode, 'elapsed_seconds': round(time.perf_counter()-start,3), 'command': command})
    (output/'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(name + ' exit ' + str(result.returncode), flush=True)
    if name in {'npm-install','build'} and result.returncode:
        break
(output/'python-environment.txt').write_text('\n'.join(sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions())) + '\n', encoding='utf-8')
report['passed'] = all(step['exit_code'] == 0 for step in report['steps'])
(output/'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
sys.exit(0 if report['passed'] else 1)
