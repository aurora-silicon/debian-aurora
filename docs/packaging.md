# Packaging

Every package of Aurora's Debian testing images is a recipe in `packages/<name>/`. `scripts/recipe.py prepare <name> <dir>` turns it into a Debian source package; `scripts/build-package [--cross] <name>...` builds it with sbuild in a clean Debian testing build root pinned to the snapshot in `images/base.json`. Binary packages land in `out/packages/` (or `$AURORA_PACKAGES_DIR`), and later builds in the same run resolve build dependencies from there.

## recipe.json

```json
{
  "source": "iio-sensor-proxy",
  "version": "3.9-1+aurora1",
  "kind": "rebuild",
  "debian": {"source": "iio-sensor-proxy", "version": "3.9-1"},
  "changes": "What this Aurora build changes, for debian/changelog.",
  "alarm": ["iio-sensor-proxy-aurora"]
}
```

| Key | Meaning |
| --- | --- |
| `source` | Debian source package name. A rebuild keeps Debian's name, so its binary packages replace Debian's. |
| `version` | Full Debian version. A rebuild is Debian's version plus `+auroraN`; a native package has no revision; everything else has one. |
| `kind` | `upstream`, `native` or `rebuild` (below). |
| `upstream` | For `upstream`: `{"pin": "<sources.json key>"}` (the GitHub archive of the pinned commit, checked against its sha256), `{"url": "...", "sha256": "..."}` for a release tarball, or `{"git": "<sources.json key>", "submodules": true}` when the archive lacks submodules. |
| `debian` | For `rebuild`: the Debian testing source and version the build starts from. apt fetches it from the pinned snapshot and checks the archive signature. `"suite": "unstable"` takes the source from unstable at the same snapshot instead (Firefox); the build root stays testing, so every build dependency must resolve there. |
| `changes` | Required. One line per changelog bullet. |
| `network` | `true` only when the build itself fetches a pinned toolchain or vendored dependencies (rustup, cargo, Go modules), as the matching alarm-aurora recipe does. Default `false`. |
| `cross` | `false` when the package cannot be cross-built; `build-package --cross` then refuses it. |
| `build_on` | `amd64` for a package that contains x86-64 code (the FEX guest layer): it builds on an amd64 machine with `--cross`, and CI gives it an amd64 runner. Default `arm64`. |
| `alarm` | The alarm-aurora packages this recipe stands in for (docs/alarm-parity.md). |
| `notes` | Free text for reviewers. |

## Kinds

**upstream**: a pinned upstream source and this repository's complete `debian/` directory (debhelper compat 13, `Rules-Requires-Root: no`). The source tree's own `debian/`, if any, is replaced. Source format `3.0 (quilt)`; upstream changes go in `debian/patches/`.

**native**: everything in the recipe directory except `recipe.json` is the source, which must contain `debian/`. Source format `3.0 (native)`. Use it for configuration, scripts and assets that live only in this repository.

**rebuild**: Debian's own source package with Aurora's changes. Patches to the upstream source go in `patches/*.patch` (applied in name order after Debian's series, as `aurora-<name>`). A change to Debian's packaging itself goes in `packaging.patch`, applied with `patch -p1` to the unpacked tree before the build. Keep it small: Debian's packaging moves with each upload.

`debian/changelog` is generated from `version` and `changes` (prepended to Debian's for a rebuild). Do not commit one.

## Conventions

- Maintainer: `Aurora Silicon <noreply@aurorasilicon.org>`.
- Install paths follow Debian (merged `/usr`, `/usr/lib/<triplet>` for libraries), not Arch. Files that alarm-aurora installs under `/usr/share/licenses` go in `debian/copyright`.
- A package that replaces a Debian package of a different name declares `Provides`, `Conflicts` and `Replaces` for it, with a version in `Provides` when anything depends on a version.
- Units are enabled by debhelper (`dh_installsystemd`) only when the alarm-aurora preset enables them; everything else is installed disabled (`dh_installsystemd --no-enable`); aurora-speaker-upgrade.service is the one exception, installed disabled because speakerguardd v2 is opt in. Presets in `aurora-boot` record the same decisions, and the image build fails if a first boot would change a unit.
- Hardware safety values come from the machine. Speaker output stays off unless a protection daemon holds it; no package may enable speakers another way. speakerguardd v2 is the protection; until it is the default, the legacy daemons (speakersafetyd with speakersafetyd-aurora-profiles, speakerguardd 0.1) run on fixed per-model values and are carried for the Macs they support as a deprecated exception, and v2 is opt in through aurora-speaker-upgrade (docs/parity/audio.md).
- No Apple code, firmware or tuning values, and no private keys, in this repository.
- Packages are `arm64` (or `all`). The x86-64 FEX guest libraries are the one exception and say so in their recipe.
- Build-Depends must resolve in a cross build too. A build tool that runs during the build carries `:native` when its `Multi-Arch` field is `allowed`, `same` or absent; a `Multi-Arch: foreign` tool must not (dpkg-checkbuilddeps rejects `:native` on it; `apt-cache show <pkg>` shows the field). The target C compiler is never listed (`gcc` would mean `gcc:arm64`, which conflicts with the build machine's; build-essential and crossbuild-essential provide it).

## Building

```sh
scripts/build-package alsa-ucm-conf-aurora              # native arm64, or emulated with qemu-user-binfmt
scripts/build-package --cross linux-aurora mesa         # on amd64, with Debian's cross toolchain
```

The build root is created once per snapshot and architecture with `mmdebstrap --variant=buildd` and kept in `cache/`. Builds are unprivileged (sbuild's unshare backend) and have no network unless the recipe sets `network`.
