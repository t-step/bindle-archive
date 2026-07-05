import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import detect_tools  # noqa: E402


class DetectToolsTest(unittest.TestCase):
    def test_reports_available_and_missing_with_hints(self):
        fake = {"scancode", "npm"}
        which = lambda name: "/usr/bin/" + name if name in fake else None
        out = detect_tools.detect(which=which)
        self.assertTrue(out["tools"]["scancode"]["available"])
        self.assertIn("install_hint", out["tools"]["scancode"])
        self.assertFalse(out["tools"]["reuse"]["available"])
        self.assertTrue(out["package_managers"]["npm"])
        self.assertFalse(out["package_managers"]["cargo"])

    def test_never_claims_missing_tool_available(self):
        out = detect_tools.detect(which=lambda name: None)
        self.assertFalse(any(t["available"] for t in out["tools"].values()))


if __name__ == "__main__":
    unittest.main()
