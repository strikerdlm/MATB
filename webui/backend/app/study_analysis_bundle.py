"""Pinned calculator source and dependency closure for portable descriptive replay."""
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import zipfile
from pathlib import Path
from packaging.tags import sys_tags
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import Version
from app.hcf_derivations import canonical

ROOT=Path(__file__).resolve().parents[3]


def compatible_wheels(wheelhouse, name, version):
    """Select the pinned inventory for this interpreter, ABI and platform."""
    supported=set(sys_tags())
    matches=[]
    for path in sorted(Path(wheelhouse).glob('*.whl')):
        try:
            distribution, wheel_version, _build, tags=parse_wheel_filename(path.name)
        except InvalidWheelFilename:
            continue
        if (distribution==canonicalize_name(name) and wheel_version==Version(version)
                and tags & supported and zipfile.is_zipfile(path)):
            matches.append(path)
    return matches


def dependency_versions(instruments):
    packages=set()
    if instruments & {'pvt','openmatb','liftoff','suas','physiology'}: packages.update(['pydantic','pydantic_core','annotated-types','typing_extensions','typing-inspection'])
    if instruments & {'liftoff','physiology'}: packages.update(['numpy','scipy'])
    if 'physiology' in instruments: packages.update(['pandas','pyarrow','python-dateutil','six','pytz','tzdata'])
    if instruments & {'liftoff','suas'}: packages.add('PyYAML')
    versions={}
    for name in sorted(packages):
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            if name not in {'typing-inspection','pytz','tzdata'}: raise
    return versions


def implementation_artifacts(instruments):
    files={}
    # Preserve exact logical paths. Optional absent modules are not imported or required.
    for path in sorted((ROOT/'matb_integration').rglob('*')):
        if path.is_file() and path.suffix in {'.py','.json'} and '__pycache__' not in path.parts:
            files['source/'+path.relative_to(ROOT).as_posix()]=path.read_bytes()
    # Preparation grading/presentation code is provenance, not imported by offline replay.
    provenance_paths=['webui/backend/app/study_preparation.py','webui/backend/app/study_native_practice.py','webui/backend/app/study_policies.py','webui/backend/app/study_preflight.py','webui/backend/app/study_admission.py','webui/backend/app/study_bindings.py','webui/backend/app/study_native.py','webui/backend/app/routers/study_preparation.py','webui/frontend/src/components/study/StudyParticipant.tsx','webui/frontend/src/lib/assigned-attempt.ts','webui/frontend/src/components/instructions/InstructionAudio.tsx']
    for relative in provenance_paths:
        files['provenance-source/'+relative]=(ROOT/relative).read_bytes()
    files['source/replay_rules.py']=(ROOT/'webui/backend/app/study_analysis_rules.py').read_bytes()
    files['verify.py']=(ROOT/'tools/verify_study_descriptive.py').read_bytes()
    versions=dependency_versions(instruments)
    lock=''.join(f'{name}=={version}\n' for name,version in sorted(versions.items()))
    files['requirements.lock']=lock.encode()
    if versions:
        wheelhouse=Path(os.getenv('MATB_DESCRIPTIVE_WHEELHOUSE',str(ROOT/'.test-tmp/repeatable-study/descriptive-wheels')))
        for name,version in versions.items():
            matches=compatible_wheels(wheelhouse, name, version)
            if len(matches)!=1: raise ValueError(f'Pinned offline wheel missing/ambiguous for {name}=={version}; prepare MATB_DESCRIPTIVE_WHEELHOUSE before execution.')
            files['wheels/'+matches[0].name]=matches[0].read_bytes()
    files['README.txt']=b'Offline descriptive replay only. Extract this archive, create a fresh Python venv of the recorded version/platform, install with: python -m pip install --no-index --find-links wheels -r requirements.lock\nThen run: python verify.py .\nChecksums detect modification; they are not an external signature. Local plan attestation does not establish absence of prior result inspection. This analysis export is not full-workspace restoration.\n'
    inventory={p:hashlib.sha256(data).hexdigest() for p,data in sorted(files.items())}
    implementation=dict(version='study-descriptive-v1',python=sys.version,platform=platform.platform(),dependencies=versions,files=inventory,
        calculator_entrypoint='matb_integration.analysis.study_calculators.calculate',aggregation_entrypoint='replay_rules.aggregate',automatic_model=None)
    return files,implementation


from app.study_analysis_rules import render_figure


def calculation_binding():
    paths=['matb_integration/analysis/study_calculators.py','webui/backend/app/study_analysis_rules.py','webui/backend/app/study_analysis_catalog.py','webui/backend/app/study_analysis_eligibility.py','webui/backend/app/study_analysis_sources.py','webui/backend/app/study_analysis.py','tools/verify_study_descriptive.py']
    paths += [p.relative_to(ROOT).as_posix() for p in (ROOT/'matb_integration').rglob('*') if p.is_file() and p.suffix in {'.py','.json'} and '__pycache__' not in p.parts]
    return hashlib.sha256(canonical({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(set(paths))}).encode()).hexdigest()
