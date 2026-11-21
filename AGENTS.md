# Aurora Debian: contributor notes

For everyone who changes this repository, human or agent. Aurora Silicon's contributor policy applies; these are the repository's own conventions.

## Commits and pull requests

- Commits carry human identity only. Agents never co-author, sign off or co-commit, so a commit has no `Co-Authored-By`, no agent `Signed-off-by`, no `Assisted-by` and no session trailers.
- When an agent helped, the last line of the pull request body says so, and only there: `Assisted-by: LLM (<Vendor>:<Model>)`.

## Packages

[docs/packaging.md](docs/packaging.md) is the recipe format. In short:

- One recipe per Debian source package in `packages/<name>/`: `recipe.json` plus `debian/` (upstream, native) or `patches/` and `packaging.patch` (rebuild). Never commit `debian/changelog`; `recipe.py` writes it from `version` and `changes`.
- A rebuild of a Debian package is preferred when Debian testing ships the same software. It keeps Debian's source name and adds `+auroraN` to Debian's version.
- Maintainer `Aurora Silicon <noreply@aurorasilicon.org>`. Install paths follow Debian (merged `/usr`, `/usr/lib/<triplet>`), not Arch.
- A package that replaces a Debian package of another name declares `Provides`, `Conflicts` and `Replaces`.
- Units are enabled by `dh_installsystemd` only where alarm-aurora's preset enables them; everything else is `--no-enable`; aurora-speaker-upgrade.service is the one exception, installed disabled because speakerguardd v2 is opt in. `aurora-boot`'s presets record the same decisions, and an image build fails if its first boot would change a unit.
- Build-Depends must resolve in a cross build: `:native` on build tools whose `Multi-Arch` is `allowed`, `same` or absent, never on `Multi-Arch: foreign` ones, and never the target compiler.
- Packages are `arm64` or `all`. The x86-64 FEX guest libraries are the one exception and say so.
- `python3 scripts/recipe.py check` must pass. Build what you change with `scripts/build-package` (`--cross` on amd64), and record each package's outcome in `docs/parity/`.

## Safety and content

- Hardware safety values come from the machine, never from tables or constants in a recipe. Speaker output stays off unless a protection daemon holds it; no package may enable speakers another way. speakerguardd v2 is the protection; until it is the default, the legacy daemons (speakersafetyd with speakersafetyd-aurora-profiles, speakerguardd 0.1) run on fixed per-model values and are carried for the Macs they support as a deprecated exception, and v2 is opt in through aurora-speaker-upgrade (docs/parity/audio.md).
- No Apple code, firmware or tuning values, and no private keys, in this repository. The development signing key (`scripts/dev-signing-key`) stays local; publication refuses a keyring that carries it.

## Images and checks

- `scripts/build-image` follows alarm-aurora's image build; [docs/images.md](docs/images.md) lists where Debian differs. Keep it that way: a change to alarm-aurora's build has a Debian counterpart here, or a note in that document.
- `scripts/check-basics.py` keeps alarm-aurora's checks and command line. A new basic every image must have goes there, with a passing and a failing case in `tests/test_check_basics.py`.
- `.github/workflows/images.yml` uploads `<profile>-candidate` with `out/<profile>-filesystems.tar.zst{,.sha256}` and attests the archive. aurora-distributions' `build-payload.yml` reads exactly that, so keep the artifact name, paths and attestation.
- Pin third-party actions and reusable workflows by full commit SHA.

## Before a pull request

```sh
scripts/test
for file in scripts/*; do [[ -f $file && $file != *.py ]] && bash -n "$file"; done
```

CI does not replace a run on the hardware a change touches. Say in the pull request what was built, booted or tested, and on which Mac.
