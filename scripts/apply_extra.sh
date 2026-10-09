#!/bin/sh
# Runs once at flatpak install/update time, inside /app/extra, after the
# official Carbide Motion installer has been downloaded and checksum-verified.
# The real install into the user's Wine prefix happens on first launch
# (see carbide-motion.sh), because apply_extra has no $HOME or display.
set -e
chmod 0644 CarbideMotionSetup.exe
