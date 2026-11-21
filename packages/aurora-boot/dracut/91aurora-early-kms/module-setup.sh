#!/bin/bash
# Coldplug the display before everything else in the initramfs, as
# fedora-aurora's 91aurora-early-kms does, with alarm-aurora's module list.
#
# The initramfs coldplug queues thousands of uevents and the root file system
# is ready long before udev reaches the platform devices; without this hook
# appledrm loads only on the real root and the splash comes late.

check() {
    return 0
}

depends() {
    return 0
}

# appledrm registers its DRM device only once every DCP has bound, the
# external ones included, and an external DCP binds only after its Type-C
# PHY, which needs the retimer or PD controller on an I2C bus. T6041's Type-C
# PHY (the external DCPs' dp-phy suppliers) and the HDMI LPDPTX PHY belong
# here too: when the initramfs takes longer than the deferred probe timeout
# (the first boot's in-place encryption, a passphrase typed late), every DCP
# would otherwise give up and the boot would have no display at all.
installkernel() {
    hostonly='' instmods appledrm mux-apple-display-crossbar \
        i2c-pasemi-platform phy-apple-atc phy-ti-cd2e22 tps6598x \
        phy-apple-t6040-usb2 phy-apple-dptx
}

install() {
    inst_hook pre-trigger 20 "$moddir/aurora-early-kms.sh"
    inst_hook pre-pivot 90 "$moddir/aurora-early-kms-wait.sh"
}
