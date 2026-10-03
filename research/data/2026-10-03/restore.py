"""Verify the private snapshot, optionally extracting into a new directory.

    python restore.py --verify-only
    python restore.py --destination E:/MATB-restored-20261003

Requires only Python 3.10+ and its standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-only', action='store_true')
    mode.add_argument('--destination', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    destination = args.destination.resolve() if args.destination else None
    if destination:
        destination.mkdir(parents=True, exist_ok=False)
    count = 0
    for archive in manifest['archives']:
        expected = {entry['path']: entry for entry in manifest['files'] if entry['archive'] == archive['name']}
        with tempfile.TemporaryFile() as joined:
            digest = hashlib.sha256()
            size = 0
            for part in archive['parts']:
                part_path = (root / part['path']).resolve()
                if part_path.parent != root:
                    raise ValueError('Invalid archive part path')
                part_digest = hashlib.sha256()
                part_size = 0
                with part_path.open('rb') as source:
                    while block := source.read(1024 * 1024):
                        joined.write(block)
                        digest.update(block)
                        part_digest.update(block)
                        size += len(block)
                        part_size += len(block)
                if part_size != part['bytes'] or part_digest.hexdigest() != part['sha256']:
                    raise ValueError('Archive part failed verification: ' + part['path'])
            if size != archive['bytes'] or digest.hexdigest() != archive['sha256']:
                raise ValueError('Joined archive failed verification: ' + archive['name'])
            joined.seek(0)
            with zipfile.ZipFile(joined) as zipped:
                names = zipped.namelist()
                if len(names) != len(set(names)) or set(names) != set(expected):
                    raise ValueError('Archive members differ from the manifest')
                for name in names:
                    relative = PurePosixPath(name)
                    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                        raise ValueError('Unsafe archive member path')
                    target = destination.joinpath(*relative.parts) if destination else None
                    if target:
                        target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    size = 0
                    sink = target.open('xb') if target else None
                    try:
                        with zipped.open(name) as source:
                            while block := source.read(1024 * 1024):
                                digest.update(block)
                                size += len(block)
                                if sink:
                                    sink.write(block)
                    finally:
                        if sink:
                            sink.close()
                    entry = expected[name]
                    if size != entry['bytes'] or digest.hexdigest() != entry['sha256']:
                        raise ValueError('Member failed verification: ' + name)
                    count += 1
        print('Verified ' + archive['name'], flush=True)
    if count != manifest['file_count']:
        raise ValueError('File count differs from the manifest')
    print(f'Verified {count} files.' + (f' Restored to {destination}' if destination else ''))


if __name__ == '__main__':
    main()
