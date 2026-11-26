#!/usr/bin/env python3
"""Verify an Aurora Debian APT repository snapshot.

    verify-repository.py --repo DIR --channel testing --keyring PATH
                         [--min-generation N] [--min-date EPOCH]
                         [--now EPOCH] [--allow-expired] [--json]

Checks the GPG signature on InRelease and Release.gpg/Release, parses only
the GPG-authenticated Release payload, enforces Origin, channel-bound
Suite/Codename (aurora-<channel>), integer Version (monotonic generation),
signed Valid-Until freshness, and SHA-256 index digests.
"""
import argparse
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import time

ORIGIN = 'Aurora Silicon'
LABEL = 'Aurora, based on Debian testing'
CHANNELS = ('testing', 'nightly', 'stable', 'edge')
DEFAULT_VALID_DAYS = {
    'testing': 7,
    'nightly': 7,
    'edge': 7,
    'stable': 14,
}
MAX_VALID_DAYS = 30
# Allow small clock skew when validating Date is not far in the future.
MAX_FUTURE_DATE_SKEW_SECONDS = 300


def suite_for_channel(channel):
    if channel not in CHANNELS:
        raise ValueError(f'unknown channel: {channel}')
    return f'aurora-{channel}'


def parse_rfc2822_utc(value, field_name):
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'invalid {field_name} timestamp: {value!r}') from exc
    if dt is None or dt.tzinfo is None:
        raise ValueError(f'{field_name} timestamp has no timezone: {value!r}')
    return int(dt.timestamp())


def parse_release_payload(text):
    """Parse RFC 822 Release headers and SHA256 file entries."""
    headers = {}
    sha256_entries = {}
    current_key = None
    in_sha256 = False

    for raw_line in text.splitlines():
        if not raw_line.strip():
            in_sha256 = False
            current_key = None
            continue
        if raw_line[0] in (' ', '\t'):
            if in_sha256:
                parts = raw_line.split()
                if len(parts) != 3:
                    raise ValueError(f'malformed SHA256 entry in Release: {raw_line!r}')
                digest, size_str, rel_path = parts
                if len(digest) != 64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
                    raise ValueError(f'invalid SHA256 digest in Release: {digest!r}')
                try:
                    size = int(size_str)
                except ValueError as exc:
                    raise ValueError(f'invalid size in Release SHA256: {size_str!r}') from exc
                if size < 0:
                    raise ValueError(f'negative size in Release SHA256: {size}')
                sha256_entries[rel_path] = (digest.lower(), size)
            elif current_key is not None and current_key not in ('MD5Sum', 'SHA1', 'SHA512'):
                headers[current_key] = headers[current_key] + ' ' + raw_line.strip()
            continue

        if ':' not in raw_line:
            raise ValueError(f'malformed Release line: {raw_line!r}')
        key, _, value = raw_line.partition(':')
        key = key.strip()
        value = value.strip()
        in_sha256 = (key == 'SHA256')
        current_key = key
        if key not in ('MD5Sum', 'SHA1', 'SHA256', 'SHA512'):
            if key in headers:
                raise ValueError(f'duplicate Release header: {key}')
            headers[key] = value

    return headers, sha256_entries


