# Networking, storage and applications

Debian testing (forky) at snapshot `20261120T000000Z`.

| alarm-aurora | Debian source | Kind | Version | Status |
| --- | --- | --- | --- | --- |
| networkmanager-aurora | network-manager | rebuild | 1.58.1-1+aurora1 | built (emulated, nocheck) |
| iwd-aurora | iwd | rebuild | 3.12-1+aurora1 | built (cross) |
| udisks2 | udisks2 | rebuild | 2.11.2-1+aurora1 | built (cross) |
| docker | docker.io | rebuild | 28.5.2+dfsg4-5+aurora1 | built (emulated, nocheck) |
| firefox | firefox | rebuild of unstable's 160.0.1-1 | 160.0.1-1+aurora1 | built (native arm64, 1 job: 2 h 48 min) |
| gtk2 | gtk+2.0 | debian | 2.24.33-10 | debian |
| aurora-system-fixes | aurora-system-fixes | native | 1.15 | built (cross) |
| aurora-keep-config | | n/a | | n/a |
| aurora-omarchy-polkit | | n/a | | n/a |
| omarchy-ane-tools | omarchy-ane-tools | upstream | 0.5.7-1 | built (emulated, with its test) |
| mil-hwx-compiler | mil-hwx-compiler | upstream | 0.3.1-1 | recipe; blocked on extra sources (built emulated from a simulated source package) |
| omdrop-awdl | omdrop-awdl | upstream | 0.10.5-1 | recipe; blocked on extra sources (built from a simulated source package) |

"emulated" is `scripts/build-package` without `--cross` (arm64 build root under
qemu-user). "nocheck" means the local build ran with `DEB_BUILD_OPTIONS=nocheck`
to save emulation time; the native CI build runs the test suites.

## Per package

### network-manager (networkmanager-aurora)

- Binaries: network-manager, network-manager-tui, network-manager-ovs,
  network-manager-team, network-manager-dev, network-manager-l10n,
  network-manager-config-connectivity-debian, libnm0, libnm-dev, gir1.2-nm-1.0.
- Patch: `0101-manager-keep-wake-on-lan-devices-that-are-still-activated-after-wake.patch`,
  unchanged from alarm-aurora (applies with a 30-line offset).
- Not carried: alarm-aurora's `0001-libnm-glib-aux-rename-_s1-variable-to-avoid-shadowing.patch`
  (Arch's GLib 2.89 test fix); Debian 1.58.1-1 already has the same fix as
  `Fix-test-suite-failure-with-glib-2.89.patch`.
- Not carried: everything else alarm-aurora's PKGBUILD does is Arch packaging
  (meson options, `ping.archlinux.org` connectivity check, the empty
  NetworkManager.conf, the split of libnm and nm-cloud-setup, the
  `aurora-keep-config` dependency). Debian's packaging stays as it is.
- `"cross": false`: Debian's Build-Depends need python3-gi and
  gobject-introspection for the host architecture beside the build
  architecture's meson, which apt cannot resolve in a cross build root. Built
  emulated in 15 minutes with nocheck.
- Open: Debian testing's arm64 binaries are the binNMU `1.58.1-1+b1`, which
  sorts above `1.58.1-1+aurora1` (see Build notes).

### iwd (iwd-aurora)

- Binaries: iwd, network-manager-iwd.
- Patches (all apply unchanged): the OWE offload pair
  `0101-linux-update-nl80211.h-for-the-OWE-offload-ext-features.patch` and
  `0102-netdev-support-OWE-on-FullMAC-devices-that-offload-it.patch` (Aurora,
  for the MacBook Neo's MT7932), and Arch's four oss-security 2026/08/02 fixes
  `0001`-`0004` (rrm beacon report overflow, HE capabilities width set,
  `mde_equal`, FTE sub-element underflow). Debian 3.12-1 carries none of the
  four (its series is only its three packaging patches), so they stay.
- Not carried: `0001-use-network-group-for-unprivileged-access.diff`, Arch's
  `network` group. Debian keeps upstream's `netdev` group.
- Not carried: Arch's configure options (`--enable-wired`, `--enable-ofono`,
  `--enable-hwsim`, `--disable-tools`) and its removal of `unit/test-storage`;
  Debian's build stays as it is.

### udisks2

- Binaries: udisks2, udisks2-btrfs, udisks2-lvm2, udisks2-doc, libudisks2-0,
  libudisks2-dev, gir1.2-udisks-2.0.
- Patch: `0001-size-nvme-drives-from-their-namespaces.patch`, unchanged
  (alarm-aurora and fedora-aurora carry the same file).

### docker.io (docker)

- Binaries: docker.io, docker-cli, docker-doc, golang-github-docker-docker-dev.
- Version deviation: alarm-aurora builds Docker 29.9.2 from upstream; Debian
  testing has 28.5.2+dfsg4-5. Aurora's patch applies to 28.5.2 after a rebase:
  `0001-libnetwork-query-permanent-policies-before-creating-docker-forwarding.patch`
  moves the path from `daemon/libnetwork/iptables/` (moby v2) to
  `engine/libnetwork/iptables/` and keeps 28.5.2's `map[string]interface{}`
  context. The code is unchanged; in 28.5.2 `errors` is github.com/pkg/errors,
  whose `As` the patch's call resolves to. The added unit test
  (`TestSetupDockerForwardingPolicy`, no root, no firewalld) is part of the
  patch; it was not run locally (nocheck) and runs in Debian's
  `hack/test/unit` on the CI build.
- Not carried: alarm-aurora's `docker.sysusers` (Debian's packaging creates the
  docker group itself) and its Arch build of cli, daemon and tini.
