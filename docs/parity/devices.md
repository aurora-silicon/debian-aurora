# Secure Enclave, Touch ID and device services

Debian testing (forky) counterparts of alarm-aurora's Secure Enclave, Touch ID and device-service packages. All of them build with `scripts/build-package --cross`. In cross mode sbuild switches on the `cross nocheck` profiles, so no package ran its tests during these builds. The Python and shell suites of aurora-xart, aurora-diag and aurora-wifi-firmware were run on the host from the pinned sources and passed. libfprint and fprintd were also built emulated (arm64 build root under qemu, no `--cross`), which runs their tests: see their sections.

## Summary

| alarm-aurora | Debian source | Binary packages | Kind | Version | Status |
| --- | --- | --- | --- | --- | --- |
| aurora-sep | aurora-sep | aurora-sep (all) | native | 1.28 | built |
| aurora-sep-luks | aurora-sep-luks | aurora-sep-luks | upstream | 0.3.0-1 | built |
| aurora-sep-sk | aurora-sep-sk | aurora-sep-sk | upstream | 0.1.0-1 | built |
| aurora-fido | aurora-fido | aurora-fido | upstream | 0.2.0-1 | built |
| aurora-touchid-rearm | aurora-touchid-rearm | aurora-touchid-rearm | upstream | 1-1 | built |
| libfprint-aurora | libfprint | libfprint-2-2, libfprint-2-dev, gir1.2-fprint-2.0, libfprint-2-doc, libfprint-2-tests | upstream (Debian's packaging) | 1:1.94.100-1+aurora1 | built |
| fprintd-aurora | fprintd | fprintd, libpam-fprintd, fprintd-doc | rebuild | 1.94.5-4+aurora1 | built (cross) |
| aurora-xart | aurora-xart | aurora-xart (all) | upstream | 0.2.0-1 | built |
| aurora-bless (+nvram, btsync, panel-nits) | aurora-bless | aurora-bless, aurora-nvram, aurora-btsync, aurora-panel-nits | upstream, network | 0.4.4.aurora5-1 | built |
| aurora-diag | aurora-diag | aurora-diag (all) | upstream | 0.5.0-1 | built |
| aurora-kbd-light | aurora-kbd-light | aurora-kbd-light | upstream | 0.1.0-1 | built |
| aurora-camera-denoise | aurora-camera-denoise | aurora-camera-denoise | upstream | 0.1.0-1 | built |
| aurora-neo-platform-config | aurora-neo-platform-config | aurora-neo-platform-config (all) | upstream | 0.1.0-1 | built |
| aurora-wifi-firmware | aurora-wifi-firmware | aurora-wifi-firmware (all) | upstream | 0.2-1 | built |
| aurora-m5-platform-config | aurora-m5-platform-config | aurora-m5-platform-config (all) | native | 1 | built |

## Touch ID PAM policy

alarm-aurora's policy (scripts/check-basics.py, `touchid`):

- sudo and polkit-1 offer a fingerprint as `sufficient` and still reach the password.
- login, su, su-l, sshd, gdm-password, plasmalogin and kde must not offer it.
- The lock screens offer it through their own stacks, gdm-fingerprint and kde-fingerprint.

On alarm, aurora-sep's touchid-pam pacman hook puts `-auth sufficient pam_fprintd.so` into /etc/pam.d/sudo and /etc/pam.d/polkit-1 only. It also appends the re-arm line to system-auth.

Debian builds every `common-*` file with pam-auth-update. Debian's own libpam-fprintd profile is off by default (`Default: no`). When an owner turns it on, it adds `pam_fprintd.so` to common-auth, so every service that includes common-auth offers a fingerprint. That would include login, su, sshd, gdm-password, kde and plasmalogin.

The Debian packages follow alarm's per-service policy without editing any service's own file:

- **Fingerprint (fprintd rebuild, packaging.patch).** The Aurora build of `/usr/share/pam-configs/fprintd` is on by default (`Default: yes`) and gates pam_fprintd on the service name:

  ```
  Auth-Type: Primary
  Auth:
  	[success=ignore default=1]	pam_succeed_if.so service in sudo:sudo-i:polkit-1 quiet
  	[success=end default=ignore]	pam_fprintd.so
  ```

  pam-auth-update writes this as the first lines of common-auth, ahead of pam_unix. Every service other than sudo, sudo -i and polkit-1 skips the fingerprint line. If pam_succeed_if errs, the line is skipped, so the failure mode is password-only.
  - pam_fprintd keeps alarm's defaults (no `max-tries=1 timeout=10` as in Debian's profile).
  - `sudo-i` is included because Debian's sudo uses that service for `sudo -i`, where Arch's uses `sudo`.
  - The owner turns the profile off with `pam-auth-update`, and the choice survives updates. This matches alarm's "a line the owner removed is left as it is".
