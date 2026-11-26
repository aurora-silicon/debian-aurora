"""scripts/sign-repository.py and scripts/check-repository.py on small signed snapshots,
and what apt itself enforces of their Release files.

The snapshots are signed with a throwaway key; their Release files are written
here rather than by apt-ftparchive, except in the assemble test. The assemble,
apt and keyring tests need apt-ftparchive, apt-get and dpkg (the Checks
workflow's debian:testing container) and skip without them.
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.datetime(2026, 11, 26, 12, 0, tzinfo=datetime.timezone.utc)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


signer = load('sign_repository', 'scripts/sign-repository.py')
checker = load('check_repository', 'scripts/check-repository.py')
stager = load('stage_channels', 'scripts/stage-channels.py')
HAVE_GPG = shutil.which('gpg') and shutil.which('gpgv')


def release_text(channel, packages):
    digest = hashlib.sha256(packages).hexdigest()
    dist = signer.distribution(channel)
    return (f'Origin: {signer.ORIGIN}\nLabel: {signer.LABEL}\nSuite: {dist}\nCodename: {dist}\n'
            f'Architectures: arm64 all\nComponents: main\nDescription: {signer.description(channel)}\n'
            f'SHA256:\n {digest} {len(packages):>16} main/binary-arm64/Packages\n')


KEYS = {}


def setUpModule():
    if not HAVE_GPG:
        return
    home = Path(tempfile.mkdtemp(prefix='aurora-gpg-'))
    os.environ['GNUPGHOME'] = str(home)
    for user in ('Aurora test archive key', 'Someone else'):
        subprocess.run(['gpg', '--batch', '--quiet', '--passphrase', '', '--quick-gen-key', user,
                        'ed25519', 'sign', 'never'], check=True, capture_output=True)
    listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'], text=True)
    KEYS['key'], KEYS['other'] = [line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:')]
    KEYS['home'] = home
    KEYS['keyring'] = home / 'archive.gpg'
    KEYS['keyring'].write_bytes(subprocess.check_output(['gpg', '--batch', '--export', KEYS['key']]))


def tearDownModule():
    if 'home' in KEYS:
        subprocess.run(['gpgconf', '--kill', 'gpg-agent'], check=False, capture_output=True)
        del os.environ['GNUPGHOME']
        shutil.rmtree(KEYS['home'], ignore_errors=True)


def make_snapshot(path, channel='testing', when=NOW, key=None, legacy=False, package='aurora-test', edit=None):
    """A snapshot of channel at path signed at when; legacy leaves out the fields sign-repository.py now adds,
    and edit changes the Release text before it is signed."""
    dists = path / 'dists' / signer.distribution(channel)
    packages = (f'Package: {package}\nVersion: 1\nArchitecture: arm64\nMaintainer: Aurora Silicon '
                f'<noreply@aurorasilicon.org>\nFilename: pool/main/{package}_1_arm64.deb\nSize: 1\n'
                f'SHA256: {"0" * 64}\nDescription: {path.name}\n').encode()
    (dists / 'main/binary-arm64').mkdir(parents=True)
    (dists / 'main/binary-arm64/Packages').write_bytes(packages)
    text = release_text(channel, packages)
    if legacy:
        text = text.replace('Components: main\n', f'Components: main\nDate: {signer.format_date(when)}\n')
    else:
        text = signer.stamp(text, when, signer.format_date(when))
    (dists / 'Release').write_text(edit(text) if edit else text)
    signer.sign(dists, key or KEYS['key'])
    return path


@unittest.skipUnless(HAVE_GPG, 'needs gpg and gpgv')
class SignedSnapshots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key, cls.other, cls.keyring = KEYS['key'], KEYS['other'], KEYS['keyring']

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='aurora-repository-'))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def snapshot(self, channel='testing', when=NOW, key=None, name='snapshot', legacy=False, edit=None):
        return make_snapshot(self.work / name, channel, when, key, legacy, edit=edit)

    def check(self, repository, channel='testing', **options):
        with contextlib.redirect_stderr(io.StringIO()):
            return checker.check(repository, channel, self.keyring, now=options.pop('now', NOW), **options)

    def refused(self, message, function, *args, **kwargs):
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
            function(*args, **kwargs)
        self.assertIn(message, str(raised.exception))

    def test_distribution_per_channel(self):
        self.assertEqual(signer.distribution('testing'), 'aurora')
        self.assertEqual(signer.distribution('stable'), 'aurora-stable')
        self.assertEqual(signer.distribution('edge'), 'aurora-edge')
        self.refused('unknown channel', signer.distribution, 'aurora')

    def test_stamp_sets_validity_and_keeps_the_rest(self):
        text = release_text('stable', b'x')
        stamped = signer.stamp(text, NOW, 'Mon, 23 Nov 2026 08:00:00 +0000')
        fields = signer.parse_release(stamped)
        self.assertEqual(fields['Date'], 'Thu, 26 Nov 2026 12:00:00 +0000')
        self.assertEqual(fields['Valid-Until'], 'Thu, 03 Dec 2026 12:00:00 +0000')
        self.assertEqual(fields[signer.SNAPSHOT_DATE], 'Mon, 23 Nov 2026 08:00:00 +0000')
        # The dates go before the hash list, and nothing else changes.
        self.assertLess(stamped.index('Valid-Until:'), stamped.index('SHA256:'))
        removed = [line for line in stamped.splitlines()
                   if not line.startswith(('Date:', 'Valid-Until:', signer.SNAPSHOT_DATE))]
        self.assertEqual(removed, text.splitlines())
        # Stamping again replaces the dates instead of adding more.
        again = signer.stamp(stamped, NOW + datetime.timedelta(days=1), fields[signer.SNAPSHOT_DATE])
        self.assertEqual(signer.parse_release(again)['Date'], 'Fri, 27 Nov 2026 12:00:00 +0000')
        self.assertEqual(again.count('Valid-Until:'), 1)

    def test_check_accepts_a_snapshot_of_its_channel(self):
        result = self.check(self.snapshot('stable'), 'stable', fresh=True)
        self.assertEqual(result['distribution'], 'aurora-stable')
        self.assertEqual(result['snapshot-date'], 'Thu, 26 Nov 2026 12:00:00 +0000')

    def test_check_refuses_another_channels_snapshot(self):
        testing = self.snapshot('testing')
        # Served as is under another channel, it lacks that channel's distribution.
        self.refused("the stable channel serves only aurora-stable", self.check, testing, 'stable')
        # Moved to that channel's directory, its signed identity still names Testing.
        (testing / 'dists/aurora').rename(testing / 'dists/aurora-stable')
        self.refused("Release Suite is 'aurora', not 'aurora-stable'", self.check, testing, 'stable')

    def test_check_refuses_a_second_distribution(self):
        repository = self.snapshot('stable')
        shutil.copytree(repository / 'dists/aurora-stable', repository / 'dists/aurora')
        self.refused('serves only aurora-stable', self.check, repository, 'stable')

    def test_check_refuses_changed_or_foreign_metadata(self):
        repository = self.snapshot()
        release = repository / 'dists/aurora/Release'
        release.write_text(release.read_text().replace('Components: main', 'Components: main contrib'))
        self.refused('gpgv', self.check, repository)
        repository = self.snapshot(name='packages')
        (repository / 'dists/aurora/main/binary-arm64/Packages').write_text('Package: other\n')
        self.refused('does not match Release', self.check, repository)
        self.refused('gpgv', self.check, self.snapshot(name='foreign', key=self.other))

    def test_check_refuses_another_channels_codename(self):
        # Every other field names Stable.
        repository = self.snapshot('stable', edit=lambda text: text.replace('Codename: aurora-stable',
                                                                            'Codename: aurora'))
        self.refused("Release Codename is 'aurora', not 'aurora-stable'", self.check, repository, 'stable')

    def test_check_refuses_a_release_other_than_the_one_inrelease_signs(self):
        repository = self.snapshot()
        dists = repository / 'dists/aurora'
        # Release and Release.gpg agree with each other, and the key signed both, but not InRelease's text.
        release = dists / 'Release'
        release.write_text(release.read_text().replace('Components: main', 'Components: main contrib'))
        subprocess.run(['gpg', '--batch', '--yes', '--armor', '--detach-sign', '--local-user', self.key,
                        '--output', str(dists / 'Release.gpg'), str(release)], check=True, capture_output=True)
        self.refused('differs from the text InRelease signs', self.check, repository)

    def test_check_refuses_an_index_outside_its_directory(self):
        outside = b'Package: outside\n'
        line = f' {hashlib.sha256(outside).hexdigest()} {len(outside):>16} ../../outside\n'
        repository = self.snapshot(edit=lambda text: text + line)
        (repository / 'outside').write_bytes(outside)
        self.refused('outside its directory', self.check, repository)

    def test_hold_needs_the_served_snapshot(self):
        served = self.snapshot('stable', name='served', when=NOW - datetime.timedelta(days=1))
        floor = str(served / 'dists/aurora-stable/InRelease')
        self.check(served, 'stable', floor=floor, hold=True)
        newer = self.snapshot('stable', name='newer')
        self.refused('is not the one the channel serves', self.check, newer, 'stable', floor=floor, hold=True)
        self.refused('serves (none)', self.check, newer, 'stable', floor=str(self.work / 'none'), hold=True)

    def test_image_sources(self):
        testing, stable, edge = (self.snapshot(channel, name=channel) for channel in ('testing', 'stable', 'edge'))

        def image(repository, channel):
            with contextlib.redirect_stderr(io.StringIO()):
                return checker.check_image_source(repository, channel, self.keyring)
        self.assertEqual(image(stable, 'stable')['distribution'], 'aurora-stable')
        self.assertEqual(image(edge, 'edge')['channel'], 'edge')
        self.assertEqual(image(testing, 'edge')['channel'], 'testing')
        self.assertEqual(image(testing, 'testing')['channel'], 'testing')
        self.refused('an image of the stable channel does not install from a snapshot of the testing channel',
                     image, testing, 'stable')
        self.refused('an image of the testing channel does not install from a snapshot of the edge channel',
                     image, edge, 'testing')
        self.refused('an image of the stable channel does not install from a snapshot of the edge channel',
                     image, edge, 'stable')
        # Moved to Stable's directory, a Testing snapshot still names Testing.
        (testing / 'dists/aurora').rename(testing / 'dists/aurora-stable')
        self.refused("Release Suite is 'aurora', not 'aurora-stable'", image, testing, 'stable')

    def test_fresh_needs_a_recent_valid_until(self):
        three_days = self.snapshot(when=NOW - datetime.timedelta(days=3))
        self.check(three_days)
        self.refused('has to be signed again', self.check, three_days, fresh=True)
        self.refused('has no Valid-Until', self.check, self.snapshot(name='legacy', legacy=True), fresh=True)

    def test_floor_refuses_an_older_snapshot(self):
        served = self.snapshot(name='served', when=NOW - datetime.timedelta(days=1))
        floor = served / 'dists/aurora/InRelease'
        self.check(self.snapshot(name='newer'), floor=str(floor))
        self.check(served, floor=str(floor))
        older = self.snapshot(name='older', when=NOW - datetime.timedelta(days=2))
        self.refused('a channel does not roll back', self.check, older, floor=str(floor))
        # A floor signed before the snapshot date existed counts its Date.
        legacy = self.snapshot(name='legacy', when=NOW - datetime.timedelta(days=1), legacy=True)
        self.refused('a channel does not roll back', self.check, older, floor=str(legacy / 'dists/aurora/InRelease'))

    def test_floor_must_be_this_channels(self):
        stable = self.snapshot('stable', name='stable')
        self.refused('not', self.check, self.snapshot(), floor=str(stable / 'dists/aurora-stable/InRelease'))

    def test_refresh_changes_only_the_dates(self):
        older = self.snapshot(when=NOW - datetime.timedelta(days=30))
        dists = signer.refresh(older, self.work / 'refreshed', 'testing', self.key, NOW)
        signer.sign(dists, self.key)
        before = (older / 'dists/aurora/Release').read_text().splitlines()
        after = (dists / 'Release').read_text().splitlines()
        dated = ('Date:', 'Valid-Until:')
        self.assertEqual([line for line in before if not line.startswith(dated)],
                         [line for line in after if not line.startswith(dated)])
        fields = signer.parse_release('\n'.join(after))
        self.assertEqual(fields['Valid-Until'], 'Thu, 03 Dec 2026 12:00:00 +0000')
        self.assertEqual(fields[signer.SNAPSHOT_DATE], 'Tue, 27 Oct 2026 12:00:00 +0000')
        # Served with the snapshot's indexes, the refreshed Release file passes as fresh,
        # and it is still as old as its packages against a newer floor.
        shutil.copytree(older / 'dists/aurora/main', dists / 'main')
        self.check(self.work / 'refreshed', fresh=True)
        floor = self.snapshot(name='served', when=NOW - datetime.timedelta(days=1)) / 'dists/aurora/InRelease'
        self.refused('a channel does not roll back', self.check, self.work / 'refreshed', floor=str(floor))

    def test_refresh_of_a_snapshot_signed_before_the_snapshot_date(self):
        legacy = self.snapshot(when=NOW - datetime.timedelta(days=1), legacy=True)
        dists = signer.refresh(legacy, self.work / 'refreshed', 'testing', self.key, NOW)
        fields = signer.parse_release((dists / 'Release').read_text())
        self.assertEqual(fields[signer.SNAPSHOT_DATE], 'Wed, 25 Nov 2026 12:00:00 +0000')

    def test_refresh_keeps_the_channel(self):
        testing = self.snapshot()
        self.refused('gpgv refused', signer.refresh, testing, self.work / 'as-stable', 'stable', self.key, NOW)
        (testing / 'dists/aurora').rename(testing / 'dists/aurora-stable')
        self.refused("Release Suite is 'aurora', not 'aurora-stable'",
                     signer.refresh, testing, self.work / 'renamed', 'stable', self.key, NOW)

    def test_refresh_needs_the_signing_keys_signature(self):
        foreign = self.snapshot(key=self.other)
        self.refused('gpgv refused', signer.refresh, foreign, self.work / 'refreshed', 'testing', self.key, NOW)

    def test_live_date_format(self):
        when = signer.parse_date('Wed, 25 Nov 2026 21:41:00 +0000', 'Date')
        self.assertEqual(when, datetime.datetime(2026, 11, 25, 21, 41, tzinfo=datetime.timezone.utc))
        self.refused('invalid Date', signer.parse_date, 'yesterday', 'Date')

    @unittest.skipUnless(shutil.which('apt-ftparchive') and shutil.which('dpkg-deb') and shutil.which('xz'),
                         'needs apt-ftparchive, dpkg-deb and xz')
    def test_assemble_signs_a_channels_distribution(self):
        package = self.work / 'aurora-test'
        (package / 'DEBIAN').mkdir(parents=True)
        (package / 'DEBIAN/control').write_text('Package: aurora-test\nVersion: 1\nArchitecture: all\n'
                                                'Maintainer: Aurora Silicon <noreply@aurorasilicon.org>\n'
                                                'Description: test\n')
        debs = self.work / 'debs'
        debs.mkdir()
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(package), str(debs)], check=True,
                       capture_output=True)
        output = self.work / 'repository'
        dists = signer.assemble(debs, output, 'edge', NOW)
        signer.sign(dists, self.key)
        signer.verify(dists, self.key, 'edge')
        fields = signer.parse_release((dists / 'Release').read_text())
        self.assertEqual((fields['Suite'], fields['Codename']), ('aurora-edge', 'aurora-edge'))
        self.assertEqual(fields['Valid-Until'], 'Thu, 03 Dec 2026 12:00:00 +0000')
        self.assertEqual(fields[signer.SNAPSHOT_DATE], fields['Date'])
        self.check(output, 'edge', fresh=True)


@unittest.skipUnless(HAVE_GPG, 'needs gpg and gpgv')
class StageChannels(unittest.TestCase):
    """scripts/stage-channels.py: what each channel serves when releases fail, and Stable promotion."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='aurora-stage-'))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.snapshots = {}
        self.releases = []

    def release(self, tag, channel=None, when=NOW, **options):
        """Publish release tag holding a snapshot of channel (tag's own by default) signed at when."""
        path = make_snapshot(self.work / 'snapshots' / tag, channel or tag.split('-')[0], when, **options)
        self.snapshots[tag] = path
        self.releases.append({'tag_name': tag, 'draft': False, 'assets': [{'name': stager.ASSET}]})
        return path

    def download(self, tag, directory):
        archive = directory / stager.ASSET
        with tarfile.open(archive, 'w') as snapshot:
            snapshot.add(self.snapshots[tag], arcname='.')
        return archive

    def served(self, tag):
        """The InRelease of release tag, as the channel's live Release file."""
        channel = tag.split('-')[0]
        return str(self.snapshots[tag] / 'dists' / signer.distribution(channel) / 'InRelease')

    def stage(self, explicit=None, floors=None):
        output = self.work / 'metadata'
        shutil.rmtree(output, ignore_errors=True)
        none = {channel: str(self.work / 'nothing-served') for channel in signer.CHANNELS}
        with contextlib.redirect_stderr(io.StringIO()):
            return stager.stage_all(explicit or {}, self.releases, KEYS['keyring'], output, self.download,
                                    dict(none, **(floors or {})))

    def test_releases_newest_first(self):
        releases = [{'tag_name': tag, 'draft': draft, 'assets': [{'name': asset}]} for tag, draft, asset in (
            ('testing-20261125.9', False, stager.ASSET), ('testing-20261125.10', False, stager.ASSET),
            ('testing-20261126.1', True, stager.ASSET), ('testing-20261124.3', False, 'other.tar'),
            ('stable-20261126.1', False, stager.ASSET), ('testing-latest', False, stager.ASSET))]
        self.assertEqual(stager.releases_of(releases, 'testing'), ['testing-20261125.10', 'testing-20261125.9'])

    def test_a_bad_release_falls_back_without_stopping_other_channels(self):
        self.release('testing-20261126.1', when=NOW - datetime.timedelta(hours=2))
        self.release('testing-20261126.2', channel='edge')
        self.release('edge-20261126.1', channel='edge')
        summary = self.stage()
        self.assertEqual(summary['tags'], {'testing': 'testing-20261126.1', 'edge': 'edge-20261126.1'})
        self.assertEqual(len(summary['failed']), 1)
        self.assertIn('testing: testing-20261126.2:', summary['failed'][0])
        self.assertTrue((self.work / 'metadata/testing/dists/aurora/InRelease').is_file())
        self.assertTrue((self.work / 'metadata/edge/dists/aurora-edge/InRelease').is_file())

    def test_a_channel_with_nothing_that_passes_is_reported_and_left_out(self):
        self.release('testing-20261126.1')
        self.release('nightly-20261126.1', channel='testing')
        summary = self.stage()
        self.assertEqual(summary['tags'], {'testing': 'testing-20261126.1'})
        self.assertIn('nightly: no release passed; the channel is not served', summary['failed'])

    def test_a_release_older_than_the_served_snapshot_is_skipped(self):
        self.release('testing-20261125.1', when=NOW - datetime.timedelta(days=1))
        self.release('testing-20261126.1', when=NOW - datetime.timedelta(days=2))
        summary = self.stage(floors={'testing': self.served('testing-20261125.1')})
        self.assertEqual(summary['tags'], {'testing': 'testing-20261125.1'})
        self.assertIn('a channel does not roll back', summary['failed'][0])

    def test_a_given_tag_that_fails_falls_back_and_is_reported(self):
        self.release('testing-20261126.1')
        self.release('testing-20261126.2', channel='stable')
        summary = self.stage({'testing': 'testing-20261126.2'})
        self.assertEqual(summary['tags'], {'testing': 'testing-20261126.1'})
        self.assertIn('testing: testing-20261126.2:', summary['failed'][0])
        summary = self.stage({'testing': 'edge-20261126.1'})
        self.assertIn('testing: edge-20261126.1 is not a testing release tag', summary['failed'])

    def test_stable_keeps_what_it_serves(self):
        self.release('stable-20261120.1', when=NOW - datetime.timedelta(days=6))
        self.release('stable-20261125.1', when=NOW - datetime.timedelta(days=1))
        self.release('stable-20261126.1', channel='testing')
        summary = self.stage(floors={'stable': self.served('stable-20261120.1')})
        self.assertEqual(summary['tags'], {'stable': 'stable-20261120.1'})
        self.assertEqual(summary['failed'], [])
        self.assertFalse(summary['stable-promotion'])
        # Nothing served, nothing staged, and that is no failure.
        summary = self.stage()
        self.assertEqual((summary['tags'], summary['failed']), ({}, []))

    def test_stable_promotion_only_when_given(self):
        self.release('stable-20261120.1', when=NOW - datetime.timedelta(days=6))
        self.release('stable-20261125.1', when=NOW - datetime.timedelta(days=1))
        floors = {'stable': self.served('stable-20261120.1')}
        summary = self.stage({'stable': 'stable-20261125.1'}, floors)
        self.assertEqual(summary['tags'], {'stable': 'stable-20261125.1'})
        self.assertTrue(summary['stable-promotion'])
        summary = self.stage({'stable': 'stable-20261120.1'}, floors)
        self.assertFalse(summary['stable-promotion'])
        # The first Stable snapshot is a promotion too.
        self.assertTrue(self.stage({'stable': 'stable-20261125.1'})['stable-promotion'])

    def test_a_given_stable_tag_that_fails_keeps_the_served_snapshot(self):
        self.release('stable-20261120.1', when=NOW - datetime.timedelta(days=6))
        self.release('stable-20261126.1', channel='testing')
        summary = self.stage({'stable': 'stable-20261126.1'}, {'stable': self.served('stable-20261120.1')})
        self.assertEqual(summary['tags'], {'stable': 'stable-20261120.1'})
        self.assertFalse(summary['stable-promotion'])
        self.assertIn('stable: stable-20261126.1:', summary['failed'][0])

    def test_stable_whose_served_release_is_gone_is_reported(self):
        served = make_snapshot(self.work / 'gone', 'stable', NOW - datetime.timedelta(days=6))
        self.release('stable-20261125.1', when=NOW - datetime.timedelta(days=1))
        summary = self.stage(floors={'stable': str(served / 'dists/aurora-stable/InRelease')})
        self.assertEqual(summary['tags'], {})
        self.assertIn('Stable is not served', summary['failed'][0])


