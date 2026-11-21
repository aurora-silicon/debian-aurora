# Graphics, video and x86 compatibility

Debian counterparts of alarm-aurora's Mesa, video decode, FEX and Steam
packages. Debian versions are testing's at snapshot 20261120T000000Z.

| alarm-aurora | Debian source → binaries | Kind | Version | Status |
| --- | --- | --- | --- | --- |
| mesa-aurora, vulkan-aurora, opencl-rusticl-aurora, vulkan-lavapipe-aurora | mesa → libgl1-mesa-dri, libegl-mesa0, libglx-mesa0, libgbm1, libgbm-dev, mesa-libgallium, mesa-vulkan-drivers, mesa-opencl-icd, mesa-common-dev, libegl1-mesa-dev, libgl1-mesa-dev, libgles2-mesa-dev, mesa-va-drivers, mesa-vdpau-drivers | upstream (mesa-aurora pin, Debian's 26.1.6-1 packaging) | 26.3.0~devel.202611150611.d4ad4a4dce6-1 | built (cross: everything but Rusticl and lavapipe, see below) |
| mesa-aurora-fex-guest | mesa-aurora-fex-guest → same (Architecture: all, x86_64 payload) | upstream (mesa-aurora-fex-guest pin) | 26.3.0~devel.202611150611.d4ad4a4dce6-1 | built (cross, on the amd64 build machine); x86_64 only, the i686 half is missing (below) |
| aurora-flatpak-gl | aurora-flatpak-gl → same | upstream (mesa-aurora pin, network) | 26.3.0~devel.202611150611.d4ad4a4dce6-1 | recipe; build blocked by the build root (flatpak-builder's bubblewrap cannot create namespaces inside sbuild's chroot) |
| libva-v4l2-request-avd | libva-v4l2-request → same | upstream (libva-v4l2-request-avd pin) | 1.3+r11.g4f60c51-1 | built (cross) |
| avd-fw | avd-fw → same (Architecture: all) | upstream (avd-fw pin) | 0.1.aurora4-1 | built (cross); all eight images match the clang 22 hash manifest |
| fex-emu, fex-emu-steam | fex-emu → fex-emu, fex-emu-config, fex-emu-steam | upstream (`{"git": "fex-emu", "submodules": true}`) | 2610+git202611061239.0c08727ae4c-1 | built (cross: fex-emu and fex-emu-steam; fex-emu-config is native-only) |
| aurora-steam-native, steam | aurora-steam-native → aurora-steam-native, steam (Architecture: all) | upstream (aurora-steam-native pin) | 1:0+git202610301134.c06f610e360-1 | built (cross); its three tests pass on the build host |

## mesa

Aurora's Mesa (aurora-silicon/mesa d4ad4a4dce6, VERSION 26.3.0-devel) with
Debian testing's mesa 26.1.6-1 `debian/` directory adapted to it. Every
Debian binary package name that applies is kept, at a version above
26.1.6-1, so Debian's reverse dependencies stay satisfied and apt upgrades
Debian's packages to these.

alarm-aurora's packages map onto Debian's:

- mesa-aurora (GL, EGL, GBM, Asahi Gallium, Zink, softpipe) →
  libgl1-mesa-dri, libegl-mesa0, libglx-mesa0, libgbm1, mesa-libgallium.
- vulkan-aurora (the Borealis Vulkan driver) → mesa-vulkan-drivers.
- vulkan-lavapipe-aurora → mesa-vulkan-drivers, where Debian ships lavapipe.
  alarm-aurora splits it out so that an Arch libLLVM soname move cannot
  strand the native drivers; in Debian a libllvm21 dependency is an ordinary
  versioned package that apt keeps, and keeping lavapipe where Debian has it
  keeps Debian's contract for packages that expect it there. The binaries
  keep alarm-aurora's property: only Rusticl and lavapipe link LLVM.
- opencl-rusticl-aurora → mesa-opencl-icd.

Build, as alarm-aurora's PKGBUILD: two trees. `build-tools` has LLVM and
makes the CL compilers (mesa_clc, vtn_bindgen2, asahi_clc), Rusticl and
lavapipe; `build` has the native GL and Vulkan drivers with `-Dllvm=disabled
-Dspirv-tools=disabled -Dmesa-clc=system -Dprecomp-compiler=system`, using
those compilers. Driver selection and options are alarm-aurora's
(`-Dgallium-drivers=asahi,zink,softpipe -Dvulkan-drivers=asahi`, plus
`swrast` and `-Dgallium-rusticl=true` in the LLVM tree, `-Dglx=dri
-Dgles1=enabled -Dgles2=enabled -Dglvnd=enabled -Dvideo-codecs=all
-Dexpat=enabled -Dzstd=enabled -Dlmsensors=enabled -Dlibunwind=disabled
-Dvalgrind=disabled`). MESA_GIT_SHA1_OVERRIDE is the pinned commit (read from
`debian/aurora-pin`). alarm-aurora's checks run in every build: the Borealis
driverInfo names the commit (`(git-d4ad4a4dce), Borealis`), Rusticl and
lavapipe are AArch64, lavapipe's manifest names its library, and no other
library has a NEEDED libLLVM or libSPIRV-Tools. Mesa's meson tests (the
native tree's) gate the build (`dh_auto_test` without Debian's `-`), as they
gate alarm-aurora's; cross builds skip them (nocheck).