- **Re-arm (aurora-touchid-rearm).** `/usr/share/pam-configs/aurora-touchid-rearm` adds `optional pam_aurora_touchid.so` to common-auth's additional block (`Auth-Type: Additional`).
  - The additional block runs only after the primary block accepted the login.
  - After a fingerprint there is no PAM_AUTHTOK, so the module does nothing; this matches upstream's README.
- **Disk password (aurora-sep-luks).** `/usr/share/pam-configs/aurora-sep-fde` adds `optional pam_aurora_sep_fde.so` to common-password's additional block. That block is reached only when pam_unix changed the password, which is what alarm's sep-fde-pam rewrite of system-auth achieves.

Result (pam-auth-update run into a scratch root, then the Debian stacks of sudo, sudo-i, login, su, su-l, sshd, polkit-1, gdm3 51.1, libkscreenlocker6 and plasma-login-manager 6.7.4):

- alarm's check-basics `pam_fingerprint()`:
  - sudo, sudo-i and polkit-1 offer a fingerprint, with the password after it.
  - gdm-fingerprint and kde-fingerprint offer one.
  - login, su, su-l, sshd, gdm-password, plasmalogin and kde do not.
- The same stacks were also run through the real libpam (pam_wrapper, with stand-in fprintd, unix and re-arm modules):
  - sudo, sudo-i and polkit-1 succeed on a fingerprint, and fall back to the password when the fingerprint fails.
  - The other seven services never call pam_fprintd.
  - The re-arm module runs after every accepted login and sees a password only after pam_unix.

Caveat: pam-auth-update enables a `Default: yes` profile only the first time it sees the profile name. A system that had Debian's libpam-fprintd installed (profile "fprintd" seen and off) keeps fingerprint off after upgrading to Aurora's; `sudo pam-auth-update --enable fprintd` turns it on. Fresh Aurora images get it on.

## Units

Enabled as alarm-aurora's presets enable them, with dh_installsystemd. No package ships a preset file; aurora-boot should carry these lines:

```
enable aurora-sep.timer
enable aurora-touchid-rearm.socket
enable aurora-touchid-boot.service
enable aurora-kbd-light.service
enable aurora-wifi-firmware.service
```

and as a user preset `enable aurora-camera-denoise.service`.

Units with an `[Install]` section that stay disabled:

- aurora-sep-greeter-fingerprint.service
- aurora-btsync.service
- aurora-fido.service
- the aurora-passkeyd user unit

aurora-fido's upstream `make install` ships disable presets for its two units, which are kept as alarm-aurora keeps them. If aurora-boot's presets do not end in a catch-all disable, add `disable` lines for the units above.

Static links kept as on alarm:

