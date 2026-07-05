#!/usr/bin/env python3
"""Normalize model-assembled findings to the stable schema. No legal inference."""
import json
import sys

RISK_LEVELS = {"critical", "high", "medium", "low", "info"}
CONFIDENCE = {"high", "medium", "low"}
SPDX_ALIASES = {
    "apache 2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache2": "Apache-2.0",
    "mit license": "MIT", "the mit license": "MIT",
    "bsd": "BSD (ambiguous — needs review)",
    "gpl": "GPL (ambiguous — needs review)",
    "gplv3": "GPL-3.0-only", "gplv2": "GPL-2.0-only",
    "cc-by": "CC-BY-4.0 (verify version)", "cc0": "CC0-1.0",
}


def canonical_spdx(expr):
    if not expr:
        return "UNKNOWN"
    return SPDX_ALIASES.get(expr.strip().lower(), expr.strip())


def normalize(doc):
    out = []
    for i, f in enumerate(doc.get("findings", []), 1):
        g = dict(f)
        g.setdefault("id", f"F-{i:04d}")
        g["license_expression"] = canonical_spdx(f.get("license_expression"))
        g["confidence"] = f.get("confidence") if f.get("confidence") in CONFIDENCE else "low"
        g["risk_level"] = f.get("risk_level") if f.get("risk_level") in RISK_LEVELS else "medium"
        cr = f.get("compatibility_risk")
        g["compatibility_risk"] = cr if cr in RISK_LEVELS else g["risk_level"]
        ev = g.get("evidence")
        g["evidence"] = ev if isinstance(ev, list) else ([ev] if ev else [])
        g.setdefault("unmet_obligation", "none")
        g.setdefault("review_notes", "")
        g.setdefault("recommended_action", "")
        out.append(g)
    doc = dict(doc)
    doc["findings"] = out
    doc.setdefault("schema_version", "1.0")
    doc.setdefault("generated_by", "license-compliance-auditor")
    doc.setdefault(
        "disclaimer",
        "Automated license detection is a starting point, not legal advice.")
    return doc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    src = json.load(open(argv[0])) if argv else json.load(sys.stdin)
    print(json.dumps(normalize(src), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
