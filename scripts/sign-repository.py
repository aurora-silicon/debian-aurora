#!/usr/bin/env python3
"""Assemble, sign and verify the apt repository of Aurora's Debian testing packages.

    sign-repository.py --packages DIR --output DIR --channel testing [--production]
    sign-repository.py --refresh DIR --output DIR --channel testing [--production]

The repository has component `main` (arm64 and all) and one distribution per
channel, served at https://aurorasilicon.org/debian-aurora/<channel>: `aurora`
for Testing, which its installed systems already follow, and `aurora-<channel>`
for the others. The distribution is the signed Suite and Codename, so a
Release file signed for one channel does not pass as another's, and apt
refuses a Codename that changes under a system that already follows a channel.

Each Release file is valid for seven days (Valid-Until) and carries the date
its packages were signed (Aurora-Snapshot-Date). --refresh re-signs the
Release file of a signed snapshot of the same channel with a new Date and
Valid-Until and nothing else changed; the Pages workflow does that daily for
every channel it serves.

The signing key is the one gpg finds in GNUPGHOME (the CI secret, or the
local development key from scripts/dev-signing-key). --production refuses a
key other than the one in keys/fingerprint.txt and a keyring package that
carries the development key.
"""
import argparse
import datetime
import email.utils
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'Aurora Silicon'
LABEL = 'Aurora, based on Debian testing'
SUITE = 'aurora'
CHANNELS = ('testing', 'nightly', 'stable', 'edge')
# How long a signed Release file is valid. apt stops taking updates from a
# channel whose Release file has expired instead of trusting an old one
# indefinitely; the Pages workflow re-signs every channel daily.
VALID_FOR = datetime.timedelta(days=7)
# The date a snapshot's packages were signed. A refresh keeps it, so it orders
# snapshots where Date only says when the Release file was last signed.
SNAPSHOT_DATE = 'Aurora-Snapshot-Date'
PAGES = 'https://aurorasilicon.org/debian-aurora'


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def gpgv(keyring, *args):
    """Run gpgv with keyring; a refusal is an error that says which file and why."""
    result = subprocess.run(['gpgv', '--keyring', str(keyring), *map(str, args)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'gpgv refused {args[-1]}:\n{result.stderr.strip()}')


def distribution(channel):
    """The Suite and Codename of a channel's Release file, and its directory under dists/."""
    if channel not in CHANNELS:
        raise SystemExit(f'unknown channel {channel}')
    return SUITE if channel == 'testing' else f'{SUITE}-{channel}'


def description(channel):
    return f'Aurora packages for Debian testing ({channel} channel)'


def format_date(when):
    return email.utils.format_datetime(when.astimezone(datetime.timezone.utc).replace(microsecond=0))


def parse_date(text, field):
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        when = None
    if when is None or when.tzinfo is None:
        raise SystemExit(f'Release file has an invalid {field}: {text!r}')
    return when


def parse_release(text):
    """The single-line fields of a Release file (the hash lists are left out)."""
    fields = {}
    for line in text.splitlines():
        if not line or line[0].isspace():
            continue
        name, separator, value = line.partition(':')
        if not separator:
            raise SystemExit(f'malformed Release line: {line!r}')
        if name in fields:
            raise SystemExit(f'Release file repeats {name}')
        fields[name] = value.strip()
    return fields


def stamp(release, now, snapshot_date):
    """release with Date now, Valid-Until VALID_FOR later and Aurora-Snapshot-Date snapshot_date."""
    dates = (f'Date: {format_date(now)}', f'Valid-Until: {format_date(now + VALID_FOR)}',
             f'{SNAPSHOT_DATE}: {snapshot_date}')
    lines = [line for line in release.splitlines()
             if line.split(':', 1)[0] not in ('Date', 'Valid-Until', SNAPSHOT_DATE) or line[:1].isspace()]
    # Single-line fields come before the hash lists, whose own line has no value.
    first_list = next((index for index, line in enumerate(lines) if re.fullmatch(r'[A-Za-z0-9-]+:\s*', line)),
                      len(lines))
    return '\n'.join(lines[:first_list] + list(dates) + lines[first_list:]) + '\n'


def snapshot_date(fields):
    """When the snapshot's packages were signed; Date for a snapshot signed before the field existed."""
    text = fields.get(SNAPSHOT_DATE) or fields.get('Date', '')
    return text, parse_date(text, SNAPSHOT_DATE if SNAPSHOT_DATE in fields else 'Date')


def check_identity(fields, channel):
    """Refuse a Release file that does not name channel in every signed identity field."""
    expected = {'Origin': ORIGIN, 'Label': LABEL, 'Suite': distribution(channel),
                'Codename': distribution(channel), 'Description': description(channel)}
    for name, value in expected.items():
        if fields.get(name) != value:
            raise SystemExit(f'Release {name} is {fields.get(name)!r}, not {value!r} of the {channel} channel')


def verified_release(dists, keyring):
    """The Release text InRelease signs, checked against Release and Release.gpg too."""
    with tempfile.TemporaryDirectory() as temporary:
        signed = Path(temporary) / 'Release'
        gpgv(keyring, '--output', signed, dists / 'InRelease')
        text = signed.read_text()
    gpgv(keyring, dists / 'Release.gpg', dists / 'Release')
    if (dists / 'Release').read_text().rstrip('\n') != text.rstrip('\n'):
        raise SystemExit(f'{dists}/Release differs from the text InRelease signs')
    return text


def check_indexes(dists, release):
    """Every index Release lists under SHA256 that exists matches it; at least one exists."""
    sums = release.split('\nSHA256:\n', 1)
    if len(sums) != 2:
        raise SystemExit('Release has no SHA256 list')
    present = 0
    for line in sums[1].splitlines():
        parts = line.split()
        if len(parts) != 3 or not line.startswith(' '):
            break
        digest, size, name = parts
        path = dists / name
        if '..' in Path(name).parts or name.startswith('/'):
            raise SystemExit(f'Release names {name} outside its directory')
        if not path.exists():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest or path.stat().st_size != int(size):
            raise SystemExit(f'{name} does not match Release')
        present += 1
    if present == 0:
        raise SystemExit(f'none of the indexes Release lists is in {dists}')


def signing_fingerprint():
    listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'], text=True)
    fingerprints = [line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:')]
    if len(fingerprints) < 1:
        raise SystemExit('no signing key in GNUPGHOME')
    return fingerprints[0]


def check_production(fingerprint, packages=None):
    expected = (ROOT / 'keys/fingerprint.txt')
    if not expected.is_file() or expected.read_text().split()[0] != fingerprint:
        raise SystemExit('the signing key is not the production key in keys/fingerprint.txt')
    for deb in packages.glob('aurora-archive-keyring_*.deb') if packages else ():
        contents = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(deb)])
        keyring = subprocess.run(['tar', '-xO', '-f', '-', './usr/share/keyrings/aurora-archive-keyring.gpg'],
                                 input=contents, capture_output=True, check=True).stdout
        # The user ID scripts/dev-signing-key gives the development key.
        if b'Aurora Debian development key' in keyring:
            raise SystemExit(f'{deb.name} carries the development key')


