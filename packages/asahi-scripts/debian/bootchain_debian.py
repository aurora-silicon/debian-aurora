#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Debian layout for Aurora's shared Stage 2 updater.

bootchain.py is alarm-aurora's copy of fedora-aurora's shared updater,
unchanged. It owns the DT ABI generation guard, the aura-try trial, the
boot-time commit and the guard. Debian's kernel packages already use its
default paths, so this file only changes what differs from Fedora:

- linux-image-<release> installs /boot/vmlinuz-<release> and
  /usr/lib/modules/<release>/{dtb/apple/,dtb-abi};
- GRUB boots with the device tree U-Boot hands it, so there is no /boot/dtb
  link or /boot/dtb-<release> copy to keep (as on Arch);
- apt removes packages, so the refusal names `apt remove`.
"""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

_spec = importlib.util.spec_from_file_location(
    'bootchain', Path(os.environ.get('BOOTCHAIN_MODULE', Path(__file__).with_name('bootchain.py'))))
bootchain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootchain)
Refused = bootchain.Refused

# The shared refusal names Fedora's command and its /boot/dtb link.
_DNF = re.compile(r"`sudo dnf remove ((?:'[^']*'(?: |(?=`)))+)`")


class DebianUpdate(bootchain.Update):
    def plan(self):
        try:
            return super().plan()
        except Refused as error:
            message = str(error)
            if 'sudo dnf remove ' not in message:
                raise
            match = _DNF.search(message)
            if not match:
                raise
            paths = match[1].strip()
            message = (message[:match.start()] + f'`sudo apt remove $(dpkg-query -S {paths} | cut -d: -f1)`' +
                       message[match.end():]).replace('Stage 2 and /boot/dtb are kept', 'Stage 2 is kept')
            raise Refused(message) from None

    def apply(self):
        selected, _source, _own, payload = self.plan()
        target = self.target()
        if target.is_symlink():
            raise Refused('Stage 2 target is a symlink')
        previous = target.read_bytes() if target.exists() else None
        if previous is not None and previous != payload and self.supports_trial():
            self.stage_trial(selected, payload)
        elif previous != payload:
            # Finish and sync the candidate before changing even the backup.
            fd, name = tempfile.mkstemp(prefix=f'.{target.name}.', dir=target.parent)
            staged = Path(name)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o644)
                    os.fsync(stream.fileno())
                if staged.read_bytes() != payload:
                    raise Refused('Stage 2 read-back failed')
                if previous is not None:
                    bootchain.replace_file(target.with_name(target.name + '.old'), previous)
                os.replace(staged, target)
                bootchain.sync_dir(target.parent)
            finally:
                staged.unlink(missing_ok=True)
        print(f'Stage 2 verified at {target}; DTBs from kernel {selected}')


def main():
    parser = bootchain.argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--guard', action='store_true')
    args = parser.parse_args()
    try:
        update = DebianUpdate()
        if args.guard:
            update.guard()
        elif args.commit:
            update.commit()
        elif args.check:
            update.plan()
        else:
            update.apply()
    except (Refused, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'update-m1n1: {error}; keeping the last complete Stage 2 and trial evidence', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
