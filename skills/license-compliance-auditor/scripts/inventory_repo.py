#!/usr/bin/env python3
"""Enumerate license-relevant files/dirs in a repo. Pure inspection; no network."""
import json
import os
import re
import sys

LICENSE_FILES = {"license", "licence", "copying", "notice", "authors",
                 "copyright", "unlicense"}
MANIFESTS = {"package.json", "pyproject.toml", "setup.py", "setup.cfg",
             "cargo.toml", "go.mod", "composer.json", "gemfile", "build.gradle",
             "pom.xml"}
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
             "uv.lock", "cargo.lock", "go.sum", "composer.lock", "gemfile.lock",
             "requirements.txt"}
VENDOR_DIRS = {"vendor", "vendors", "third_party", "third-party", "external",
               "deps", "extern"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
MODEL_EXT = {".gltf", ".glb", ".obj", ".fbx", ".stl", ".blend", ".dae"}
DATA_EXT = {".csv", ".parquet", ".jsonl", ".geojson", ".sqlite", ".db"}
TEXT_SCAN_EXT = {".c", ".h", ".cpp", ".cc", ".py", ".js", ".ts", ".tsx", ".jsx",
                 ".go", ".rs", ".java", ".rb", ".php", ".css", ".scss"}
ECOSYSTEM_BY_MANIFEST = {
    "package.json": "npm", "pyproject.toml": "pip", "setup.py": "pip",
    "setup.cfg": "pip", "cargo.toml": "cargo", "go.mod": "go",
    "composer.json": "composer", "gemfile": "rubygems", "build.gradle": "gradle",
    "pom.xml": "maven",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".tox"}
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*(.+)")
PROVENANCE_RE = re.compile(
    r"(stackoverflow\.com|stackexchange\.com|gist\.github|codepen\.io|"
    r"jsfiddle\.net|copied from|adapted from)", re.I)
MAX_SCAN_BYTES = 200_000


def _read(path, limit=MAX_SCAN_BYTES):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read(limit)


def _spdx_from_manifest(path, name):
    try:
        text = _read(path)
    except OSError:
        return None
    patterns = {
        "package.json": r'"license"\s*:\s*"([^"]+)"',
        "composer.json": r'"license"\s*:\s*"([^"]+)"',
        "cargo.toml": r'license\s*=\s*"([^"]+)"',
        "pyproject.toml": r'license\s*=\s*["\']?([A-Za-z0-9.\-+ ]+)',
        "setup.cfg": r'license\s*=\s*([A-Za-z0-9.\-+ ]+)',
    }
    pat = patterns.get(name)
    if not pat:
        return None
    m = re.search(pat, text)
    return m.group(1).strip() if m else None


def inventory(root):
    root = os.path.abspath(root)
    inv = {
        "root": root, "license_files": [], "declared_license_candidates": [],
        "manifests": [], "lockfiles": [], "ecosystems": set(), "submodules": [],
        "vendored_dirs": [], "spdx_headers": [], "provenance_markers": [],
        "fonts": [], "assets": {"images": [], "audio": [], "video": [],
                                "models": [], "data": []},
    }
    gm = os.path.join(root, ".gitmodules")
    if os.path.isfile(gm):
        for m in re.finditer(r"path\s*=\s*(.+)", _read(gm)):
            inv["submodules"].append(m.group(1).strip())
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in list(dirnames):
            if d.lower() in VENDOR_DIRS:
                inv["vendored_dirs"].append(
                    os.path.relpath(os.path.join(dirpath, d), root))
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            low = fn.lower()
            stem, ext = os.path.splitext(low)
            if stem in LICENSE_FILES or low in LICENSE_FILES:
                inv["license_files"].append(rel)
            if low in MANIFESTS:
                inv["manifests"].append(rel)
                eco = ECOSYSTEM_BY_MANIFEST.get(low)
                if eco:
                    inv["ecosystems"].add(eco)
                spdx = _spdx_from_manifest(full, low)
                if spdx:
                    inv["declared_license_candidates"].append(
                        {"file": rel, "spdx": spdx})
            if low in LOCKFILES:
                inv["lockfiles"].append(rel)
            if ext in FONT_EXT:
                inv["fonts"].append({"path": rel})
            elif ext in IMAGE_EXT:
                inv["assets"]["images"].append(rel)
            elif ext in AUDIO_EXT:
                inv["assets"]["audio"].append(rel)
            elif ext in VIDEO_EXT:
                inv["assets"]["video"].append(rel)
            elif ext in MODEL_EXT:
                inv["assets"]["models"].append(rel)
            elif ext in DATA_EXT:
                inv["assets"]["data"].append(rel)
            if ext in TEXT_SCAN_EXT:
                try:
                    text = _read(full)
                except OSError:
                    continue
                for m in SPDX_RE.finditer(text):
                    inv["spdx_headers"].append(
                        {"path": rel, "spdx": m.group(1).strip()})
                for lineno, line in enumerate(text.splitlines(), 1):
                    if PROVENANCE_RE.search(line):
                        inv["provenance_markers"].append(
                            {"path": rel, "line": lineno,
                             "marker": line.strip()[:200]})
    inv["ecosystems"] = sorted(inv["ecosystems"])
    for k in ("license_files", "manifests", "lockfiles", "vendored_dirs"):
        inv[k].sort()
    return inv


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else "."
    print(json.dumps(inventory(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