Deviations from Debian's packaging, and why:

- Drivers: alarm-aurora's set only. Debian's arm64 build has 20 Gallium and 11
  Vulkan drivers for other hardware; this one has Asahi (with the kmsro
  display aliases such as apple_dri.so and aurora_dri.so), Zink and softpipe.
  No llvmpipe in libgl1-mesa-dri: softpipe is the software GL, as in
  alarm-aurora.
- Dropped binaries: mesa-teflon-delegate (no Teflon/Rocket; alarm-aurora
  builds neither) and mesa-drm-shim (no `-Dtools=drm-shim`). Debian's
  26.1.6-1 copies stay installable; nothing depends on them.
- No Gallium VA-API front end (alarm-aurora builds none; video decode is
  libva-v4l2-request). mesa-libgallium no longer provides `va-driver` or
  enhances libva2; it keeps the mesa-va-drivers/mesa-vdpau-drivers provides
  and transitional packages for upgrades.
- Vulkan layers: anti-lag, device-select, overlay and screenshot are built
  into mesa-vulkan-drivers, where Debian ships them (alarm-aurora builds none
  and depends on Arch's vulkan-mesa-implicit-layers instead). intel-nullhw
  is dropped: it needs an Intel driver.
- `libudev-dev` added: alarm-aurora's Vulkan driver links libudev (systemd-
  libs is always present on Arch) for VK_KHR_display hotplug; Debian's build
  has none.
