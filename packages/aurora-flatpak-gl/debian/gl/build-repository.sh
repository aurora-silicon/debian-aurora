#!/bin/sh
# build-repository.sh REPO WORKDIR BRANCH...
#
# Installs the aarch64 Freedesktop Platform, SDK and LLVM 22 SDK extension of
# each BRANCH from Flathub into the (private) user installation and builds
# org.freedesktop.Platform.GL.aurora for it into the OSTree repository REPO.
# flatpak-builder names its cache branch after the manifest's path, which
# must be a valid OSTree ref: WORKDIR must not contain a "~", as Debian
# source directories with a ~ in the version do.
set -eu
repo=$1
workdir=$2
shift 2
here=$(dirname -- "$0")
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
for branch in "$@"; do
	flatpak install --user --noninteractive --no-related -y flathub \
		"org.freedesktop.Platform/aarch64/$branch" \
		"org.freedesktop.Sdk/aarch64/$branch" \
		"org.freedesktop.Sdk.Extension.llvm22/aarch64/$branch"
	bash "$here/build-extension.sh" "$branch" "$repo" "$workdir/work-$branch"
done
