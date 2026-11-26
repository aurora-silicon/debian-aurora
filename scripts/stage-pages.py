#!/usr/bin/env python3
"""Verify and stage signed APT snapshot tarballs for GitHub Pages deployment.

    stage-pages.py --keyring PATH --fingerprint FPR --site DIR
                   --channels-json PATH [--allow-recovery]
                   [--recovery-reason TEXT] [--live-base-url URL]
                   [--now EPOCH] [--github-output PATH] [--summary-file PATH]

channels-json maps each channel to:
  {
    "tag": "testing-20261126.1",
    "latest_tag": "testing-20261126.1",
    "tarball": "/path/to/debian-aurora-repository.tar",
    "live_inrelease": "/optional/path/to/live/InRelease"
  }

Enforces unconditionally:
  - valid release tag syntax (<channel>-YYYYMMDD.N)
  - GPG signatures on InRelease and Release.gpg/Release against keyring
  - channel-bound Origin, Suite (aurora-<channel>) and Codename (aurora-<channel>)
  - SHA-256 index digests matching files on disk

Enforces unless --allow-recovery with non-empty --recovery-reason is supplied:
  - tag is not older than latest_tag for that channel
  - Valid-Until is present and strictly in the future
  - signed generation and Date do not regress below the currently live InRelease
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        'verify_repository', Path(__file__).resolve().with_name('verify-repository.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verifier = _load_verifier()
CHANNELS = _verifier.CHANNELS
suite_for_channel = _verifier.suite_for_channel


def parse_tag_order(channel, tag):
    match = re.fullmatch(rf'{re.escape(channel)}-([0-9]{{8}})\.([0-9]+)', tag or '')
    if not match:
        raise ValueError(f'invalid release tag for {channel}: {tag!r}')
    return (int(match.group(1)), int(match.group(2)))


def safe_extract_tar(tar_path, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, 'r:*') as tf:
        try:
            tf.extractall(dest_dir, filter='data')
        except TypeError:
            # Python < 3.12 fallback: reject unsafe members manually.
            dest_resolved = dest_dir.resolve()
            for member in tf.getmembers():
                if member.issym() or member.islnk() or member.isdev():
                    raise ValueError(f'refusing special tar member: {member.name}')
                target = (dest_dir / member.name).resolve()
                if target != dest_resolved and dest_resolved not in target.parents:
                    raise ValueError(f'tar member escapes destination: {member.name}')
            tf.extractall(dest_dir)


def read_live_metadata(channel, keyring_path, live_inrelease_path=None, live_base_url=None, now=None):
    """Return verified metadata of the currently deployed live channel, or None if not deployed."""
    tmp_path = None
    try:
        if live_inrelease_path is not None:
            path = Path(live_inrelease_path)
            if not path.is_file():
                return None
        elif live_base_url:
            suite = suite_for_channel(channel)
            url = f'{live_base_url.rstrip("/")}/{channel}/dists/{suite}/InRelease'
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                raise ValueError(f'failed to fetch live {url}: HTTP {exc.code}') from exc
            except urllib.error.URLError as exc:
                raise ValueError(f'failed to fetch live {url}: {exc}') from exc
            import tempfile
            fd, tmp_name = tempfile.mkstemp(prefix=f'live-{channel}-', suffix='.InRelease')
            import os
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
            tmp_path = Path(tmp_name)
            path = tmp_path
        else:
            return None

        verified = _verifier.verify_clearsigned_inrelease(path, keyring_path)
        return _verifier.validate_release_metadata(
            verified, channel=channel, now=now, allow_expired=True)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def stage_site(channels_spec, keyring_path, fingerprint, site_dir, asc_path=None,
               allow_recovery=False, recovery_reason='', live_base_url=None, now=None):
    if now is None:
        now = int(time.time())
    if allow_recovery and not recovery_reason.strip():
        raise ValueError('--allow-recovery requires a non-empty --recovery-reason')

    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / '.nojekyll').touch()
    if asc_path is not None:
        shutil.copy2(asc_path, site_dir / 'aurora-debian-archive.asc')

    staged = {}
    index_items = []
    summary_lines = []
    stable_changed = False

    for channel in CHANNELS:
        entry = channels_spec.get(channel)
        if not entry:
            continue
        tag = entry['tag']
        latest_tag = entry.get('latest_tag') or tag
        tarball = Path(entry['tarball'])
        tag_order = parse_tag_order(channel, tag)
        latest_order = parse_tag_order(channel, latest_tag)

        if not allow_recovery and tag_order < latest_order:
            raise ValueError(
                f'{channel}: refusing rollback from latest release {latest_tag} to older {tag} '
                f'(requires authorized recovery)')

        live_meta = None
        if entry.get('live_inrelease') is not None or live_base_url:
            live_meta = read_live_metadata(
                channel,
                keyring_path=keyring_path,
                live_inrelease_path=entry.get('live_inrelease'),
                live_base_url=live_base_url,
                now=now,
            )

        min_generation = None
        min_date = None
        if not allow_recovery and live_meta is not None:
            min_generation = live_meta['generation']
            min_date = live_meta['date_epoch']

        channel_dir = site_dir / channel
        if channel_dir.exists():
            shutil.rmtree(channel_dir)
        safe_extract_tar(tarball, channel_dir)

        meta = _verifier.verify_repository(
            channel_dir,
            channel=channel,
            keyring_path=keyring_path,
            now=now,
            allow_expired=allow_recovery,
            min_generation=min_generation,
            min_date=min_date,
        )

        if channel == 'stable':
            if (live_meta is None
                    or meta['generation'] != live_meta['generation']
                    or meta['date_epoch'] != live_meta['date_epoch']):
                stable_changed = True

        suite = meta['suite']
        index_items.append(
            f'  <li><a href="{channel}/dists/{suite}/InRelease">{channel}</a> '
            f'({tag}, suite {suite}, generation {meta["generation"]}, valid until {meta["valid_until"]})</li>')
        summary_lines.append(
            f'Verified and staged {channel} -> {tag} (suite={suite}, generation={meta["generation"]}, '
            f'valid_until={meta["valid_until"]}, gpgv OK against {fingerprint})')
        staged[channel] = {'tag': tag, **meta}

    if not staged:
        raise ValueError('no signed snapshot releases staged for any channel')

    index_html = (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head><meta charset="utf-8"><title>Aurora Debian Archive</title></head>\n'
        '<body>\n'
        '<h1>Aurora, based on Debian testing — APT Archive</h1>\n'
        f'<p>Archive signing key (<a href="aurora-debian-archive.asc">aurora-debian-archive.asc</a>): '
        f'<code>{fingerprint}</code></p>\n'
        '<ul>\n'
        + '\n'.join(index_items) + '\n'
        '</ul>\n'
        '</body>\n'
        '</html>\n'
    )
    (site_dir / 'index.html').write_text(index_html, encoding='utf-8')
    return {
        'staged': staged,
        'stable_changed': stable_changed,
        'summary_lines': summary_lines,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--keyring', type=Path, required=True)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--asc', type=Path, default=None)
    parser.add_argument('--channels-json', type=Path, required=True)
    parser.add_argument('--allow-recovery', action='store_true')
    parser.add_argument('--recovery-reason', default='')
    parser.add_argument('--live-base-url', default=None)
    parser.add_argument('--now', type=int, default=None)
    parser.add_argument('--github-output', type=Path, default=None)
    parser.add_argument('--summary-file', type=Path, default=None)
    args = parser.parse_args()

    channels_spec = json.loads(args.channels_json.read_text(encoding='utf-8'))
    try:
        result = stage_site(
            channels_spec,
            keyring_path=args.keyring,
            fingerprint=args.fingerprint,
            site_dir=args.site,
            asc_path=args.asc,
            allow_recovery=args.allow_recovery,
            recovery_reason=args.recovery_reason,
            live_base_url=args.live_base_url,
            now=args.now,
        )
    except ValueError as exc:
        sys.exit(f'stage-pages: {exc}')

    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as out:
            out.write(f"stable_changed={'true' if result['stable_changed'] else 'false'}\n")
    if args.summary_file:
        with args.summary_file.open('a', encoding='utf-8') as summary:
            for line in result['summary_lines']:
                summary.write(line + '\n')
    for line in result['summary_lines']:
        print(line)


if __name__ == '__main__':
    main()
