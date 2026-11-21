#!/bin/bash
# alarm-aurora's install-runtime.sh: mil-hwxc and its private libobjc2 and
# GNUstep Base. The licenses are in debian/copyright.
set -euo pipefail
prefix=${1:?destination prefix}
install -Dm755 build/mil-hwxc "$prefix/bin/mil-hwxc"
private="$prefix/lib/mil-hwx-compiler"
mkdir -p "$private"
cp -a .gnustep/lib/libobjc.so* .gnustep/lib/libgnustep-base.so* "$private/"
# These are private dependencies. Never publish global libobjc SONAME provides
# or make their incompatible ARC ABI available to unrelated GNUstep software.
patchelf --set-rpath '$ORIGIN/../lib/mil-hwx-compiler' "$prefix/bin/mil-hwxc"
for library in "$private"/*.so*; do
  if [ ! -L "$library" ]; then patchelf --set-rpath '$ORIGIN' "$library"; fi
done
# Exercise the installed compiler with only its relative private-library path.
env -u LD_LIBRARY_PATH "$prefix/bin/mil-hwxc" --target H14 --mil tests/fixtures/h14/add.mil \
  --model-root . --output build/installed-h14-add
printf '%s  %s\n' b416b9d14059a0918f6b05bfcf4a8ba982dd92e7b25f2b042c1a15f1ab2a439a \
  build/installed-h14-add/program-0.anec | sha256sum -c -
