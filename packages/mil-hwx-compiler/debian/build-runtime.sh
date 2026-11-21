#!/bin/bash
# alarm-aurora's build-runtime.sh (the offline counterpart of upstream's
# bootstrap-linux-toolchain.sh) for the source package's component
# directories: build the private libobjc2, GNUstep Make and GNUstep Base into
# .gnustep. Never replace the system Objective-C ABI.
set -eo pipefail
sources=$(realpath "${1:?directory with the libobjc2, gnustep-make and gnustep-base sources}")
prefix="$PWD/.gnustep"
jobs=${JOBS:-8}
export CC=clang CXX=clang++ OBJC=clang OBJCXX=clang++
# Keep the failing compiler/link/run probe, not just configure's summary.
configure_stage() {
  local ane_config_rc=0
  ./configure "$@" || ane_config_rc=$?
  if [ "$ane_config_rc" != 0 ]; then
    if [ -f config.log ]; then cat config.log >&2; fi
    return "$ane_config_rc"
  fi
}
cmake -S "$sources/libobjc2" -B .objc-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DCMAKE_INSTALL_LIBDIR=lib -DGNUSTEP_INSTALL_TYPE=NONE \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON -DTESTS=OFF
cmake --build .objc-build -j "$jobs"
cmake --install .objc-build
export PATH="$prefix/bin:$PATH" LD_LIBRARY_PATH="$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export CPPFLAGS="-I$prefix/include" LDFLAGS="-L$prefix/lib -Wl,-rpath,$prefix/lib -fuse-ld=lld"
(
  cd "$sources/gnustep-make"
  configure_stage --prefix="$prefix" --with-layout=fhs --with-library-combo=ng-gnu-gnu \
    --with-runtime-abi=gnustep-2.0 --enable-objc-arc --enable-native-objc-exceptions
  make -j "$jobs"
  make install
)
export GNUSTEP_CONFIG_FILE="$prefix/etc/GNUstep/GNUstep.conf"
. "$prefix/share/GNUstep/Makefiles/GNUstep.sh"
(
  cd "$sources/gnustep-base"
  configure_stage --prefix="$prefix" --disable-tls --disable-xslt --disable-zeroconf \
    --disable-libdispatch --disable-nsurlsession
  make -j "$jobs"
  make install
)
