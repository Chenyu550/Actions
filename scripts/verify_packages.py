#!/usr/bin/env python3
"""Check actual release payloads, never the runner's preinstalled node/npm."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from audit_pe import audit


ROOT = Path(__file__).resolve().parents[1]


def run_logged(command: list[str], logfile: Path, timeout: int = 120) -> str:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout)
    logfile.write_text(result.stdout, encoding='utf-8')
    print(result.stdout, flush=True)
    result.check_returncode()
    return result.stdout


def check_payload(executable: Path, label: str, reports: Path, version: str) -> None:
    folder = executable.parent
    actual = run_logged([str(executable), '--version'], reports / f'{label}-version.txt').strip()
    if actual != 'v' + version:
        raise RuntimeError(f'Unexpected packaged version: {actual}')
    audit(executable, reports / f'{label}-imports.json')
    for name in ['npm.cmd', 'npx.cmd', 'corepack.cmd', 'LICENSE']:
        if not (folder / name).is_file():
            raise RuntimeError(f'Missing packaged file: {folder / name}')
    run_logged([str(executable), str(ROOT / 'scripts/smoke.cjs')],
               reports / f'{label}-smoke.txt')
    # Invoke the bundled CLI using the packaged interpreter explicitly.
    for name, relative in [
        ('npm', 'node_modules/npm/bin/npm-cli.js'),
        ('npx', 'node_modules/npm/bin/npx-cli.js'),
        ('corepack', 'node_modules/corepack/dist/corepack.js'),
    ]:
        run_logged([str(executable), str(folder / relative), '--version'],
                   reports / f'{label}-{name}.txt')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--reports', type=Path, default=Path('reports'))
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Package execution/MSI extraction requires a Windows build host.')
    source = args.source.resolve()
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'patches/manifest.json').read_text(encoding='utf-8'))['node_version']
    archive = source / f'Release/node-v{version}-win-x64.zip'
    installer = source / f'node-v{version}-x64.msi'
    for file in [archive, installer]:
        if not file.is_file() or file.stat().st_size == 0:
            raise RuntimeError(f'Build did not produce {file}')

    with tempfile.TemporaryDirectory(prefix='node24-win7-') as tmp:
        tmp = Path(tmp).resolve()
        unpacked_zip = tmp / 'zip'
        with zipfile.ZipFile(archive) as zipped:
            bad_file = zipped.testzip()
            if bad_file:
                raise RuntimeError(f'Corrupt ZIP entry: {bad_file}')
            for name in zipped.namelist():
                if not (unpacked_zip / name).resolve().is_relative_to(unpacked_zip):
                    raise RuntimeError(f'Invalid ZIP entry path: {name}')
            zipped.extractall(unpacked_zip)
        zip_exe = unpacked_zip / f'node-v{version}-win-x64/node.exe'
        check_payload(zip_exe, 'zip', reports, version)

        # Administrative extraction validates MSI/cabinet contents without
        # upgrading/removing the runner's globally installed official Node.
        unpacked_msi = tmp / 'msi'
        msi_log = reports / 'msi-admin-extract.log'
        result = subprocess.run([
            'msiexec.exe', '/a', str(installer), '/qn', '/norestart',
            f'TARGETDIR={unpacked_msi}', '/L*v', str(msi_log),
        ], timeout=240)
        if result.returncode not in [0, 3010]:
            raise RuntimeError(f'MSI administrative extraction failed: {result.returncode}; see {msi_log}')
        candidates = list(unpacked_msi.rglob('node.exe'))
        if len(candidates) != 1:
            raise RuntimeError(f'Expected one MSI node.exe, found {len(candidates)}')
        msi_exe = candidates[0]
        if hashlib.sha256(msi_exe.read_bytes()).digest() != hashlib.sha256(zip_exe.read_bytes()).digest():
            raise RuntimeError('ZIP and MSI contain different node.exe binaries.')
        check_payload(msi_exe, 'msi', reports, version)
    print('ZIP and MSI payload checks passed on the current Windows host.')
    print('Windows 7 execution/installation still requires a real Windows 7 SP1 x64 test.')


if __name__ == '__main__':
    main()
