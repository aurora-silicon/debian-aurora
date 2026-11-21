# Desktop

Debian testing at the `images/base.json` snapshot (20261120T000000Z) ships
older desktop releases than alarm-aurora: Plasma 6.7.4 (alarm-aurora 6.8.2),
Mutter 51.0 and gnome-settings-daemon 51.0 (alarm-aurora 51.1). Aurora's
patches are carried on Debian's versions. Every build except the emulated
ones was a cross build (`build-package --cross`) on amd64.

| alarm-aurora | Debian source | Binary packages | Kind | Version | Status |
| --- | --- | --- | --- | --- | --- |
| kwin-aurora | kwin | kwin-common, kwin-data, kwin-dev, kwin-wayland, libkwin6 | rebuild | 4:6.7.4-2+aurora1 | recipe; cross build failed in Debian's packaging (below) |
| kinfocenter | kinfocenter | kinfocenter | rebuild | 4:6.7.4-1+aurora1 | built (cross) |
| plasma-setup | plasma-setup | plasma-setup | upstream | 6.7.4-1 | built (emulated) |
| mutter-aurora | mutter | mutter, mutter-common, mutter-common-bin, mutter-dev-bin, libmutter-51-0, libmutter-51-dev, libmutter-test-51, mutter-51-tests, gir1.2-mutter-51 | rebuild | 51.0-3+aurora1 | built (cross) |
| gnome-settings-daemon-aurora | gnome-settings-daemon | gnome-settings-daemon, gnome-settings-daemon-common, gnome-settings-daemon-dev | rebuild | 51.0-2+aurora1 | built (cross) |
| plymouth | plymouth | plymouth, plymouth-themes, plymouth-label, plymouth-x11, libplymouth5, libplymouth-dev | rebuild | 26.134.222-1+aurora1 | built (cross) |
| plymouth-theme-aurora | plymouth-theme-aurora | plymouth-theme-aurora (all) | native | 1 | built (emulated) |
| aurora-logos | aurora-logos | aurora-logos (all) | native | 1 | built |
| power-profiles-daemon | power-profiles-daemon | power-profiles-daemon | rebuild | 0.30-2+aurora1 | built (emulated) |
| upower-aurora | upower | upower, libupower-glib3, libupower-glib-dev, gir1.2-upowerglib-1.0, upower-doc, upower-tests | rebuild | 1.91.5-1+aurora1 | built (cross) |

## kwin

alarm-aurora's Night Light ambient white point patch
(`0001-nightlight-ambient-white-point.patch`, identical to fedora-aurora's)
applies to 6.7.4 unchanged, with a 3-line offset in `src/workspace.h`. 6.7.4
already has the `LightSensor` that the patch extends (`Workspace::m_lightSensor`,
`intoFuture` D-Bus calls). Debian configures with `BUILD_TESTING=OFF`, so the
patch's autotests are not built.

alarm-aurora also carries upstream c9d72079 (6.8 branch): no crash when a
scanout device has no render device (DisplayLink). It is **not needed on
6.7.4** and not carried: the bug came with 6783f9610c, which moved the
cross-GPU direct scanout check from `backends/drm` into the compositor in 6.8.
6.7.4 still checks in `EglGbmLayer::importScanoutBuffer()`
(`src/backends/drm/drm_egl_layer.cpp`), with the null check on
`gpu()->renderDevice()`.

Build: the one cross attempt failed at 11 % in Debian's packaging, before the
patched files were compiled. `debian/rules` passes
`-DQTWAYLANDSCANNER_KDE_EXECUTABLE=/usr/lib/qt6/libexec/qtwaylandscanner`,
which KWin uses only when cross-compiling, in place of its own
`qtwaylandscanner_kde`. That path is Qt's own scanner (shipped by
`qt6-base-dev-tools` 6.11.2), which does not accept KWin's `--basename=` option:
`qwayland-server-alpha-modifier-v1.h` fails with Qt's usage message. A native
build builds `qtwaylandscanner_kde` itself and is unaffected. Open: build KWin
natively on arm64 (CI), or cross-build it with a `packaging.patch` that drops
that flag and passes `-DKF6_HOST_TOOLING` with `qt6-base-dev:native`, so KWin
builds the scanner for the build machine. The ambient white point patch has
therefore not been compiled against 6.7.4 yet.

