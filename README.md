# Carbide Motion Flatpak (unofficial)

Runs the **official Windows build** of [Carbide Motion](https://carbide3d.com/carbidemotion/)
on Linux under Wine, packaged as a Flatpak that updates itself when Carbide 3D
ships a new build.

> Not affiliated with or supported by Carbide 3D. Carbide Motion is proprietary
> software; this repo never redistributes it. The flatpak declares the installer
> as `extra-data`, so **your machine downloads it directly from carbide3d.com**
> at install/update time and verifies a pinned sha256.

## Install

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user https://adman234.github.io/carbide-motion-fp/carbide-motion.flatpakref
```

If the repo is unsigned (no `FLATPAK_GPG_PRIVATE_KEY` secret configured, see below), add the
remote manually instead:

```sh
flatpak remote-add --user --no-gpg-verify carbide-motion https://adman234.github.io/carbide-motion-fp/repo/
flatpak install --user carbide-motion io.github.adman234.CarbideMotion
```

Updates then arrive through the normal `flatpak update` (or GNOME Software / Discover).

Each build is also attached to a [GitHub release](https://github.com/adman234/carbide-motion-fp/releases)
as a single-file `.flatpak` bundle (`flatpak install --user CarbideMotion-<build>.flatpak`).

### Serial port / machine connection

- Your user needs access to the controller's USB serial port:
  `sudo usermod -aG dialout $USER` (Debian/Ubuntu/Fedora) or `uucp` (Arch), then log out and back in.
- **Plug in and power on the machine before launching.** The launcher maps every
  `/dev/ttyACM*` / `/dev/ttyUSB*` to `COM3`, `COM4`, … in the Wine prefix at startup.
- The first launch creates the Wine prefix and runs the Carbide Motion installer, so it takes
  a minute. When a new build is installed via `flatpak update`, the next launch reinstalls it.

Wine prefix: `~/.var/app/io.github.adman234.CarbideMotion/data/wine`.
G-code access is granted for `~/Documents`, `~/Downloads` and `~/Desktop`; for other
folders use `flatpak override --user --filesystem=/path io.github.adman234.CarbideMotion`.

Debugging: `flatpak run --env=WINEDEBUG=err+all io.github.adman234.CarbideMotion`.

## How the automation works

`.github/workflows/flatpak.yml`:

1. **check** (daily, on push to `main`, or manually) runs `scripts/check_update.py`, which
   scrapes carbide3d.com's download pages for `CarbideMotion-<build>.exe` links, picks the
   highest build, downloads it to compute sha256/size, rewrites the pinned values in the
   manifest + metainfo, and commits the change.
2. **build** runs `flatpak-builder` (Wine base app `org.winehq.Wine` from Flathub), does a smoke
   install that fetches and verifies the real installer, builds an OSTree repo + `.flatpak` bundle,
   and creates a GitHub release.
3. **deploy** publishes the OSTree repo to GitHub Pages, which is what `flatpak update` pulls from.

Manual runs (*Actions → Carbide Motion Flatpak → Run workflow*) can pin an explicit
`installer_url` (useful if Carbide's page layout changes and auto-detection breaks),
track the `beta` channel, or force a rebuild. Set the repo variable `CM_CHANNEL=beta`
to make the scheduled check track betas.

### One-time repo setup

1. **Settings → Pages → Source: GitHub Actions.**
2. The schedule runs only on the default branch (`main`).
3. Optional but recommended: sign the repo. Create a key and add it as the secret
   `FLATPAK_GPG_PRIVATE_KEY`:
   ```sh
   gpg --quick-gen-key "Carbide Motion Flatpak" default default never
   gpg --armor --export-secret-keys "Carbide Motion Flatpak"
   ```
   The public key is embedded in the generated `.flatpakrepo` / `.flatpakref` automatically.

## Building locally

```sh
flatpak install --user flathub org.freedesktop.Sdk//24.08 org.winehq.Wine//stable-24.08
python3 scripts/check_update.py   # pin the latest installer (the committed pin may be stale)
flatpak-builder --user --install --install-deps-from=flathub --force-clean build-dir io.github.adman234.CarbideMotion.yml
```
