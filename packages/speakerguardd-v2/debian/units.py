#!/usr/bin/env python3
"""Write the upstream speakerguardd 1.0 units under their speakerguardd-v2 names.

alarm-aurora's prepare() with Debian's program directory: the programs move to
LIBEXEC, every unit and the legacy gate are renamed beside speakerguardd 0.1,
and the lines the stack depends on must be present after the rewrite.
Provisioning and the self-check are hard prerequisites of the supervisor, and
every system unit carries the fleet gate.

    units.py LIBEXEC OUTPUT_DIRECTORY
"""
import re
import sys
from pathlib import Path

UNITS = ['speakerguardd.service', 'speakerguardd-provision.service', 'speakerguardd-selfcheck.service',
         'speakerguardd-switchtest.service', 'speakerguardd-seat.service', 'speakerguardd-seat.path',
         'speakerguardd-session.service', 'speakerguardd-graph.service', 'speakerguardd-sleep.service']


def main():
    lx, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for unit in UNITS:
        text = Path('packaging/systemd', unit).read_text()
        text = text.replace('/usr/libexec/speakerguardd/', lx + '/')
        text = text.replace('ExecStart=/usr/bin/speakerguardd ', f'ExecStart={lx}/speakerguardd ')
        text = re.sub(r'\bspeakerguardd(-[a-z]+)?\.(service|path)\b', r'speakerguardd-v2\1.\2', text)
        for line in text.splitlines():
            if (line.startswith(('OnFailure=', 'OnSuccess=')) or 'speakersafetyd' in line
                    or line.endswith('=speakerguardd.service') or '/usr/libexec/speakerguardd/' in line):
                sys.exit(f'{unit}: a speakerguardd 1.0 unit chains to or names another daemon, '
                         f'or a path was not moved: {line}')
        (out / unit.replace('speakerguardd', 'speakerguardd-v2', 1)).write_text(text)

    def must(name, *lines):
        have = (out / name).read_text().splitlines()
        for line in lines:
            if line not in have:
                sys.exit(f'{name}: missing {line!r}')

    must('speakerguardd-v2.service', f'ExecStart={lx}/speakerguardd $SGV2_ARGS',
         'Requires=speakerguardd-v2-provision.service speakerguardd-v2-selfcheck.service',
         f'ExecCondition={lx}/speakerguardd-gate v2',
         # A dual kernel: the supervisor's start puts it on the lease.
         f'ExecStartPre={lx}/speakerguardd-gate interface')
    must('speakerguardd-v2-selfcheck.service', 'Requires=speakerguardd-v2-provision.service',
         f'ExecCondition={lx}/speakerguardd-gate prepare',
         f'ExecStartPost={lx}/speakerguardd-provision activate --graph-unit speakerguardd-v2-graph.service',
         f'ExecStart={lx}/speakerguardd-selfcheck run --defer --params ${{SGV2_PARAMS}} -- $SGV2_TUNING')
    # The switch test runs after login, before the supervisor.
    must('speakerguardd-v2.service', 'Requires=speakerguardd-v2-switchtest.service',
         'After=speakerguardd-v2-switchtest.service')
    must('speakerguardd-v2-switchtest.service', 'Requires=speakerguardd-v2-selfcheck.service',
         'After=speakerguardd-v2-selfcheck.service systemd-user-sessions.service',
         'Before=speakerguardd-v2.service', f'ExecCondition={lx}/speakerguardd-selfcheck pending',
         f'ExecStartPost={lx}/speakerguardd-provision activate --graph-unit speakerguardd-v2-graph.service',
         f'ExecStopPost={lx}/speakerguardd-selfcheck pending --clear')
    must('speakerguardd-v2-provision.service', 'Before=speakerguardd-v2-selfcheck.service speakerguardd-v2.service',
         f'ExecStart={lx}/speakerguardd-provision run', f'ExecCondition={lx}/speakerguardd-gate prepare')
    must('speakerguardd-v2-seat.service', f'ExecStart={lx}/speakerguardd-provision seat --unit speakerguardd-v2.service',
         f'ExecCondition={lx}/speakerguardd-gate prepare')
    must('speakerguardd-v2-seat.path', 'Unit=speakerguardd-v2-seat.service')
    must('speakerguardd-v2-sleep.service', 'Before=sleep.target', f'ExecCondition={lx}/speakerguardd-gate v2',
         f'ExecStart={lx}/speakerguardd-provision sleep --unit speakerguardd-v2.service',
         f'ExecStop={lx}/speakerguardd-provision wake --unit speakerguardd-v2.service')
    must('speakerguardd-v2-session.service', f'ExecCondition={lx}/speakerguardd-provision is-seat')
    # The kernel's "Speaker Protection" lock and lease writes need CAP_SYS_ADMIN.
    if not re.search(r'^CapabilityBoundingSet=.*\bCAP_SYS_ADMIN\b', (out / 'speakerguardd-v2.service').read_text(), re.M):
        sys.exit('speakerguardd-v2.service: CapabilityBoundingSet lacks CAP_SYS_ADMIN')

    # The older daemons start only where v2 does not run and the kernel has no
    # v2 interface: exactly one stack holds the speakers on each boot.
    gate = Path('packaging/systemd/legacy-gate.conf').read_text().replace('/usr/libexec/speakerguardd/', lx + '/')
    (out / 'legacy-gate.conf').write_text(gate)
    must('legacy-gate.conf', f'ExecCondition=+{lx}/speakerguardd-gate legacy')


if __name__ == '__main__':
    main()
