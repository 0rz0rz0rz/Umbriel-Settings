#!/usr/bin/env bash
# Build the Umbriel Settings AppImage into ./dist (run from anywhere).
#
#   appimage/build-appimage.sh [python-version]     default python-version: 3.12
#
# Needs network access (downloads the python-appimage base image and the pinned
# wheels from python/requirements.txt) and FUSE, or APPIMAGE_EXTRACT_AND_RUN=1.
set -euo pipefail

PYTHON_VERSION="${1:-3.12}"
PYTHON_APPIMAGE_VERSION="1.4.7"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
dist="$root/dist"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/python/umbriel_settings/__init__.py")"
arch="$(uname -m)"
[ -n "$version" ] || { echo "Could not read __version__" >&2; exit 1; }

python3 -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet "python-appimage==$PYTHON_APPIMAGE_VERSION"

# Stage a clean copy: recipe metadata, pinned requirements, and the package without caches.
mkdir -p "$work/recipe" "$work/extra"
cp "$here"/recipe/* "$work/recipe/"
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
(
    cd "$work"
    "$work/venv/bin/python-appimage" build app --no-packaging \
        -p "$PYTHON_VERSION" -n umbriel-settings \
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

chmod -R a+rX "$appdir"
appimagetool="$("$work/venv/bin/python" -c 'from python_appimage.utils.deps import ensure_appimagetool as e; print(e())')"

mkdir -p "$dist"
output="$dist/Umbriel-Settings-$version-$arch.AppImage"
ARCH="$arch" "$appimagetool" --no-appstream "$appdir" "$output"
chmod +x "$output"
echo "Built $output"