- `"cross": false`: Debian's golang-*-dev Build-Depends are Architecture: all
  without Multi-Arch: foreign, so a cross build root cannot install them.
  Built emulated in 18 minutes with nocheck.

### firefox (rebuild of unstable's firefox)

- Decision: ship the current Firefox, as every other Aurora distribution
  does (alarm-aurora and omarchy-aurora 160.0, fedora-aurora 160.0.1,
  nixos-aurora nixpkgs' `firefox-unwrapped`), not Debian testing's ESR.
  Debian testing ships only firefox-esr; the rapid-release `firefox` lives in
  unstable and never migrates. The recipe rebuilds unstable's 160.0.1-1
  (`"suite": "unstable"` in its `debian` object); the build root stays
  testing. Every versioned build dependency resolves there (libnss3-dev
  2:3.132-1, libnspr4-dev 2:4.40-1, rustc/cargo 1.98.1, cbindgen 0.29.4,
  nodejs 24, clang/lld and the wasm32 libraries 21.1.8), so the binaries
  depend only on testing's libraries. Binaries keep Debian's names:
  firefox and the firefox-l10n-* packages. The images install `firefox`.
- Patch: `rdd-v4l2-request.patch`, the file alarm-aurora, fedora-aurora and
  nixos-aurora carry, split at its two commits into `patches/0001-…` and
  `patches/0002-…` and otherwise unchanged (concatenated they are the same
  file, sha256 8bf37b91…): dpkg-source refuses a quilt patch that changes
  the same file twice. The two commits allow
  V4L2 stateless decoders in the RDD sandbox (Mozilla bug 2080696, under
  review) and sysinfo there for Mesa's zink driver. Firefox 160 builds with
  `MOZ_ENABLE_V4L2` on arm64 and `MOZ_ENABLE_VAAPI`, so the patched code is
  compiled.
- Not carried: `0001-Install-under-remoting-name.patch`, which is Arch's (Jan
  Steffens) for installing several channels side by side, imported with
  ALARM's recipe, not an Aurora change. Not carried either: ALARM's
  mozconfig, `vendor.js`, `distribution.ini`, desktop file, metainfo and
  icons; Debian's packaging provides its own.