@unittest.skipUnless(HAVE_GPG and shutil.which('apt-get'), 'needs apt-get, gpg and gpgv')
class AptClient(unittest.TestCase):
    """apt-get update against a copy: repository, with nothing of the host's apt configuration."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='aurora-apt-'))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.repository = self.work / 'repository'
        for directory in ('etc/apt.conf.d', 'etc/sources.list.d', 'etc/trusted.gpg.d', 'state/lists/partial',
                          'cache/archives/partial'):
            (self.work / directory).mkdir(parents=True)
        (self.work / 'state/status').touch()
        user = pwd.getpwuid(os.geteuid()).pw_name
        # APT_CONFIG is read before anything else, so the host's configuration never applies.
        (self.work / 'apt.conf').write_text(
            f'Dir::Etc::Parts "{self.work}/etc/apt.conf.d"; Dir::Etc::Main "/dev/null";\n'
            f'Dir::Etc::SourceList "/dev/null"; Dir::Etc::SourceParts "{self.work}/etc/sources.list.d";\n'
            f'Dir::Etc::Trusted "/dev/null"; Dir::Etc::TrustedParts "{self.work}/etc/trusted.gpg.d";\n'
            f'Dir::State "{self.work}/state"; Dir::State::status "{self.work}/state/status";\n'
            f'Dir::Cache "{self.work}/cache"; Debug::NoLocking "true"; APT::Sandbox::User "{user}";\n'
            'APT::Architecture "arm64"; APT::Architectures { "arm64"; }; Acquire::Languages "none";\n')

    def serve(self, channel, when, follow=None):
        """Replace the repository with a snapshot of channel signed at when, at follow's distribution."""
        shutil.rmtree(self.repository, ignore_errors=True)
        make_snapshot(self.repository, channel, when)
        follow = follow or channel
        if follow != channel:
            (self.repository / 'dists' / signer.distribution(channel)).rename(
                self.repository / 'dists' / signer.distribution(follow))
        (self.work / 'etc/sources.list.d/aurora.sources').write_text(
            f'Types: deb\nURIs: copy:{self.repository}\nSuites: {signer.distribution(follow)}\n'
            f'Components: main\nSigned-By: {KEYS["keyring"]}\n')

    def update(self, *options):
        environment = dict(os.environ, APT_CONFIG=str(self.work / 'apt.conf'), LC_ALL='C.UTF-8')
        result = subprocess.run(['apt-get', 'update', *options], env=environment, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def stored_date(self):
        lists = list((self.work / 'state/lists').glob('*_InRelease'))
        self.assertEqual(len(lists), 1, lists)
        # The Date line of the signed text; the file is clearsigned.
        return re.search(r'^Date: (.+)$', lists[0].read_text(), re.MULTILINE)[1]

    def test_expired_release_is_refused(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self.serve('testing', now)
        status, output = self.update()
        self.assertEqual(status, 0, output)
        self.serve('testing', now - signer.VALID_FOR - datetime.timedelta(days=1))
        shutil.rmtree(self.work / 'state/lists')
        (self.work / 'state/lists/partial').mkdir(parents=True)
        status, output = self.update()
        self.assertNotEqual(status, 0, output)
        self.assertIn('is expired', output)
        # What images built before this change set: then apt takes it.
        status, output = self.update('-o', 'Acquire::Check-Valid-Until=false')
        self.assertEqual(status, 0, output)

    def test_another_channels_codename_is_refused_once_followed(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self.serve('stable', now - datetime.timedelta(hours=2))
        status, output = self.update()
        self.assertEqual(status, 0, output)
        # Testing's signed snapshot, moved to where Stable's is served.
        self.serve('testing', now - datetime.timedelta(hours=1), follow='stable')
        status, output = self.update()
        self.assertNotEqual(status, 0, output)
        self.assertIn("changed its 'Codename' value from 'aurora-stable' to 'aurora'", output)

    def test_older_release_does_not_replace_a_newer_one(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self.serve('testing', now - datetime.timedelta(hours=1))
        self.assertEqual(self.update()[0], 0)
        newer = self.stored_date()
        self.serve('testing', now - datetime.timedelta(days=2))
        status, output = self.update()
        self.assertEqual(status, 0, output)
        self.assertEqual(self.stored_date(), newer)


@unittest.skipUnless(shutil.which('dpkg') and shutil.which('cmp'), 'needs dpkg and cmp')
class ArchiveKeyringUpgrade(unittest.TestCase):
    """aurora-archive-keyring's postinst and the apt configuration images kept from their build."""

    POSTINST = ROOT / 'packages/aurora-archive-keyring/debian/postinst'
    BUILT = 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n'

    def configure(self, content, *arguments):
        root = Path(tempfile.mkdtemp(prefix='aurora-root-'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        conf = root / 'etc/apt/apt.conf.d/99mmdebstrap'
        conf.parent.mkdir(parents=True)
        conf.write_text(content)
        subprocess.run(['sh', str(self.POSTINST), 'configure', *arguments], check=True,
                       env=dict(os.environ, DPKG_ROOT=str(root)))
        return conf.exists()

    def test_upgrade_removes_the_build_configuration(self):
        self.assertFalse(self.configure(self.BUILT, '2026.11.3'))

    def test_anything_else_stays(self):
        self.assertTrue(self.configure(self.BUILT + 'Acquire::http::Proxy "http://proxy";\n', '2026.11.3'))
        self.assertTrue(self.configure('Acquire::Retries "5";\n', '2026.11.3'))
        # A first install (an image build, which still needs it) and later upgrades leave it.
        self.assertTrue(self.configure(self.BUILT))
        self.assertTrue(self.configure(self.BUILT, '2026.11.4'))


if __name__ == '__main__':
    unittest.main()
