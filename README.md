# debian-aurora

Debian testing (forky) packages and images for Aurora Linux on Apple Silicon Macs: the Debian producer beside [alarm-aurora](https://github.com/aurora-silicon/alarm-aurora) (Arch Linux ARM), fedora-aurora, nixos-aurora and omarchy-aurora. It mirrors alarm-aurora package for package and image step for step, and publishes KDE Plasma, GNOME and minimal images (`debian-kde`, `debian-gnome`, `debian-minimal`) through the same contract as the other producers: aurora-distributions' `build-payload.yml` turns an attested image build into a signed payload for the native [Aurora installer](https://github.com/aurora-silicon/aurora-installer).

The installer offers them as "Aurora, based on Debian testing". Debian's trademark policy keeps its marks out of product names, so the product is Aurora, and "based on Debian testing" is a factual description.

## Development status

Nothing here is hardware-qualified yet. debian-minimal, debian-kde and debian-gnome, built locally, have been installed with a test build of the installer and booted on a MacBook Air (M1, J313). No other Mac has run them, and the CI workflows have not run yet.

- Every alarm-aurora package has a recipe, or is Debian's own package, or is marked not applicable: [docs/alarm-parity.md](docs/alarm-parity.md), with each package group's build results in `docs/parity/`.
- Publication needs the production archive key: its public half in `packages/aurora-archive-keyring/keys/aurora-debian-archive.asc` and its fingerprint in `keys/fingerprint.txt` ([packages/aurora-archive-keyring/keys/README.md](packages/aurora-archive-keyring/keys/README.md)).
- CI image builds need the `aurora-firstboot` pin in `sources.json` to reach an aurora-platform commit whose `images/finalize-image` seals `debian-*` profiles. Until then, local builds use a local checkout (`AURORA_PLATFORM_SOURCE`, below).
- Payload publication needs aurora-distributions to accept `debian-*` profiles from this repository ([.github/workflows/publish-payload.yml](.github/workflows/publish-payload.yml)).

## Layout

| Path | What |
| --- | --- |
| `packages/<name>/` | One recipe per Debian source package ([docs/packaging.md](docs/packaging.md)) |
| `images/base.json` | The Debian testing snapshot that package builds and images start from |
| `sources.json` | Pinned upstream revisions, identical to alarm-aurora's |
| `scripts/recipe.py` | Turns a recipe into a Debian source package; `check` validates every recipe |
| `scripts/build-package` | Builds recipes with sbuild in a clean build root from the snapshot |
| `scripts/sign-repository.py` | Assembles, signs and verifies the apt repository of a channel ([below](#the-apt-repository)); `--refresh` signs a snapshot's Release file again |
| `scripts/check-repository.py` | The checks a snapshot passes before `deploy-pages.yml` serves it for a channel |
| `scripts/build-image` | Builds and seals an image for the installer ([docs/images.md](docs/images.md)) |
| `scripts/check-basics.py` | The checks every image must pass before it is sealed |
| `scripts/test` | Every unit test, and `recipe.py check` |

## Building packages

On a Debian testing host with `mmdebstrap`, `sbuild`, `uidmap`, `dpkg-dev`, `apt-utils`, `git`, `python3` and `debian-archive-keyring`, as a user with subordinate user and group IDs (`/etc/subuid`, `/etc/subgid`):

```sh
python3 scripts/recipe.py check
scripts/build-package --cross alsa-ucm-conf-aurora      # amd64 host: Debian's cross toolchain
scripts/build-package --cross libfprint fprintd         # fprintd builds against the libfprint just built
```

`--cross` is the fast path on an amd64 host; recipes with `"cross": false` build only natively (on arm64, or emulated with `qemu-user-binfmt` without `--cross`). Builds are unprivileged and have no network unless the recipe says so. Binary packages go to `out/packages/` (or `$AURORA_PACKAGES_DIR`), and later builds resolve their build dependencies from there, so a recipe that needs another recipe's packages builds after it. CI builds every recipe natively in that order.

## Building an image

An image needs a disposable, privileged, native arm64 builder (a Debian testing machine or VM; the build loop-mounts the image and runs as root) with `mmdebstrap`, `btrfs-progs`, `dosfstools`, `e2fsprogs`, `fdisk`, `udev`, `gnupg`, `curl`, `zstd` and `python3`. It installs from a signed Aurora package repository. For a local image, sign one with a development key:

```sh
scripts/dev-signing-key            # once: a local key; its public half goes to packages/aurora-archive-keyring/keys/development.asc
scripts/build-package aurora-archive-keyring linux-aurora ...   # every package the profile installs, native on arm64
GNUPGHOME=$PWD/cache/dev-signing/gnupg \
  python3 scripts/sign-repository.py --packages out/packages --output out/repository --channel testing
sudo AURORA_ARCHIVE_KEY=$PWD/packages/aurora-archive-keyring/keys/development.asc \
  AURORA_PLATFORM_SOURCE=/path/to/aurora-platform \
  scripts/build-image debian-kde out/repository testing
```

- `scripts/dev-signing-key` keeps the key in `cache/dev-signing/gnupg`. The development key is never committed, and an image built with it is for local testing only: `sign-repository.py --production` refuses a keyring package that carries it.
- `AURORA_ARCHIVE_KEY` is the key `build-image` checks the repository with. It defaults to the production key.
- `AURORA_PLATFORM_SOURCE` points at a local aurora-platform checkout with Debian support, used while the pin in `sources.json` lacks it.
- The repository may also be an https URL.
- The result is `out/debian-kde-filesystems.tar.zst` (with its `.sha256`) and `out/debian-kde-installer/`, the files the installer writes.

## Image basics

`scripts/build-image` runs `scripts/check-basics.py` on the finished root and on the files the installer writes. The build fails unless the image has:

- a generated UTF-8 default locale in `/etc/default/locale` and `/etc/locale.conf`, with no global Mesa driver override;
- its desktop's terminal with a launcher, and GNOME's backgrounds and default picture or Plasma's wallpapers;
- Aurora's icons and About logo;
- NetworkManager enabled, with the desktop's network settings;
- logind's lid-close suspend in place and sleep not masked;
- the Touch ID policy:
  - `sudo`, `sudo -i` and polkit offer a fingerprint and still reach the password;
  - the lock screens offer a fingerprint;
  - the login screens, the console login, `su` and ssh ask for the password;
  - a short power-button press suspends or is ignored, and a long press powers off;
- no ssh unit enabled and no unit file or drop-in marked executable;
- Plasma Login as the KDE display manager;
- a GRUB that finds /boot by filesystem UUID on the startup disk only.

## The apt repository

Each channel is served at `https://aurorasilicon.org/debian-aurora/<channel>` from a signed snapshot release (`<channel>-YYYYMMDD.N`), with component `main` (arm64 and all) and its own distribution: `aurora` for Testing, which installed systems already follow, and `aurora-<channel>` for the others. The distribution is the Suite and Codename the Release file signs, and an installed system's `aurora.sources` names it, so:

- `deploy-pages.yml` serves a snapshot only for the channel its signed Release file names, and only if its packages were signed no earlier than those the channel serves now (`Aurora-Snapshot-Date`), so it never rolls a channel back. Going back is a new snapshot built from the older sources.
- apt refuses a Release file whose Codename changes under a system that already follows the channel. A first `apt update` only warns, which is why the deployment checks it.

A Release file is valid for seven days (`Valid-Until`), and `deploy-pages.yml` signs every served channel's Release file again daily with a new `Date` and `Valid-Until` and nothing else changed. If that stops for a week, apt stops taking updates from the channel rather than trusting an old snapshot indefinitely, and apt never replaces a Release file it has with an older one.

## CI

| Workflow | Does |
| --- | --- |
| `checks.yml` | `scripts/test` and `bash -n` on the scripts, on every push and pull request |
| `packages.yml` | On main: builds every recipe natively on arm64 in dependency order (`package-level.yml` builds one level), signs the repository in the `testing-signing` environment (`DEBIAN_SIGNING_KEY`, `DEBIAN_SIGNING_PASSPHRASE`), publishes it as an immutable release `testing-YYYYMMDD.N`, and deploys it to GitHub Pages via `deploy-pages.yml` |
| `deploy-pages.yml` | Daily, manual or called by `packages.yml`: checks each channel's snapshot release with `check-repository.py` against the key in `keys/fingerprint.txt`, signs its Release file again in the `testing-signing` environment, and deploys the apt repository to `https://aurorasilicon.org/debian-aurora/<channel>` |
| `images.yml` | Manual: builds one profile from a package release for a channel, attests `out/<profile>-filesystems.tar.zst` and uploads the `<profile>-candidate` artifact |
| `publish-payload.yml` | Manual: aurora-distributions' `build-payload.yml` for a successful image run, signed with `INSTALLER_CATALOG_SIGNING_KEY` from the `catalog-signing` environment |

## Contributing

[AGENTS.md](AGENTS.md) has the conventions for contributors, human or agent. Run `scripts/test` before opening a pull request.
