#!/usr/bin/env bash
# Build the Umbriel Settings AppImage into ./dist (run from anywhere).
#
#   appimage/build-appimage.sh
#
# Needs network access. Every download (python-appimage, the Python base image, appimagetool and the wheels
# from python/requirements.txt with their dependencies) is checked against appimage/pins.sh and the *.lock
# files first (fetch-pinned.sh); the AppImage's pip then installs only from those verified wheels.
# Python version, tool versions and checksums: tools/update_appimage_pins.py.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
dist="$root/dist"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/python/umbriel_settings/__init__.py")"
arch="$(uname -m)"
[ -n "$version" ] || { echo "Could not read __version__" >&2; exit 1; }

"$here/fetch-pinned.sh" "$work" "$arch"

# Stage a clean copy: recipe metadata, pinned requirements, and the package without caches.
mkdir -p "$work/recipe" "$work/extra"
cp "$here"/recipe/* "$work/recipe/"
cp "$root/python/umbriel_settings/assets/icon.png" "$work/recipe/umbriel-settings.png"  # Icon= in the .desktop file
cp "$root/python/requirements.txt" "$work/recipe/requirements.txt"
cp -r "$root/python/umbriel_settings" "$work/extra/umbriel_settings"
cp -r "$root/python/umbriel_core" "$work/extra/umbriel_core"
# The app runs the plugin's Luau UI; host/paths.py finds this bundled copy first.
plugin="$root/noctalia-plugin/umbriel-settings"
mkdir -p "$work/extra/umbriel_settings/ui_shared"
cp -r "$plugin"/{app.luau,lib,ui,pages,umbriel_settings.py} "$work/extra/umbriel_settings/ui_shared/"
find "$work/extra" -name __pycache__ -type d -prune -exec rm -rf {} +

# --no-packaging leaves an AppDir; appimagetool is run here because python-appimage
# mishandles output names derived from a desktop entry name containing spaces.
# PIP_NO_INDEX: the base image's pip installs the requirements from the verified wheels only, never PyPI.
(
    cd "$work"
    PIP_NO_INDEX=1 PIP_FIND_LINKS="$work/wheels" PIP_DISABLE_PIP_VERSION_CHECK=1 \
        "$work/venv/bin/python-appimage" build app --no-packaging \
        -b "$(echo "$work"/base/python*.AppImage)" -n umbriel-settings \
        "$work/recipe" \
        -x "$work/extra/umbriel_settings" "$work/extra/umbriel_core"
)

appdir="$(find "$work" -maxdepth 1 -mindepth 1 -type d -name '*-'"$arch" | head -n 1)"
[ -n "$appdir" ] || { echo "AppDir was not produced" >&2; exit 1; }
license_dir="$appdir/usr/share/licenses/Umbriel-Settings"
mkdir -p "$license_dir"
cp "$root/LICENSE" "$license_dir/LICENSE"
chmod -R a+rX "$appdir"

# The app uses QtCore/Gui/Widgets plus QtWebEngine (with QtWebChannel/QtNetwork) for its UI.
# WebEngine needs Qml/Quick/Positioning/OpenGL/PrintSupport libraries, QtWebEngineProcess
# (Qt/libexec), its resources and locales. Drop the other PySide6 modules and Qt libraries
# (3D, Multimedia/ffmpeg, Designer, Charts, ...), tools and the remaining translations.
pyside="$(find "$appdir" -type d -name PySide6 -path '*site-packages*' | head -n 1)"
[ -n "$pyside" ] || { echo "PySide6 not found in AppDir" >&2; exit 1; }
find "$pyside" -maxdepth 1 \( -name 'Qt*.abi3.so' -o -name 'Qt*.pyi' \) \
    ! -name 'QtCore.*' ! -name 'QtGui.*' ! -name 'QtWidgets.*' ! -name 'QtNetwork.*' \
    ! -name 'QtWebChannel.*' ! -name 'QtWebEngineCore.*' ! -name 'QtWebEngineWidgets.*' \
    ! -name 'QtPrintSupport.*' -delete
find "$pyside" -maxdepth 1 -type f -name 'PySide6_*.json' -delete
find "$pyside/Qt/lib" -maxdepth 1 \( \
    -name 'libQt63D*' -o -name 'libQt6Multimedia*' -o -name 'libQt6Designer*' -o -name 'libQt6Pdf*' \
    -o -name 'libQt6Charts*' -o -name 'libQt6Graphs*' -o -name 'libQt6DataVisualization*' \
    -o -name 'libQt6Location*' -o -name 'libQt6Sensors*' \
    -o -name 'libQt6Bluetooth*' -o -name 'libQt6Nfc*' -o -name 'libQt6ShaderTools*' \
    -o -name 'libQt6Help*' -o -name 'libQt6Test*' -o -name 'libQt6Sql*' \
    -o -name 'libav*' -o -name 'libsw*' \
    -o -name 'libQt6Quick3D*' -o -name 'libQt6SpatialAudio*' -o -name 'libQt6VirtualKeyboard*' \
    -o -name 'libQt6RemoteObjects*' -o -name 'libQt6Scxml*' -o -name 'libQt6StateMachine*' \
    -o -name 'libQt6TextToSpeech*' -o -name 'libQt6Serial*' -o -name 'libQt6HttpServer*' \
    -o -name 'libQt6WebView*' -o -name 'libQt6Lottie*' \) -delete
rm -f "$pyside"/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so
find "$pyside/Qt/translations" -mindepth 1 -maxdepth 1 ! -name 'qtwebengine_locales' -exec rm -rf {} +
# The UI is English and has no browser chrome: one WebEngine locale is enough, and DevTools is unused.
find "$pyside/Qt/translations/qtwebengine_locales" -type f ! -name 'en-US.pak' -delete
rm -f "$pyside/Qt/resources/qtwebengine_devtools_resources.pak"
rm -rf "$pyside/Qt/qml" "$pyside/Qt/metatypes" "$pyside/include" "$pyside/glue" "$pyside/doc" \
    "$pyside"/Qt/plugins/{designer,multimedia,qmltooling,sceneparsers,assetimporters,geometryloaders,renderers,renderplugins,sqldrivers,sensors,geoservices,webview,texttospeech,canbus,scxmldatamodel}
for tool in assistant balsam balsamui designer linguist lrelease lupdate qmlformat qmllint qmlls qsb \
    uic rcc deploy; do rm -rf "${pyside:?}/$tool"; done
rm -rf "${pyside:?}"/pyside6-*
# Qt/qml is gone, so the Quick Controls styles, dialogs, templates and Labs modules can never be
# imported; the compositor, UiTools and QML compiler libraries serve other Qt tools only.
find "$pyside/Qt/lib" -maxdepth 1 \( \
    -name 'libQt6QuickControls2*' -o -name 'libQt6QuickDialogs2*' -o -name 'libQt6QuickTemplates2*' \
    -o -name 'libQt6Labs*' -o -name 'libQt6QmlCompiler*' -o -name 'libQt6UiTools*' \
    -o -name 'libQt6WaylandCompositor*' -o -name 'libQt6WaylandEglCompositorHwIntegration*' \
    -o -name 'libQt6QuickTest*' -o -name 'libQt6QmlLocalStorage*' -o -name 'libQt6FFmpegStub*' \
    -o -name 'libQt6EglFs*' \) -delete
# EGLFS (no display server), PDF images, positioning and Lottie plugins: the app uses xcb/Wayland only.
rm -rf "$pyside"/Qt/plugins/{wayland-graphics-integration-server,vectorimageformats,egldeviceintegrations,position} \
    "$pyside"/Qt/plugins/imageformats/libqpdf.so \
    "$pyside"/Qt/libexec/{qmlcachegen,qmlimportscanner,qmltyperegistrar}

# python-appimage ships pip/build tooling, Tk and the stdlib test suite; the app needs none of them.
stdlib="$(find "$appdir/opt" -maxdepth 3 -type d -name 'python3.*' -path '*/lib/*' | head -n 1)"
[ -n "$stdlib" ] || { echo "Python stdlib not found in AppDir" >&2; exit 1; }
find "$stdlib" -maxdepth 1 \( -name test -o -name tkinter -o -name idlelib -o -name turtledemo \
    -o -name lib2to3 -o -name ensurepip -o -name 'config-*' \) -exec rm -rf {} +
rm -f "$stdlib"/lib-dynload/_tkinter.* "$stdlib"/lib-dynload/_ctypes_test.* \
    "$appdir"/usr/lib/libtcl8*.so* "$appdir"/usr/lib/libtk8*.so*
for name in pip build pyproject_hooks certifi; do
    rm -rf "${stdlib:?}/site-packages/$name" "${stdlib:?}/site-packages/$name"-*.dist-info
done

# Fail the build rather than ship a Qt library or plugin whose dependency was pruned above.
command -v readelf >/dev/null || { echo "readelf (binutils) is required" >&2; exit 1; }
missing="$(find "$pyside" -type f \( -name '*.so' -o -name '*.so.*' -o -name QtWebEngineProcess \) -print0 \
    | xargs -0 readelf -d 2>/dev/null \
    | sed -n 's/.*NEEDED.*\[\(libQt6[A-Za-z0-9]*\.so[.0-9]*\)\].*/\1/p' | sort -u \
    | while read -r lib; do [ -e "$pyside/Qt/lib/$lib" ] || echo "$lib"; done)"
[ -z "$missing" ] || { echo "Pruned Qt libraries are still required:" >&2; echo "$missing" >&2; exit 1; }

chmod -R a+rX "$appdir"
# The verified appimagetool, extracted so packaging needs no FUSE.
(cd "$work" && ./appimagetool.AppImage --appimage-extract >/dev/null && mv squashfs-root appimagetool)
appimagetool="$work/appimagetool/AppRun"

mkdir -p "$dist"
output="$dist/Umbriel-Settings-$version-$arch.AppImage"
# zstd 22 costs no start time; block size does (FUSE decompresses whole blocks on every launch).
# Measured: 128K 145 MB/0.70 s, 256K 140 MB/0.76 s, 512K 137 MB/0.92 s, 1M 133 MB/1.13 s.
ARCH="$arch" "$appimagetool" --no-appstream --comp zstd \
    --mksquashfs-opt -Xcompression-level --mksquashfs-opt 22 \
    --mksquashfs-opt -b --mksquashfs-opt 256K "$appdir" "$output"
chmod +x "$output"
echo "Built $output"
