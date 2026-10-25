#!/usr/bin/env python3
"""Apply the locked patch series to exactly the audited Node source revision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(source), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding='utf-8', errors='replace',
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--report', type=Path, default=Path('reports/build-info.json'))
    args = parser.parse_args()
    source = args.source.resolve()
    manifest = json.loads((ROOT / 'patches/manifest.json').read_text(encoding='utf-8'))
    actual_commit = git(source, 'rev-parse', 'HEAD')
    if actual_commit != manifest['node_commit']:
        raise SystemExit(f'Unexpected Node revision: {actual_commit}; expected {manifest["node_commit"]}')
    if git(source, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Node source has tracked modifications; use a fresh checkout.')
    header = (source / 'src/node_version.h').read_text(encoding='utf-8')
    version = '.'.join(re.search(rf'^#define NODE_{part}_VERSION\s+(\d+)', header, re.M)[1]
                       for part in ['MAJOR', 'MINOR', 'PATCH'])
    if version != manifest['node_version']:
        raise SystemExit(f'Node version mismatch: {version}')

    # Check every file's digest before making any source changes.
    for entry in manifest['patches']:
        path = ROOT / 'patches' / entry['file']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise SystemExit(f'Patch checksum mismatch: {path.name}')
    for entry in manifest['patches']:
        path = ROOT / 'patches' / entry['file']
        git(source, 'apply', '--check', str(path))
        git(source, 'apply', '--whitespace=error', str(path))
        print(f'Applied {path.name}', flush=True)
    git(source, 'diff', '--check')

    report = dict(manifest)
    report.update({
        'node_commit_verified': actual_commit,
        'architecture': 'x64',
        'target': 'Windows 7 SP1 / Server 2008 R2 SP1 or later (experimental)',
        'build_host': 'GitHub windows-2022',
        'windows_7_tested': False,
        'signing': 'unsigned community build',
        'command': 'vcbuild.bat x64 vs2022 clang-cl no-cctest msi',
        'zip': '7z a -tzip -mx=7 node-v24.20.0-win-x64.zip node-v24.20.0-win-x64',
    })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