- New install entries for Aurora's drirc files: 00-asahi-defaults.conf and
  00-zink-defaults.conf (libgl1-mesa-dri), 00-hk-defaults.conf
  (mesa-vulkan-drivers, instead of radv's).
- `-Dvulkan-manifest-per-architecture=false` and the multiarch dri path stay
  Debian's (asahi_icd.json, lvp_icd.json with a bare library name).
- VERSION is the Debian version, as Debian does, so libgallium's file name
  changes with every upload; the clean target restores upstream's VERSION.
- reportbug control/script dropped: bug reports belong to Aurora, not
  Debian's BTS. control.in/regen_control, the cargo wrap rewriting (NVK) and
  watch/gbp files are gone; Debian's two small patches still apply and stay.
- `dh_missing --list-missing` instead of compat 13's failure, so one new
  file in Aurora's tree does not fail the build; the cross build listed
  none.
- LLVM 21 (Debian's default and Debian's mesa choice); alarm-aurora uses
  Arch's current LLVM.

### Cross builds

Debian's LLVM development packages cannot be cross-installed: llvm-21-dev
is not Multi-Arch, and llvm-21-tools of the host architecture needs
python3-yaml of the host architecture, which conflicts with the build
machine's Python that Mesa's build (python3-mako) needs. So a cross build
has no host LLVM. With the `cross` build profile:

- `build-tools` is a build-machine (amd64) tree that makes only the CL
  compilers (`-Dtools=asahi -Dmesa-clc=enabled -Dprecomp-compiler=enabled`,
  no drivers), as Mesa documents for cross builds; LLVM, clang,
  LLVMSPIRVLib and SPIRV-Tools are build dependencies with `:native`.
- Rusticl and lavapipe are not built: mesa-opencl-icd has
  `Build-Profiles: <!cross>` and mesa-vulkan-drivers has no lavapipe.

The first cross attempt (host LLVM, bindgen and the CL compilers run through
binfmt_misc) stopped at dependency resolution, before any compiling: first on
python3-mako, which needed `:native`, and, checked afterwards, host LLVM
cannot be installed beside the build machine's Python at all. That led to
the profile above; the second attempt built (10.5 minutes with 6 jobs).
Native arm64 builds are complete and are the reference; none has run here.

## mesa-aurora-fex-guest

The x86 Mesa that FEX's guests load, from the same Mesa commit as the host
`mesa`. Design for Debian:

- Architecture: all, built on an amd64 build machine (with
  `build-package --cross`, where arch-all packages build natively on amd64).
  debian/rules stops with a message on any other build machine, as
  alarm-aurora's PKGBUILD and fedora-aurora's spec do. It is the one package
  here with non-arm64 code.
- A build-machine compiler tree (LLVM) makes mesa_clc, vtn_bindgen2 and
  asahi_clc; the x86_64 drivers are built with alarm-aurora's options
  (Asahi, Zink, softpipe, Borealis, no LLVM, SPIRV-Tools, lm-sensors,
  libunwind, video codecs or Vulkan layers; release build without the host's
  flags) and the upstream VERSION.
- The layer is laid out for Debian and Ubuntu root filesystems: x86_64 in
  `usr/lib/x86_64-linux-gnu` (DRI drivers in its `dri/`), Vulkan manifest
  `asahi_icd.x86_64.json` with an absolute library path, installed under
  `/usr/share/guestos/aurora-fex-mesa-layer` with `.aurora-mesa-commit`;
  headers and pkg-config files removed. alarm-aurora's layer uses
  `usr/lib64` and `usr/lib`; fex-emu's aurora-fex-rootfs was taught the
  Debian directory (below).
- alarm-aurora's checks: the drivers are ELF64 x86-64, nothing NEEDs libLLVM,
  libSPIRV-Tools, libsensors or libunwind, and Borealis names the commit.
  dh_strip, dh_makeshlibs and dh_shlibdeps do not run for an Architecture:
  all package, so the guest libraries are neither stripped nor scanned
  (guest code: nothing on the host links it).
- aurora-fex-mesa.service (alarm-aurora's unit) is enabled, as Aurora images
  enable it. alarm-aurora's pacman hook and .install become
  `dh_installsystemd --no-restart-after-upgrade` (stopped in preinst before
  the layer below the overlay is replaced, started in postinst) and a preinst
  check that refuses the upgrade if the overlay is still mounted after the
  stop. The fex-emu trigger then remounts the provider.
- Depends on `libgl1-mesa-dri` and `mesa-vulkan-drivers` of exactly its own
  version (the host mesa, kept in lockstep like alarm-aurora's mesa-aurora
  and vulkan-aurora), mount and util-linux.

Cross attempts: the first stopped at dependency checking (`linux-libc-dev`
is Multi-Arch: foreign, so `:native` cannot be satisfied); the second built
but left the unit out (dh_installsystemd needs `--name` for a
`package.name.service` file); the third built the complete package (12 MB,
about 3.5 minutes).

Missing: the i686 half. Debian build dependencies can only name the host or
build architecture (`:native`), the build root has no i386 foreign
architecture, and the i686 build needs i386 libdrm, expat, zlib, zstd, X11,
xcb, wayland, glvnd, vulkan-loader and libudev development packages. 32-bit
x86 programs under FEX keep their RootFS's own Mesa. Possible ways: a recipe
option for an extra foreign architecture in the build root, or a build that
downloads the signed i386 packages from the snapshot into a private sysroot
(network).

## aurora-flatpak-gl

alarm-aurora's recipe (helper, environment.d and profile.d settings,
build-extension.sh, the manifest and the validators, unchanged except below)
in `debian/gl`. The build installs the aarch64 Freedesktop 25.08 and 26.08
Platform, SDK and LLVM 22 SDK extension from Flathub into a private user
installation, builds org.freedesktop.Platform.GL.aurora with flatpak-builder
for both branches into a local OSTree repository, checks the repository with
alarm-aurora's validator, and ships it in `/usr/share/aurora-flatpak-gl/repo`.
postinst runs `aurora-flatpak-gl enable` (a failure only prints the retry
command), prerm runs `disable`.

Deviations:

- Kind upstream on the mesa-aurora pin instead of native: the manifest's
  Mesa module builds from this source package's orig tarball (the same
  archive and sha256 as sources.json) instead of downloading it again, and
  the version is the host mesa's, so the package depends on
  libgl1-mesa-dri and mesa-vulkan-drivers of exactly that version, as
  alarm-aurora's depends on mesa-aurora and vulkan-aurora. The other
  manifest sources (SPIRV-Headers, SPIRV-Tools, the translator,
  llvm-project's libclc, PyYAML) are fetched by flatpak-builder at their
  pinned commits and hashes, as in alarm-aurora.
- flatpak-builder runs with `--jobs` from DEB_BUILD_OPTIONS.

Status: not built, for a reason outside the packaging. Three cross attempts:
the first stopped at dependency checking (`:native` on the Multi-Arch:
foreign bubblewrap, dbus-daemon and git); the second installed the 25.08
runtimes from Flathub and stopped at flatpak-builder's cache, whose OSTree
branch is named after the manifest's path, and a `~` from the version is not
valid in a ref (the work directories are now in `/tmp/aurora-flatpak-gl`);
the third reached the first module and stopped there:

    bwrap: No permissions to create a new namespace, likely because the
    kernel does not allow non-privileged user namespaces.

The host allows unprivileged user namespaces (max_user_namespaces 253486,
unprivileged_userns_clone 1); sbuild's unshare backend chroots into the
build root, and the kernel refuses CLONE_NEWUSER to a chrooted process, so
nothing that needs bubblewrap (flatpak-builder, `flatpak build`) can run in
a build. alarm-aurora builds with makepkg in the build user's own namespace;
fedora-aurora builds the repository outside rpmbuild (scripts/build-rpm runs
build-extension.sh and hands the spec a repository tarball, Source10) and the
spec only validates and installs it. Either the build root needs a
pivot_root-based session, or scripts/build-package builds the repository the
Fedora way and gives the recipe a second orig tarball
(`aurora-flatpak-gl_<version>.orig-repo.tar.xz`) to validate and install.

## libva-v4l2-request

The AVD fork of libva-v4l2_request at 4f60c51 with alarm-aurora's three
patches (all apply unchanged: offline test portability, Chrome's AV1 path,
multi-tile AV1), codecs H.264, HEVC, VP9 and AV1 forced on, installed in
Debian's VA driver directory with the `asahi_drv_video.so` and
`aurora_drv_video.so` aliases. The binary package provides `va-driver`
(libva2 recommends one). Its 61 meson tests run in native builds; cross
builds skip them.

## avd-fw

Open Cortex-M3 firmware for the Apple Video Decoder, built from source with
Debian's clang-22, lld-22 and llvm-22 through the source's `llvm.ini` cross
file and without the host's build flags (alarm-aurora's `!buildflags`).
Every build checks the eight images against alarm-aurora's clang 22 hash
manifest (debian/check-firmware.py, the same list); Debian's clang 22.1.8
reproduces all eight hashes. Images in `/usr/lib/firmware/apple` (mode 644),
the linked ELF files in `/usr/lib/debug/firmware/apple` as in alarm-aurora.
Architecture: all instead of aarch64: the package holds firmware for a
coprocessor, not host code (linux-aurora depends on it by this name).

