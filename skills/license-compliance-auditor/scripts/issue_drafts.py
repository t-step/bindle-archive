#!/usr/bin/env python3
"""Write grouped local issue drafts from findings. Never calls gh or the network."""
import json
import os
import re
import sys

LABELS_BY_TYPE = {
    "dependency": ["license-compliance", "dependencies"],
    "vendored": ["license-compliance", "legal-review"],
    "submodule": ["license-compliance", "legal-review"],
    "font": ["license-compliance", "fonts"],
    "asset": ["license-compliance", "assets"],
    "dataset": ["license-compliance", "assets", "legal-review"],
    "snippet": ["license-compliance", "legal-review"],
    "spdx-header": ["license-compliance", "documentation"],
}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "issue"


def group(findings):
    groups = {}
    for f in findings:
        if f.get("risk_level") not in ("critical", "high"):
            continue
        groups.setdefault(f.get("type", "other"), []).append(f)
    return groups


def draft_markdown(group_type, items):
    labels = LABELS_BY_TYPE.get(group_type, ["license-compliance"])
    highest = "critical" if any(f.get("risk_level") == "critical"
                                for f in items) else "high"
    lines = [f"# License compliance: {group_type} findings", "",
             f"**Suggested labels:** {', '.join(labels)}",
             f"**Highest risk:** {highest}", "", "## Affected items", ""]
    for f in items:
        lines.append(f"- `{f.get('item')}` ({f.get('path')}) — "
                     f"{f.get('unmet_obligation')} [{f.get('risk_level')}]")
    lines += ["", "## Evidence", ""]
    for f in items:
        for e in f.get("evidence", []):
            lines.append(f"- {f.get('item')}: {e}")
    lines += ["", "## Recommended action", ""]
    for f in items:
        lines.append(f"- {f.get('item')}: {f.get('recommended_action')}")
    lines += ["", "## Human-review boundary", "",
              "This draft flags risk and likely obligation gaps; it is not legal "
              "advice. Confirm obligations with a qualified reviewer before acting.",
              "", "## Acceptance criteria", "",
              "- [ ] Each affected item resolved or explicitly accepted with rationale",
              "- [ ] Required license text / attribution added where applicable"]
    return "\n".join(lines)


def write_drafts(doc, out_dir="license-compliance-issues"):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for gtype, items in sorted(group(doc.get("findings", [])).items()):
        path = os.path.join(out_dir, f"{_slug(gtype)}.md")
        with open(path, "w") as fh:
            fh.write(draft_markdown(gtype, items) + "\n")
        written.append(path)
    return written


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    doc = json.load(open(argv[0]))
    out_dir = argv[1] if len(argv) > 1 else "license-compliance-issues"
    for p in write_drafts(doc, out_dir):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