def verify_clearsigned_inrelease(inrelease_path, keyring_path):
    """Verify InRelease with gpgv and return the authenticated payload text."""
    with tempfile.TemporaryDirectory() as temporary:
        verified_path = Path(temporary) / 'Release.verified'
        result = subprocess.run(
            ['gpgv', '--keyring', str(keyring_path), '--output', str(verified_path), str(inrelease_path)],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError(f'gpgv failed for {inrelease_path}: {result.stderr.strip()}')
        if not verified_path.is_file():
            raise ValueError(f'gpgv produced no verified payload for {inrelease_path}')
        return verified_path.read_text(encoding='utf-8')


def verify_detached_release(release_path, sig_path, keyring_path):
    """Verify Release.gpg against Release with gpgv and return Release text."""
    result = subprocess.run(
        ['gpgv', '--keyring', str(keyring_path), str(sig_path), str(release_path)],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f'gpgv failed for {sig_path}: {result.stderr.strip()}')
    return release_path.read_text(encoding='utf-8')


def normalize_lines(text):
    return [line.rstrip(' \t') for line in text.replace('\r\n', '\n').splitlines()]


def validate_release_metadata(text, channel, now=None, allow_expired=False,
                              min_generation=None, min_date=None):
    """Validate authenticated Release metadata for channel, freshness and floor."""
    if now is None:
        now = int(time.time())
    expected_suite = suite_for_channel(channel)
    headers, sha256_entries = parse_release_payload(text)

    if headers.get('Origin') != ORIGIN:
        raise ValueError(f'unexpected Origin: {headers.get("Origin")!r} (expected {ORIGIN!r})')
    if headers.get('Suite') != expected_suite:
        raise ValueError(f'unexpected Suite: {headers.get("Suite")!r} (expected {expected_suite!r})')
    if headers.get('Codename') != expected_suite:
        raise ValueError(f'unexpected Codename: {headers.get("Codename")!r} (expected {expected_suite!r})')

    version_str = headers.get('Version', '')
    if not version_str.isdigit() or int(version_str) < 1:
        raise ValueError(f'invalid or missing monotonic Version header: {version_str!r}')
    generation = int(version_str)

    date_str = headers.get('Date')
    if not date_str:
        raise ValueError('missing Date header in Release')
    date_epoch = parse_rfc2822_utc(date_str, 'Date')
    if date_epoch > now + MAX_FUTURE_DATE_SKEW_SECONDS:
        raise ValueError(f'Release Date is in the future: {date_str}')

    valid_until_str = headers.get('Valid-Until')
    if not valid_until_str:
        raise ValueError('missing Valid-Until header in Release')
    valid_until_epoch = parse_rfc2822_utc(valid_until_str, 'Valid-Until')

    if valid_until_epoch <= date_epoch:
        raise ValueError(f'Valid-Until ({valid_until_str}) must be after Date ({date_str})')
    if valid_until_epoch - date_epoch > MAX_VALID_DAYS * 86400:
        raise ValueError(
            f'Valid-Until span exceeds maximum {MAX_VALID_DAYS} days: '
            f'{valid_until_epoch - date_epoch}s')
    if not allow_expired and valid_until_epoch <= now:
        raise ValueError(f'Release has expired: Valid-Until {valid_until_str}')

    if min_generation is not None and generation < min_generation:
        raise ValueError(
            f'Release generation {generation} is below required floor {min_generation}')
    if min_date is not None and date_epoch < min_date:
        raise ValueError(
            f'Release Date {date_str} ({date_epoch}) is below required floor {min_date}')

    return {
        'channel': channel,
        'origin': headers['Origin'],
        'label': headers.get('Label', ''),
        'suite': headers['Suite'],
        'codename': headers['Codename'],
        'generation': generation,
        'date': date_str,
        'date_epoch': date_epoch,
        'valid_until': valid_until_str,
        'valid_until_epoch': valid_until_epoch,
        'sha256_entries': sha256_entries,
    }


def _safe_rel_path(base_dir, rel_path):
    posix = PurePosixPath(rel_path)
    if posix.is_absolute() or '..' in posix.parts:
        raise ValueError(f'unsafe path in Release SHA256: {rel_path!r}')
    resolved = (base_dir / rel_path).resolve()
    base_resolved = base_dir.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError(f'path escapes dists directory: {rel_path!r}')
    return resolved


def verify_repository(repo_dir, channel, keyring_path, now=None, allow_expired=False,
                      min_generation=None, min_date=None):
    """Verify an assembled APT repository directory for a specific channel."""
    repo_dir = Path(repo_dir)
    keyring_path = Path(keyring_path)
    if not keyring_path.is_file():
        raise ValueError(f'keyring not found: {keyring_path}')

    expected_suite = suite_for_channel(channel)
    dists_root = repo_dir / 'dists'
    if not dists_root.is_dir():
        raise ValueError(f'missing dists directory in {repo_dir}')

    suites_present = sorted(p.name for p in dists_root.iterdir())
    if suites_present != [expected_suite]:
        raise ValueError(
            f'unexpected suites in {dists_root}: {suites_present} (expected [{expected_suite!r}])')

    dists = dists_root / expected_suite
    inrelease = dists / 'InRelease'
    release = dists / 'Release'
    release_gpg = dists / 'Release.gpg'
    for required in (inrelease, release, release_gpg):
        if not required.is_file():
            raise ValueError(f'missing required metadata file: {required}')

    verified_inrelease = verify_clearsigned_inrelease(inrelease, keyring_path)
    verified_release = verify_detached_release(release, release_gpg, keyring_path)
    if normalize_lines(verified_inrelease) != normalize_lines(verified_release):
        raise ValueError('InRelease payload does not match detached Release file')

    meta = validate_release_metadata(
        verified_inrelease,
        channel=channel,
        now=now,
        allow_expired=allow_expired,
        min_generation=min_generation,
        min_date=min_date,
    )

    sha256_entries = meta.pop('sha256_entries')
    if not sha256_entries:
        raise ValueError('Release SHA256 index table is empty')

    required_indexes = (
        'main/binary-arm64/Packages',
        'main/binary-arm64/Packages.xz',
        'main/binary-all/Packages',
        'main/binary-all/Packages.xz',
    )
    for req in required_indexes:
        if req not in sha256_entries:
            raise ValueError(f'missing required index in Release SHA256: {req}')

    for rel_path, (expected_digest, expected_size) in sha256_entries.items():
        if rel_path == 'Release':
            continue
        target = _safe_rel_path(dists, rel_path)
        if not target.is_file():
            raise ValueError(f'file listed in Release is missing: {rel_path}')
        data = target.read_bytes()
        if len(data) != expected_size:
            raise ValueError(f'size mismatch for {rel_path}: {len(data)} != {expected_size}')
        actual_digest = hashlib.sha256(data).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(f'SHA256 mismatch for {rel_path}: {actual_digest} != {expected_digest}')

    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--channel', choices=CHANNELS, required=True)
    parser.add_argument('--keyring', type=Path, required=True)
    parser.add_argument('--now', type=int, default=None)
    parser.add_argument('--min-generation', type=int, default=None)
    parser.add_argument('--min-date', type=int, default=None)
    parser.add_argument('--allow-expired', action='store_true')
    parser.add_argument('--json', action='store_true', dest='as_json')
    args = parser.parse_args()

    try:
        meta = verify_repository(
            args.repo,
            channel=args.channel,
            keyring_path=args.keyring,
            now=args.now,
            allow_expired=args.allow_expired,
            min_generation=args.min_generation,
            min_date=args.min_date,
        )
    except ValueError as exc:
        sys.exit(f'verify-repository: {exc}')

    if args.as_json:
        print(json.dumps(meta, sort_keys=True))
    else:
        print(
            f"{args.repo}: verified suite={meta['suite']} generation={meta['generation']} "
            f"date={meta['date']} valid_until={meta['valid_until']}")


if __name__ == '__main__':
    main()
