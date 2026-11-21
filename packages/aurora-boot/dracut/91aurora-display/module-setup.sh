#!/bin/bash
# The display chain belongs in the initramfs (alarm-aurora's aurora-display
# hook). On the M4 Pro the kernel's T6041 display gate brings the external
# display processors up only once the PMP driver binds, and gives up 20 s
# into the boot. With apple-pmp only on the root file system, an encrypted
# root holds it back until the passphrase is typed, so the gate gives up and
# every external display and Type-C DP route stays off for the whole boot.
# appledrm brings apple-pmp, dcp-fabric-core and typec as dependencies, and
# its crossbar soft dependency; all are named so that none depends on that
# resolution. udev loads them during the initramfs coldplug.

check() {
    return 0
}

depends() {
    return 0
}

installkernel() {
    hostonly='' instmods apple-pmp mux-apple-display-crossbar appledrm
}
