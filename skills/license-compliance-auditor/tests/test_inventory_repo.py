import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import inventory_repo  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class InventoryTest(unittest.TestCase):
    def test_finds_license_and_manifest_in_mit_clean(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "mit-clean"))
        self.assertIn("LICENSE", inv["license_files"])
        self.assertIn("package.json", inv["manifests"])
        self.assertIn("npm", inv["ecosystems"])
        self.assertTrue(any(c["spdx"] == "MIT"
                            for c in inv["declared_license_candidates"]))

    def test_flags_spdx_header_mismatch(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "spdx-header-mismatch"))
        self.assertTrue(any(h["spdx"] == "GPL-3.0-only"
                            for h in inv["spdx_headers"]))

    def test_flags_vendored_dir(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "vendored-separate-license"))
        self.assertTrue(any("vendor" in v for v in inv["vendored_dirs"]))

    def test_flags_stackoverflow_provenance(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "so-snippet-no-date"))
        self.assertTrue(any("stackoverflow" in m["marker"].lower()
                            for m in inv["provenance_markers"]))

    def test_finds_font(self):
        inv = inventory_repo.inventory(os.path.join(FIX, "ofl-font-missing-text"))
        self.assertTrue(any(f["path"].endswith(".ttf") for f in inv["fonts"]))


if __name__ == "__main__":
    unittest.main()