- Build: without debug symbols on arm64 (`packaging.patch` adds arm64 to
  Debian's `--disable-debug-symbols` case, which riscv64 already uses), as
  alarm-aurora (`RUSTFLAGS=-Cdebuginfo=0`, `-g0`) and fedora-aurora
  (`-Cdebuginfo=0` on aarch64, `-g1`, no debuginfo package) build Firefox for
  aarch64. With Debian's debug info (`-C debuginfo=2`), rustc needed more than
  13 GB of memory for gkrust alone and was killed on a 15 GB machine even with
  one job. Firefox's Cargo release profile sets no `debug`, so the switch
  gives Rust debuginfo 0; Debian's rules already strip `-g` from the C/C++
  flags. Rust LTO stays as Debian sets it (no PGO). Built natively on arm64
  (`"cross": false`).
- Built on 2026-11-21 on an M1 Mac mini (16 GB, Debian, 16K pages) with
  `TMPDIR=/var/tmp AURORA_BUILD_JOBS=1` and the build pinned to the four
  P-cores (`taskset -c 4-7`; the energy-aware scheduler otherwise kept the
  single job on an E-core): 2 h 48 min, 18.5 GB of disk at the peak (sbuild's
  figure), memory never short once debug info was off. 105 packages:
  `firefox` (75 MB), `firefox-dbgsym` (9 MB, symbol tables only) and 103
  `firefox-l10n-*`. libxul contains the patched broker code. An empty
  testing arm64 system installs `firefox` with 154 dependencies, all from
  testing.
- Tracking: unstable uploads a new Firefox about every four weeks, and each
  one needs a version bump here (alarm-aurora's track-firefox workflow does
  the same for ALARM's). Not automated yet.
- Hardware decoding: checked on a MacBook Air (M1, J313) running a
  debian-minimal install with an X session: `about:support` reports hardware
  video decoding through VA-API (libva-v4l2-request) with the patched RDD
  sandbox.

### gtk+2.0 (gtk2): debian

- alarm-aurora builds GTK 2 only because Arch Linux ARM dropped it and Valve's
  native ARM64 Steam client loads `libgtk-x11-2.0.so.0`. Debian testing ships
  gtk+2.0 2.24.33-10 for arm64 (libgtk2.0-0t64 2.24.33-10+b2).
- `0002-Stop-looking-for-modules-in-cwd.patch` (CVE-2024-6655) is in Debian as
  `debian/patches/CVE-2024-6655.patch`, the same change.
- `0001-Lower-severity-of-XID-collision-warnings.patch` is Arch's (Jan
  Steffens): a `g_warning` becomes `g_debug`. Cosmetic Arch housekeeping, not
  an Aurora change; not carried.
- The rest is Arch packaging (the pacman hook for the input-method cache,
  which Debian's triggers do; the Adwaita gtkrc defaults; removing
  gtk-update-icon-cache). No recipe.

### aurora-system-fixes (native, 1.15)

alarm-aurora's 1-15; a native version has no revision. Arch: all.
Depends: systemd, udev, bluez (>= 5.87), ethtool, iw, procps, aurora-panel-nits,
aurora-nvram, aurora-btsync (the last three are aurora-bless's binaries, as in
alarm-aurora; Debian testing has bluez 5.88). Every file:

| File | Installed as | Decision |
| --- | --- | --- |
| 50-after-swapfile.conf | /usr/lib/systemd/system/var-swap-swapfile2.swap.d/ | kept |
| 61-aurora-dmi-id.rules | /usr/lib/udev/rules.d/ | kept (`/usr/bin/sed` exists with merged /usr) |
| 60-aurora-dmi-vendor.hwdb | /usr/lib/udev/hwdb.d/ | kept (udev's trigger updates hwdb) |
| 62-aurora-gpu-render-only.rules | /usr/lib/udev/rules.d/ | kept |
| aurora-wake-for-network | /usr/lib/aurora/ | kept (ethtool and iw are in /usr/sbin, which its PATH has) |
| 63-aurora-wake-for-network.rules | /usr/lib/udev/rules.d/ | kept |
| 64-aurora-trackpad-clicks.rules | /usr/lib/udev/rules.d/ | kept |
| 60-aurora-trackpad-palms.quirks | /usr/share/libinput/ | kept (Debian's libinput 1.31 reads it there) |
| 60_aurora-apple-keys.gschema.override | /usr/share/glib-2.0/schemas/ | kept; glib's trigger compiles it. `dh_installgsettings` is skipped so the package does not pull in a GSettings backend (alarm-aurora has none either) |
| 90-aurora-reboot-watchdog.conf | /usr/lib/systemd/system.conf.d/ | kept |
| aurora-power-defaults.service | /usr/lib/systemd/system/, plus the static `sysinit.target.wants` link | kept; `/usr/bin/sysctl` changed to `/usr/sbin/sysctl` (Debian's procps). Not started on installation and not stopped on upgrade (`dh_installsystemd --no-start --no-stop-on-upgrade`), as with pacman |
| drkonqi-ordering.conf | /usr/lib/systemd/user/{drkonqi-coredump-cleanup.timer,drkonqi-sentry-postman.path}.d/50-aurora-ordering.conf | kept; Debian's drkonqi 6.7.4 ships both units unchanged |
| nm-dispatcher-persist.conf | /usr/lib/systemd/system/NetworkManager-dispatcher.service.d/50-aurora-persist.conf | kept; `ExecStart=/usr/lib/nm-dispatcher` changed to `/usr/libexec/nm-dispatcher` (Debian's libexecdir) |
| malcontent-signal.conf | (malcontent-timerd, -timer-extension-agent, -webd) | dropped: Debian testing has malcontent 0.13.1, which has none of these units (they came with malcontent 0.14). Bring back once Debian ships 0.14 without upstream af8226a7d3c3 |
| malcontent-webd-update-signal.conf | (malcontent-webd-update) | dropped, same reason |
| LICENSE | debian/copyright | MIT |

Open: alarm-aurora's `bluez>=5.87` dependency has no recorded reason (its
history is squashed); it is kept for parity.

### aurora-keep-config: n/a

On Arch, swapping a distribution package for its Aurora build (networkmanager
and networkmanager-aurora, upower and upower-aurora, gnome-settings-daemon and
gnome-settings-daemon-aurora) is a conflict removal plus a fresh install, so
pacman saves an edited backup file as `.pacsave` and installs the default; the
hook puts the edit back. The Debian rebuilds keep Debian's source and binary
names, so moving between Debian's package and Aurora's (either way) is an
ordinary upgrade or downgrade of the same package, and dpkg keeps a modified
conffile (it asks, or follows `--force-confold`/`confdef`, and keeps the new
default as `.dpkg-dist`). Nothing to port; the network-manager rebuild does
not need the dependency alarm-aurora adds. If a later Aurora package does take
over a conffile from a differently named Debian package, that case needs its
own check (dpkg-maintscript-helper), not this hook.

### aurora-omarchy-polkit: n/a

alarm-aurora's KDE and GNOME images do not install it (it is not in
`scripts/build-image`'s package lists). It is an optional companion for
Omarchy, an Arch Linux desktop setup whose Quickshell plugin manager and
pacman hooks it targets; no Debian image installs Omarchy. Debian testing has
quickshell 0.3.2 and the fprintd rebuild carries the polkit password switch, so
a port is possible later: a native package with the plugin files, the D-Bus
policy and `aurora-polkit-pam`, with dpkg maintainer scripts instead of the
three pacman hooks.

### omarchy-ane-tools (upstream, 0.5.7-1)

- Binary: omarchy-ane-tools (arm64). Installs omarchy-ane-run (libane linked
  statically), omarchy-ane-smoke, omarchy-ane-firmware-fetch, the H13 and H14
  add fixtures in /usr/share/omarchy-ane/fixtures, `70-omarchy-ane.rules`
  (accel group, 0660) and the `g accel -` sysusers entry
  (dh_installsysusers runs systemd-sysusers in postinst).
- alarm-aurora's `fix-smoke.py` is `debian/patches/smoke-fixtures-under-prefix.patch`
  (the same two replacements).
- The check is alarm-aurora's: `python3 tools/test_ane_firmware_fetch.py`
  (passed in the emulated build); `test_ane_smoke.py` is left out as there.
- `"cross": false`: libane's Makefile uses a bare `ld -r` and `gcc`.
- Note: Debian's udev gives accel nodes group render 0660 by default; the rule
  keeps alarm-aurora's accel group.

### mil-hwx-compiler (upstream, 0.3.1-1)

- Binary: mil-hwx-compiler (arm64): `/usr/bin/mil-hwxc` with the private
  libobjc2 and GNUstep Base in `/usr/lib/mil-hwx-compiler` (RUNPATH set with
  patchelf, `dh_makeshlibs -X` so no SONAME is exported), as alarm-aurora's.
- Sources: the pin plus its `extra_sources` libobjc2, gnustep-make and
  gnustep-base as Debian component tarballs (`orig-libobjc2`, `orig-gnustep-make`,
  `orig-gnustep-base`), unpacked in `libobjc2/`, `gnustep-make/`,
  `gnustep-base/`. alarm-aurora's `gnustep-base-block-ivar.patch` is
  `debian/patches/gnustep-base-block-ivar.patch` (path moved into
  `gnustep-base/`, regenerated with symmetric context, since alarm's hunk only
  applies with fuzz). `build-runtime.sh` and `install-runtime.sh` are in
  `debian/`, adapted to the component directories; the licenses go to
  debian/copyright instead of /usr/share/licenses. The build copies the
  components to `debian/runtime-src` so the source tree stays clean.
- Tests as alarm-aurora: `make test-h13` and `tests/test_h14_fixture_programs.py`,
  and install-runtime.sh checks the installed compiler's H14 add output hash.
- Build-Depends follow fedora-aurora's list (Debian names, robin-map-dev for
  libobjc2): curl and GMP are not build dependencies, so GNUstep Base is built
  without them, as on Fedora; alarm-aurora's build picks them up only because
  its build root has them.
- `"cross": false`: the build runs the compiler it builds.
- `dh_dwz` is skipped: dwz does not know clang's DWARF 5 sections
  (`.debug_str_offsets`, `.debug_addr`) and failed the first build after
  every test had passed.
- Status: built emulated (its `extra_sources` become component orig
  tarballs): the first build passed `make test-h13`, the H14 fixture
  programs and the installed compiler's H14 hash check (27 minutes), then
  stopped in dh_dwz; the rebuild with dh_dwz skipped ran with nocheck (the
  install-time hash check still runs and passed) and succeeded in 13 minutes.
  The package depends only on Debian libraries (libffi8, libicu78, libxml2-16,
  zlib1g, libstdc++6 and the like); mil-hwxc finds the private libraries
  through its RUNPATH.

### omdrop-awdl (upstream, 0.10.5-1)

- Binary: omdrop-awdl (all). Helpers in /usr/lib/omdrop (upstream's path, as
  alarm-aurora; fedora-aurora moves them to /usr/libexec), awdl0.service and
  awdl-warmup.service installed disabled and not started
  (`dh_installsystemd --no-enable --no-start`), the user unit
  airdrop-receiver.service not enabled (`dh_installsystemduser --no-enable`),
  the sleep hook, the polkit action, `99-awdl-unmanaged.conf` for
  NetworkManager, and the omdrop-plugin receiver in /usr/share/omdrop/receiver.
- Patches: alarm-aurora's three as `debian/patches/0001`-`0003`, unchanged and
  in alarm-aurora's order; its `sed` of the receiver unit is
  `0004-receiver-unit-for-the-packaged-receiver.patch` on
  `omdrop-plugin/share/airdrop-receiver.service` (the installed file is
  identical to alarm-aurora's).
- Depends map Arch's: iputils-ping, polkitd and pkexec (Debian splits pkexec),
  procps, python3-libarchive-c, plus kmod (the scripts run modprobe; Arch's
  base has it). The optdepends become Recommends: network-manager, python3-pil
  and Suggests: bluez, python3-dbus, python3-gi, keyutils.
  `Conflicts: brcmfmac-awdl-dkms` is kept although Debian has no such package.
- The check runs alarm-aurora's syntax checks and greps (Python files are
  parsed with `ast` instead of `py_compile`, so no bytecode lands in the tree).
- Note: the receiver installs omdrop-plugin's public Apple root and AAI CA
  certificates (`share/certs/apple_root_ca.pem`, `bin/apple-ca/*.pem`), as
  alarm-aurora does; they come from the upstream archive, not this repository.
- Status: built (cross); its `extra_sources` become component orig
  tarballs.

## Build notes

1. **`redistribute_source: false` is not honoured.** omarchy-ane-tools and
   mil-hwx-compiler are pinned with it because the upstream archives carry
   unrelated binary research inputs (alarm-aurora never mirrors them). A
   Debian source package ships the archive as its .orig tarball, so these
   source packages must not be published as they are. Either publish only the
   binary packages for such pins, or repack the orig without the research
   directories (Files-Excluded, a `+ds` version).
2. **Debian binNMUs sort above `+auroraN`.** Testing's arm64 network-manager
   binaries are `1.58.1-1+b1` (gtk+2.0 is `+b2`), and
   `1.58.1-1+aurora1 < 1.58.1-1+b1`. aurora-archive-keyring pins Aurora's
   archive at 990, so a fresh install takes Aurora's build; replacing an
   already installed binNMU would need 1000 or more. Alternatively the
   validator could allow a rebuild version based on the binNMU
   (`1.58.1-1+b1+aurora1`).
3. `DEB_BUILD_OPTIONS` passes through build-package to sbuild (nocheck for
   emulated builds).
4. `aurora-keep-config` and `aurora-omarchy-polkit` are n/a.

