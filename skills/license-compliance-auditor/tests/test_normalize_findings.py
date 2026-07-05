import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import normalize_findings as nf  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_assigns_ids_and_defaults(self):
        out = nf.normalize({"findings": [{"item": "x", "type": "dependency"}]})
        f = out["findings"][0]
        self.assertEqual(f["id"], "F-0001")
        self.assertEqual(f["confidence"], "low")
        self.assertEqual(f["risk_level"], "medium")
        self.assertEqual(f["unmet_obligation"], "none")
        self.assertIn("not legal advice", out["disclaimer"])

    def test_canonicalizes_spdx_and_flags_ambiguous(self):
        self.assertEqual(nf.canonical_spdx("apache 2.0"), "Apache-2.0")
        self.assertIn("ambiguous", nf.canonical_spdx("BSD").lower())
        self.assertEqual(nf.canonical_spdx(None), "UNKNOWN")

    def test_evidence_scalar_becomes_list(self):
        out = nf.normalize({"findings": [{"item": "x", "evidence": "LICENSE"}]})
        self.assertEqual(out["findings"][0]["evidence"], ["LICENSE"])

    def test_never_invents_election_for_or_expression(self):
        out = nf.normalize({"findings": [
            {"item": "x", "license_expression": "MIT OR Apache-2.0"}]})
        self.assertEqual(out["findings"][0]["license_expression"],
                         "MIT OR Apache-2.0")


if __name__ == "__main__":
    unittest.main()