## kinfocenter

alarm-aurora's `0001-handle-unknown-installed-memory.patch` (fedora-aurora's,
with a different diff prefix) applies to 6.7.4 unchanged. Built.

## plasma-setup

Plasma Setup 6.7.4 from `download.kde.org/stable/plasma/6.7.4/`, pinned by
sha256 `d8d761c78c4ea51eb7e2b9342f10fbe0b46d4cedfeeeb5150c9d387b2eb79d03`. Its
`.sig` verifies with `gpgv` against Debian's KDE Plasma keys
(`debian/upstream/signing-key.asc` of Debian's kwin): Bhushan Shah's signing
subkey B3CB366552540BE06EE9AD9711968C44928CAEFC, the key alarm-aurora names for
6.8.1. The `debian/` directory is new (Debian has no plasma-setup), following
Debian's KDE packaging (`dh-sequence-kf6`, so programs are in
`/usr/lib/aarch64-linux-gnu/libexec`, the KAuth helper in
`/usr/lib/kf6/kauth/libexec`).

- alarm-aurora's tmpfiles patch (`Z /run/plasma-setup ~0750`) applies
  unchanged.
- Deviation: `debian/patches/0002-debian-admin-group.patch` sets
  `UserGroups=sudo` in `/etc/xdg/plasmasetuprc`. Upstream's default `wheel`
  does not exist on Debian, and the KAuth helper rejects an unknown group
  ("Unknown group: wheel"), so the owner account would not get its groups.
  Debian's sudoers and polkit (`40-debian-sudo.rules`) treat `sudo` as the
  administrator group.
- `plasma-setup.service` is installed disabled and never started by the
  package (`dh_installsystemd --no-enable --no-start`): alarm-aurora enables
  it in its KDE image build (`systemctl enable plasmalogin.service
  plasma-setup.service`), not in a preset. The Debian image build must do the
  same; aurora-platform's first-boot code waits for it.
- `dh_installsysusers` creates the `plasma-setup` user from upstream's
  sysusers file and `dh_installtmpfiles` its `/run/plasma-setup` home.
- 6.7.4 configures both SDDM and Plasma Login Manager autologin
  (`/etc/sddm.conf.d`, `/etc/plasmalogin.conf.d`), so it works with Debian's
  plasma-login-manager 6.7.4.
- Runtime QML dependencies are explicit: plasma-desktop (kcm_keyboard),
  plasma-nm, qml6-module-org-kde-plasma-workspace (time zone selector, kicker,
  which pulls the Qt Location map), Kirigami, Kirigami Addons and the Qt Quick
  modules. Upstream's cellular page (org.kde.plasma.mm) is not built in 6.7.4.
- `"cross": false`: `ecm_find_qmlmodule(org.kde.plasma.private.kcm_keyboard
  REQUIRED)` looks for the arm64 qmldir, and plasma-desktop:arm64 cannot be
  installed in a cross build root (kde-cli-tools-data is not Multi-Arch:
  foreign). Built emulated (7.5 minutes).
- Upstream also installs a static `libcomponentspluginplugin.a`; left as
  upstream installs it.

## mutter

alarm-aurora's five patches (identical to fedora-aurora's) apply to 51.0 in
order, with line offsets only (fuzz 0), and are carried byte for byte:
VRR preferred mode, PQ reference white from `PQ_REFERENCE_LUMINANCE`, VRR on
the whole desktop of built-in panels, power save page flip onscreens dropped on
dispose, and the frame clock minimum-estimate fix. They add no exported
symbols, so Debian's `DPKG_GENSYMBOLS_CHECK_LEVEL = 4` passes.

