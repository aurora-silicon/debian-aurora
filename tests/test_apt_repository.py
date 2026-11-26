"""Tests for channel-bound APT signing, verification, Pages staging, and aurora-apt-guard."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SIGN_SCRIPT = ROOT / 'scripts/sign-repository.py'
VERIFY_SCRIPT = ROOT / 'scripts/verify-repository.py'
STAGE_SCRIPT = ROOT / 'scripts/stage-pages.py'
GUARD_SCRIPT = ROOT / 'packages/aurora-archive-keyring/aurora-apt-guard'

REQUIRED_TOOLS = ('apt-ftparchive', 'dpkg-deb', 'gpg', 'gpgv', 'xz')


def has_repo_tools():
    return all(shutil.which(tool) for tool in REQUIRED_TOOLS)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_dummy_deb(dest_dir, pkg='aurora-test-pkg', version='1.0-1', arch='all'):
    stage = dest_dir / f'_build_{pkg}_{version}_{arch}'
    (stage / 'DEBIAN').mkdir(parents=True, exist_ok=True)
    (stage / 'DEBIAN' / 'control').write_text(
        f'Package: {pkg}\n'
        f'Version: {version}\n'
        f'Architecture: {arch}\n'
        'Maintainer: Aurora Silicon <noreply@aurorasilicon.org>\n'
        'Description: synthetic test package\n',
        encoding='utf-8',
    )
    deb_path = dest_dir / f'{pkg}_{version}_{arch}.deb'
    subprocess.run(['dpkg-deb', '--build', str(stage), str(deb_path)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(stage)
    return deb_path


def make_gpg_key(gnupg_dir, uid='Aurora Test Signer <test@aurorasilicon.org>'):
    gnupg_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = dict(os.environ, GNUPGHOME=str(gnupg_dir))
    subprocess.run(
        ['gpg', '--batch', '--passphrase', '', '--quick-generate-key',
         uid, 'ed25519', 'sign', 'never'],
        env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    listing = subprocess.check_output(
        ['gpg', '--batch', '--with-colons', '--list-secret-keys'], env=env, text=True)
    fpr = [line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:')][0]
    keyring = gnupg_dir.parent / f'{gnupg_dir.name}.gpg'
    keyring.write_bytes(subprocess.check_output(['gpg', '--batch', '--export', fpr], env=env))
    asc = gnupg_dir.parent / f'{gnupg_dir.name}.asc'
    asc.write_bytes(subprocess.check_output(['gpg', '--batch', '--armor', '--export', fpr], env=env))
    return env, fpr, keyring, asc


def pack_repo_tar(repo_dir, tar_path):
    with tarfile.open(tar_path, 'w') as tf:
        for item in sorted(repo_dir.iterdir()):
            tf.add(item, arcname=item.name)
    return tar_path


@unittest.skipUnless(has_repo_tools(), 'requires apt-ftparchive, dpkg-deb, gpg, gpgv and xz')
class AptRepositorySecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared_tmp = tempfile.TemporaryDirectory()
        cls.shared = Path(cls.shared_tmp.name)
        cls.env, cls.fpr, cls.keyring, cls.asc = make_gpg_key(cls.shared / 'gnupg-main')
        cls.other_env, cls.other_fpr, cls.other_keyring, _ = make_gpg_key(
            cls.shared / 'gnupg-other', uid='Other Key <other@example.com>')
        cls.pkg_dir = cls.shared / 'pkgs'
        cls.pkg_dir.mkdir()
        make_dummy_deb(cls.pkg_dir, pkg='aurora-test-pkg', version='1.0-1', arch='all')

    @classmethod
    def tearDownClass(cls):
        cls.shared_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def sign_repo(self, name, channel='testing', valid_days=None, generation=None,
                  min_generation=None, env=None, expect_ok=True):
        out = self.base / name
        cmd = [sys.executable, str(SIGN_SCRIPT),
               '--packages', str(self.pkg_dir),
               '--output', str(out),
               '--channel', channel]
        if valid_days is not None:
            cmd += ['--valid-days', str(valid_days)]
        if generation is not None:
            cmd += ['--generation', str(generation)]
        if min_generation is not None:
            cmd += ['--min-generation', str(min_generation)]
        res = subprocess.run(cmd, env=env or self.env, capture_output=True, text=True)
        if expect_ok:
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        return out, res

    def verify_repo(self, repo, channel, keyring=None, now=None, allow_expired=False,
                    min_generation=None, min_date=None):
        cmd = [sys.executable, str(VERIFY_SCRIPT),
               '--repo', str(repo),
               '--channel', channel,
               '--keyring', str(keyring or self.keyring),
               '--json']
        if now is not None:
            cmd += ['--now', str(now)]
        if allow_expired:
            cmd.append('--allow-expired')
        if min_generation is not None:
            cmd += ['--min-generation', str(min_generation)]
        if min_date is not None:
            cmd += ['--min-date', str(min_date)]
        return subprocess.run(cmd, capture_output=True, text=True)

    # --- Signing & Verification (#211, #214) ---

    def test_sign_emits_channel_suite_valid_until_and_generation(self):
        repo, _ = self.sign_repo('repo-testing', channel='testing', generation=1001)
        res = self.verify_repo(repo, channel='testing')
        self.assertEqual(res.returncode, 0, res.stderr)
        meta = json.loads(res.stdout)
        self.assertEqual(meta['suite'], 'aurora-testing')
        self.assertEqual(meta['codename'], 'aurora-testing')
        self.assertEqual(meta['origin'], 'Aurora Silicon')
        self.assertEqual(meta['generation'], 1001)
        self.assertEqual(meta['valid_until_epoch'] - meta['date_epoch'], 7 * 86400)

        stable_repo, _ = self.sign_repo('repo-stable', channel='stable', generation=2001)
        sres = self.verify_repo(stable_repo, channel='stable')
        self.assertEqual(sres.returncode, 0, sres.stderr)
        smeta = json.loads(sres.stdout)
        self.assertEqual(smeta['suite'], 'aurora-stable')
        self.assertEqual(smeta['valid_until_epoch'] - smeta['date_epoch'], 14 * 86400)

    def test_sign_rejects_invalid_valid_days_and_non_monotonic_generation(self):
        _, res0 = self.sign_repo('bad-vd0', valid_days=0, expect_ok=False)
        self.assertNotEqual(res0.returncode, 0)
        _, res31 = self.sign_repo('bad-vd31', valid_days=31, expect_ok=False)
        self.assertNotEqual(res31.returncode, 0)
        _, res_gen = self.sign_repo('bad-gen', generation=100, min_generation=100, expect_ok=False)
        self.assertNotEqual(res_gen.returncode, 0)

        repo, _ = self.sign_repo('auto-gen', min_generation=9999999999)
        meta = json.loads(self.verify_repo(repo, 'testing').stdout)
        self.assertEqual(meta['generation'], 10000000000)

    def test_verify_rejects_channel_mismatch_even_if_directory_renamed(self):
        repo, _ = self.sign_repo('testing-repo', channel='testing', generation=100)
        # Unmodified testing repo rejected for stable.
        res1 = self.verify_repo(repo, channel='stable')
        self.assertNotEqual(res1.returncode, 0)
        self.assertIn('unexpected suites', res1.stderr)

        # Even if an attacker moves dists/aurora-testing -> dists/aurora-stable,
        # the signed Suite/Codename inside InRelease still fails verification.
        (repo / 'dists' / 'aurora-testing').rename(repo / 'dists' / 'aurora-stable')
        res2 = self.verify_repo(repo, channel='stable')
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn('unexpected Suite', res2.stderr)

    def test_verify_rejects_expired_and_rollback_and_wrong_key(self):
        repo, _ = self.sign_repo('repo-exp', channel='testing', valid_days=7, generation=500)
        meta = json.loads(self.verify_repo(repo, 'testing').stdout)

        # Expired snapshot rejected unless --allow-expired.
        after_expiry = meta['valid_until_epoch'] + 1
        res_exp = self.verify_repo(repo, 'testing', now=after_expiry)
        self.assertNotEqual(res_exp.returncode, 0)
        self.assertIn('expired', res_exp.stderr)
        res_allow = self.verify_repo(repo, 'testing', now=after_expiry, allow_expired=True)
        self.assertEqual(res_allow.returncode, 0, res_allow.stderr)

        # Generation floor enforced.
        res_floor = self.verify_repo(repo, 'testing', min_generation=501)
        self.assertNotEqual(res_floor.returncode, 0)
        self.assertIn('below required floor', res_floor.stderr)

        # Wrong keyring rejected.
        res_key = self.verify_repo(repo, 'testing', keyring=self.other_keyring)
        self.assertNotEqual(res_key.returncode, 0)
        self.assertIn('gpgv failed', res_key.stderr)

        # Tampered Packages digest rejected.
        (repo / 'dists/aurora-testing/main/binary-all/Packages').write_text('tampered\n')
        res_tamper = self.verify_repo(repo, 'testing')
        self.assertNotEqual(res_tamper.returncode, 0)
        self.assertIn('mismatch', res_tamper.stderr)

    # --- Pages Staging (#211, #214) ---

    def _run_stage(self, channels_spec, allow_recovery=False, recovery_reason='', now=None):
        spec_path = self.base / 'channels.json'
        spec_path.write_text(json.dumps(channels_spec), encoding='utf-8')
        site = self.base / f'site-{time.time_ns()}'
        gh_out = self.base / f'gh-out-{time.time_ns()}'
        cmd = [
            sys.executable, str(STAGE_SCRIPT),
            '--keyring', str(self.keyring),
            '--fingerprint', self.fpr,
            '--site', str(site),
            '--asc', str(self.asc),
            '--channels-json', str(spec_path),
            '--github-output', str(gh_out),
        ]
        if allow_recovery:
            cmd += ['--allow-recovery', '--recovery-reason', recovery_reason]
        if now is not None:
            cmd += ['--now', str(now)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return site, gh_out, res

    def test_stage_pages_blocks_testing_replayed_as_stable(self):
        testing_repo, _ = self.sign_repo('t1', channel='testing', generation=100)
        testing_tar = pack_repo_tar(testing_repo, self.base / 'testing.tar')

        # Exact #214 attack: copy testing tarball under a stable-YYYYMMDD.N tag.
        _, _, res = self._run_stage({
            'stable': {
                'tag': 'stable-20261126.1',
                'latest_tag': 'stable-20261126.1',
                'tarball': str(testing_tar),
            },
        })
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('aurora-stable', res.stderr)

        # Even with --allow-recovery, cross-channel replay MUST STILL FAIL.
        _, _, res_rec = self._run_stage(
            {
                'stable': {
                    'tag': 'stable-20261126.1',
                    'latest_tag': 'stable-20261126.1',
                    'tarball': str(testing_tar),
                },
            },
            allow_recovery=True,
            recovery_reason='testing cross-channel bypass',
        )
        self.assertNotEqual(res_rec.returncode, 0)

    def test_stage_pages_blocks_historical_tag_and_live_rollback_and_expiry(self):
        repo_old, _ = self.sign_repo('t-old', channel='testing', valid_days=7, generation=100)
        repo_new, _ = self.sign_repo('t-new', channel='testing', valid_days=7, generation=200)
        tar_old = pack_repo_tar(repo_old, self.base / 't-old.tar')
        tar_new = pack_repo_tar(repo_new, self.base / 't-new.tar')
        live_new_inrelease = repo_new / 'dists/aurora-testing/InRelease'

        # 1. Explicit older tag when latest_tag is newer -> rejected.
        _, _, res_tag = self._run_stage({
            'testing': {
                'tag': 'testing-20261125.1',
                'latest_tag': 'testing-20261126.1',
                'tarball': str(tar_old),
            },
        })
        self.assertNotEqual(res_tag.returncode, 0)
        self.assertIn('refusing rollback', res_tag.stderr)

        # 2. Newer tag name carrying older signed generation below live -> rejected.
        _, _, res_live = self._run_stage({
            'testing': {
                'tag': 'testing-20261126.2',
                'latest_tag': 'testing-20261126.2',
                'tarball': str(tar_old),
                'live_inrelease': str(live_new_inrelease),
            },
        })
        self.assertNotEqual(res_live.returncode, 0)
        self.assertIn('below required floor', res_live.stderr)

        # 3. Expired snapshot rejected without recovery.
        meta_new = json.loads(self.verify_repo(repo_new, 'testing').stdout)
        _, _, res_exp = self._run_stage(
            {
                'testing': {
                    'tag': 'testing-20261126.2',
                    'latest_tag': 'testing-20261126.2',
                    'tarball': str(tar_new),
                },
            },
            now=meta_new['valid_until_epoch'] + 10,
        )
        self.assertNotEqual(res_exp.returncode, 0)
        self.assertIn('expired', res_exp.stderr)

        # 4. Authorized recovery without reason -> rejected; with reason -> allowed.
        _, _, res_noreason = self._run_stage(
            {
                'testing': {
                    'tag': 'testing-20261125.1',
                    'latest_tag': 'testing-20261126.1',
                    'tarball': str(tar_old),
                    'live_inrelease': str(live_new_inrelease),
                },
            },
            allow_recovery=True,
            recovery_reason='   ',
        )
        self.assertNotEqual(res_noreason.returncode, 0)

        site, _, res_ok = self._run_stage(
            {
                'testing': {
                    'tag': 'testing-20261125.1',
                    'latest_tag': 'testing-20261126.1',
                    'tarball': str(tar_old),
                    'live_inrelease': str(live_new_inrelease),
                },
            },
            allow_recovery=True,
            recovery_reason='incident rollback approved by owners',
            now=meta_new['valid_until_epoch'] + 10,
        )
        self.assertEqual(res_ok.returncode, 0, res_ok.stderr)
        self.assertIn('testing/dists/aurora-testing/InRelease', (site / 'index.html').read_text())

    def test_stage_pages_tracks_stable_changed_output(self):
        t_repo, _ = self.sign_repo('t-cur', channel='testing', generation=100)
        s_repo, _ = self.sign_repo('s-cur', channel='stable', generation=100)
        t_tar = pack_repo_tar(t_repo, self.base / 't-cur.tar')
        s_tar = pack_repo_tar(s_repo, self.base / 's-cur.tar')

        # First deployment of stable marks stable_changed=true.
        _, gh_out1, res1 = self._run_stage({
            'testing': {'tag': 'testing-20261126.1', 'latest_tag': 'testing-20261126.1', 'tarball': str(t_tar)},
            'stable': {'tag': 'stable-20261126.1', 'latest_tag': 'stable-20261126.1', 'tarball': str(s_tar)},
        })
        self.assertEqual(res1.returncode, 0, res1.stderr)
        self.assertIn('stable_changed=true', gh_out1.read_text())

        # Redeploying with stable matching currently live stable marks stable_changed=false.
        _, gh_out2, res2 = self._run_stage({
            'testing': {'tag': 'testing-20261126.1', 'latest_tag': 'testing-20261126.1', 'tarball': str(t_tar)},
            'stable': {
                'tag': 'stable-20261126.1',
                'latest_tag': 'stable-20261126.1',
                'tarball': str(s_tar),
                'live_inrelease': str(s_repo / 'dists/aurora-stable/InRelease'),
            },
        })
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertIn('stable_changed=false', gh_out2.read_text())

    # --- Real apt-get + aurora-apt-guard end-to-end tests (#211, #214) ---

    def _make_apt_sandbox(self, repo_uri, suite, keyring_path=None):
        sandbox = self.base / f'apt-{time.time_ns()}'
        for d in ('etc/apt/sources.list.d', 'etc/apt/apt.conf.d', 'etc/apt/preferences.d',
                  'var/lib/apt/lists/partial', 'var/cache/apt/archives/partial',
                  'var/lib/dpkg', 'var/lib/aurora-apt'):
            (sandbox / d).mkdir(parents=True)
        (sandbox / 'var/lib/dpkg/status').write_text('')
        (sandbox / 'etc/apt/sources.list.d/aurora.sources').write_text(
            f'Types: deb\n'
            f'URIs: {repo_uri}\n'
            f'Suites: {suite}\n'
            f'Components: main\n'
            f'Check-Valid-Until: yes\n'
            f'Valid-Until-Max: 604800\n'
            f'Signed-By: {keyring_path or self.keyring}\n',
            encoding='utf-8',
        )
        return sandbox

    def _apt_update_with_guard(self, sandbox, now=None):
        state_file = sandbox / 'var/lib/aurora-apt/floor.json'
        guard_cmd = (
            f'{sys.executable} {GUARD_SCRIPT} '
            f'--state-file {state_file} '
            f'--sources-dir {sandbox}/etc/apt/sources.list.d '
            f'--lists-dir {sandbox}/var/lib/apt/lists'
        )
        if now is not None:
            guard_cmd += f' --now {now}'
        guard_cmd += ' update'
        return subprocess.run(
            [
                'apt-get', 'update',
                '-o', 'APT::Architecture=arm64',
                '-o', f'Dir::Etc={sandbox}/etc/apt',
                '-o', f'Dir::Etc::sourcelist={sandbox}/etc/apt/sources.list',
                '-o', f'Dir::Etc::sourceparts={sandbox}/etc/apt/sources.list.d',
                '-o', f'Dir::State::lists={sandbox}/var/lib/apt/lists',
                '-o', f'Dir::State::status={sandbox}/var/lib/dpkg/status',
                '-o', f'Dir::Cache={sandbox}/var/cache/apt',
                '-o', 'Acquire::Check-Valid-Until=true',
                '-o', 'Acquire::AllowInsecureRepositories=false',
                '-o', f'APT::Update::Post-Invoke-Success::={guard_cmd}',
            ],
            capture_output=True, text=True,
        )

    @unittest.skipUnless(shutil.which('apt-get'), 'requires apt-get')
    def test_apt_guard_enforces_monotonic_floor_and_recovery(self):
        repo_v1, _ = self.sign_repo('apt-v1', channel='testing', generation=1000)
        repo_v2, _ = self.sign_repo('apt-v2', channel='testing', generation=2000)

        live_repo = self.base / 'live_repo'
        shutil.copytree(repo_v1, live_repo)
        sandbox = self._make_apt_sandbox(f'file://{live_repo}', 'aurora-testing')
        state_file = sandbox / 'var/lib/aurora-apt/floor.json'

        # 1. Initial update at generation 1000 succeeds and persists floor.
        res1 = self._apt_update_with_guard(sandbox)
        self.assertEqual(res1.returncode, 0, res1.stderr + res1.stdout)
        state1 = json.loads(state_file.read_text())
        self.assertEqual(state1['channels']['testing']['generation'], 1000)

        # 2. Advance to generation 2000 succeeds and raises floor.
        shutil.rmtree(live_repo)
        shutil.copytree(repo_v2, live_repo)
        res2 = self._apt_update_with_guard(sandbox)
        self.assertEqual(res2.returncode, 0, res2.stderr + res2.stdout)
        state2 = json.loads(state_file.read_text())
        self.assertEqual(state2['channels']['testing']['generation'], 2000)

        # 3. Replay generation 1000 (still cryptographically valid and unexpired!) ->
        #    rejected AND list files quarantined so apt-get install cannot use them.
        shutil.rmtree(live_repo)
        shutil.copytree(repo_v1, live_repo)
        res3 = self._apt_update_with_guard(sandbox)
        self.assertNotEqual(res3.returncode, 0)
        self.assertIn('rollback rejected', res3.stderr)
        remaining = [p.name for p in (sandbox / 'var/lib/apt/lists').iterdir() if p.is_file()]
        self.assertFalse(any('aurora-testing' in n for n in remaining), remaining)

        # 4. Explicit root disaster recovery lowers floor with audit reason, then v1 works.
        res_reset = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT),
             '--state-file', str(state_file),
             'reset-floor', '--channel', 'testing',
             '--generation', '1000', '--date-epoch', '0',
             '--reason', 'emergency rollback drill'],
            capture_output=True, text=True)
        self.assertEqual(res_reset.returncode, 0, res_reset.stderr)
        res4 = self._apt_update_with_guard(sandbox)
        self.assertEqual(res4.returncode, 0, res4.stderr + res4.stdout)

    @unittest.skipUnless(shutil.which('apt-get'), 'requires apt-get')
    def test_apt_guard_rejects_channel_swap_even_when_apt_only_warns(self):
        # Raw apt-get update only warns ("Conflicting distribution") and exits 0 when
        # a signed aurora-testing InRelease is served under dists/aurora-stable/.
        # aurora-apt-guard must hard-fail and quarantine the lists.
        repo, _ = self.sign_repo('swap-repo', channel='testing', generation=3000)
        (repo / 'dists' / 'aurora-testing').rename(repo / 'dists' / 'aurora-stable')
        sandbox = self._make_apt_sandbox(f'file://{repo}', 'aurora-stable')

        res = self._apt_update_with_guard(sandbox)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('unexpected Suite', res.stderr)
        remaining = [p.name for p in (sandbox / 'var/lib/apt/lists').iterdir() if p.is_file()]
        self.assertFalse(any('aurora-stable' in n for n in remaining), remaining)

    @unittest.skipUnless(shutil.which('apt-get'), 'requires apt-get')
    def test_apt_guard_seed_protects_first_update_and_check_mode(self):
        repo_old, _ = self.sign_repo('seed-old', channel='testing', generation=100)
        repo_new, _ = self.sign_repo('seed-new', channel='testing', generation=500)

        sandbox = self._make_apt_sandbox(f'file://{repo_old}', 'aurora-testing')
        state_file = sandbox / 'var/lib/aurora-apt/floor.json'

        # Seed image floor from repo_new (generation 500).
        res_seed = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT),
             '--state-file', str(state_file),
             'seed',
             '--release', str(repo_new / 'dists/aurora-testing/InRelease'),
             '--keyring', str(self.keyring),
             '--channel', 'testing'],
            capture_output=True, text=True)
        self.assertEqual(res_seed.returncode, 0, res_seed.stderr)

        # check mode passes on a freshly seeded image before first apt-get update.
        res_check = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT),
             '--state-file', str(state_file),
             '--sources-dir', str(sandbox / 'etc/apt/sources.list.d'),
             '--lists-dir', str(sandbox / 'var/lib/apt/lists'),
             'check'],
            capture_output=True, text=True)
        self.assertEqual(res_check.returncode, 0, res_check.stderr)

        # Very first apt-get update against older generation 100 is rejected!
        res_first = self._apt_update_with_guard(sandbox)
        self.assertNotEqual(res_first.returncode, 0)
        self.assertIn('rollback rejected', res_first.stderr)

    def test_apt_guard_rejects_unbound_legacy_suite_and_corrupt_state(self):
        sandbox = self._make_apt_sandbox('https://aurorasilicon.org/debian-aurora/testing', 'aurora')
        state_file = sandbox / 'var/lib/aurora-apt/floor.json'
        res = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT),
             '--state-file', str(state_file),
             '--sources-dir', str(sandbox / 'etc/apt/sources.list.d'),
             '--lists-dir', str(sandbox / 'var/lib/apt/lists'),
             'check'],
            capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('unbound or unknown Aurora suite', res.stderr)

        # Corrupt floor.json fails closed.
        state_file.write_text('{not valid json')
        res_corrupt = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT),
             '--state-file', str(state_file),
             '--sources-dir', str(sandbox / 'etc/apt/sources.list.d'),
             '--lists-dir', str(sandbox / 'var/lib/apt/lists'),
             'check'],
            capture_output=True, text=True)
        self.assertNotEqual(res_corrupt.returncode, 0)
        self.assertIn('cannot read floor state', res_corrupt.stderr)


if __name__ == '__main__':
    unittest.main()
