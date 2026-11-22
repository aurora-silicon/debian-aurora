#!/usr/bin/env python3
"""Assemble, sign and verify the apt repository of Aurora's Debian testing packages.

    sign-repository.py --packages DIR --output DIR --channel testing [--production]

The repository has one suite, `aurora`, with component `main` (arm64 and
all), served at https://aurorasilicon.org/debian-aurora/<channel>. The
signing key is the one gpg finds in GNUPGHOME (the CI secret, or the local
development key from scripts/dev-signing-key). --production refuses a key
other than the one in keys/fingerprint.txt and a keyring package that carries
the development key.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'Aurora Silicon'
LABEL = 'Aurora, based on Debian testing'
SUITE = 'aurora'
CHANNELS = ('testing', 'stable', 'edge')


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


def assemble(packages, output, channel):
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
    dists = output / 'dists' / SUITE
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
        '-o', f'APT::FTPArchive::Release::Suite={SUITE}',
        '-o', f'APT::FTPArchive::Release::Codename={SUITE}',
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


def verify(output, dists, fingerprint):
    with tempfile.TemporaryDirectory() as temporary:
        keyring = Path(temporary) / 'keyring.gpg'
        exported = subprocess.check_output(['gpg', '--batch', '--export', fingerprint])
        keyring.write_bytes(exported)
        for args in ([str(dists / 'InRelease')], [str(dists / 'Release.gpg'), str(dists / 'Release')]):
            run(['gpgv', '--keyring', str(keyring), *args], capture_output=True)
    # Every index digest in Release matches the file it names.
    release = (dists / 'Release').read_text().split('SHA256:')[1]
    for line in release.strip().splitlines():
        parts = line.split()
        if len(parts) != 3 or not line.startswith(' '):
            break
        digest, size, name = parts
        path = dists / name
        if path.exists() and (hashlib.sha256(path.read_bytes()).hexdigest() != digest
                              or path.stat().st_size != int(size)):
            raise SystemExit(f'{name} does not match Release')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--channel', choices=CHANNELS, required=True)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f'{args.output} exists; use a new directory')
    fingerprint = signing_fingerprint()
    if args.production:
        check_production(fingerprint, args.packages)
    dists = assemble(args.packages, args.output, args.channel)
    sign(dists, fingerprint)
    verify(args.output, dists, fingerprint)
    print(f'{args.output}: suite {SUITE}, channel {args.channel}, signed by {fingerprint}')


if __name__ == '__main__':
    main()
