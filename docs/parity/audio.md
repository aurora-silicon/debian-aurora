# Audio and speaker safety

Debian counterparts of alarm-aurora's audio and speaker protection packages.
Debian versions are testing's at snapshot 20261120T000000Z.

| alarm-aurora | Debian source → binaries | Kind | Version | Status |
| --- | --- | --- | --- | --- |
| aurora-audio | aurora-audio → aurora-audio | upstream | 4.1.aurora2-1 | built (cross) |
| speakerguardd | speakerguardd → speakerguardd | upstream (network) | 0.1.12-1 | built (cross) |
| speakerguardd-v2 | speakerguardd-v2 → speakerguardd-v2 | upstream (network) | 1.0.0~alpha.2-1 | built (cross) |
| aurora-speaker-upgrade | aurora-speaker-upgrade → aurora-speaker-upgrade | upstream | 0.1-1 | built (cross) |
| speakersafetyd | rust-speakersafetyd → speakersafetyd | rebuild of 3.0.0-1 (not cross) | 3.0.0-1+aurora1 | built (emulated; its tests, including 0002 and 0003, pass) |
| speakersafetyd-aurora-profiles | speakersafetyd-aurora-profiles → same | native | 1.2 | built (cross) |
| alsa-utils-aurora | alsa-utils → alsa-utils, alsa-utils-udeb | rebuild of 1.2.16-1 | 1.2.16-1+aurora1 | built (cross) |
| pipewire | pipewire → pipewire, libspa-0.2-modules, … (23 binaries) | rebuild of 1.6.9-2 | 1.6.9-2+aurora1 | built (cross) |
| lsp-plugins-lv2 | lsp-plugins → lsp-plugins-lv2, … | rebuild of 1.2.37-1 | 1.2.37-1+aurora1 | built (cross) |
| bankstown | bankstown-lv2 | debian | 1.1.0-3+b10 | debian |
| triforce-lv2 | triforce-lv2 | debian | 0.4.0-1 | debian |
| lzfse | lzfse (liblzfse1, lzfse) | debian | 1.0-2+b1 | debian |
| alsa-ucm-conf-aurora | alsa-ucm-conf-aurora | upstream | 10.aurora2-1 | done earlier, reused unchanged |

## Speaker safety: what the Debian packages keep

The dependency chain is alarm-aurora's, each dependency mapped to its
Debian name:

- `aurora-audio` depends on `alsa-ucm-conf-aurora`, `pipewire-audio`,
  `wireplumber (>= 0.5.16)`, `bankstown-lv2`, `triforce-lv2`,
  `lsp-plugins-lv2`, `speakersafetyd`, `speakerguardd`,
  `alsa-utils (>= 1.2.16-1+aurora1)` (alarm-aurora: `alsa-utils-aurora`),
  `speakerguardd-v2 (>= 1.0.0~alpha.2-1)` and
  `aurora-speaker-upgrade (>= 0.1-1)`. It provides, conflicts with and
  replaces `asahi-audio`, so Debian's asahi-audio 5.0-1 cannot be installed
  beside it, and anything that depends on `asahi-audio` (Debian's
  `asahi-platform-audio`) is satisfied by aurora-audio instead of pulling
  Debian's.
- `speakerguardd-v2` depends on `python3`, `alsa-utils`, `pipewire`,
  `pipewire-speaker-graph (>= 2)`, `systemd` and
  `aurora-audio (>= 4.1.aurora2-1)`. Only Aurora's PipeWire provides
  `pipewire-speaker-graph` (on `libspa-0.2-modules`, which carries the
  patched ALSA and filter-graph plugins), so Debian's stock PipeWire can
  never satisfy it, whatever its version. aurora-audio and speakerguardd-v2
  depend on each other, as in alarm-aurora; neither has a maintainer script
  that needs the other configured.
- `speakersafetyd-aurora-profiles` depends on
  `speakersafetyd (>= 3.0.0-1+aurora1)`, the first build that tries a
  machine's own configuration (j575c.conf needs it). It is pulled by
  aurora-boot in alarm-aurora, not by aurora-audio; that stays so here.
