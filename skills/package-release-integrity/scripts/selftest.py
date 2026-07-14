#!/usr/bin/env python3
"""Pure-logic self-test for release_integrity.py. Auto-run by bin/check.sh.
Exits non-zero on any failure; prints a one-line tally."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_integrity as ri

_fail = 0


def check(desc, got, want):
    global _fail
    if got == want:
        print(f"  ok: {desc}")
    else:
        _fail += 1
        print(f"  FAIL: {desc} -> got {got!r}, want {want!r}")


# parse_version
check("parse valid", ri.parse_version("1.2.3"), (1, 2, 3))
check("parse strips ws", ri.parse_version("  0.3.0 "), (0, 3, 0))
check("parse rejects non-semver", ri.parse_version("1.2"), None)
check("parse rejects suffix", ri.parse_version("1.2.3rc1"), None)

# is_pre_1_0
check("pre-1.0 true", ri.is_pre_1_0((0, 4, 0)), True)
check("pre-1.0 false", ri.is_pre_1_0((1, 0, 0)), False)

# bump_type
check("bump major", ri.bump_type((1, 2, 3), (2, 0, 0)), "major")
check("bump minor", ri.bump_type((1, 2, 3), (1, 3, 0)), "minor")
check("bump patch", ri.bump_type((1, 2, 3), (1, 2, 4)), "patch")
check("bump none (equal)", ri.bump_type((1, 2, 3), (1, 2, 3)), None)
check("bump none (decrease)", ri.bump_type((1, 2, 3), (1, 2, 2)), None)

# required_movement — post-1.0
check("post breaking->major", ri.required_movement("breaking", False), "major")
check("post additive->minor", ri.required_movement("additive", False), "minor")
check("post patch->patch", ri.required_movement("patch", False), "patch")
# required_movement — pre-1.0 (0.x: breaking bumps minor, additive/fix bump patch)
check("pre breaking->minor", ri.required_movement("breaking", True), "minor")
check("pre additive->patch", ri.required_movement("additive", True), "patch")
check("pre patch->patch", ri.required_movement("patch", True), "patch")
# data-only never moves the package version
check("data-only->none post", ri.required_movement("data-only", False), None)
check("data-only->none pre", ri.required_movement("data-only", True), None)

print(f"selftest: {'PASS' if _fail == 0 else 'FAIL'} ({_fail} failing)")
sys.exit(1 if _fail else 0)
