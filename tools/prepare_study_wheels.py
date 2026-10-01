"""Prepare matching calculator wheels. Execution/export itself never downloads dependencies."""
import argparse
import subprocess
import sys
from pathlib import Path
import zipfile

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output'); parser.add_argument('--instruments',nargs='+',default=['pvt','screen','openmatb','questionnaire','liftoff','suas','physiology']); parser.add_argument('--check', action='store_true', help='Check installed-version wheel inventory without downloading or writing files'); args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webui/backend'))
    from app.study_analysis_bundle import dependency_versions
    versions=dependency_versions(set(args.instruments)); target=Path(args.output)
    if args.check:
        missing=[]
        for name,version in versions.items():
            prefix=name.lower().replace('-','_')+'-'+version.replace('-','_')+'-'
            matches=[p for p in target.glob('*.whl') if p.name.lower().startswith(prefix)]
            if len(matches)!=1 or not zipfile.is_zipfile(matches[0]): missing.append(f'{name}=={version}')
        print('Missing or invalid offline wheels: '+', '.join(missing) if missing else 'Offline calculator wheels are ready.')
        sys.exit(int(bool(missing)))
    target.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','--dest',str(target),*[f'{name}=={version}' for name,version in versions.items()]],check=True)
