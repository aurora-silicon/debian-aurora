#!/usr/bin/env python3
"""Check a signed snapshot of the apt repository before it is served for a channel or installed in an image.

    check-repository.py --repository DIR --channel testing --keyring FILE [--fresh] [--floor [URL|FILE]] [--hold]
    check-repository.py --repository DIR --image stable --keyring FILE
    check-repository.py --deploying JSON --keyring FILE

Refuses the snapshot unless:
- InRelease and Release.gpg verify with the keyring and sign the same Release;
- its only distribution is the channel's, and every signed identity field
  (Origin, Label, Suite, Codename, Description) names the channel;
- every index Release lists that is present matches it;
- with --fresh, its Release file is valid for most of scripts/sign-repository.py's
  VALID_FOR still;
- with --floor, its packages were signed no earlier than those of the Release
  file at --floor (by default the channel's live one), so a deployment never
  rolls a channel back. A floor that is not there (HTTP 404, or no such file)
  sets no bound;
- with --hold as well, it is the snapshot the floor names, and there is one.

--image takes the snapshot's channel from its distribution and refuses one an
image of that channel must not install from: a Stable image installs only a
Stable snapshot, and any other image its own channel's or a Testing one.

--deploying is deploy-pages.yml's last check before it replaces the whole site,
JSON mapping each channel the new site serves to its snapshot date. Every
channel the site serves must be no older than the one live now, and every
channel it leaves out must still not be served (its live Release file answers
404); a live Release file that cannot be read refuses the deployment too.

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
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load_signer():
    spec = importlib.util.spec_from_file_location('sign_repository', ROOT / 'scripts/sign-repository.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


signer = load_signer()


def live_floor(channel):
    return f'{signer.PAGES}/{channel}/dists/{signer.distribution(channel)}/InRelease'


def read_floor(floor, channel):
    """The signed InRelease at floor (a URL or a file), or None when there is none."""
    if '://' not in floor:
        path = Path(floor)
        return path.read_bytes() if path.exists() else None
    if not floor.startswith('https://'):
        raise SystemExit(f'refusing a floor that is not https: {floor}')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(floor, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            failure = error
        except urllib.error.URLError as error:
            failure = error
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f'cannot read the {channel} channel\'s live Release file {floor}: {failure}')


def floor_date(signed, keyring, channel):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'InRelease'
        path.write_bytes(signed)
        output = Path(temporary) / 'Release'
        signer.gpgv(keyring, '--output', output, path)
        fields = signer.parse_release(output.read_text())
    signer.check_identity(fields, channel)
    return signer.snapshot_date(fields)


def served_snapshot(floor, keyring, channel):
    """The (text, date) of the snapshot the Release file at floor was signed for, or None."""
    signed = read_floor(floor, channel)
    return None if signed is None else floor_date(signed, keyring, channel)


def check(repository, channel, keyring, fresh=False, floor=None, now=None, served=None, hold=False):
    """Check repository as channel's snapshot. served, if given, is served_snapshot()'s answer for floor."""
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
    if floor and served is None:
        served = served_snapshot(floor, keyring, channel)
    if served is not None and snapshot < served[1]:
        raise SystemExit(f'the {channel} snapshot signed {signed_at} is older than the one served, '
                         f'signed {served[0]}; a channel does not roll back')
    if hold and (served is None or snapshot != served[1]):
        raise SystemExit(f'the {channel} snapshot signed {signed_at} is not the one the channel serves '
                         f'({served[0] if served else "none"})')
    return {'channel': channel, 'distribution': dist, 'snapshot-date': signed_at,
            'valid-until': fields.get('Valid-Until'), 'served-snapshot-date': served[0] if served else None}


def check_not_behind(channel, keyring, snapshot_date, floor):
    """Refuse when the Release file at floor was signed for a newer snapshot than the one of snapshot_date."""
    snapshot = signer.parse_date(snapshot_date, 'snapshot date')
    served = served_snapshot(floor, keyring, channel)
    if served is not None and snapshot < served[1]:
        raise SystemExit(f'the {channel} channel now serves a snapshot signed {served[0]}, newer than this '
                         f'one, signed {snapshot_date}; a channel does not roll back')
    return {'channel': channel, 'snapshot-date': snapshot_date, 'served-snapshot-date': served[0] if served else None}


def check_deployment(snapshots, keyring, floors=None):
    """Check a site serving snapshots ({channel: snapshot date}) against the channels' live Release files."""
    unknown = sorted(set(snapshots) - set(signer.CHANNELS))
    if unknown:
        raise SystemExit(f'the site serves unknown channels {unknown}')
    checked = {}
    for channel in signer.CHANNELS:
        floor = (floors or {}).get(channel) or live_floor(channel)
        if channel in snapshots:
            checked[channel] = check_not_behind(channel, keyring, snapshots[channel], floor)
            continue
        served = served_snapshot(floor, keyring, channel)
        if served is not None:
            raise SystemExit(f'the {channel} channel is served now (signed {served[0]}), and this deployment '
                             'would remove it')
        checked[channel] = None
    return checked


def snapshot_channel(repository):
    """The channel whose distribution is repository's only one."""
    found = sorted(path.name for path in (repository / 'dists').iterdir()) if (repository / 'dists').is_dir() else []
    channels = [channel for channel in signer.CHANNELS if [signer.distribution(channel)] == found]
    if not channels:
        raise SystemExit(f'{repository} has distributions {found}, not one channel\'s')
    return channels[0]


def check_image_source(repository, image, keyring):
    """Check repository as the snapshot an image of channel image installs from."""
    channel = snapshot_channel(repository)
    if channel != image and (image == 'stable' or channel != 'testing'):
        raise SystemExit(f'an image of the {image} channel does not install from a snapshot of the {channel} channel')
    return dict(check(repository, channel, keyring), image=image)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--repository', type=Path)
    source.add_argument('--deploying', metavar='JSON', type=json.loads,
                        help='the snapshot date of each channel a new site serves, as a JSON object')
    purpose = parser.add_mutually_exclusive_group()
    purpose.add_argument('--channel', choices=signer.CHANNELS, help='the channel that will serve the snapshot')
    purpose.add_argument('--image', choices=signer.CHANNELS, help='the channel an image built from it follows')
    parser.add_argument('--keyring', type=Path, required=True, help='the archive key, dearmored')
    parser.add_argument('--fresh', action='store_true', help='require a freshly signed Release file')
    parser.add_argument('--floor', nargs='?', const='live',
                        help="the InRelease the snapshot may not be older than (a URL or file; default the "
                             "channel's live one)")
    parser.add_argument('--hold', action='store_true', help='require the snapshot --floor names')
    args = parser.parse_args()
    if args.image and (args.fresh or args.floor or args.hold):
        parser.error('--image takes no --fresh, --floor or --hold')
    if args.hold and not args.floor:
        parser.error('--hold needs --floor')
    if args.deploying is not None and (args.channel or args.image or args.fresh or args.floor or args.hold):
        parser.error('--deploying takes only --keyring')
    if args.repository and not (args.channel or args.image):
        parser.error('--repository needs --channel or --image')
    try:
        if args.deploying is not None:
            result = check_deployment(args.deploying, args.keyring)
        elif args.image:
            result = check_image_source(args.repository, args.image, args.keyring)
        else:
            floor = live_floor(args.channel) if args.floor == 'live' else args.floor
            result = check(args.repository, args.channel, args.keyring, args.fresh, floor, hold=args.hold)
    except subprocess.CalledProcessError as error:
        sys.exit(f'{" ".join(map(str, error.cmd))} failed:\n{(error.stderr or b"").decode(errors="replace")}')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