def assemble(packages, output, channel, now):
    pool = output / 'pool/main'
    pool.mkdir(parents=True)
    debs = sorted(p for p in packages.glob('*.deb') if not p.name.endswith('-dbgsym.deb')
                  and '-dbgsym_' not in p.name)
    if not debs:
        raise SystemExit(f'no packages in {packages}')
    seen = {}
    for deb in debs:
        fields = subprocess.check_output(['dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture'],
                                         text=True)
        key = tuple(line.split(': ', 1)[1] for line in fields.splitlines())
        digest = hashlib.sha256(deb.read_bytes()).hexdigest()
        if key in seen and seen[key] != digest:
            raise SystemExit(f'conflicting builds of {key}')
        seen[key] = digest
        shutil.copy2(deb, pool / deb.name)
    dists = output / 'dists' / distribution(channel)
    for arch in ('arm64', 'all'):
        binary = dists / 'main' / f'binary-{arch}'
        binary.mkdir(parents=True)
        index = subprocess.check_output(['apt-ftparchive', '--arch', arch, 'packages', 'pool/main'],
                                        cwd=output)
        (binary / 'Packages').write_bytes(index)
        run(['xz', '-k', '-9', str(binary / 'Packages')])
    release = subprocess.check_output([
        'apt-ftparchive',
        '-o', f'APT::FTPArchive::Release::Origin={ORIGIN}',
        '-o', f'APT::FTPArchive::Release::Label={LABEL}',
        '-o', f'APT::FTPArchive::Release::Suite={distribution(channel)}',
        '-o', f'APT::FTPArchive::Release::Codename={distribution(channel)}',
        '-o', 'APT::FTPArchive::Release::Architectures=arm64 all',
        '-o', 'APT::FTPArchive::Release::Components=main',
        '-o', f'APT::FTPArchive::Release::Description={description(channel)}',
        'release', '.'], cwd=dists, text=True)
    (dists / 'Release').write_text(stamp(release, now, format_date(now)))
    return dists


