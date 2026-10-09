#!/bin/sh
# Launcher for the Windows build of Carbide Motion running under Wine.
#
# - Creates a private Wine prefix in ~/.var/app/<app-id>/data/wine
# - Installs (or upgrades) Carbide Motion from the installer shipped as
#   flatpak extra-data whenever the packaged version changes
# - Maps the CNC controller's USB serial ports (/dev/ttyACM*, /dev/ttyUSB*)
#   to Windows COM ports so Carbide Motion can find the machine
set -eu

export WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/wine"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"

INSTALLER=/app/extra/CarbideMotionSetup.exe
PKG_VERSION="$(cat /app/share/carbide-motion/version 2>/dev/null || echo unknown)"
STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/carbide-motion"
VERSION_STAMP="$STATE_DIR/installed-version"
EXE_STAMP="$STATE_DIR/exe-path"
FIRST_COM=3

log() { echo "carbide-motion: $*" >&2; }

notify() {
    # Best effort: tell the user something slow is happening.
    if command -v zenity >/dev/null 2>&1; then
        zenity --notification --text="$1" >/dev/null 2>&1 &
    fi
    log "$1"
}

init_prefix() {
    if [ ! -f "$WINEPREFIX/system.reg" ]; then
        notify "Setting up Wine for Carbide Motion (first run)…"
        mkdir -p "$WINEPREFIX"
        wine wineboot --init
        wineserver -w
    fi
}

run_installer() {
    if [ ! -f "$INSTALLER" ]; then
        log "installer missing at $INSTALLER (extra-data not downloaded?)"
        exit 1
    fi
    notify "Installing Carbide Motion $PKG_VERSION…"

    # Pick unattended flags based on the installer technology; fall back to
    # the normal interactive installer if it isn't recognised.
    if grep -qa "Inno Setup" "$INSTALLER"; then
        wine "$INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- || true
    elif grep -qa "Nullsoft" "$INSTALLER"; then
        wine "$INSTALLER" /S || true
    elif grep -qa "QtIFW\|installerbase" "$INSTALLER"; then
        wine "$INSTALLER" install --accept-licenses --default-answer --confirm-command || true
    else
        wine "$INSTALLER" || true
    fi
    wineserver -w

    exe="$(find "$WINEPREFIX/drive_c" -type f -iname '*motion*.exe' \
            ! -iname 'unins*' ! -iname '*setup*' ! -iname '*install*' \
            ! -ipath '*/windows/*' 2>/dev/null | head -n1)"
    if [ -z "$exe" ]; then
        log "could not find Carbide Motion executable after install"
        exit 1
    fi
    mkdir -p "$STATE_DIR"
    printf '%s\n' "$exe" > "$EXE_STAMP"
    printf '%s\n' "$PKG_VERSION" > "$VERSION_STAMP"
}

map_serial_ports() {
    dd="$WINEPREFIX/dosdevices"
    mkdir -p "$dd"

    # Drop mappings from a previous run that point at USB serial devices.
    for link in "$dd"/com*; do
        [ -L "$link" ] || continue
        case "$(readlink "$link")" in
            /dev/ttyACM*|/dev/ttyUSB*) rm -f "$link" ;;
        esac
    done

    reg="$(mktemp)"
    printf 'REGEDIT4\n\n[HKEY_LOCAL_MACHINE\\HARDWARE\\DEVICEMAP\\SERIALCOMM]\n' > "$reg"
    n=$FIRST_COM
    found=0
    for dev in /dev/ttyACM* /dev/ttyUSB*; do
        [ -e "$dev" ] || continue
        ln -sfn "$dev" "$dd/com$n"
        printf '"\\\\Device\\\\CarbideSerial%d"="COM%d"\n' "$n" "$n" >> "$reg"
        if [ ! -r "$dev" ] || [ ! -w "$dev" ]; then
            log "WARNING: no read/write access to $dev — add your user to the" \
                "'dialout' (Debian/Ubuntu/Fedora) or 'uucp' (Arch) group and log in again"
        fi
        log "mapped $dev -> COM$n"
        n=$((n + 1))
        found=1
    done
    if [ "$found" = 1 ]; then
        wine regedit /S "$reg" || true
    else
        log "no USB serial devices found — connect the machine before launching"
    fi
    rm -f "$reg"
}

init_prefix

if [ ! -f "$VERSION_STAMP" ] || [ "$(cat "$VERSION_STAMP")" != "$PKG_VERSION" ] \
   || [ ! -f "$EXE_STAMP" ] || [ ! -f "$(cat "$EXE_STAMP")" ]; then
    run_installer
fi

map_serial_ports

exe="$(cat "$EXE_STAMP")"
cd "$(dirname "$exe")"
exec wine "$exe" "$@"
