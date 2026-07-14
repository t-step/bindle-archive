#!/usr/bin/env python3
"""Portable package release-integrity checker (issue #59).

Deterministic, mechanical checks for a Python package release. Judgment checks
(change classification, track routing) return 'uncertain' — never guessed.
Stdlib only. Never mutates; a green check is not authorization to publish.
"""
import re

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# change class -> required bump component, split by pre/post 1.0.
# Pre-1.0 (0.x): a breaking change bumps the MINOR; additive/fix bump PATCH.
# Post-1.0: standard semver.
_MOVEMENT = {
    False: {"breaking": "major", "additive": "minor", "patch": "patch"},
    True: {"breaking": "minor", "additive": "patch", "patch": "patch"},
}


def parse_version(s):
    """Parse an exact MAJOR.MINOR.PATCH string. Returns a tuple or None."""
    if s is None:
        return None
    m = SEMVER_RE.match(s.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def is_pre_1_0(ver):
    """True when the version is in the 0.x unstable series."""
    return ver[0] == 0


def bump_type(old, new):
    """Which single component increased old->new. None if no clean increase."""
    if new[0] > old[0]:
        return "major"
    if new[0] == old[0] and new[1] > old[1]:
        return "minor"
    if new[0] == old[0] and new[1] == old[1] and new[2] > old[2]:
        return "patch"
    return None


def required_movement(change_class, pre_1_0):
    """Required bump component for a change class. data-only -> None (no move)."""
    if change_class == "data-only":
        return None
    return _MOVEMENT[bool(pre_1_0)].get(change_class)
