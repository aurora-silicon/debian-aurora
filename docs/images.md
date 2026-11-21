# Images

```sh
scripts/build-image PROFILE REPOSITORY [CHANNEL]
```

`PROFILE` is `debian-kde`, `debian-gnome` or `debian-minimal`. `REPOSITORY` is the signed Aurora package repository the image installs from: an https URL, or a local `scripts/sign-repository.py` output directory, which `build-image` serves on loopback so apt reaches it at the same URL outside and inside the image. `CHANNEL` (`testing`, `stable` or `edge`) is the Aurora feed the installed system follows. The build needs root on a disposable native arm64 builder, as the shared finalizer does. In CI, `images.yml` runs it in a privileged `debian:testing` container on `ubuntu-24.04-arm`, from a `testing-YYYYMMDD.N` package release.

## The build

The build follows alarm-aurora's `scripts/build-image` step for step:

1. The disk is the same as alarm-aurora's: a GPT image with 4096-byte sectors, 6 GiB for minimal and 16 GiB for desktops. It has a 512 MiB EFI partition, a 1 GiB ext4 `/boot` (an XBOOTLDR partition) and a btrfs root with `root` and `home` subvolumes, compressed with `zstd:1`.
2. Install the base, Aurora's packages and the desktop. Configure the locale, the accounts, the units and the display manager.
3. Configure GRUB, the initrd and Stage 2 (`update-m1n1`).
4. Point apt at the live feeds, and check that the first boot finds nothing left to change.
5. Run `scripts/check-basics.py` on the root.
6. Seal the image with aurora-platform's `images/finalize-image`. Without `AURORA_PLATFORM_SOURCE`, this is the `aurora-firstboot` pin in `sources.json`. With `AURORA_PLATFORM_SOURCE`, it is a local checkout.
7. Prepare the CTXR Stage 2 files when aura has no monitor, then run `check-basics.py` on the EFI and `/boot` files the installer writes.
8. Pack `out/<profile>-filesystems.tar.zst` and its `.sha256`.

## Where Debian differs from alarm-aurora

### Base system

- alarm-aurora unpacks the signed Arch Linux ARM root filesystem and initializes a pacman keyring. Here, `mmdebstrap --variant=important` builds the base from the snapshot pinned in `images/base.json`, checked with Debian's archive keyring.
- The built system follows live Debian testing (`testing`, `testing-updates`, `testing-security` on deb.debian.org) and `https://aurorasilicon.org/debian-aurora/<channel>`, signed with `aurora-archive-keyring`'s key. The build-time source and key are removed.

### The apt pin

During the build, apt checks the Aurora repository against `AURORA_ARCHIVE_KEY` (by default `packages/aurora-archive-keyring/keys/aurora-debian-archive.asc`). Aurora's builds replace Debian's packages of the same name, even when Debian has a newer version. The pin that does this is `aurora-archive-keyring`'s `/etc/apt/preferences.d/aurora.pref`: `o=Aurora Silicon` at priority 990. The build writes the pin before installing anything; the package installs the same file. alarm-aurora gets the same effect by listing `[aurora]` before `[core]` and `[extra]`. After installation, the build fails if any of these hold:

- Debian's `alsa-ucm-conf-asahi`, `asahi-audio` or `sddm` is installed;
- `alsa-ucm-conf-aurora`, `aurora-audio` or `linux-image-aurora` is missing;
- `libgl1-mesa-dri`, `libegl-mesa0` and `mesa-vulkan-drivers` are not one Aurora Mesa build.

### Packages and the desktop

- Debian's package names:
  - `linux-image-aurora`, `network-manager`, `openssh-server` and `fprintd`/`libpam-fprintd`;
  - `kde-plasma-desktop` for `plasma-meta`, and `gnome-core` and `gdm3` for GNOME;
  - `grub-efi-arm64-bin` and `grub2-common`. Debian's `grub-efi-arm64` would reinstall GRUB on every update and undo the hardened core.
- Desktops install with recommendations, which bring Debian's desktop applications. Minimal images install without them.
- SDDM is excluded. `kde-plasma-desktop` recommends it, and the install refuses it (`sddm-`). Plasma Login is the KDE display manager: its greeter runs on KWin Wayland at the display's scale. A drop-in keeps the splash up until the greeter starts, as GDM does.

### Locale and accounts

- The default locale is written twice: to `/etc/default/locale`, which Debian's PAM sessions read through `pam_env`, and to `/etc/locale.conf`, which systemd reads. alarm-aurora writes only `/etc/locale.conf`. `en_US.UTF-8` is enabled in `/etc/locale.gen` and generated.
- Debian has no `wheel` group. The image creates it as a system group, and `aurora-firstboot` puts the owner in it, as on Arch. `root` is locked.

### Units

- The images contain no account, no machine ID and no ssh host keys. Debian's `ssh.service` expects host keys, so a drop-in (`ssh.service.d/10-aurora-host-keys.conf`) runs `ssh-keygen -A` before sshd starts. Remote login stays off until the owner enables it.
- Debian's unit names: `ssh.service` and `ssh.socket` (`sshd.service` is an alias), `gdm.service`, `plasmalogin.service`. `systemd-resolved` is its own package. NetworkManager uses it for DNS, and systemd-networkd is disabled.

### Presets

An install's first boot applies every preset in enable-only mode. On Debian, maintainer scripts enable units at installation without consulting presets, and Debian ships no `99-default.preset`. Without one, that first boot would enable every installed unit nobody chose.

`aurora-boot` carries two presets:

- `80-aurora-image.preset`: alarm-aurora's units, with Debian's names.
- `99-aurora-default.preset` (`disable *`): the disable-everything rule Arch and Fedora ship as `99-default.preset`.

The build applies the presets before enabling the image's own units. It fails if applying them again would still change a unit. The finalizer checks the same in enable-only mode.

### Initrd and GRUB

- The initrd is built by dracut, with `aurora-boot`'s dracut modules (alarm-aurora uses mkinitcpio). It is written to Debian's `/boot/initrd.img-<kernel>`, and the finalizer regenerates it with its `aurora-root` module.
- `/etc/default/grub` starts from `grub2-common`'s template, and `update-grub` writes `/boot/grub/grub.cfg`. Debian's GRUB has Arch's layout, so the finalizer hardens it with `harden-grub.py`'s `arch` flavour, and `check-basics.py --esp` checks the same files as on alarm-aurora.

### Image checks

`scripts/check-basics.py` is alarm-aurora's, read with Debian's file names:

- the locale in both locale files;
- PAM services that `@include common-auth`, with vendor files in `/usr/lib/pam.d` and a service without a file run as `other`;
- `sudo-i` for `sudo -i`;
- logind's main file and drop-ins as Debian's systemd reads them;
- `ssh.service` and `ssh.socket`.

It checks the Touch ID policy, not how a package implements it. `fprintd`'s pam-auth-update profile puts `pam_fprintd` in `common-auth` behind a service test, and a `sufficient` line in each service file would pass as well. Its NixOS (`--system`) and Fedora (`--grub-flavor fedora`) paths are gone.

### Not carried over yet

These alarm-aurora image steps have no Debian counterpart yet:

- the Edge overlay snapshot (an `edge` image installs from the given repository and follows the Edge feed);
- the Flatpak GL runtime check;
- the checks that the camera filter, keyboard backlight and Wi-Fi firmware units are enabled.