def refresh(snapshot, output, channel, fingerprint, now):
    """Re-sign the Release file of snapshot, a signed snapshot of channel, with a new Date and Valid-Until."""
    source = snapshot / 'dists' / distribution(channel)
    with tempfile.TemporaryDirectory() as temporary:
        keyring = Path(temporary) / 'keyring.gpg'
        keyring.write_bytes(subprocess.check_output(['gpg', '--batch', '--export', fingerprint]))
        with tempfile.TemporaryDirectory() as unpacked:
            signed = Path(unpacked) / 'Release'
            gpgv(keyring, '--output', signed, source / 'InRelease')
            release = signed.read_text()
    fields = parse_release(release)
    check_identity(fields, channel)
    signed_at, _ = snapshot_date(fields)
    dists = output / 'dists' / distribution(channel)
    dists.mkdir(parents=True)
    (dists / 'Release').write_text(stamp(release, now, signed_at))
    return dists


def sign(dists, fingerprint):
    common = ['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--local-user', fingerprint]
    passphrase = os.environ.get('DEBIAN_SIGNING_PASSPHRASE', '')
    common += ['--passphrase-fd', '0']
    run(common + ['--clearsign', '--output', str(dists / 'InRelease'), str(dists / 'Release')],
        input=passphrase.encode())
    run(common + ['--armor', '--detach-sign', '--output', str(dists / 'Release.gpg'), str(dists / 'Release')],
        input=passphrase.encode())


def verify(dists, fingerprint, channel, indexes=True):
    with tempfile.TemporaryDirectory() as temporary:
        keyring = Path(temporary) / 'keyring.gpg'
        keyring.write_bytes(subprocess.check_output(['gpg', '--batch', '--export', fingerprint]))
        release = verified_release(dists, keyring)
    check_identity(parse_release(release), channel)
    if indexes:
        check_indexes(dists, release)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--packages', type=Path, help='the .deb files of a new snapshot')
    source.add_argument('--refresh', type=Path, metavar='SNAPSHOT',
                        help='a signed snapshot (at least dists/<distribution>/InRelease) to re-sign')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--channel', choices=CHANNELS, required=True)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f'{args.output} exists; use a new directory')
    fingerprint = signing_fingerprint()
    if args.production:
        check_production(fingerprint, args.packages)
    now = datetime.datetime.now(datetime.timezone.utc)
    if args.packages:
        dists = assemble(args.packages, args.output, args.channel, now)
    else:
        dists = refresh(args.refresh, args.output, args.channel, fingerprint, now)
    sign(dists, fingerprint)
    verify(dists, fingerprint, args.channel, indexes=bool(args.packages))
    print(f'{args.output}: {distribution(args.channel)} for the {args.channel} channel, valid until '
          f'{format_date(now + VALID_FOR)}, signed by {fingerprint}')


if __name__ == '__main__':
    main()