- `aurora-speaker-upgrade` depends on `python3`, `python3-cryptography`,
  `util-linux`, `alsa-utils` and `systemd`, and suggests `speakerguardd-v2`
  and `lzfse` (alarm-aurora's optdepends).

How the speakers are held (alarm-aurora's chain, except that v2 is opt in):

- speakerguardd v2 is opt in, and the legacy daemons are deprecated. A
  fresh install keeps speakersafetyd (with the profiles) and, on the J700,
  speakerguardd 0.1 on the Macs they support, until the user runs
  `aurora-speaker-upgrade`. The pinned kernel is a dual kernel: at every
  card bind the legacy "Speaker Volume Unlock" interface is in charge, and
  the gate admits v2 only after aurora-speaker-upgrade wrote its setting
  (`/var/lib/aurora-speaker-upgrade/interface`). alarm-aurora and
  fedora-aurora enable aurora-speaker-upgrade.service, which makes that
  switch at the next boot; here it is installed disabled. While a legacy
  daemon holds the speakers, aurora-speaker-upgrade's notice says the legacy
  protection is deprecated and asks the user to bring up v2 and report the
  result (console and SSH logins through `/etc/update-motd.d`, once per user
  in the desktop through `/etc/xdg/autostart`, both silent once v2 holds the
  speakers).

- The kernel keeps the speakers at its safe level until a protection daemon
  takes the lock. No package here writes a speaker amplifier control or
  unlocks the speakers: the only writers are speakersafetyd, speakerguardd
  0.1 and the speakerguardd v2 supervisor. alsactl (patched) now skips a
  control another process has locked instead of failing on it; it never
  could write one.
- speakerguardd-v2 installs `60-speakerguardd-v2-gate.conf` drop-ins on
  `speakersafetyd.service` and `speakerguardd.service`
  (`ExecCondition=+/usr/libexec/speakerguardd-v2/speakerguardd-gate legacy`),
  and every v2 unit carries the gate too, so exactly one stack holds the
  speakers on each boot. The v2 supervisor starts only on a Mac that
  aurora-speaker-upgrade switched and whose own tuning passed compilation,
  the parity attestation and the silent wiring self-check; provisioning
  compiles the protection parameters from the Mac's own tuning bundle at run
  time. Any failure fails closed.
- speakerguardd 0.1 adds `50-j700-guard.conf` to `speakersafetyd.service`:
  speakersafetyd stands down on the J700, which has no speaker sense.
- The generated units were compared line by line with what alarm-aurora's
  prepare() produces from the same pin: identical apart from the program
  directory (`/usr/libexec/speakerguardd-v2` instead of
  `/usr/lib/speakerguardd-v2`). debian/units.py keeps every one of
  alarm-aurora's required-line checks and adds fedora-aurora's check of the
  supervisor's `ExecStartPre=… speakerguardd-gate interface`.

Enablement, mirroring alarm-aurora (which ships the wants links in the
package) through debhelper:

| Unit | Enabled | Started by maintainer scripts |
| --- | --- | --- |
| speakerguardd-v2.service, speakerguardd-v2-seat.path, speakerguardd-v2-sleep.service | yes | never (`--no-start`) |
| speakerguardd-v2-provision/-selfcheck/-switchtest/-seat.service | no (pulled by the supervisor's Requires=) | never |
| user: speakerguardd-v2-graph.service, speakerguardd-v2-session.service | yes (global, WantedBy=pipewire.service) | never (compat 13 does not restart user units) |
| aurora-speaker-upgrade.service | no: v2 is opt in (alarm-aurora's preset enables it) | never |
| speakerguardd.service | no (udev starts it for the J700 card) | a running daemon is restarted on upgrade, as fedora-aurora does |
| speakersafetyd.service | no (Debian's packaging, udev starts it) | as Debian: a running daemon is restarted on upgrade |

The presets say the same, so a full `systemctl preset` (aurora-boot ends
the presets with `disable *`) keeps them: speakerguardd-v2 ships
90-speakerguardd-v2.preset (system and user) enabling the v2 units above,
which their gate keeps from running until the Mac is switched.
aurora-speaker-upgrade ships no preset (alarm-aurora's
90-aurora-speaker-upgrade.preset enables it), so `disable *` covers it, and
the image build checks that it is not enabled.

## speakersafetyd: 3.0.0 rebuilt, no epoch

Debian testing ships rust-speakersafetyd 3.0.0-1; alarm-aurora and
fedora-aurora ship 2.0.1 with downstream patches. The Aurora stack needs
2.0.1's daemon (its model, configuration format, flag file
`/run/speakersafetyd/speakersafetyd.flag`, which speakerguardd 0.1 and the
warm-restart drop-in rely on, unit name and udev activation) plus Aurora's
0002 and 0003. Comparing the trees:

- 3.0.0 is 2.0.1 with alarm-aurora's 0001 (j504 speaker names) merged, a
  relicence to GPL-2.0-only, and log timestamps (`without_timestamps()`
  dropped). Every model value in every shipped configuration is identical.
- Debian's own patches only relax crate versions and rename the dynamic user
  to `_speakersafetyd`.
- 0002 and 0003 apply with a one-line offset; they are rebased (refreshed)
  in packages/speakersafetyd/patches. Debian 3.0.0 plus both is
  byte-for-byte alarm-aurora's patched 2.0.1 apart from the licence headers
  and the timestamp line.
- The profiles were checked against 3.0.0's j316.conf and j575.conf: the
  model values they reuse are unchanged.

So the rebuild of Debian's 3.0.0 runs the same daemon as alarm-aurora's
2.0.1-1.2, and 0001 is dropped (upstream has it).

Why Aurora's build wins: 3.0.0-1+aurora1 sorts above Debian's 3.0.0-1. With
the planned pin of the Aurora repository at 990, Aurora's build stays the
candidate when Debian uploads a newer speakersafetyd (990 beats 500
regardless of version), so no epoch is needed on fresh installs or upgrades.
An epoch would only matter where a newer Debian speakersafetyd is already
installed when the Aurora repository is added (a 990 pin never downgrades),
or where someone runs `apt -t testing` (Debian at 990 too, so the higher
version wins). Recommendation for aurora-archive-keyring instead of an
epoch: pin Debian's `speakersafetyd`, `asahi-audio` and
`alsa-ucm-conf-asahi` at -1 (Pin: release o=Debian), so the Debian builds
of the safety packages are never candidates, whatever their version. Epochs
are permanent and would not stop `apt install asahi-audio`.
(Had 2.0.1 been packaged instead, it would sort below Debian's 3.0.0-1 and
need an epoch or a pin of 1000 or more to replace an installed Debian build.)

## Per package

### aurora-audio (upstream, arch all)

Pinned fork c967141 with alarm-aurora's
`0001-restore-legacy-speaker-graphs.patch` as a quilt patch, and
`99-aurora-speaker-irq.conf` in `/usr/share/wireplumber/wireplumber.conf.d/`.
The build checks, like alarm-aurora's check(), that the j316, j413, j616
and j700 speaker graphs and j700/48.wav are installed and named in
99-asahi.conf. Deviations:

- Not carried: `90-aurora-audio.conf` (mkinitcpio `MODULES+=(snd-seq)`) and
  its pacman hook. fedora-aurora carries snd-seq in the initramfs because
  Fedora's dist-alsa.conf loads snd-seq whenever snd-pcm loads; Debian has
  no such modprobe rule (checked kmod, alsa-utils and the host's
  modprobe.d), so nothing in the initramfs loads snd-seq.
- Not carried: `aurora-audio-v2-cleanup` and its install hook. It removes
  per-user links that the speakerguardd v2 preview left in ~/.config; no
  Debian install ever had the preview, and the script exits at its first
  check whenever speakerguardd-v2 is installed, which aurora-audio depends
  on.
- Not carried: provides/conflicts/replaces of `asahi-audio-aurora` and of
  the retired `speakerguardd-v2 <= 1.0.0alpha.1-25` previews; neither ever
  existed in Debian.
- `pipewire-audio` is Debian's metapackage (pipewire-pulse, pipewire-alsa,
  wireplumber, libspa-0.2-bluetooth); Arch's `pipewire-audio` is the split
  that carries the SPA plugins. Both end with the same plugins installed.
- As upstream asahi-audio does, `asahi-lock-volume.lua` holds the raw
  speaker route at 100 % unmuted (the DSP graph carries the volume); the
  speaker level stays bounded by the kernel and the protection daemon.

### speakerguardd (upstream, network)

Built with `cargo build --locked --release` (crates.io, only `libc`) and
Debian's rustc/cargo; cross-builds with `libstd-rust-dev:arm64` and the
cross linker. The unit is rewritten to name only AppleJ700 (exactly one
ExecStart, verified). `use-feedback-guard` goes to
`/usr/libexec/speakerguardd/` (alarm-aurora: `/usr/lib/speakerguardd/`,
fedora-aurora: libexec), and `50-j700-guard.conf` points there. alarm-aurora
lists `alsa-lib` as a dependency; the binary does not link it (the crate
uses only libc), so `${shlibs:Depends}` (libc6, libgcc-s1) is all it needs.

### speakerguardd-v2 (upstream, network)

The four shipped crates built with `cargo --locked` and Debian's toolchain,
the session helpers, gate.json, parity.json, the reference graphs, the sgv2
LV2 bundle in `/usr/lib/lv2/sgv2.lv2` (Debian's LV2 directory, one of the
system directories the self-check knows), the renamed units and the legacy
gate drop-ins. No source file is patched (the parity attestation is bound
to a hash of the voicing sources). Deviations: programs in
`/usr/libexec/speakerguardd-v2` (see above); alarm-aurora's packaging
README is not installed (it describes pacman). Tests (cargo test and the
three Python suites alarm-aurora runs) run in native builds; a cross build
runs none (sbuild sets nocheck). The Python suites pass on the pinned source.

### aurora-speaker-upgrade (upstream, arch all)

`make -C packaging/upgrade install`, unit installed disabled and never
started from the maintainer scripts, as upstream ships it (alarm-aurora:
preset plus `systemctl preset` in post_install). The package adds the
deprecation notice (`/usr/libexec/aurora-speaker-upgrade/legacy-notice`, run
from `/etc/update-motd.d/60-aurora-speaker-protection` and, with
`--desktop`, from `/etc/xdg/autostart/aurora-speaker-legacy-notice.desktop`;
the desktop notification goes through `busctl --user` to
org.freedesktop.Notifications, so it needs nothing beyond systemd) and a
README.Debian with the opt-in steps. No path rewrite: upgrade.py's LIBEXEC
tuple starts with `/usr/libexec/speakerguardd-v2`, where speakerguardd-v2
installs; the build checks that. The tool loads liblzfse through ctypes
(`liblzfse.so.1` or find_library); Debian's liblzfse1 provides exactly that
soname. alarm-aurora's preset and its upgrade-from-0.1-0.17 preset step are
not shipped (v2 is opt in; there are no older Debian builds). The unit
tests (46) pass on the pinned source; they run in native builds only.

### speakersafetyd (rebuild, emulated)

See above. Debian's librust-*-dev build dependencies are not installable
for a cross build (`librust-configparser-dev:arm64` needs
`librust-async-std-1+default-dev:arm64`, which has no installable
candidate), so the recipe sets `"cross": false`.

### speakersafetyd-aurora-profiles (native, arch all)

alarm-aurora's four files unchanged (sha256 checked): j616.conf and
j575c.conf in `/usr/share/speakersafetyd/apple/`,
`96-speakersafetyd-aurora.rules` in `/usr/lib/udev/rules.d/`, and
`50-aurora-warm-restart.conf` as a drop-in for speakersafetyd.service.
Debian's speakersafetyd ships neither j616.conf nor j575c.conf, so there is
no file conflict. Version 1.2 encodes alarm-aurora's 1-2.

### alsa-utils (rebuild)

alarm-aurora's `alsactl-skip-locked-controls.patch` applies to Debian's
1.2.16-1 unchanged (same upstream version). Debian's sysvinit script that
unmutes mixer controls is masked under systemd and never touches
"Speaker" controls except to mute them.

### pipewire (rebuild)

Aurora's 11 patches (1000-1010), written against 1.6.11, apply to Debian's
1.6.9-2 (after Debian's CVE patch) unchanged, with no offset or fuzz; none
needed a rebase. Between 1.6.9 and 1.6.11 the files they touch differ in a
single cast in alsa-pcm.c, and the tests they add build from the same
test/meson.build. `packaging.patch` adds `Provides: pipewire-speaker-graph
(= 2)` to libspa-0.2-modules (alarm-aurora: on pipewire-audio, Arch's split
with the SPA plugins). A cross build runs no tests.

### lsp-plugins (rebuild)

The loud_comp latency patch applies to Debian's 1.2.37-1 unchanged.
alarm-aurora's check() also runs `lsp-latency-check` (an LV2 host comparing
the latency ports the speaker graphs use with an impulse's delay); it is not
ported: Debian disables lsp-plugins' tests in its packaging, adding it needs
a packaging patch with a new C file and liblilv-dev, and a cross build could
not run it. Open question whether it is wanted in native builds.

### bankstown-lv2, triforce-lv2, lzfse (Debian's, unchanged)

- bankstown-lv2 1.1.0-3: the LV2 interface aurora-audio's graphs use is the
  same. alarm-aurora's pin (8e6f96f) is 1.1.0 plus one upstream fix: no
  panic when instantiated at sample rate 0, which happens when WirePlumber
  installs it as an audioconvert filter-graph (`node.filter-graph.rules`).
  aurora-audio loads its graphs through `node.software-dsp.rules` /
  module-filter-chain, which only activates a graph with a non-zero rate
  (it errors out at 0), and the v2 graphs use no bankstown. Debian's
  1.1.0 therefore satisfies aurora-audio; a user-made audioconvert
  filter-graph with bankstown would crash PipeWire (fails silent, not loud).
- triforce-lv2 0.4.0-1 (alarm-aurora 0.3.2): triforce.ttl and manifest.ttl
  are identical (same URI, ports and controls the microphone graphs set);
  0.4.0 replaces the FFT Hilbert transform with an IIR one. Microphones
  only; no speaker path uses it.
- lzfse 1.0-2: upstream 1.0 plus a SONAME (liblzfse.so.1) and a CMake
  minimum version; exports lzfse_decode_buffer and
  lzfse_decode_scratch_size, which aurora-speaker-upgrade calls. alarm-aurora
  installs lzfse in its image explicitly (scripts/build-image); the Debian
  image should list `lzfse` too, since aurora-speaker-upgrade only suggests it.

## Installability check

apt, simulating an empty arm64 system with the snapshot's arm64 index plus
these packages and alsa-ucm-conf-aurora:

- `install aurora-audio speakersafetyd-aurora-profiles lzfse` picks every
  Aurora build (alsa-utils, libspa-0.2-modules and pipewire, lsp-plugins-lv2,
  speakersafetyd 3.0.0-1+aurora1, speakerguardd, speakerguardd-v2,
  aurora-speaker-upgrade, aurora-audio, the profiles) and Debian's
  wireplumber 0.5.19, bankstown-lv2, triforce-lv2 and lzfse.
- `install aurora-audio asahi-audio` is refused (aurora-audio conflicts
  with asahi-audio).
- `install aurora-audio asahi-platform-audio` installs no Debian asahi-audio
  or alsa-ucm-conf-asahi: aurora-audio and alsa-ucm-conf-aurora provide them.

## Build notes

- Debian's Rust (debcargo) packages cannot be cross-built with sbuild's
  apt resolver (librust-*-dev:arm64 dependency chains do not resolve), so
  rust-speakersafetyd is built natively or emulated (`"cross": false`).
- A recipe key for a virtual Provides would avoid packaging patches like
  pipewire's for the common "this Aurora build carries fix level N" case.

## Decisions

- Speaker protection (2026-11-21): carry the existing handling. The legacy
  daemons stay installed and keep the speakers of the Macs they support:
  speakersafetyd with its models (Debian's, plus j616.conf and j575c.conf in
  speakersafetyd-aurora-profiles) and speakerguardd 0.1 with
  conf/apple/j700.conf. They run on fixed per-model values, not values from
  the machine, so they are a deliberate exception to "speakerguardd v2
  only" and to the hardware-safety rule, and they are deprecated: users are
  told so and asked to bring up v2 (above). speakerguardd v2, which takes
  its values from the Mac, is opt in through aurora-speaker-upgrade. This is
  expected to change soon: when v2 becomes the default, aurora-speaker-upgrade
  gets its preset back, and the legacy daemons and profiles are later
  removed.
- Pins: aurora-archive-keyring pins Debian's speakersafetyd, asahi-audio and
  alsa-ucm-conf-asahi at -1.

## Open questions

- lsp-latency-check in native builds (above).
