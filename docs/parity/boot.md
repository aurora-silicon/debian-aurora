# Boot chain, kernel and platform

| alarm-aurora | Debian source → binaries | Kind | Version |
| --- | --- | --- | --- |
| linux-aurora, linux-aurora-headers, aurora-userpages | linux-aurora → linux-image-7.3.0-2-aurora, linux-headers-7.3.0-2-aurora, linux-image-aurora, linux-headers-aurora, aurora-userpages | upstream (kernel-aurora pin) | 7.3.0-2 |
| aura | aura | upstream (aura pin) | 1.0.0~b17-1 |
| uboot-aurora | uboot-aurora | upstream (uboot-aurora pin) | 2026.07.aurora11-1 |
| asahi-scripts | asahi-scripts | upstream (asahi-alarm tag 20261023) | 20261023-1 |
| aurora-boot | aurora-boot | native | 20261018.1 |
| aurora-firmware | aurora-firmware | native | 20261018.1 |
| aurora-firstboot, aurora-power-budget, aurora-gamemode, aurora-secboot | aurora-platform → the same four | upstream (aurora-firstboot pin) | 0.1.13-1 |
| aurora-keyring | aurora-archive-keyring | native | 2026.11.1 |

## Deviations from alarm-aurora, and why

- **Kernel packaging.** Debian's conventions instead of Arch's single in-place package: versioned `linux-image-<release>`/`linux-headers-<release>` with `linux-image-aurora`/`linux-headers-aurora` meta packages, so an upgrade installs the new kernel beside the running one (the Stage 2 updater's DT ABI guard is built for several kernels, as on Fedora). The release is `7.3.0-2-aurora` (`ABINUM` in debian/rules, bumped with each pin; debian/control names it, and the build checks they agree) instead of Arch's `-ARCH` suffix, which only Arch's DTB discovery needed. Image in `/boot/vmlinuz-<release>` (where update-grub looks), device trees in `/usr/lib/modules/<release>/dtb/apple` with `dtb-abi` (the layout the shared updater reads by default). Configuration, toolchain (clang 23.1.5, which Debian testing ships as clang-23, the pinned Rust 1.99.0 and private bindgen) and the CTXR/Rust/option assertions are alarm-aurora's. Maintainer scripts run `/etc/kernel/{preinst,postinst,prerm,postrm}.d`, which drive dracut, update-grub, update-m1n1 and aurora-secboot. Headers carry host tools, so they build only natively (`<!cross>`).
- **Stage 2 updater.** alarm-aurora's `bootchain.py` and shared tests, unchanged; `bootchain_debian.py` replaces `bootchain_arch.py` and only drops the `/boot/dtb` link and names `apt remove`. fedora-aurora's bootchain.py has moved on (Stage 2 signing in `apply()`, a T6050 device-tree node fix); the Arch-style `apply()` override is written against alarm-aurora's copy, so Debian follows alarm-aurora's and moves with it. Triggered by `/etc/kernel/postinst.d` and `postrm.d` (per kernel, like Fedora's kernel-install plugin) and by a dpkg trigger on `/usr/lib/asahi-boot` (aura and U-Boot updates). A refusal keeps Stage 2 and does not fail the apt transaction, as alarm-aurora's pacman hook does not. Like Fedora's wrapper, update-m1n1 leaves Stage 2 to the image builder when there is no device tree.
- **Initrd.** dracut, so the initrd follows fedora-aurora's modules (asahi-scripts' `kernel-modules-asahi` and `asahi-firmware`, `98aurora-peripherals`, `91aurora-usb4`, `91aurora-early-kms`, aurora-platform's `97aurora-root`), with alarm-aurora's module lists where they are newer (the T6040 USB2 and DPTX PHYs in early KMS, and a `91aurora-display` module for alarm-aurora's display-chain hook). Packages that change initrd contents activate Debian dracut's `update-initramfs` trigger.
- **GRUB.** `grub-efi-arm64-bin` and `grub2-common` only: the full `grub-efi-arm64` package reinstalls GRUB on every update, which would replace aurora-platform's hardened core image. The console drop-in recognises Debian's default 5 s menu (no `GRUB_TIMEOUT_STYLE`).
- **Presets.** `80-aurora-image.preset` with Debian's ssh unit names, plus `99-aurora-default.preset` (`disable *`): Debian ships no catch-all, and the first boot's enable-only preset pass would otherwise enable every installed unit.
- **No per-machine keyring.** alarm-aurora's `aurora-alarm-keyring.service` initialises pacman's local master key; apt has no equivalent. `aurora-archive-keyring` ships Aurora's public key and the apt pin (priority 990 for origin "Aurora Silicon").
- **aurora-platform patch.** The Debian support in aurora-platform (`finalize-image`'s `debian-*` branch, the `initrd.img-*` keymap check) is on its `feat/debian` branch; until the pin includes it, the package carries the runtime part as a patch and `build-image` takes the finalizer from `AURORA_PLATFORM_SOURCE`.
- **aurora-secboot.** Debian's kernel packages run `/etc/kernel` hooks rather than kernel-install plugins, so the package adds a postinst.d/postrm.d hook calling the same `aurora-secboot hook`. A later initrd rebuild through `update-initramfs` alone does not rebuild the UKI; that needs a dracut hook and is open.
- **aura / kernel version constraints.** alarm-aurora's `Conflicts: aurora-fido<0.2.0-2` is dropped: no older Debian aurora-fido exists. `aurora-audio` and `avd-fw` are unversioned until their Debian versions settle.

## Open

- The archive key is the production Aurora Debian Archive Signing Key (`EC1D8379B48ADD58D5C8A74E52BF31CC0019FCFE`, see `packages/aurora-archive-keyring/keys/README.md`).
- Hardware: nothing here has booted a Mac. The kernel and boot chain were built from source only.
