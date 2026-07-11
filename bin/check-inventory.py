#!/usr/bin/env python3
"""Validate capabilities.json against the Bindle repo. Stdlib-only.

Usage: check-inventory.py [--root DIR]
Exits 0 if the inventory is consistent, 1 (with per-line diagnostics) otherwise.
"""
import argparse
import json
import os
import re
import sys

TYPES = {"skill", "command", "agent", "global-guidance", "script", "contract"}
PROVIDER_STATUS = {"installed", "manual", "untested", "unsupported", "n/a"}
MATURITY = {"draft", "documented", "tested"}
MUTATION_FLAGS = {"disk", "network", "external"}
REQUIRED = ["name", "type", "path", "description", "provider", "maturity",
            "mutation", "version_introduced"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_inventory(root):
    path = os.path.join(root, "capabilities.json")
    if not os.path.isfile(path):
        raise ValueError("capabilities.json: missing at repo root")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("capabilities.json: invalid JSON (%s)" % exc)
    if not isinstance(data, dict):
        raise ValueError("capabilities.json: top level must be an object")
    caps = data.get("capabilities")
    ledger = data.get("not_a_capability", [])
    if not isinstance(caps, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    if not isinstance(ledger, list):
        raise ValueError("capabilities.json: 'not_a_capability' must be an array")
    return caps, ledger


def read_version(root):
    with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def _semver_tuple(v):
    return tuple(int(x) for x in v.split("."))


def check_schema(caps, version):
    errors = []
    seen = set()
    for i, cap in enumerate(caps):
        label = cap.get("name", "<row %d>" % i)
        for field in REQUIRED:
            if field not in cap:
                errors.append("%s: missing required field '%s'" % (label, field))
        if cap.get("type") not in TYPES:
            errors.append("%s: invalid type '%s'" % (label, cap.get("type")))
        key = (cap.get("type"), cap.get("name"))
        if key in seen:
            errors.append("%s: duplicate (type, name) %s" % (label, key))
        seen.add(key)
        prov = cap.get("provider")
        if isinstance(prov, dict):
            for p in ("claude", "codex"):
                if prov.get(p) not in PROVIDER_STATUS:
                    errors.append("%s: provider.%s '%s' not in %s"
                                  % (label, p, prov.get(p), sorted(PROVIDER_STATUS)))
        else:
            errors.append("%s: provider must be an object with claude+codex" % label)
        if cap.get("maturity") not in MATURITY:
            errors.append("%s: invalid maturity '%s'" % (label, cap.get("maturity")))
        mut = cap.get("mutation")
        if not isinstance(mut, list) or any(m not in MUTATION_FLAGS for m in mut):
            errors.append("%s: mutation must be a subset of %s"
                          % (label, sorted(MUTATION_FLAGS)))
        vi = str(cap.get("version_introduced", ""))
        if not SEMVER.match(vi):
            errors.append("%s: version_introduced '%s' is not semver" % (label, vi))
        elif _semver_tuple(vi) > _semver_tuple(version):
            errors.append("%s: version_introduced %s is ahead of VERSION %s"
                          % (label, vi, version))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        caps, ledger = load_inventory(root)
        version = read_version(root)
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    errors = []
    errors += check_schema(caps, version)
    # NOTE: later tasks append more checks here.
    if errors:
        for e in errors:
            print(e)
        return 1
    print("capability inventory OK (%d capabilities, %d ledgered exclusions)"
          % (len(caps), len(ledger)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