## fex-emu

Aurora's FEX fork at 0c08727ae4c with its submodules, alarm-aurora's three
patches (all apply unchanged), built with clang and lld, LTO,
`-DTUNE_CPU=none`, no thunks, OVERRIDE_VERSION `FEX-2610-aurora-g0c08727`,
plus the separate Steam compatibility tool build ("FEX (Aurora)",
fex-emu-steam, in `/usr/share/steam/compatibilitytools.d/fex-aurora`).

Deviations:

- **fex-emu-config.** FEXConfig is a separate binary package, so fex-emu does
  not pull in Qt 6 through its shared library dependencies (alarm-aurora
  ships it in fex-emu with Qt as an optional dependency, which pacman
  allows; Fedora splits it into fex-emu-utils). It has `Build-Profiles:
  <!cross>`: Qt 6 is not cross-built here.
- **fmt.** Both builds use the bundled fmt 12 (the pinned submodule):
  Debian's libfmt-dev 11.1 fails on FEX's compiled format strings.
  alarm-aurora links Arch's fmt. xxHash is Debian's in native builds (FEX
  bundles it when cross-compiling).
- **RootFS.** alarm-aurora depends on fex-emu-rootfs-arch (the Asahi ALARM
  image) and names it in FEX's missing-RootFS error. Debian has no RootFS
  package, so ROOTFS_PACKAGE is not set (FEX points to FEXRootFSFetcher) and
  there is no dependency. The global config still names
  `/usr/share/fex-emu/RootFS/default.erofs`, and the lower-layer mount unit
  waits for an image there.