Deviations:
- `packaging.patch` annotates `python3:native` and `python3-argcomplete:native`
  in Build-Depends, needed only for the cross build (Debian names both without
  an architecture, and python3-argcomplete is not Multi-Arch: foreign).
- alarm-aurora's `-O3`, `-Bsymbolic-functions` and its removal of the
  development kit are Arch packaging choices; Debian's packaging is kept.

Note: fedora-aurora's 50.6 also carries upstream 13ed6cae ("wayland/touch: Do
not crash on empty focus surface"), which alarm-aurora gets from 51.1. Debian's
51.0 lacks it (the patch applies), but alarm-aurora does not carry it and it
only concerns touchscreens, so it is not carried here.

## gnome-settings-daemon

alarm-aurora's colour plugin ambient white point patch (also fedora-aurora's),
without its last hunk, which only creates an empty `subprojects/.wraplock` (a
Meson by-product). The rest applies to 51.0 unchanged. Debian's 51.0 already
names the compile-schemas target `compiled_schemas`, which fedora-aurora's
50.1 copy has to add. The `ambient-white-point-enabled` key is off by default.
alarm-aurora's dependency on aurora-keep-config is not carried: dpkg keeps
edited conffiles itself.

## plymouth

Patches (in `packages/plymouth/patches`, numbered in alarm-aurora's order):

1. Upstream cea90be3 (default XKB keymap no longer overrides a console
   KEYMAP), as fedora-aurora's copy; alarm-aurora cherry-picks it. Not in
   26.134.222, so it is needed. It is consistent with Debian's
   `fallback-etc-default-keyboard.patch` (keymap from `/etc/default/keyboard`).
2. fb_device_has_drm_device race (frame-buffer plugin for a DRM fbdev).
3. Nonblocking terminal input.
4. plymouth-start.service without waiting for coldplug: **rebased** onto
   Debian's unit, which `drop-systemd-vconsole-setup-service.patch` already
   changes: `After=systemd-udevd.service keyboard-setup.service
   dracut-pre-trigger.service` (Debian keeps keyboard-setup.service).
5. Splash keyboard lifetime. `packaging.patch` adds `Provides:
   plymouth-script-keyboard-lifetime (= 1)` to the plymouth package, the
   capability alarm-aurora's theme requires.
6. Reset inherited HDR connector state before SDR.
7. Flush only the damaged areas.

The keyboard lifetime patch adds `ply_terminal_get_input_fd` to
libply-splash-core; dpkg-gensymbols only warns about the new symbol.

Not carried (Arch only): the mkinitcpio hooks, the `plymouth-font-file`
helper and the shutdown tmpfiles snippet (Debian builds its initramfs with
dracut, whose `45plymouth` module copies the theme and its fonts), the Arch
logo and spinner watermark, `Theme=bgrt` and the Adwaita font switch.

Open: alarm-aurora's and fedora-aurora's regression programs
(`test-terminal-input.c`, `test-drm-sdr.c`, `test-drm-damage.c`,
`check-keyboard-lifetime.sh`) are not wired into Debian's `dh_auto_test`. They
would run only in native builds; cross builds are `nocheck`.

## plymouth-theme-aurora

Native package with alarm-aurora's theme, logos (byte-identical to aura's),
`aurora-plymouth` helper, `plymouth-start.service.d/aurora-plymouth.conf`
drop-in and `test_geometry.py` (run in `dh_auto_test`; its 9 tests pass in
the emulated build), all byte for byte.

Deviations:
- Initramfs: Debian's kernel packages prefer dracut, so the mkinitcpio hook and
  `mkinitcpio.conf.d` snippet are replaced by fedora-aurora's dracut module
  (`/usr/lib/dracut/modules.d/96aurora-plymouth`), which runs the helper at
  pre-trigger and copies the drop-in. There is no initramfs-tools hook: with
  initramfs-tools the generated `/run/plymouth/aurora.script` would be
  missing in the initramfs.
- Dependencies: `plymouth-themes` (Debian ships the spinner theme, the
  `ImageDir`, there), `fonts-cantarell` and
  `plymouth-script-keyboard-lifetime (>= 1)`.