- aurora-sep-initrd-check.service in multi-user.target.wants (aurora-sep-luks, from upstream's Makefile)
- aurora-m5-sleep-policy.service in sysinit.target.wants

Start and restart behaviour:

- aurora-sep starts nothing at installation and restarts nothing on upgrade (`--no-start`): the enclave takes one attach per boot.
- aurora-touchid-boot.service is not started at installation; it applies the setting at the next boot, and alarm does not start it either.
- aurora-touchid-rearm.socket starts at once, as alarm's post_install does.

## Packages

### aurora-sep (native, 1.28)

- **Why native.** alarm-aurora's recipe has no archive: its sources are files from tools/aurora-sep in aurora-silicon/linux (provenance.json) plus alarm's adaptations. The Debian recipe directory holds the same files.
- **Install paths.** Units, scripts and drop-ins go where alarm puts them: /usr/libexec, the fprintd.service.d drop-ins, `05-aurora-sep.conf` in logind.conf.d, `20-aurora-suspend.conf` in sleep.conf.d, the suspend unit drop-ins, `/etc/xdg/powerdevilrc` (conffile) and modprobe.d.
- **Depends:**
  - aurora-touchid-rearm and aurora-xart
  - `fprintd-aurora (>= 1.94.5-4+aurora1)` and `libfprint-aurora (>= 1:1.94.100-1+aurora1)`, which Aurora's fprintd and libfprint-2-2 provide; a later Debian upload of libfprint or fprintd cannot satisfy them
  - `libpam-fprintd (>= 1.94.5-4+aurora1)`
  - keyutils, kmod, python3 and systemd
- **Suggests:** libglib2.0-bin (gresource, for the greeter unit).
- **postinst.** Runs `systemctl daemon-reload` so that the fprintd and suspend drop-ins apply at once, as systemd's pacman hook does on alarm; it starts nothing.
- **Deviations from alarm-aurora:**
  - touchid-pam and its pacman hook are not shipped. The PAM lines come from the libpam-fprintd and aurora-touchid-rearm profiles above.
  - aurora-touchid-setup is in /usr/sbin, Debian's place for admin commands, and its unit's `ExecStart=/usr/sbin/...` is kept. alarm moves it to /usr/bin, which is the same directory on Arch.
  - The fprintd path in the no-timeout drop-in is `/usr/libexec/fprintd` (Debian's).
  - `/usr/lib/dracut/dracut.conf.d/90-aurora-sep.conf` (`omit_drivers+=" apple_sep "`) is added from fedora-aurora, for images built with dracut. aurora-sep-luks's dracut module overrides it when the kernel has the key-store-only phase, as on Fedora.
  - README.md describes the Debian PAM profiles instead of the pacman hook, says there is no SELinux policy, and names libpam-fprintd and libfprint-2-2. The greeter script's message names libglib2.0-bin instead of glib2-devel.
  - dh_compress leaves the Markdown docs uncompressed, because the units and scripts name README.md and XART-SAFETY.md.
  - There is no Conflicts on linux-aurora. alarm's `linux-aurora<7.2.10-4` cut-off predates every Debian linux-aurora build (7.3.0-1 and later).
  - No 80-aurora-sep.preset (see Units).

### aurora-sep-luks (upstream, 0.3.0-1)

- **Source.** luks/ of aurora-sep-userspace at the aurora-sep-luks pin.
- **Installed:**
  - `make install install-dracut`
  - the token plugin in /usr/lib/aarch64-linux-gnu/cryptsetup (Debian's libcryptsetup token path)
  - pam_aurora_sep_fde in /usr/lib/aarch64-linux-gnu/security
  - /usr/libexec/aurora-sep-fde-passwd
  - /etc/aurora-sep/fde.conf (conffile)
  - the initrd files in /usr/lib/aurora-sep/initrd
  - the docs
- **Depends:** aurora-sep and libpam-runtime. Recommends: cryptsetup-bin. Suggests: dracut.
- **Tests.** The test-seal check from alarm's check() runs in native builds, with the same handling of exit 77 and of a restricted AF_ALG.
- **Deviations:**
  - The initramfs integration is upstream's dracut module (as fedora-aurora), not the mkinitcpio hook. There is no initramfs-tools hook upstream: with initramfs-tools, root volumes sealed by the Secure Enclave ask for their passphrase in the initramfs, and other volumes still unlock through systemd-cryptsetup and the token plugin.
  - The PAM password line is a pam-auth-update profile instead of the sep-fde-pam rewrite of system-auth.

### aurora-sep-sk (upstream, 0.1.0-1)

- **Source.** sk/ at the aurora-sep-sk pin.
- **Installed:**
  - /usr/lib/aarch64-linux-gnu/libaurora-sep-sk.so
  - the sep-key udev rule
  - /usr/lib/sysusers.d/aurora-sep-key.conf. dh_installsysusers (`--with installsysusers`) creates the group in postinst, then udev re-applies the rule to an existing /dev/sep-key.
- **Depends:** aurora-sep, openssh-client (Debian's ssh-sk-helper already links libfido2) and systemd.
- **Deviation:** the provider is in Debian's library directory instead of /usr/lib/libaurora-sep-sk.so. The upstream ssh-sk.md shows Fedora's /usr/lib64 path.

### aurora-fido (upstream, 0.2.0-1)

- **Source.** fido/ at the aurora-fido pin, built with `LIBEXECDIR=/usr/lib/aurora-fido` as alarm builds it.
- **Units.** Opt in: neither aurora-fido.service nor the aurora-passkeyd user unit is enabled or started.
- **Depends:** aurora-sep, python3, python3-cryptography and systemd.
- **Suggests:** libnotify-bin, fido2-tools, libpam-u2f and python3-jeepney (alarm's optdepends).
- **Docs.** fido.md stays uncompressed, because the units and `aurora-fido status` name it.

### aurora-touchid-rearm (upstream, 1-1)

- **Source.** touchid-rearm/ at the aurora-touchid-rearm pin.
- **Installed:**
  - the PAM module in /usr/lib/aarch64-linux-gnu/security
  - the helper in /usr/libexec
  - the socket, template and boot units
  - /etc/aurora/touchid.conf (conffile)
  - the pam-auth-update profile above
- **Units.** The socket and aurora-touchid-boot.service are enabled.
- **Deviations:**
  - The helper's own PAM service is /etc/pam.d/aurora-touchid-rearm (a conffile), not /usr/lib/pam.d. Debian's libpam maintainer does not support /usr/lib/pam.d (libpam0g 1.7.0-7 changelog, #1140029), and a patch to log its use is pending.
  - The re-arm line is a pam-auth-update profile, not an edit of system-auth.
  - README.md is not compressed, because the units name it.

### libfprint (upstream with Debian's packaging, 1:1.94.100-1+aurora1)

- **Kind.** Upstream rather than a rebuild.
  - alarm-aurora and fedora-aurora both ship upstream 1.94.100 (released 2026-07-25) with Aurora's patches.
  - Debian testing has 1:1.94.10-1. There the driver-list hunks of the apple-sep and lid patches do not apply, and fp-device.c, which 0003 and 0011 change, differs by several hundred lines.
  - Building the pinned 1.94.100 keeps the library alarm and Fedora test.
- **Source.** The pinned gitlab.freedesktop.org archive, given by URL because recipe pins are GitHub-only; the sha256 is the one in sources.json.
- **Patches.** The 11 patches go into debian/patches unchanged.
- **Packaging.** debian/ is Debian's 1:1.94.10-1 with these changes:
  - Maintainer set to Aurora Silicon.
  - `Provides: libfprint-aurora (= ${binary:Version})` on libfprint-2-2.
  - The new symbol `fp_device_get_password_required` in the symbols file, at `1:1.94.100-1+aurora1~` so that anything using it needs Aurora's library.
  - The postinst udev triggers regenerated from 1.94.100's autosuspend.hwdb with Debian's update-udev-triggers.sh.
  - `<linux/apple-sep.h>` in debian/aurora-uapi, added to CFLAGS as alarm does.
  - alarm's test_interface.py and test_lockout_reason.py run before meson test in native builds.
  - The fprintd drop-in `50-libfprint-lid-switch.conf` (DeviceAllow /dev/sep-bio and char-input) is installed in libfprint-2-2, as alarm's libfprint-aurora installs it.
- **Cross-build fixes:**
  - `cross-exe-wrapper <cross>`, plus an exe_wrapper cross file and GI's `/usr/share/meson/cross/<triplet>-gobject-introspection.ini` passed to meson.
  - `libgusb-doc <!nodoc !cross>`. That arch-all -doc package depends on libgusb-dev of the build architecture and cannot be installed beside the host's.
- **Version.** Keeps epoch 1 and sorts above Debian's 1:1.94.10-1. It also sorts above a future Debian 1:1.94.100-1.
- **Tests.** An emulated native build passed alarm's two checks and meson test (131 OK, 0 failed; the lid-switch uinput subtests skip in the build root).

### fprintd (rebuild, 1.94.5-4+aurora1)

- **Patches.** Debian's 1.94.5-4 plus alarm's 0001-0005 (0001-0004 are fedora-aurora's too; 0005 is the opt-in polkit password switch, off). All apply unchanged. 0006 adds alarm's check scripts as tests/aurora/.
- **packaging.patch:**
  - The PAM profile above.
  - `libfprint-2-dev (>= 1:1.94.100-1+aurora1~)`, so the lockout and password error codes come from Aurora's headers. alarm and Fedora define them by hand when building against stock headers.
  - fprintd `Depends: libfprint-aurora (>= 1:1.94.100-1+aurora1~)`, because fp_device_get_password_required is looked up at run time and shlibs cannot see it, and `Provides: fprintd-aurora`.
  - The test-only Build-Depends get `<!nocheck>` and python3 is `:native`. Debian's stock control cannot cross-build: python3:arm64 conflicts with meson's python3.
  - debian/rules runs alarm's test_account_gate.py and the password-switch test before Debian's own tests in native builds.
- **Not run:** alarm's grep sanity checks. The quilt series guarantees that the patches applied.
- Status: built in cross mode.
- **Tests.** An emulated native build passed alarm's test_account_gate.py and the password-switch test, and Debian's test suite with the Aurora patches (588 OK, 0 failed).

### aurora-xart (upstream, 0.2.0-1, all)

- Upstream `make install`.
- Depends: python3. Suggests: fprintd (alarm's optdepends fprintd-aurora).
- No deviations. 64 host tests passed.

### aurora-bless (upstream, 0.4.4.aurora5-1)

- **Binaries.** aurora-bless, aurora-nvram, aurora-btsync and aurora-panel-nits, with the asahi-* command symlinks and the asahi-btsync.service alias, as alarm installs them.
- **Build.** `"network": true`: cargo fetches the crates of the pinned Cargo.lock (`--locked`), as alarm does. Debian's own cargo and rustc build them (cross target aarch64-unknown-linux-gnu); no rustup toolchain is needed.
- **Package relations.** Each binary has Provides (versioned), Conflicts and Replaces for Debian's asahi-bless, asahi-nvram and asahi-btsync. alarm's aurora-bless has no replaces=; Debian adds it, as docs/packaging.md requires.
- **Units:**
  - aurora-btsync.service is not enabled, not started and left alone on upgrade (udev starts it).
  - aurora-panel-nits.service is static and is try-restarted on upgrade. pacman never restarts it; this is a minor deviation.
- **Tests.** cargo test runs only in native builds.

### aurora-diag (upstream, 0.5.0-1, all)

- Depends: python3.
- alarm's optdepends become Suggests: python3-textual, alsa-utils, vulkan-tools, mesa-utils, iw, smartmontools, bluez and libglib2.0-bin.
- Host tests: 146 passed, 2 skipped (no textual).

### aurora-kbd-light (upstream, 0.1.0-1)

- alarm's udev rule is installed as /usr/lib/udev/rules.d/90-aurora-kbd-light.rules.
- The service is enabled, not started at installation, and try-restarted on upgrade, as alarm's .install does.

### aurora-camera-denoise (upstream, 0.1.0-1)

- **Build.** Configured as alarm configures it: daemon enabled, GPU backend disabled.
- **Units.** The user unit is enabled globally by dh_installsystemduser and not started.
- **Deviations:**
  - The backends directory is /usr/lib/aarch64-linux-gnu/aurora-camera-denoise (Debian's libdir, built into the daemon). alarm uses /usr/lib/aurora-camera-denoise.
  - README.md and docs/ are installed.
- **Open question.** The upstream Neural Engine programs (`/usr/share/aurora-camera-denoise/ane/h16g-960x540/*.bin`, `model.hwx`) are shipped, as alarm ships them. Someone should confirm they are Aurora-built and contain nothing Apple-derived.

### aurora-neo-platform-config (upstream, 0.1.0-1, all)

- The NetworkManager conf.d snippet and the libinput quirks file.
- No deviations.

### aurora-wifi-firmware (upstream, 0.2-1, all)

- **Source.** tools/wifi-firmware of the pinned aurora-installer.
- **Depends:** python3, util-linux, mount and systemd. Recommends: liblzfse1 (alarm's optdepends lzfse).
- **Units.** The service is enabled, not started, and not stopped on upgrade; it runs at the next boot, as on alarm.
- **Rules.** debian/rules overrides dh_auto_configure and dh_auto_clean, because the repository's top-level setup.py would otherwise select the removed python_distutils buildsystem.
- Host tests: 41 passed.

### aurora-m5-platform-config (native, 1, all)

- **Files.** alarm's local files. /etc/aurora-m5-sleep.conf is a conffile.
- **Units:**
  - The static sysinit.target.wants link is kept.
  - postinst starts aurora-m5-sleep-policy.service on first installation, as alarm's post_install does; deb-systemd-invoke never starts a static unit by itself.
  - An upgrade restarts the unit if it runs.

## Open questions

- **Initramfs generator.** aurora-sep-luks only integrates with dracut, and aurora-sep ships a dracut omit_drivers file. If Aurora's Debian images use initramfs-tools:
  - Root volumes sealed by the Secure Enclave cannot unlock in the initramfs.
  - The modprobe.d blacklist alone keeps apple_sep from autoloading there.
- **Upgrades from Debian's libpam-fprintd.** These keep fingerprint off: pam-auth-update had already seen the profile. Should Aurora's libpam-fprintd enable it once on such an upgrade? alarm only ever adds the line on a fresh hook run.
- **Camera-denoise ANE programs.** Confirm that the files are not Apple-derived (see aurora-camera-denoise).
- **Native test run.** libfprint and fprintd passed their tests in emulated native builds. The other packages' compiled tests (cargo test, meson test, touchid-rearm, sep-sk, fido and luks checks) have not run yet; the native CI will run them.

## Build notes

- **Arch-all Build-Depends-Indep in cross builds.** `--cross --arch-all` resolves Build-Depends-Indep for the host architecture. An arch-all -doc package without Multi-Arch: foreign that depends on a -dev package (libgusb-doc) cannot be installed beside the host's -dev package.
- **Meson cross builds.**
  - Builds that run a host program need cross-exe-wrapper and an `exe_wrapper` in a meson cross file.
  - Builds with GObject introspection need `/usr/share/meson/cross/<triplet>-gobject-introspection.ini`.
  - debhelper's generated cross file has neither.
  - libfprint adds both in debian/rules; a shared helper (DH_MESON_CROSS_FILE) would help every GI package (mutter, network-manager and udisks2 stopped at install-deps too).
- **Tests in cross builds.** `--cross` never runs tests: sbuild adds `nocheck` to cross builds. Test coverage needs the native CI (or `build-package` without `--cross`).
- **/usr/lib/pam.d.** Debian does not support it (see aurora-touchid-rearm). PAM services belong in /etc/pam.d.