- **Global config** in `/etc/fex-emu/Config.json` (a conffile, as
  alarm-aurora's `backup=` makes it) with `/usr/share/fex-emu/Config.json`
  a symlink to it.
- **Helper paths** `/usr/libexec/fex-emu` (fedora-aurora's) instead of
  `/usr/lib/fex-emu`; the drop-in and aurora-fex-provider-up name them.
- **pacman hooks → dpkg triggers.** fex-emu's triggers on
  `/usr/share/fex-emu/RootFS` and `/usr/share/guestos/aurora-fex-mesa-layer`
  run aurora-fex-provider-up (alarm-aurora's 70 and 71 hooks: on install,
  upgrade and removal of an image or of mesa-aurora-fex-guest). postinst and
  postrm are alarm-aurora's .install. dh_installsystemd leaves fex-emu's
  units alone: nothing enables or restarts the lower-layer mount; the
  provider service pulls it in and aurora-fex-provider-up restarts both.
- **aurora-fex-rootfs** also looks for the x86-64 loader and Vulkan driver in
  `usr/lib/x86_64-linux-gnu`, where a Debian or Ubuntu RootFS and Debian's
  mesa-aurora-fex-guest layer keep them.
- README.aurora is rewritten for Debian (apt, the missing RootFS package,
  qemu-user-binfmt).
- Recommends aurora-userpages, mesa-aurora-fex-guest, erofs-utils and
  squashfs-tools (alarm-aurora: optional dependencies; Fedora: Recommends);
  depends on erofsfuse, squashfuse, fuse3 and util-linux.
- FEXCore headers and libFEXCore.so stay in fex-emu, as in alarm-aurora.
- dh_dwz is skipped (clang's DWARF 5).

Cross attempts: the first stopped at configure (debhelper's `-GUnix
Makefiles` against the recipe's `-GNinja`; now `--buildsystem=cmake+ninja`),
the second at its first compile (Debian's fmt 11.1, now the bundled fmt);
the third built (2.5 minutes with 6 jobs). fex-emu has no -dbgsym package:
FEX links its tools with `--gc-sections --strip-all` (its LinkerGC macro).

The submodule checkout is 1.4 GB (vixl alone is 412 MB, the three x86
test-binary repositories about 800 MB), giving a 218 MB orig tarball; the
Debian packages ship none of the test binaries.

## aurora-steam-native and steam

alarm-aurora's split: aurora-steam-native (the launcher, the per-user
installer of Valve's client and Aurora Play, in `/usr/lib/aurora-steam-native`)
and `steam` (`/usr/bin/steam` from alarm-aurora's template, steam.desktop).
The template's hint for a kernel without 4 KiB pages names Debian's
update-grub. Dependencies mapped to Debian: aurora-userpages, fex-emu,
libgtk2.0-0t64, libibus-1.0-5, lsof, python3; Recommends
mesa-aurora-fex-guest, mesa-vulkan-drivers, python3-gi, gir1.2-gtk-4.0,
gir1.2-adw-1, libnotify-bin. steam depends on aurora-gamemode, python3 and
systemd and conflicts with Debian's steam-installer and steam-launcher (same
/usr/share/applications/steam.desktop; they are x86 only). Epoch 1, as
alarm-aurora's: steam-devices declares relations on `steam (<< 1.0.0.51-1~)`,
which an unversioned 0+git would match. alarm-aurora's checks: the filled-in
template (bash -n, no placeholder left, the userpages and lib lines) in every
build; desktop-file-validate and the three tests when tests run (not in
cross builds). The tests were also run on the build host and pass.

## Build notes

- **Submodules.** `git submodule update --init --recursive` fetches every
  submodule, including FEX's x86 test-binary repositories (about 800 MB)
  that alarm-aurora does not use; sources.json's `extra_sources` lists the
  ten it needs.
- **x86 build host.** mesa-aurora-fex-guest sets `"build_on": "amd64"`: it
  builds on an amd64 machine with `--cross`. Its i686 layer needs an extra
  foreign architecture (i386) in the build root.
- **No user namespaces in builds.** sbuild's unshare backend chroots, so
  bubblewrap cannot run in a build; aurora-flatpak-gl's repository cannot
  be built there (above).
- **Cross builds with LLVM.** Debian's LLVM packages are not cross-
  installable (above); any package that needs host LLVM headers cannot
  cross-build.

## Open questions

- No Debian package provides an x86-64 FEX RootFS image
  (`/usr/share/fex-emu/RootFS/default.erofs`); alarm-aurora uses ALARM's
  fex-emu-rootfs-arch, fedora-aurora Fedora's fex-emu-rootfs-fedora. A
  Debian or Ubuntu x86-64 image package (built with mmdebstrap, with
  graphics_provider.json for Steam) would complete the provider chain.
- qemu-user-binfmt registers qemu for the same x86 binaries; with both
  installed, systemd-binfmt's order decides. Should fex-emu override it, as
  fedora-aurora overrides binfmt-dispatcher?
- The i686 half of mesa-aurora-fex-guest (above).
- Native arm64 builds have not run here: mesa's LLVM tree, Rusticl, lavapipe
  and Mesa's tests, fex-emu-config, libva-v4l2-request's tests.