- Maintainer scripts make alarm-aurora's choices: Aurora becomes the theme
  unless `/etc/plymouth/plymouthd.conf` names one (Debian's default,
  ceratopsian from desktop-base, comes from `plymouthd.defaults` and is
  replaced), and `DeviceScale=1` is added under `[Daemon]` unless set; removal
  undoes both. The initramfs is rebuilt through the `update-initramfs` trigger
  (Debian's dracut handles it) instead of alarm-aurora's message.
- Not here (other groups): `plymouth.ignore-serial-consoles` and `splash` on
  the kernel command line. alarm-aurora sets the former in aurora-boot's GRUB
  snippet, fedora-aurora in this package's `%posttrans`.

## aurora-logos

Native package with alarm-aurora's images (byte for byte; `provenance.json`
installed as documentation): `aurora-logo-icon` and `places/start-here` in
hicolor at ten sizes, and `/usr/share/pixmaps/system-logo-white.png`.

Deviations:
- `kcm-about-distrorc` says `Name=Aurora Debian` (alarm-aurora: `Aurora
  Alarm`); `LogoPath` and `Website` are alarm-aurora's.
- Debian's desktop-base owns `/etc/xdg/kcm-about-distrorc` (`LogoPath=
  emblem-debian`, `Version=forky/sid`) as a conffile, and Debian's desktops
  install desktop-base. aurora-logos declares `Replaces: desktop-base` to take
  that one file over: dpkg moves it with desktop-base's recorded hash (an
  unmodified file is replaced without a prompt) and keeps aurora-logos' copy
  when desktop-base is upgraded. Open question: whether the image should
  rather not install desktop-base, or brand through `/etc/os-release`
  (`LOGO=`, `NAME=`), which kinfocenter uses when no distrorc overrides it.

## power-profiles-daemon

alarm-aurora's platform-profile class-interface patch applies to Debian's 0.30
with line offsets only. `"cross": false`: Debian's Build-Depends name
`python3` and `python3-gi` without `:native`, so a cross build root cannot
install them next to dh-python. Built emulated, with Debian's test suite: 129
tests pass, including the patch's `test_platform_profile_class_device`.

## upower

`packages/upower/patches` is aurora-silicon/upower d8a24ffc (the sources.json
pin) against upstream v1.91.5 (233615a1, the merge base), one patch per
non-merge commit, without the GitHub workflow and the merge of the 1.91.4
fork (whose content is already in 687cae29): macsmc kernel time estimates and
their tests (687cae29, a2723024), and upstream cherry-picks a6d72c77,
bb7af5f1 (composite KbdBacklight object only while a keyboard backlight
exists) and c2e6e110 (keyboard backlight I/O watch lifetime). On Debian's
1.91.5 source the patched tree is identical to the pinned commit (except
`.github`). Debian's binary package names are kept.

`packaging.patch` adds alarm-aurora's (and fedora-aurora's)
`upower-charge-limit-migrate` (`/usr/libexec/aurora/`) and its unit, pulled in
by a static `upower.service.wants` link as on alarm-aurora. It matters on
Debian: Debian's asahi-scripts ships the macsmc-battery charge-control units
that save `/etc/udev/macsmc-battery.conf`. Difference: Debian's
`dh_installsystemd` (no `--no-start` in Debian's rules) also starts the
migration unit with upowerd on package configure; its
`ConditionPathExists` keeps that a no-op without the old file, and its
`Before=upower.service` still orders it first.

Not carried: alarm-aurora's `check()` that greps the registered macsmc tests;
Debian does not run upower's tests at build time (they need the system bus).
alarm-aurora's aurora-keep-config dependency is not needed on Debian.

## Build notes

- Many Debian packages name `python3` (and Python modules) without `:native`,
  which a cross build root cannot install next to dh-python
  (power-profiles-daemon, mutter). Small packages can use `"cross": false`;
  large ones need a `packaging.patch`.
- KWin cannot be cross-built from Debian's packaging (above); it needs a native
  arm64 build.
