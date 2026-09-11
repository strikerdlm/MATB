"""Prepare matching calculator wheels. Execution/export itself never downloads dependencies."""
import argparse
import subprocess
import sys
from pathlib import Path

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output'); parser.add_argument('--instruments',nargs='+',default=['pvt','screen','openmatb','questionnaire','liftoff','suas','physiology']); args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webui/backend'))
    from app.study_analysis_bundle import dependency_versions
    versions=dependency_versions(set(args.instruments)); target=Path(args.output); target.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','--dest',str(target),*[f'{name}=={version}' for name,version in versions.items()]],check=True)
