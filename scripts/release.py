#!/usr/bin/env python3
"""Check for a newer stable Node 24 release, or publish the built packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


API = 'https://api.github.com'
UPLOADS = 'https://uploads.github.com'
NODE_INDEX = 'https://nodejs.org/dist/index.json'
VERSION = re.compile(r'v?(24)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
MARKER = '<!-- node24-win7-daily-release -->'


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    return tuple(map(int, match.groups())) if match else None


def version_text(value: tuple[int, int, int]) -> str:
    return '.'.join(map(str, value))


def request_json(url: str, *, token: str = '', method: str = 'GET',
                 payload: dict | None = None, binary: bytes | None = None,
                 allow_missing: bool = False):
    headers = {'User-Agent': 'node24-win7-release', 'Accept': 'application/vnd.github+json'}
    if token:
        if urllib.parse.urlsplit(url).hostname not in ['api.github.com', 'uploads.github.com']:
            raise RuntimeError('Refusing to send a GitHub token outside GitHub API hosts.')
        headers['Authorization'] = f'Bearer {token}'
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    data = binary
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    elif binary is not None:
        headers['Content-Type'] = 'application/octet-stream'
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180 if binary is not None else 45) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        details = error.read().decode('utf-8', errors='replace')[:2000]
        raise RuntimeError(f'{method} {url}: HTTP {error.code}: {details}') from error


def pages(path: str, token: str) -> list[dict]:
    rows = []
    page = 1
    while True:
        batch = request_json(f'{API}{path}?per_page=100&page={page}', token=token)
        if not isinstance(batch, list):
            raise RuntimeError(f'Expected a list from {path}')
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def repository_version(releases: list[dict], tags: list[dict]) -> tuple[int, int, int] | None:
    # A draft left by a failed upload must not suppress the next retry.
    excluded_tags = {r['tag_name'] for r in releases if r['draft'] or r['prerelease']}
    names = [r['tag_name'] for r in releases if not r['draft'] and not r['prerelease']]
    names += [t['name'] for t in tags if t['name'] not in excluded_tags]
    versions = [parsed for name in names if (parsed := version_tuple(name)) is not None]
    return max(versions) if versions else None


def node_commit(version: str, token: str) -> str:
    ref = request_json(f'{API}/repos/nodejs/node/git/ref/tags/v{version}', token=token)['object']
    for _ in range(8):
        if not SHA.fullmatch(ref['sha']):
            raise RuntimeError('Invalid upstream commit/tag SHA.')
        if ref['type'] == 'commit':
            return ref['sha']
        if ref['type'] != 'tag':
            break
        ref = request_json(f'{API}/repos/nodejs/node/git/tags/{ref["sha"]}', token=token)['object']
    raise RuntimeError('Could not resolve the official Node release tag to a commit.')


def output(values: dict[str, str]) -> None:
    if filename := os.environ.get('GITHUB_OUTPUT'):
        with open(filename, 'a', encoding='utf-8') as handle:
            for key, value in values.items():
                if '\n' in value or '\r' in value:
                    raise RuntimeError('Invalid multiline workflow output.')
                handle.write(f'{key}={value}\n')


def summary(message: str) -> None:
    print(message, flush=True)
    if filename := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(filename, 'a', encoding='utf-8') as handle:
            handle.write(message + '\n\n')


def check(repository: str, token: str) -> None:
    index = request_json(NODE_INDEX)
    candidates = [parsed for row in index
                  if (parsed := version_tuple(row.get('version', ''))) is not None]
    if not candidates:
        raise RuntimeError('The official distribution index contains no stable Node 24 version.')
    latest = max(candidates)
    current = repository_version(pages(f'/repos/{repository}/releases', token),
                                 pages(f'/repos/{repository}/tags', token))
    version = version_text(latest)
    needed = current is None or latest > current
    values = {'needs_build': str(needed).lower(), 'version': version,
              'repository_version': version_text(current) if current else 'none',
              'node_commit': node_commit(version, token) if needed else ''}
    output(values)
    summary(f'## Node 24 update check\n\nOfficial stable: **{version}**  \n'
            f'Repository stable release/tag: **{values["repository_version"]}**  \n'
            + ('A newer version is available; starting the Windows build.' if needed
               else 'No newer stable version. Finished without starting a Windows build.'))


def publish(repository: str, token: str, version: str, directory: Path) -> None:
    if version_tuple(version) is None or version.startswith('v'):
        raise RuntimeError('Expected a stable version such as 24.22.1, without a v prefix.')
    target = os.environ.get('GITHUB_SHA', '')
    source = os.environ.get('NODE_COMMIT', '')
    if not SHA.fullmatch(target) or not SHA.fullmatch(source):
        raise RuntimeError('Missing or invalid workflow/source commit SHA.')
    filenames = [f'node-v{version}-win7-x64.msi', f'node-v{version}-win7-x64.zip', 'SHASUMS256.txt']
    files = [directory / name for name in filenames]
    for file in files:
        if not file.is_file() or not file.stat().st_size:
            raise RuntimeError(f'Missing or empty release asset: {file}')
    expected = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                for name in filenames[:2]}
    checksums = {line.split(maxsplit=1)[1].strip().lstrip('*'): line.split()[0]
                 for line in files[2].read_text(encoding='utf-8-sig').splitlines() if line.strip()}
    if any(checksums.get(name) != digest for name, digest in expected.items()):
        raise RuntimeError('Release package checksums do not match SHASUMS256.txt.')

    base = f'/repos/{repository}/releases'
    release = request_json(f'{API}{base}/tags/{version}', token=token, allow_missing=True)
    if release and not release['draft']:
        # Never recreate or overwrite the user's existing published releases.
        summary(f'Release **{version}** already exists and was left unchanged: {release["html_url"]}')
        return
    if release and MARKER not in (release.get('body') or ''):
        raise RuntimeError('An unrelated draft release already uses this tag; leaving it unchanged.')

    run_url = f'https://github.com/{repository}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    title = f'{version}'
    notes = (f'{MARKER}\nWindows 7 build of Node.js v{version}.\n\n'
             f'- Official Node source commit: `{source}`\n'
             '- Includes the MSI installer, portable ZIP, and SHA-256 checksums.\n'
             f'- Build [results]({run_url})')
    if release is None:
        release = request_json(f'{API}{base}', token=token, method='POST', payload={
            'tag_name': version, 'target_commitish': target, 'name': title,
            'body': notes, 'draft': True, 'prerelease': False,
        })
    release_id = release['id']
    assets = {asset['name']: asset for asset in release.get('assets', [])}
    for file in files:
        # Only this workflow's own draft assets may be replaced on a retry.
        if file.name in assets:
            request_json(f'{API}{base}/assets/{assets[file.name]["id"]}', token=token, method='DELETE')
        request_json(f'{UPLOADS}{base}/{release_id}/assets?name={urllib.parse.quote(file.name)}',
                     token=token, method='POST', binary=file.read_bytes())
        print(f'Uploaded release asset: {file.name}', flush=True)
    uploaded = request_json(f'{API}{base}/{release_id}', token=token)
    sizes = {asset['name']: asset['size'] for asset in uploaded['assets']}
    if any(sizes.get(file.name) != file.stat().st_size for file in files):
        raise RuntimeError('Release asset upload did not complete; keeping the release as a draft.')
    release = request_json(f'{API}{base}/{release_id}', token=token, method='PATCH', payload={
        'name': title, 'body': notes, 'draft': False, 'prerelease': False,
    })
    output({'release_url': release['html_url']})
    summary(f'## Release published\n\n[{version}: MSI, ZIP and SHA-256 checksums]({release["html_url"]})'
            '\n\nThe package verification step runs after publication.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'publish'])
    parser.add_argument('--version')
    parser.add_argument('--directory', type=Path, default=Path('dist'))
    args = parser.parse_args()
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not token:
        raise SystemExit('GITHUB_REPOSITORY and a repository-scoped GitHub token are required.')
    if args.action == 'check':
        check(repository, token)
    else:
        publish(repository, token, args.version or '', args.directory)


if __name__ == '__main__':
    main()
