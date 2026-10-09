#!/usr/bin/env python3
"""Detect new Windows builds of Carbide Motion and pin them in the manifest.

Scrapes Carbide 3D's download pages for Carbide Motion Windows installers,
picks the highest build number, downloads it to compute sha256/size, and
rewrites the managed sections of the flatpak manifest and metainfo.

Writes `changed`, `version` and `url` to $GITHUB_OUTPUT when run in Actions.

Usage:
  check_update.py                      # auto-detect from carbide3d.com
  check_update.py --url URL            # pin a specific installer URL
  check_update.py --channel beta       # also consider beta builds
"""

import argparse
import datetime
import hashlib
import html
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "io.github.adman234.CarbideMotion"
MANIFEST = os.path.join(ROOT, f"{APP_ID}.yml")
METAINFO = os.path.join(ROOT, "data", f"{APP_ID}.metainfo.xml")

PAGES = [
    "https://carbide3d.com/carbidemotion/download/",
    "https://carbide3d.com/carbidemotion/",
    "https://carbide3d.com/downloads/",
    "https://carbide3d.com/download/",
]
BETA_PAGES = [
    "https://carbide3d.com/carbidemotion/beta/",
    "https://carbide3d.com/carbidemotion/download/beta/",
]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

EXE_RE = re.compile(r"""["'(=\s](https?://[^"'()<>\s]+?\.exe|/[^"'()<>\s]+?\.exe)(?:\?[^"'()<>\s]*)?["')\s>]""", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def build_number(url):
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    nums = re.findall(r"\d{3,}", name)
    return int(nums[-1]) if nums else None


def find_installers(channel):
    pages = PAGES + (BETA_PAGES if channel == "beta" else [])
    found = {}
    for page in pages:
        try:
            body, final = fetch(page)
        except Exception as e:  # noqa: BLE001 - keep scanning other pages
            print(f"  skip {page}: {e}", file=sys.stderr)
            continue
        body = html.unescape(body)
        for m in EXE_RE.finditer(body):
            url = urllib.parse.urljoin(final, m.group(1))
            low = urllib.parse.unquote(url).lower()
            if "motion" not in low.rsplit("/", 1)[-1]:
                continue
            if channel == "stable" and "beta" in low:
                continue
            build = build_number(url)
            if build is None:
                continue
            found[url] = build
            print(f"  found build {build}: {url}", file=sys.stderr)
    return found


def download(url):
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as r, tempfile.TemporaryFile() as tmp:
        final = r.geturl()
        while chunk := r.read(1 << 20):
            h.update(chunk)
            tmp.write(chunk)
            size += len(chunk)
        tmp.seek(0)
        head = tmp.read(2)
    if head != b"MZ":
        sys.exit(f"error: {url} is not a Windows executable (got {head!r})")
    return final, h.hexdigest(), size


def current_pin():
    text = open(MANIFEST).read()
    ver = re.search(r"CM_VERSION: '([^']*)'", text).group(1)
    url = re.search(r"filename: CarbideMotionSetup\.exe\n\s+url: (\S+)", text).group(1)
    return ver, url


def write_pin(version, url, sha256, size):
    text = open(MANIFEST).read()
    text = re.sub(r"CM_VERSION: '[^']*'", f"CM_VERSION: '{version}'", text)
    text = re.sub(
        r"(filename: CarbideMotionSetup\.exe\n(\s+))url: .*\n\s+sha256: .*\n\s+size: .*\n",
        lambda m: f"{m.group(1)}url: {url}\n{m.group(2)}sha256: '{sha256}'\n{m.group(2)}size: {size}\n",
        text,
    )
    open(MANIFEST, "w").write(text)

    meta = open(METAINFO).read()
    if f'version="{version}"' not in meta:
        today = datetime.date.today().isoformat()
        meta = meta.replace(
            "<!-- managed by scripts/check_update.py -->",
            "<!-- managed by scripts/check_update.py -->\n"
            f'    <release version="{version}" date="{today}"/>',
            1,
        )
        open(METAINFO, "w").write(meta)


def set_output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kw.items():
        print(f"{k}={v}")
        if path:
            with open(path, "a") as f:
                f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="pin this installer URL instead of scraping")
    ap.add_argument("--version", help="version label to use with --url")
    ap.add_argument("--channel", choices=["stable", "beta"], default=os.environ.get("CM_CHANNEL") or "stable")
    args = ap.parse_args()

    cur_ver, cur_url = current_pin()
    print(f"current: {cur_ver} {cur_url}", file=sys.stderr)

    if args.url:
        url = args.url
        version = args.version or str(build_number(url) or "")
        if not version:
            sys.exit("error: could not infer version from URL; pass --version")
    else:
        found = find_installers(args.channel)
        if not found:
            sys.exit(
                "error: no Carbide Motion Windows installer links found on "
                + ", ".join(PAGES)
                + "\nThe download page layout may have changed; run the workflow "
                "manually with an explicit installer_url."
            )
        url, build = max(found.items(), key=lambda kv: kv[1])
        version = str(build)

    try:
        newer = int(version) > int(cur_ver)
    except ValueError:
        newer = version != cur_ver
    if not args.url and not newer:
        print(f"up to date ({cur_ver})", file=sys.stderr)
        set_output(changed="false", version=cur_ver, url=cur_url)
        return

    print(f"pinning {version}: {url}", file=sys.stderr)
    final_url, sha256, size = download(url)
    # Pin the URL as published (not a CDN redirect target, which may expire).
    write_pin(version, url, sha256, size)
    print(f"sha256={sha256} size={size} (served from {final_url})", file=sys.stderr)
    set_output(changed="true", version=version, url=url)


if __name__ == "__main__":
    main()
