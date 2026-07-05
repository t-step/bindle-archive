import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import issue_drafts as idr  # noqa: E402

DOC = {"findings": [
    {"item": "DemoSans", "type": "font", "path": "assets/fonts/DemoSans.ttf",
     "risk_level": "high", "unmet_obligation": "missing OFL.txt",
     "evidence": ["no OFL.txt"], "recommended_action": "add OFL.txt"},
    {"item": "left-pad", "type": "dependency", "path": "n/left-pad",
     "risk_level": "info", "unmet_obligation": "none"},
]}


class IssueDraftsTest(unittest.TestCase):
    def test_only_groups_critical_high(self):
        groups = idr.group(DOC["findings"])
        self.assertIn("font", groups)
        self.assertNotIn("dependency", groups)  # info excluded

    def test_writes_grouped_draft_with_required_sections(self):
        with tempfile.TemporaryDirectory() as d:
            paths = idr.write_drafts(DOC, out_dir=d)
            self.assertEqual(len(paths), 1)
            text = open(paths[0]).read()
            for section in ("Suggested labels", "Affected items", "Evidence",
                            "Recommended action", "Human-review boundary",
                            "Acceptance criteria"):
                self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
