#!/usr/bin/env python3
"""Check a signed snapshot of the apt repository before it is served for a channel.

    check-repository.py --repository DIR --channel testing --keyring FILE [--fresh] [--floor URL|FILE]

Refuses the snapshot unless:
- InRelease and Release.gpg verify with the keyring and sign the same Release;
- its only distribution is the channel's, and every signed identity field
  (Origin, Label, Suite, Codename, Description) names the channel;
- every index Release lists that is present matches it;
- with --fresh, its Release file is valid for most of scripts/sign-repository.py's
  VALID_FOR still;
- with --floor, its packages were signed no earlier than those of the Release
  file at --floor (by default the channel's live one), so a deployment never
  rolls a channel back. A floor that is not there (HTTP 404) sets no bound.

Prints the channel, distribution, snapshot date and validity as JSON.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load_signer():
    spec = importlib.util.spec_from_file_location('sign_repository', ROOT / 'scripts/sign-repository.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


signer = load_signer()


def read_floor(floor, channel):
    """The signed InRelease at floor (a URL or a file), or None when the URL answers 404."""
    if '://' not in floor:
        return Path(floor).read_bytes()
    if not floor.startswith('https://'):
        raise SystemExit(f'refusing a floor that is not https: {floor}')
    try:
        with urllib.request.urlopen(floor, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise SystemExit(f'cannot read the {channel} channel\'s live Release file {floor}: {error}')
    except urllib.error.URLError as error:
        raise SystemExit(f'cannot read the {channel} channel\'s live Release file {floor}: {error}')


def floor_date(signed, keyring, channel):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'InRelease'
        path.write_bytes(signed)
        output = Path(temporary) / 'Release'
        signer.gpgv(keyring, '--output', output, path)
        fields = signer.parse_release(output.read_text())
    signer.check_identity(fields, channel)
    return signer.snapshot_date(fields)


def check(repository, channel, keyring, fresh=False, floor=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    dist = signer.distribution(channel)
    found = sorted(path.name for path in (repository / 'dists').iterdir()) if (repository / 'dists').is_dir() else []
    if found != [dist]:
        raise SystemExit(f'{repository} has distributions {found}; the {channel} channel serves only {dist}')
    dists = repository / 'dists' / dist
    release = signer.verified_release(dists, keyring)
    fields = signer.parse_release(release)
    signer.check_identity(fields, channel)
    signer.check_indexes(dists, release)
    signed_at, snapshot = signer.snapshot_date(fields)
    valid_until = None
    if 'Valid-Until' in fields:
        valid_until = signer.parse_date(fields['Valid-Until'], 'Valid-Until')
    if fresh:
        if valid_until is None:
            raise SystemExit(f'the {channel} Release file has no Valid-Until')
        if valid_until - now < signer.VALID_FOR - datetime.timedelta(days=1):
            raise SystemExit(f'the {channel} Release file is valid only until {fields["Valid-Until"]}; '
                             'it has to be signed again')
        if signer.parse_date(fields['Date'], 'Date') > now + datetime.timedelta(minutes=10):
            raise SystemExit(f'the {channel} Release file is dated in the future: {fields["Date"]}')
    if floor:
        signed = read_floor(floor, channel)
        if signed is not None:
            served_at, served = floor_date(signed, keyring, channel)
            if snapshot < served:
                raise SystemExit(f'the {channel} snapshot signed {signed_at} is older than the one served, '
                                 f'signed {served_at}; a channel does not roll back')
    return {'channel': channel, 'distribution': dist, 'snapshot-date': signed_at,
            'valid-until': fields.get('Valid-Until')}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--channel', choices=signer.CHANNELS, required=True)
    parser.add_argument('--keyring', type=Path, required=True, help='the archive key, dearmored')
    parser.add_argument('--fresh', action='store_true', help='require a freshly signed Release file')
    parser.add_argument('--floor', nargs='?', const='live',
                        help="the InRelease the snapshot may not be older than (a URL or file; default the "
                             "channel's live one)")
    args = parser.parse_args()
    floor = args.floor
    if floor == 'live':
        floor = f'{signer.PAGES}/{args.channel}/dists/{signer.distribution(args.channel)}/InRelease'
    try:
        result = check(args.repository, args.channel, args.keyring, args.fresh, floor)
    except subprocess.CalledProcessError as error:
        sys.exit(f'{" ".join(map(str, error.cmd))} failed:\n{(error.stderr or b"").decode(errors="replace")}')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
