#!/usr/bin/env bash
# Download everything the AppImage build uses and verify each file against appimage/pins.sh and the lock files.
#
#   appimage/fetch-pinned.sh <work-dir> [arch]      default arch: uname -m
#
# Leaves in <work-dir>: venv/ (python-appimage), wheels/ (the app's packages), base/<release file name> (Python;
# python-appimage reads its version from that name) and appimagetool.AppImage. Any mismatch stops with an
# error; regenerate pins with tools/update_appimage_pins.py.
set -euo pipefail

work="${1:?usage: fetch-pinned.sh <work-dir> [arch]}"
arch="${2:-$(uname -m)}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=appimage/pins.sh
. "$here/pins.sh"

pin() { local name="$1_$arch"; printf '%s' "${!name:-}"; }
for kind in BASE_IMAGE APPIMAGETOOL; do
    [ -n "$(pin "${kind}_URL")" ] || { echo "No pinned ${kind,,} for $arch in appimage/pins.sh" >&2; exit 1; }
done

fetch() {  # url sha256 destination
    curl -fsSL --retry 3 -o "$3" "$1"
    echo "$2  $3" | sha256sum -c --quiet - || { echo "Checksum mismatch: $1" >&2; rm -f "$3"; exit 1; }
}

mkdir -p "$work"
export PIP_DISABLE_PIP_VERSION_CHECK=1
python3 -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet --require-hashes --only-binary :all: -r "$here/build-tools.lock"

base_url="$(pin BASE_IMAGE_URL)"
base_image="$work/base/${base_url##*/}"
mkdir -p "$work/base"
fetch "$base_url" "$(pin BASE_IMAGE_SHA256)" "$base_image"
fetch "$(pin APPIMAGETOOL_URL)" "$(pin APPIMAGETOOL_SHA256)" "$work/appimagetool.AppImage"
chmod +x "$base_image" "$work/appimagetool.AppImage"

# Wheels for the bundled Python and this machine type; the build installs only from this folder.
abi="cp${PINNED_PYTHON_VERSION/./}"
platforms=()
for tag in manylinux_2_39 manylinux_2_34 manylinux_2_28 manylinux_2_17 manylinux2014; do
    platforms+=(--platform "${tag}_$arch")
done
"$work/venv/bin/pip" download --quiet --require-hashes --no-deps --only-binary :all: \
    --python-version "$PINNED_PYTHON_VERSION" --implementation cp --abi "$abi" --abi abi3 --abi none \
    "${platforms[@]}" -r "$here/requirements.lock" -d "$work/wheels"
echo "Verified downloads in $work"
