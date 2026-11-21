"""scripts/check-basics.py on synthetic Debian image roots.

alarm-aurora's tests for the same checks, with Debian's file layout, plus
cases for what Debian does differently: /etc/default/locale, common-auth,
the vendor PAM directory and "other", sudo-i, and logind's main file.
"""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check-basics.py'
BOOT = '2025cecd-807c-5835-9ad4-e547cfdeb279'
PREAMBLE = '# Aurora: look for this installation only on the disk GRUB started from.\n'


def load_checker():
    spec = importlib.util.spec_from_file_location('check_basics', SCRIPT)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def write(path, text='', mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    if mode:
        path.chmod(mode)


def link(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, path)


def logos(usr):
    for size in (16, 22, 24, 32, 48, 64, 96, 128, 256, 512):
        for directory, name in (('apps', 'aurora-logo-icon'), ('places', 'start-here')):
            write(usr / f'share/icons/hicolor/{size}x{size}/{directory}/{name}.png', b'\x89PNG\r\n\x1a\n')
    write(usr / 'share/pixmaps/system-logo-white.png', b'\x89PNG\r\n\x1a\n')


# Touch ID as the Debian image should have it: pam-auth-update's common-auth
# offers the fingerprint to sudo, sudo -i and polkit only, in front of the
# password; the lock screens use their packages' fingerprint stacks; a short
# power-button press suspends.
COMMON_AUTH_TOUCHID = (
    'auth\t[success=ignore default=1]\tpam_succeed_if.so service in sudo:sudo-i:polkit-1 quiet\n'
    'auth\t[success=2 default=ignore]\tpam_fprintd.so\n'
    'auth\t[success=1 default=ignore]\tpam_unix.so nullok\n'
    'auth\trequisite\t\t\tpam_deny.so\n'
    'auth\trequired\t\t\tpam_permit.so\n')
# Debian's own common-auth, before any fingerprint profile.
COMMON_AUTH = ('auth\t[success=1 default=ignore]\tpam_unix.so nullok\n'
               'auth\trequisite\t\t\tpam_deny.so\n'
               'auth\trequired\t\t\tpam_permit.so\n')
STACK = '@include common-auth\n@include common-account\n'
FPRINTD = 'auth sufficient pam_fprintd.so\n'
LOGIN = ('auth optional pam_faildelay.so delay=3000000\nauth requisite pam_nologin.so\n'
         '@include common-auth\nauth optional pam_group.so\n@include common-account\n')
SU = 'auth sufficient pam_rootok.so\n@include common-auth\n@include common-account\n'
# gdm-password, kde and plasmalogin as Debian ships them (auth lines).
GREETER = ('auth requisite pam_nologin.so\nauth required pam_succeed_if.so user != root quiet_success\n'
           '@include common-auth\n-auth optional pam_kwallet5.so\n')
# gdm-fingerprint and kde-fingerprint as Debian ships them (auth lines).
LOCK = ('auth requisite pam_nologin.so\nauth required pam_succeed_if.so user != root quiet_success\n'
        'auth required pam_fprintd.so\nauth optional pam_gnome_keyring.so\n')
LOGIND_DEFAULTS = '# See logind.conf(5).\n[Login]\n#HandlePowerKey=poweroff\n#HandleLidSwitch=suspend\n'
LOGIND = '[Login]\nHandlePowerKey=suspend\nHandlePowerKeyLongPress=poweroff\n'
SEP_DROP_IN = 'usr/lib/systemd/logind.conf.d/05-aurora-sep.conf'
POWERDEVIL = ''.join(f'[{group}][SuspendAndShutdown]\nPowerButtonAction=1\n'
                     for group in ('AC', 'Battery', 'LowBattery'))


def touchid_files(root, profile):
    pam = root / 'etc/pam.d'
    write(pam / 'common-auth', COMMON_AUTH_TOUCHID)
    write(pam / 'common-account', 'account required pam_unix.so\n')
    write(pam / 'other', STACK + '@include common-password\n@include common-session\n')
    write(pam / 'sudo', 'session required pam_limits.so\n' + STACK)
    write(pam / 'sudo-i', 'session required pam_limits.so\n' + STACK)
    write(root / 'usr/lib/pam.d/polkit-1', STACK)
    write(pam / 'login', LOGIN)
    write(pam / 'su', SU)
    write(pam / 'su-l', SU)
    write(pam / 'sshd', STACK)
    if profile == 'gnome':
        write(pam / 'gdm-fingerprint', LOCK)
        write(pam / 'gdm-password', GREETER)
    if profile == 'kde':
        write(pam / 'kde-fingerprint', LOCK)
        write(pam / 'kde', GREETER)
        write(root / 'usr/lib/pam.d/plasmalogin', GREETER)
        write(root / 'etc/xdg/powerdevilrc', POWERDEVIL)
    write(root / 'etc/systemd/logind.conf', LOGIND_DEFAULTS)
    write(root / SEP_DROP_IN, LOGIND)


class CheckBasicsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def fresh(self):
        self.temporary.cleanup()
        self.setUp()

    def check(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    def desktop_root(self, profile):
        root = self.base / 'root'
        u, e = root / 'usr', root / 'etc'
        # Debian's merged /usr.
        link(root / 'bin', 'usr/bin')
        link(root / 'lib', 'usr/lib')
        write(e / 'default/locale', 'LANG=en_US.UTF-8\n')
        write(e / 'locale.conf', 'LANG=en_US.UTF-8\n')
        write(u / 'lib/locale/locale-archive', b'\0en_US.utf8\0')
        link(e / 'systemd/system/multi-user.target.wants/NetworkManager.service',
             '/usr/lib/systemd/system/NetworkManager.service')
        touchid_files(root, profile)
        if profile != 'minimal':
            logos(u)
        if profile == 'gnome':
            write(u / 'bin/gnome-terminal', mode=0o755)
            write(u / 'share/applications/org.gnome.Terminal.desktop')
            write(u / 'bin/gnome-control-center', mode=0o755)
            write(u / 'share/backgrounds/gnome/adwaita-l.jxl')
            write(u / 'share/glib-2.0/schemas/org.gnome.desktop.background.gschema.xml',
                  "<key name=\"picture-uri\" type=\"s\">\n<default>'file:///usr/share/backgrounds/gnome/adwaita-l.jxl'</default>")
        if profile == 'kde':
            write(u / 'bin/konsole', mode=0o755)
            write(u / 'share/applications/org.kde.konsole.desktop')
            write(u / 'share/applications/kcm_networkmanagement.desktop')
            for name in ('Next', 'Air', 'Horos', 'Altai', 'Kokkini', 'Canopee', 'Cluster', 'Flow', 'Mountain'):
                write(u / f'share/wallpapers/{name}/contents/images/1920x1080.png')
            # systemctl enable plasmalogin.service links its Alias=.
            write(u / 'lib/systemd/system/plasmalogin.service', '[Service]\nExecStart=/usr/bin/plasmalogin\n')
            link(e / 'systemd/system/display-manager.service', '/usr/lib/systemd/system/plasmalogin.service')
        return root

    def boot(self):
        esp, boot = self.base / 'esp', self.base / 'boot'
        write(esp / 'EFI/BOOT/BOOTAA64.EFI', b'MZ\0/EFI/BOOT\0')
        write(esp / 'EFI/BOOT/grub.cfg', PREAMBLE + f'probe --set=aurora_uuid --fs-uuid "($aurora_disk,gpt$n)"\n'
              f'  search --no-floppy --fs-uuid --set=root --hint="$aurora_boot" {BOOT}\n')
        write(boot / 'grub/grub.cfg', f'search --no-floppy --fs-uuid --set=root --hint="${{aurora_disk}}," {BOOT}\n')
        return ['--esp', str(esp), '--boot-dir', str(boot), '--boot-uuid', BOOT]

    def assert_passes(self, profile, mutate=lambda root: None):
        root = self.desktop_root(profile)
        mutate(root)
        result = self.check('--profile', profile, '--root', str(root))
        self.assertEqual(result.returncode, 0, result.stdout)
        return result

    def assert_fails(self, profile, mutate, expected):
        root = self.desktop_root(profile)
        boot = self.boot()
        mutate(root)
        result = self.check('--profile', profile, '--root', str(root), *boot)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stdout)

    def test_complete_images_pass(self):
        for profile in ('gnome', 'kde', 'minimal'):
            with self.subTest(profile=profile):
                self.fresh()
                root = self.desktop_root(profile)
                result = self.check('--profile', profile, '--root', str(root), *self.boot())
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('FAIL', result.stdout)

    def test_nothing_to_check_is_a_usage_error(self):
        self.assertEqual(self.check('--profile', 'minimal').returncode, 2)
        self.assertEqual(self.check('--profile', 'minimal', '--esp', str(self.base)).returncode, 2)

    # GL selection

    def test_global_gl_selector_fails(self):
        self.assert_fails('gnome', lambda root: write(root / 'etc/environment',
                          'MESA_LOADER_DRIVER_OVERRIDE="zink"\n'), 'global MESA_LOADER_DRIVER_OVERRIDE')

    def test_global_gallium_environment_d_fails(self):
        self.assert_fails('minimal', lambda root: write(root / 'usr/lib/environment.d/90-gl.conf',
                          "export GALLIUM_DRIVER='zink'\n"), 'global GALLIUM_DRIVER')

    def test_no_gl_selector_or_empty_value_passes(self):
        def mutate(root):
            write(root / 'etc/environment', '# MESA_LOADER_DRIVER_OVERRIDE=zink\nLANG=en_US.UTF-8\n')
            write(root / 'etc/environment.d/90-gl.conf', 'GALLIUM_DRIVER=""\n')
        self.assert_passes('gnome', mutate)

    # Locale

    def test_c_locale_fails(self):
        self.assert_fails('gnome', lambda root: write(root / 'etc/default/locale', 'LANG=C\n'),
                          'locale: FAIL: no UTF-8 default locale: /etc/default/locale has LANG=C')

    def test_locale_conf_must_also_be_utf8(self):
        self.assert_fails('minimal', lambda root: (root / 'etc/locale.conf').unlink(),
                          'no UTF-8 default locale: /etc/locale.conf has LANG=(unset)')

    def test_ungenerated_locale_fails(self):
        self.assert_fails('minimal', lambda root: write(root / 'usr/lib/locale/locale-archive', b'\0de_DE.utf8\0'),
                          'is not generated')

    def test_locale_directory_or_c_utf8_passes(self):
        def directory(root):
            (root / 'usr/lib/locale/locale-archive').unlink()
            write(root / 'usr/lib/locale/en_US.utf8/LC_CTYPE')
        self.assert_passes('minimal', directory)
        self.fresh()

        def c_utf8(root):
            (root / 'usr/lib/locale/locale-archive').unlink()
            for name in ('etc/default/locale', 'etc/locale.conf'):
                write(root / name, 'LANG="C.UTF-8"\n')
        self.assert_passes('minimal', c_utf8)

    # Logos, terminal, wallpaper

    def test_missing_launcher_icon_fails(self):
        self.assert_fails('kde', lambda root: (
            root / 'usr/share/icons/hicolor/32x32/places/start-here.png').unlink(), 'logos: FAIL')

    def test_corrupt_about_logo_fails(self):
        self.assert_fails('kde', lambda root: write(
            root / 'usr/share/pixmaps/system-logo-white.png', b'broken'), 'logos: FAIL')

    def test_missing_terminal_fails(self):
        self.assert_fails('kde', lambda root: (root / 'usr/bin/konsole').unlink(), 'terminal: FAIL')

    def test_gnome_console_is_a_terminal(self):
        def mutate(root):
            (root / 'usr/bin/gnome-terminal').unlink()
            write(root / 'usr/bin/kgx', mode=0o755)
            write(root / 'usr/share/applications/org.gnome.Console.desktop')
        self.assert_passes('gnome', mutate)

    def test_terminal_without_launcher_fails(self):
        self.assert_fails('gnome', lambda root: (root / 'usr/share/applications/org.gnome.Terminal.desktop').unlink(),
                          'no terminal with a launcher')

    def test_missing_gnome_backgrounds_fails(self):
        self.assert_fails('gnome', lambda root: (root / 'usr/share/backgrounds/gnome/adwaita-l.jxl').unlink(),
                          'gnome-backgrounds')

    def test_default_gnome_picture_must_exist(self):
        def mutate(root):
            write(root / 'usr/share/glib-2.0/schemas/10_vendor.gschema.override',
                  "[org.gnome.desktop.background]\npicture-uri='file:///usr/share/backgrounds/vendor/missing.png'\n")
        self.assert_fails('gnome', mutate, 'does not exist')

    def test_desktop_base_picture_through_its_alternative_passes(self):
        # Debian's desktop-base points the default at its active theme, an
        # alternatives symlink chain inside the image.
        def mutate(root):
            write(root / 'usr/share/glib-2.0/schemas/10_desktop-base.gschema.override',
                  "[org.gnome.desktop.background]\npicture-uri='file:///usr/share/desktop-base/active-theme/"
                  "wallpaper/contents/images/1920x1080.svg'\n")
            write(root / 'usr/share/desktop-base/ceratopsian-theme/wallpaper/contents/images/1920x1080.svg')
            link(root / 'usr/share/desktop-base/active-theme', '/etc/alternatives/desktop-theme')
            link(root / 'etc/alternatives/desktop-theme', '/usr/share/desktop-base/ceratopsian-theme')
        self.assert_passes('gnome', mutate)

    def test_missing_plasma_wallpapers_fails(self):
        def mutate(root):
            # What plasma-workspace alone ships: Next, Air and Horos.
            for name in ('Altai', 'Kokkini', 'Canopee', 'Cluster', 'Flow', 'Mountain'):
                (root / f'usr/share/wallpapers/{name}/contents/images/1920x1080.png').unlink()
        self.assert_fails('kde', mutate, 'plasma-workspace-wallpapers')

    # Network

    def test_disabled_networkmanager_fails(self):
        self.assert_fails('minimal', lambda root: (
            root / 'etc/systemd/system/multi-user.target.wants/NetworkManager.service').unlink(), 'network: FAIL')

    def test_desktop_network_settings_are_required(self):
        self.assert_fails('gnome', lambda root: (root / 'usr/bin/gnome-control-center').unlink(), 'GNOME Settings')
        self.fresh()
        self.assert_fails('kde', lambda root: (root / 'usr/share/applications/kcm_networkmanagement.desktop').unlink(),
                          'plasma-nm')

    # Lid

    def test_lid_policy_and_masked_sleep_fail(self):
        self.assert_fails('minimal', lambda root: write(root / 'etc/systemd/logind.conf.d/10-lid.conf',
                                                         '[Login]\nHandleLidSwitch=ignore\n'), 'HandleLidSwitch=ignore')
        self.fresh()
        self.assert_fails('minimal', lambda root: link(root / 'etc/systemd/system/suspend.target', '/dev/null'),
                          'suspend.target is masked')

    def test_lid_suspend_drop_in_passes(self):
        # aurora-m5-platform-config's drop-in.
        self.assert_passes('minimal', lambda root: write(
            root / 'etc/systemd/logind.conf.d/90-aurora-m5-lid.conf',
            '[Login]\nHandleLidSwitch=suspend\nHandleLidSwitchExternalPower=suspend\n'))

    # ssh

    def test_enabled_ssh_fails(self):
        for wants, unit in (('multi-user.target.wants', 'ssh.service'), ('sockets.target.wants', 'ssh.socket'),
                            ('multi-user.target.wants', 'sshd.service')):
            with self.subTest(unit=unit):
                self.fresh()
                self.assert_fails('kde', lambda root: link(root / f'etc/systemd/system/{wants}/{unit}',
                                                           f'/usr/lib/systemd/system/{unit}'), f'{unit} is enabled')

    def test_installed_but_disabled_ssh_passes(self):
        result = self.assert_passes('minimal', lambda root: write(
            root / 'usr/lib/systemd/system/ssh.service', '[Service]\nExecStart=/usr/sbin/sshd -D\n'))
        self.assertIn('ssh: ok', result.stdout)

    # Unit modes

    def test_executable_unit_or_drop_in_fails(self):
        for name in ('usr/lib/systemd/system/macsmc-battery-charge-control-end-threshold.path',
                     'usr/lib/systemd/user/drkonqi-sentry-postman.path.d/50-aurora-ordering.conf',
                     'etc/systemd/system/ssh.service.d/10-aurora-host-keys.conf'):
            with self.subTest(name=name):
                self.fresh()
                self.assert_fails('minimal', lambda root: write(root / name, '[Unit]\n', mode=0o755),
                                  f'/{name} is marked executable')

    def test_plain_units_and_drop_ins_pass(self):
        def mutate(root):
            write(root / 'usr/lib/systemd/system/example.service', '[Service]\n', mode=0o644)
            write(root / 'usr/lib/systemd/system/example.service.d/50-example.conf', '[Unit]\n', mode=0o644)
        self.assertIn('units: ok', self.assert_passes('minimal', mutate).stdout)

    # Greeter

    def test_kde_signs_in_with_plasma_login(self):
        self.assertIn('greeter: ok', self.assert_passes('kde').stdout)

    def test_kde_with_sddm_fails(self):
        def mutate(root):
            write(root / 'usr/lib/systemd/system/sddm.service', '[Service]\nExecStart=/usr/bin/sddm\n')
            (root / 'etc/systemd/system/display-manager.service').unlink()
            link(root / 'etc/systemd/system/display-manager.service', '/usr/lib/systemd/system/sddm.service')
        self.assert_fails('kde', mutate, 'the display manager is sddm.service, not Plasma Login')

    def test_kde_without_a_display_manager_fails(self):
        self.assert_fails('kde', lambda root: (root / 'etc/systemd/system/display-manager.service').unlink(),
                          'no display manager is enabled')

    def test_gnome_and_minimal_have_no_greeter_requirement(self):
        for profile in ('gnome', 'minimal'):
            with self.subTest(profile=profile):
                self.fresh()
                self.assertIn('greeter: ok', self.assert_passes(profile).stdout)

    # Boot (the installer's EFI and /boot files)

    def test_core_with_an_early_uuid_search_fails(self):
        self.assert_fails('minimal', lambda root: write(self.base / 'esp/EFI/BOOT/BOOTAA64.EFI',
                                                         f'MZ\0/EFI/BOOT\0search.fs_uuid {BOOT} root\0'.encode()),
                          'all-disk search')

    def test_partition_numbered_core_fails(self):
        self.assert_fails('minimal', lambda root: write(self.base / 'esp/EFI/BOOT/BOOTAA64.EFI',
                                                         b'MZ\0(,gpt2)/grub\0'), 'partition number')

    def test_unhinted_search_fails(self):
        self.assert_fails('minimal', lambda root: write(self.base / 'boot/grub/grub.cfg',
                                                         f'search --no-floppy --fs-uuid --set=root {BOOT}\n'),
                          'without a hint')

    def test_stub_must_name_the_boot_uuid(self):
        self.assert_fails('minimal', lambda root: write(self.base / 'esp/EFI/BOOT/grub.cfg', PREAMBLE),
                          'by UUID on the startup disk')

    @unittest.skipUnless(shutil.which('mkfs.ext4') and shutil.which('debugfs'), 'requires e2fsprogs')
    def test_boot_filesystem_image_is_read_with_debugfs(self):
        # build-image passes the installer's boot.img, not a directory.
        arguments = self.boot()
        image = self.base / 'boot.img'
        for expected, contents in ((0, self.base / 'boot'), (1, self.base / 'empty')):
            with self.subTest(expected=expected):
                contents.mkdir(exist_ok=True)
                image.unlink(missing_ok=True)
                subprocess.run(['mkfs.ext4', '-q', '-F', '-d', str(contents), str(image), '8M'], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                result = self.check('--profile', 'minimal', *arguments[:2], '--boot-image', str(image),
                                    '--boot-uuid', BOOT)
                self.assertEqual(result.returncode, expected, result.stdout)
                if expected:
                    self.assertIn('/boot/grub/grub.cfg is missing', result.stdout)

    # Touch ID: PAM

    def test_fingerprint_for_every_common_auth_service_fails(self):
        # pam_fprintd in common-auth without the service test reaches every
        # service that includes it.
        ungated = COMMON_AUTH_TOUCHID.split('\n', 1)[1]
        expected = {'minimal': 'login offers a fingerprint; su offers a fingerprint; su-l offers a fingerprint; '
                               'sshd offers a fingerprint',
                    'gnome': 'sshd offers a fingerprint; gdm-password offers a fingerprint',
                    'kde': 'plasmalogin offers a fingerprint; kde offers a fingerprint'}
        for profile, message in expected.items():
            with self.subTest(profile=profile):
                self.fresh()
                self.assert_fails(profile, lambda root: write(root / 'etc/pam.d/common-auth', ungated), message)

    def test_fingerprint_in_front_of_sudo_and_polkit_passes(self):
        # The policy, not one implementation: alarm-aurora's sufficient line
        # in each service file satisfies it as well.
        def mutate(root):
            write(root / 'etc/pam.d/common-auth', COMMON_AUTH)
            for name in ('sudo', 'sudo-i', 'polkit-1'):
                write(root / 'etc/pam.d' / name, FPRINTD + STACK)
        for profile in ('minimal', 'kde'):
            with self.subTest(profile=profile):
                self.fresh()
                self.assert_passes(profile, mutate)

    def test_sudo_and_polkit_without_fingerprint_fail(self):
        self.assert_fails('gnome', lambda root: write(root / 'etc/pam.d/common-auth', COMMON_AUTH),
                          'sudo does not offer a fingerprint; sudo-i does not offer a fingerprint; '
                          'polkit-1 does not offer a fingerprint')

    def test_fingerprint_that_replaces_the_password_fails(self):
        self.assert_fails('minimal', lambda root: write(root / 'etc/pam.d/sudo', 'auth required pam_fprintd.so\n' + STACK),
                          'sudo has no password after the fingerprint')
        self.fresh()
        # A fingerprint whose failure ends authentication.
        self.assert_fails('minimal', lambda root: write(root / 'etc/pam.d/common-auth', COMMON_AUTH_TOUCHID.replace(
            '[success=2 default=ignore]', '[success=2 default=die]')), 'polkit-1 has no password after the fingerprint')

    def test_fingerprint_at_the_login_screen_fails(self):
        self.assert_fails('kde', lambda root: write(root / 'usr/lib/pam.d/plasmalogin', FPRINTD + GREETER),
                          'plasmalogin offers a fingerprint')

    def test_lock_screen_without_fingerprint_fails(self):
        self.assert_fails('kde', lambda root: write(root / 'etc/pam.d/kde-fingerprint', 'auth required pam_deny.so\n'),
                          'kde-fingerprint does not offer a fingerprint')
        self.fresh()
        self.assert_fails('gnome', lambda root: (root / 'etc/pam.d/gdm-fingerprint').unlink(),
                          'PAM service gdm-fingerprint is missing')

    def test_etc_pam_file_overrides_the_vendor_one(self):
        self.assert_fails('minimal', lambda root: write(root / 'etc/pam.d/polkit-1', 'auth required pam_unix.so\n'),
                          'polkit-1 does not offer a fingerprint')
        self.fresh()
        self.assert_fails('minimal', lambda root: (root / 'usr/lib/pam.d/polkit-1').unlink(),
                          'PAM service polkit-1 is missing')

    def test_service_without_a_file_runs_as_other(self):
        # Debian's "other" includes common-auth, whose service test keeps
        # the fingerprint to sudo and polkit.
        self.assert_passes('kde', lambda root: (root / 'etc/pam.d/kde').unlink())
        self.fresh()

        def mutate(root):
            (root / 'etc/pam.d/kde').unlink()
            write(root / 'etc/pam.d/other', FPRINTD + STACK)
        self.assert_fails('kde', mutate, 'kde offers a fingerprint')

    def test_missing_console_login_fails(self):
        self.assert_fails('minimal', lambda root: (root / 'etc/pam.d/login').unlink(), 'PAM service login is missing')

    # Touch ID: the power button

    def test_power_key_that_powers_off_fails(self):
        self.assert_fails('minimal', lambda root: (root / SEP_DROP_IN).unlink(),
                          'logind HandlePowerKey=(default), not suspend or ignore')
        self.fresh()
        self.assert_fails('gnome', lambda root: write(root / 'etc/systemd/logind.conf.d/90-local.conf',
                          '[Login]\nHandlePowerKey=poweroff\n'), 'logind HandlePowerKey=poweroff, not suspend or ignore')

    def test_explicit_power_key_suspend_or_ignore_passes(self):
        for profile in ('minimal', 'gnome', 'kde'):
            for value in ('suspend', 'ignore'):
                with self.subTest(profile=profile, value=value):
                    self.fresh()
                    self.assert_passes(profile, lambda root: write(
                        root / 'etc/systemd/logind.conf.d/10-ignore-power-button.conf',
                        f'[Login]\nHandlePowerKey={value}\n'))

    def test_empty_power_key_override_fails(self):
        self.assert_fails('minimal', lambda root: write(root / 'etc/systemd/logind.conf.d/90-local.conf',
                          '[Login]\nHandlePowerKey=\n'), 'logind HandlePowerKey=(default), not suspend or ignore')

    def test_long_press_must_still_power_off(self):
        for value in ('ignore', ''):
            with self.subTest(value=value):
                self.fresh()
                self.assert_fails('minimal', lambda root: write(root / 'etc/systemd/logind.conf.d/90-local.conf',
                                  f'[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress={value}\n'),
                                  f'logind HandlePowerKeyLongPress={value or "(default)"}, not poweroff')

    def test_etc_logind_conf_replaces_the_vendor_main_file(self):
        def vendor_main(root):
            (root / SEP_DROP_IN).unlink()
            write(root / 'usr/lib/systemd/logind.conf', LOGIND)
        # Debian ships /etc/systemd/logind.conf, so logind never reads the
        # vendor file.
        self.assert_fails('minimal', vendor_main, 'logind HandlePowerKey=(default)')
        self.fresh()
        self.assert_passes('minimal', lambda root: (vendor_main(root), (root / 'etc/systemd/logind.conf').unlink()))

    def test_same_name_etc_drop_in_replaces_the_vendor_one(self):
        self.assert_fails('minimal', lambda root: write(root / 'etc/systemd/logind.conf.d/05-aurora-sep.conf',
                                                         '[Login]\nHandlePowerKey=ignore\n'),
                          'logind HandlePowerKeyLongPress=(default), not poweroff')

    def test_plasma_power_button_must_suspend(self):
        self.assert_fails('kde', lambda root: (root / 'etc/xdg/powerdevilrc').unlink(),
                          'Plasma AC power button action is the logout screen, not suspend')


class LogindPrecedenceTests(unittest.TestCase):
    """check-basics reads logind's configuration as systemd does."""

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'requires systemd-analyze')
    def test_matches_systemd(self):
        checker = load_checker()
        vendor, local, etc = ('usr/lib/systemd/logind.conf.d/', 'usr/local/lib/systemd/logind.conf.d/',
                              'etc/systemd/logind.conf.d/')
        ignore = '[Login]\nHandlePowerKey=ignore\n'
        cases = {
            'vendor-drop-in-alone': {vendor + '05-aurora-sep.conf': LOGIND},
            'later-etc-drop-in-wins': {vendor + '05-aurora-sep.conf': LOGIND, etc + '10-ignore.conf': ignore},
            'same-name-etc-wins': {vendor + '05-aurora-sep.conf': LOGIND, etc + '05-aurora-sep.conf': ignore},
            'same-name-local-wins': {vendor + '05-aurora-sep.conf': LOGIND, local + '05-aurora-sep.conf': ignore},
            'etc-main-file-wins': {'etc/systemd/logind.conf': ignore, 'usr/lib/systemd/logind.conf': LOGIND},
            'vendor-main-file': {'usr/lib/systemd/logind.conf': LOGIND, etc + '90-local.conf': ignore},
        }
        with tempfile.TemporaryDirectory() as temporary:
            for name, files in cases.items():
                with self.subTest(case=name):
                    root = Path(temporary) / name
                    for path, text in files.items():
                        write(root / path, text)
                    result = subprocess.run(['systemd-analyze', '--root=' + str(root), 'cat-config',
                                             'systemd/logind.conf'], capture_output=True, text=True, check=True)
                    values = {}
                    for line in result.stdout.splitlines():
                        if line.startswith(('HandlePowerKey=', 'HandlePowerKeyLongPress=')):
                            key, _, value = line.partition('=')
                            values[key] = value
                    texts = checker.logind_texts(checker.Root(root))
                    for key in ('HandlePowerKey', 'HandlePowerKeyLongPress'):
                        self.assertEqual(checker.config_value(texts, '[Login]', key), values.get(key), result.stdout)


if __name__ == '__main__':
    unittest.main()
