import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import render_report as rr  # noqa: E402

DOC = {
    "repo": {"declared_license": "MIT", "declared_license_evidence": ["LICENSE"]},
    "coverage": [{"category": "javascript-deps", "status": "checked"}],
    "findings": [
        {"item": "DemoSans", "type": "font", "path": "assets/fonts/DemoSans.ttf",
         "risk_level": "high", "unmet_obligation": "missing OFL.txt",
         "compatibility_risk": "high", "confidence": "medium",
         "evidence": ["no OFL.txt beside font"], "recommended_action": "add OFL.txt",
         "review_notes": "confirm OFL applies"},
        {"item": "left-pad", "type": "dependency", "path": "node_modules/left-pad",
         "risk_level": "info", "unmet_obligation": "none"},
    ],
}


class RenderTest(unittest.TestCase):
    def test_terminal_has_baseline_coverage_and_top_findings(self):
        term = rr.terminal_report(DOC)
        self.assertIn("Declared license: MIT", term)
        self.assertIn("javascript-deps", term)
        self.assertIn("DemoSans", term)
        self.assertIn("HIGH", term)

    def test_writes_md_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            rr.render(DOC, out_dir=d)
            md = open(os.path.join(d, "license-compliance-report.md")).read()
            self.assertIn("not legal advice", md.lower())
            self.assertIn("| Item |", md)
            data = json.load(open(os.path.join(d, "license-compliance-findings.json")))
            self.assertEqual(len(data["findings"]), 2)

    def test_reconciliation_table_has_evidence_column(self):
        md = rr.markdown_report(DOC)
        self.assertIn("Evidence", md)
        self.assertIn("no OFL.txt beside font", md)

    def test_has_executive_summary_section(self):
        md = rr.markdown_report(DOC)
        self.assertIn("## Executive summary", md)

    def test_disclaimer_is_last_section(self):
        md = rr.markdown_report(DOC)
        sections = [line for line in md.splitlines() if line.startswith("## ")]
        self.assertEqual(sections[-1], "## Disclaimer")
        self.assertIn("not legal advice", md.lower())


if __name__ == "__main__":
    unittest.main()
