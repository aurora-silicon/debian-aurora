#!/usr/bin/env python3
"""Assemble, sign and verify the apt repository of Aurora's Debian testing packages.

    sign-repository.py --packages DIR --output DIR --channel testing
                       [--valid-days N] [--generation N] [--min-generation N]
                       [--production]

Each channel has its own signed suite and codename (`aurora-<channel>`), with
component `main` (arm64 and all), served at
https://aurorasilicon.org/debian-aurora/<channel>. Every signed Release carries
a bounded `Valid-Until` freshness deadline and a strictly positive integer
`Version` acting as the channel's monotonic generation.

The signing key is the one gpg finds in GNUPGHOME (the CI secret, or the local
development key from scripts/dev-signing-key). --production refuses a key
other than the one in keys/fingerprint.txt and a keyring package that carries
the development key.
"""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        'verify_repository', Path(__file__).resolve().with_name('verify-repository.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verifier = _load_verifier()
ORIGIN = _verifier.ORIGIN
LABEL = _verifier.LABEL
CHANNELS = _verifier.CHANNELS
DEFAULT_VALID_DAYS = _verifier.DEFAULT_VALID_DAYS
MAX_VALID_DAYS = _verifier.MAX_VALID_DAYS
suite_for_channel = _verifier.suite_for_channel


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def signing_fingerprint():
    listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'], text=True)
    fingerprints = [line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:')]
    if len(fingerprints) < 1:
        raise SystemExit('no signing key in GNUPGHOME')
    return fingerprints[0]


def check_production(fingerprint, packages):
    expected = (ROOT / 'keys/fingerprint.txt')
    if not expected.is_file() or expected.read_text().split()[0] != fingerprint:
        raise SystemExit('the signing key is not the production key in keys/fingerprint.txt')
    for deb in packages.glob('aurora-archive-keyring_*.deb'):
        contents = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(deb)])
        keyring = subprocess.run(['tar', '-xO', '-f', '-', './usr/share/keyrings/aurora-archive-keyring.gpg'],
                                 input=contents, capture_output=True, check=True).stdout
        # The user ID scripts/dev-signing-key gives the development key.
        if b'Aurora Debian development key' in keyring:
            raise SystemExit(f'{deb.name} carries the development key')


def resolve_generation(generation, min_generation):
    if min_generation is not None and min_generation < 0:
        raise SystemExit(f'--min-generation must be non-negative (got {min_generation})')
    if generation is None:
        resolved = int(time.time())
        if min_generation is not None and resolved <= min_generation:
            resolved = min_generation + 1
    else:
        resolved = generation
        if resolved < 1:
            raise SystemExit(f'--generation must be a positive integer (got {resolved})')
        if min_generation is not None and resolved <= min_generation:
            raise SystemExit(
                f'--generation {resolved} must be strictly greater than --min-generation {min_generation}')
    return resolved


def assemble(packages, output, channel, valid_days=None, generation=None):
    if valid_days is None:
        valid_days = DEFAULT_VALID_DAYS[channel]
    if valid_days < 1 or valid_days > MAX_VALID_DAYS:
        raise SystemExit(f'--valid-days must be between 1 and {MAX_VALID_DAYS} (got {valid_days})')
    if generation is None:
        generation = int(time.time())
    if generation < 1:
        raise SystemExit(f'--generation must be a positive integer (got {generation})')

    suite = suite_for_channel(channel)
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
    dists = output / 'dists' / suite
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
        '-o', f'APT::FTPArchive::Release::Suite={suite}',
        '-o', f'APT::FTPArchive::Release::Codename={suite}',
        '-o', f'APT::FTPArchive::Release::Version={generation}',
        '-o', f'APT::FTPArchive::Release::ValidTime={valid_days * 86400}',
        '-o', 'APT::FTPArchive::Release::Architectures=arm64 all',
        '-o', 'APT::FTPArchive::Release::Components=main',
        '-o', f'APT::FTPArchive::Release::Description=Aurora packages for Debian testing ({channel} channel)',
        'release', '.'], cwd=dists)
    (dists / 'Release').write_bytes(release)
    return dists


def sign(dists, fingerprint):
    common = ['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--local-user', fingerprint]
    passphrase = os.environ.get('DEBIAN_SIGNING_PASSPHRASE', '')
    common += ['--passphrase-fd', '0']
    run(common + ['--clearsign', '--output', str(dists / 'InRelease'), str(dists / 'Release')],
        input=passphrase.encode())
    run(common + ['--armor', '--detach-sign', '--output', str(dists / 'Release.gpg'), str(dists / 'Release')],
        input=passphrase.encode())


def verify(output, channel, fingerprint):
    with tempfile.TemporaryDirectory() as temporary:
        keyring = Path(temporary) / 'keyring.gpg'
        exported = subprocess.check_output(['gpg', '--batch', '--export', fingerprint])
        keyring.write_bytes(exported)
        try:
            return _verifier.verify_repository(output, channel=channel, keyring_path=keyring)
        except ValueError as exc:
            raise SystemExit(f'repository verification failed: {exc}') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--channel', choices=CHANNELS, required=True)
    parser.add_argument('--valid-days', type=int, default=None)
    parser.add_argument('--generation', type=int, default=None)
    parser.add_argument('--min-generation', type=int, default=None)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f'{args.output} exists; use a new directory')
    valid_days = DEFAULT_VALID_DAYS[args.channel] if args.valid_days is None else args.valid_days
    generation = resolve_generation(args.generation, args.min_generation)
    fingerprint = signing_fingerprint()
    if args.production:
        check_production(fingerprint, args.packages)
    dists = assemble(args.packages, args.output, args.channel,
                     valid_days=valid_days, generation=generation)
    sign(dists, fingerprint)
    meta = verify(args.output, args.channel, fingerprint)
    print(
        f"{args.output}: suite {meta['suite']}, channel {args.channel}, "
        f"generation {meta['generation']}, valid-until {meta['valid_until']}, "
        f"signed by {fingerprint}")


if __name__ == '__main__':
    main()
