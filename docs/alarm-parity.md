# alarm-aurora parity

Every package alarm-aurora builds has a Debian counterpart here: an Aurora build (a recipe in `packages/`), or Debian's own package where alarm-aurora only packages what Arch Linux ARM lacks and changes nothing. Versions are Debian testing's at the snapshot in `images/base.json`. Status: **recipe** (written, source package prepared), **built** (binary packages built), **debian** (Debian's package is used unchanged), **n/a** (not part of a Debian image, with the reason).

## Boot chain, kernel and platform

Details and deviations: [parity/boot.md](parity/boot.md). Stage 2 composed from these packages (bootchain_debian.py, then aurora-platform's prepare-stage2.py) covers every board the installer requires: 61 board payloads from 68 device trees, and 26 CTXR-slot payloads.

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| linux-aurora (+headers, aurora-userpages) | linux-aurora | upstream | built (cross; headers native only) |
| aura | aura | upstream | built |
| uboot-aurora | uboot-aurora | upstream | built |
| asahi-scripts (update-m1n1, bootchain) | asahi-scripts | upstream | built |
| aurora-boot | aurora-boot | native | built |
| aurora-firmware | aurora-firmware | native | built |
| aurora-firstboot (+power-budget, gamemode, secboot) | aurora-platform | upstream | built |
| aurora-keyring | aurora-archive-keyring | native | built (temporary test key) |

## Graphics, video and x86 compatibility

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| mesa-aurora (+vulkan, rusticl, lavapipe) | mesa | upstream (Debian's packaging, Aurora's source) | built (cross; Rusticl and lavapipe native only) |
| mesa-aurora-fex-guest | mesa-aurora-fex-guest | upstream | built (x86-64 only, on amd64; no i686 half) |
| aurora-flatpak-gl | aurora-flatpak-gl | native | **blocked**: Flatpak cannot run inside sbuild |
| libva-v4l2-request-avd | libva-v4l2-request | upstream | built |
| avd-fw | avd-fw | upstream | built (images match alarm-aurora's hashes) |
| fex-emu (+fex-emu-steam) | fex-emu | upstream | built (no x86-64 root filesystem provider yet) |
| aurora-steam-native (steam) | aurora-steam-native | upstream | built |

## Audio and speaker safety

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| alsa-ucm-conf-aurora | alsa-ucm-conf-aurora | upstream | |
| aurora-audio | aurora-audio | upstream | built |
| speakerguardd | speakerguardd | upstream | built |
| speakerguardd-v2 | speakerguardd-v2 | upstream | built |
| aurora-speaker-upgrade | aurora-speaker-upgrade | upstream | built |
| speakersafetyd | speakersafetyd | rebuild (Debian 3.0.0) | built |
| speakersafetyd-aurora-profiles | speakersafetyd-aurora-profiles | native | built (deprecated legacy protection, docs/parity/audio.md) |
| alsa-utils-aurora | alsa-utils | rebuild | built |
| pipewire | pipewire | rebuild | built |
| lsp-plugins-lv2 | lsp-plugins | rebuild | built |
| bankstown | bankstown-lv2 | debian | debian |
| triforce-lv2 | triforce-lv2 | debian | debian |
| lzfse | lzfse | debian | debian |

## Desktops

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| kwin-aurora | kwin | rebuild | recipe (needs a native arm64 build) |
| kinfocenter | kinfocenter | rebuild | built |
| plasma-setup | plasma-setup | upstream | built |
| mutter-aurora | mutter | rebuild | built |
| gnome-settings-daemon-aurora | gnome-settings-daemon | rebuild | built |
| iio-sensor-proxy-aurora | iio-sensor-proxy | rebuild | built |
| plymouth | plymouth | rebuild | built |
| plymouth-theme-aurora | plymouth-theme-aurora | native | built |
| aurora-logos | aurora-logos | native | built |
| power-profiles-daemon | power-profiles-daemon | rebuild | built |
| upower-aurora | upower | rebuild | built |

## Secure Enclave, Touch ID and device services

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| aurora-sep | aurora-sep | native | built |
| aurora-sep-luks | aurora-sep-luks | upstream | built |
| aurora-sep-sk | aurora-sep-sk | upstream | built |
| aurora-fido | aurora-fido | upstream | built |
| aurora-touchid-rearm | aurora-touchid-rearm | upstream | built |
| libfprint-aurora | libfprint | upstream (Debian's packaging) | built (131 tests pass) |
| fprintd-aurora | fprintd | rebuild | built (588 tests pass) |
| aurora-xart | aurora-xart | upstream | built |
| aurora-bless (+nvram, btsync, panel-nits) | aurora-bless | upstream | built |
| aurora-diag | aurora-diag | upstream | built |
| aurora-kbd-light | aurora-kbd-light | upstream | built |
| aurora-camera-denoise | aurora-camera-denoise | upstream | built |
| aurora-neo-platform-config | aurora-neo-platform-config | upstream | built |
| aurora-m5-platform-config | aurora-m5-platform-config | native | built |
| aurora-wifi-firmware | aurora-wifi-firmware | upstream | built |

## Networking, storage and applications

| alarm-aurora | Debian | Kind | Status |
| --- | --- | --- | --- |
| networkmanager-aurora | network-manager | rebuild | built |
| iwd-aurora | iwd | rebuild | built |
| udisks2 | udisks2 | rebuild | built |
| docker | docker.io | rebuild | built |
| firefox | firefox | rebuild (unstable's 160.0.1) | built (native arm64) |
| gtk2 | gtk+2.0 | debian | debian |
| aurora-system-fixes | aurora-system-fixes | native | built |
| aurora-keep-config |  | n/a | n/a: dpkg keeps edited conffiles |
| aurora-omarchy-polkit |  | n/a | n/a: Omarchy only; not in alarm-aurora's KDE/GNOME images |
| omarchy-ane-tools | omarchy-ane-tools | upstream | built (binaries only may be published) |
| mil-hwx-compiler | mil-hwx-compiler | upstream | built (binaries only may be published) |
| omdrop-awdl | omdrop-awdl | upstream | built |
