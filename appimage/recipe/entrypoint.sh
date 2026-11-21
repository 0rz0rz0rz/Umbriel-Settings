# shellcheck shell=sh
# Run only the bundled interpreter and packages: ignore user site-packages and any
# PYTHON* variables from the host that could shadow the bundled PySide6/tomlkit.
# The host values are recorded first so programs launched by the app (editors,
# terminals, umbriel) get the user's original environment back (see python/umbriel_core/launch.py).
for name in PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONNOUSERSITE; do
    if eval "[ -n \"\${$name+x}\" ]"; then
        eval "export UMBRIEL_SETTINGS_HOST_$name=\"\$$name\""
    fi
done
export UMBRIEL_SETTINGS_APPIMAGE_ENV=1

unset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE
export PYTHONNOUSERSITE=1
export PYTHONPATH="$APPDIR"

exec "{{ python-executable }}" -s -m umbriel_settings "$@"
