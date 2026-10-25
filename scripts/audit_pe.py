#!/usr/bin/env python3
"""Reject known Win8+ imports. This is a partial audit, not Win7 certification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pefile


FORBIDDEN_APIS = set('''
GetSystemTimePreciseAsFileTime GetHostNameW GetCurrentThreadStackLimits
WaitOnAddress WakeByAddressAll WakeByAddressSingle GetOverlappedResultEx
GetThreadDescription SetThreadDescription GetThreadInformation SetThreadInformation
GetProcessInformation SetProcessInformation
GetProcessMitigationPolicy SetProcessMitigationPolicy
GetSystemCpuSetInformation GetProcessDefaultCpuSets SetProcessDefaultCpuSets
GetThreadSelectedCpuSets SetThreadSelectedCpuSets SetThreadSelectedCpuSetMasks
VirtualAlloc2 VirtualAlloc2FromApp MapViewOfFile3 UnmapViewOfFile2
DiscardVirtualMemory OfferVirtualMemory ReclaimVirtualMemory PrefetchVirtualMemory
GetTempPath2A GetTempPath2W CreateFile2 CreateFile2FromAppW
GetCurrentPackageFullName GetCurrentPackageFamilyName GetPackageFamilyName
ProcessPrng RtlAddGrowableFunctionTable RtlDeleteGrowableFunctionTable
GetSystemTimeAdjustmentPrecise QueryInterruptTime QueryInterruptTimePrecise
QueryUnbiasedInterruptTimePrecise IsUserCetAvailableInEnvironment
'''.split())

FORBIDDEN_DLLS = {
    'api-ms-win-core-path-l1-1-0.dll',
    'api-ms-win-core-synch-l1-2-0.dll',
    'api-ms-win-core-winrt-l1-1-0.dll',
    'api-ms-win-core-winrt-string-l1-1-0.dll',
}


def audit(path: Path, output: Path) -> dict:
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT'],
        ])
        imports = []
        problems = []
        for kind, attribute in [('normal', 'DIRECTORY_ENTRY_IMPORT'),
                                ('delay', 'DIRECTORY_ENTRY_DELAY_IMPORT')]:
            for entry in getattr(pe, attribute, []):
                dll = entry.dll.decode('ascii', errors='replace')
                if dll.lower() in FORBIDDEN_DLLS:
                    problems.append(f'{kind}: DLL {dll}')
                functions = []
                for symbol in entry.imports:
                    name = (symbol.name.decode('ascii', errors='replace')
                            if symbol.name else f'ordinal:{symbol.ordinal}')
                    functions.append(name)
                    if name in FORBIDDEN_APIS:
                        problems.append(f'{kind}: {dll}!{name}')
                imports.append({'kind': kind, 'dll': dll, 'functions': functions})
        subsystem = (pe.OPTIONAL_HEADER.MajorSubsystemVersion,
                     pe.OPTIONAL_HEADER.MinorSubsystemVersion)
        os_version = (pe.OPTIONAL_HEADER.MajorOperatingSystemVersion,
                      pe.OPTIONAL_HEADER.MinorOperatingSystemVersion)
        if pe.FILE_HEADER.Machine != 0x8664:
            problems.append('Expected an x64 PE executable.')
        if subsystem > (6, 1):
            problems.append(f'PE subsystem version {subsystem} is greater than 6.1.')
        if os_version > (6, 1):
            problems.append(f'PE minimum OS version {os_version} is greater than 6.1.')
        report = {
            'file': path.name,
            'scope': 'Known-incompatible normal/delay imports and PE header versions only.',
            'windows_7_runtime_tested': False,
            'machine': hex(pe.FILE_HEADER.Machine),
            'subsystem_version': list(subsystem),
            'os_version': list(os_version),
            'problems': problems,
            'imports': imports,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if problems:
            raise RuntimeError('Known Windows 7 incompatibilities:\n' + '\n'.join(problems))
        return report
    finally:
        pe.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    audit(args.executable, args.output)
