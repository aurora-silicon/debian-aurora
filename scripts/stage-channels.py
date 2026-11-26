#!/usr/bin/env python3
"""Choose and check the snapshot each channel of the apt repository site serves.

    stage-channels.py --releases FILE --keyring FILE --output DIR [--testing TAG] [--nightly TAG] [--stable TAG] [--edge TAG]

deploy-pages.yml runs this before it signs anything. For each channel it tries
the given tag, then the channel's releases newest first (tags
<channel>-YYYYMMDD.N with a debian-aurora-repository.tar asset; the newest
TRIES of them), and stages the first one check-repository.py passes against the
channel's live Release file: signed for the channel, matching its indexes, and
not older than the snapshot the channel serves.

Stable changes only on request. Without --stable it stages the snapshot Stable
serves now, so that its Release file is signed again, and nothing if it serves
none. A --stable snapshot other than the served one is a promotion, which
deploy-pages.yml lets through only with the stable-promotion environment's
approval.

A given tag or newer release that fails is reported, and the next one that
passes is staged instead, so one bad release does not stop every channel being
signed again. Writes DIR/<channel>/dists/<distribution>/InRelease for each
staged channel and prints {"tags": {channel: tag}, "failed": [...],
"stable-promotion": bool} as JSON; --releases is the repository's releases as
the GitHub API lists them.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSET = 'debian-aurora-repository.tar'
TAG = re.compile(r'(?P<channel>[a-z]+)-(?P<date>[0-9]{8})\.(?P<sequence>[0-9]+)')
# Releases tried per channel after the given tag. A channel's served snapshot is
# normally its newest or next newest release.
TRIES = 10


def load_checker():
    spec = importlib.util.spec_from_file_location('check_repository', ROOT / 'scripts/check-repository.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def releases_of(releases, channel):
    """channel's release tags with a snapshot, newest first."""
    found = []
    for release in releases:
        match = TAG.fullmatch(release.get('tag_name') or '')
        if release.get('draft') or not match or match['channel'] != channel:
            continue
        if any(asset.get('name') == ASSET for asset in release.get('assets') or ()):
            found.append((int(match['date']), int(match['sequence']), match.string))
    return [tag for _, _, tag in sorted(found, reverse=True)]


def download(tag, directory):
    """The snapshot archive of release tag, downloaded into directory."""
    subprocess.run(['gh', 'release', 'download', tag, '--repo', os.environ['GITHUB_REPOSITORY'],
                    '--dir', str(directory), '--pattern', ASSET], check=True, capture_output=True, text=True)
    return directory / ASSET


def stage(channel, explicit, releases, keyring, output, download=download, floor=None):
    """Stage channel's snapshot. Returns (tag or None, check result, failures, whether Stable is promoted)."""
    try:
        served = checker.served_snapshot(floor or checker.live_floor(channel), keyring, channel)
    except SystemExit as error:
        return None, None, [f'{channel}: {error}'], False
    if channel == 'stable' and not explicit and served is None:
        return None, None, [], False
    failures = []
    candidates = ([explicit] if explicit else []) + [tag for tag in releases_of(releases, channel)[:TRIES]
                                                      if tag != explicit]
    if not candidates:
        # A channel with no releases is not served; one that is served now has lost them.
        return None, None, [] if served is None else [f'{channel}: no releases; the channel is not served'], False
    for tag in candidates:
        match = TAG.fullmatch(tag)
        if not match or match['channel'] != channel:
            failures.append(f'{channel}: {tag} is not a {channel} release tag')
            continue
        # Stable keeps what it serves unless the given tag passes; the
        # releases it is not serving are not failures.
        hold = channel == 'stable' and tag != explicit
        if hold and served is None:
            break
        with tempfile.TemporaryDirectory(prefix=f'stage-{channel}-') as work:
            try:
                archive = download(tag, Path(work))
                repository = Path(work) / 'repository'
                with tarfile.open(archive) as snapshot:
                    snapshot.extractall(repository, filter='data')
                result = checker.check(repository, channel, keyring, served=served, hold=hold)
            except subprocess.CalledProcessError as error:
                if not hold:
                    failures.append(f'{channel}: {tag}: {" ".join(error.cmd[:3])} failed: '
                                    f'{(error.stderr or "").strip()}')
                continue
            except (SystemExit, tarfile.TarError, OSError) as error:
                if not hold:
                    failures.append(f'{channel}: {tag}: {error}')
                continue
            staged = output / channel / 'dists' / result['distribution']
            staged.mkdir(parents=True)
            shutil.copy2(repository / 'dists' / result['distribution'] / 'InRelease', staged / 'InRelease')
        snapshot = checker.signer.parse_date(result['snapshot-date'], 'snapshot date')
        promoted = channel == 'stable' and not hold and (served is None or snapshot != served[1])
        return tag, result, failures, promoted
    if channel == 'stable' and served is not None:
        return None, None, failures + [f'stable: no release of the snapshot Stable serves (signed {served[0]}) '
                                       'passed; Stable is not served'], False
    return None, None, failures + [f'{channel}: no release passed; the channel is not served'], False


def stage_all(explicit, releases, keyring, output, download=download, floors=None):
    """Stage every channel; explicit and floors map channels to a given tag and a floor."""
    summary = {'tags': {}, 'failed': [], 'stable-promotion': False, 'snapshots': {}}
    for channel in checker.signer.CHANNELS:
        tag, result, failures, promoted = stage(channel, explicit.get(channel), releases, keyring, output,
                                                download, (floors or {}).get(channel))
        summary['failed'] += failures
        if tag:
            summary['tags'][channel] = tag
            summary['snapshots'][channel] = result
            summary['stable-promotion'] |= promoted
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--releases', type=Path, required=True)
    parser.add_argument('--keyring', type=Path, required=True, help='the archive key, dearmored')
    parser.add_argument('--output', type=Path, required=True)
    for channel in checker.signer.CHANNELS:
        parser.add_argument(f'--{channel}', default='', metavar='TAG', help=f'the release {channel} serves')
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f'{args.output} exists; use a new directory')
    releases = json.loads(args.releases.read_text())
    explicit = {channel: getattr(args, channel) for channel in checker.signer.CHANNELS}
    summary = stage_all(explicit, releases, args.keyring, args.output)
    for failure in summary['failed']:
        print(failure, file=sys.stderr)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
