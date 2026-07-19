"""Unit tests for structural_graph.redaction."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import redaction


class TestNormalizePath(unittest.TestCase):
    def test_plain_relative_path_passes_through(self):
        self.assertEqual(redaction.normalize_path("src/app.py", ""), "src/app.py")

    def test_leading_dot_slash_is_stripped(self):
        self.assertEqual(redaction.normalize_path("./src/app.py", ""), "src/app.py")

    def test_backslashes_become_forward_slashes(self):
        self.assertEqual(redaction.normalize_path("src\\app.py", ""), "src/app.py")

    def test_absolute_path_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("/etc/passwd", ""))

    def test_windows_drive_path_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("C:/repo/app.py", ""))

    def test_traversal_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("src/../../secret", ""))

    def test_query_string_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("src/app.py?raw=1", ""))

    def test_tilde_user_path_is_unnormalizable(self):
        # "~jane/x" resolves outside the repository and carries a username.
        # Anchors are exempt from redaction, so accepting one would persist
        # that username in a fact nothing downstream rewrites.
        self.assertIsNone(redaction.normalize_path("~jane/secret.py", ""))

    def test_tilde_slash_path_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("~/secret.py", ""))

    def test_tilde_inside_a_path_is_still_fine(self):
        # Only a leading "~" is home-relative; one mid-path is an ordinary
        # (if unusual) filename character.
        self.assertEqual(
            redaction.normalize_path("src/a~b.py", ""), "src/a~b.py"
        )

    def test_empty_value_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("", ""))

    def test_path_inside_root_is_kept(self):
        self.assertEqual(
            redaction.normalize_path("pkg/src/app.py", "pkg"), "pkg/src/app.py"
        )

    def test_path_outside_root_is_unnormalizable(self):
        self.assertIsNone(redaction.normalize_path("other/app.py", "pkg"))

    def test_root_itself_is_normalizable(self):
        self.assertEqual(redaction.normalize_path("pkg", "pkg"), "pkg")

    def test_sibling_with_shared_prefix_is_not_inside_root(self):
        self.assertIsNone(redaction.normalize_path("pkgother/app.py", "pkg"))


class TestRedact(unittest.TestCase):
    def test_clean_string_is_unchanged_and_matches_nothing(self):
        scrubbed, names = redaction.redact("parsed 12 symbols in src/app.py")
        self.assertEqual(scrubbed, "parsed 12 symbols in src/app.py")
        self.assertEqual(names, ())

    def test_home_directory_path_is_redacted(self):
        scrubbed, names = redaction.redact(
            "failed to open " + "/Users" + "/jane/repo/app.py"
        )
        self.assertNotIn("jane", scrubbed)
        self.assertIn("home-path", names)
        self.assertIn("[redacted:home-path]", scrubbed)

    def test_bearer_token_is_redacted(self):
        scrubbed, names = redaction.redact("auth failed for ghp_" + "A" * 36)
        self.assertNotIn("ghp_" + "A" * 36, scrubbed)
        self.assertIn("token", names)

    def test_aws_key_is_redacted(self):
        scrubbed, names = redaction.redact("key AKIA" + "B" * 16)
        self.assertNotIn("AKIA" + "B" * 16, scrubbed)
        self.assertIn("token", names)

    def test_multiple_patterns_all_reported_sorted(self):
        scrubbed, names = redaction.redact(
            "/Users" + "/jane/x and sk-" + "C" * 32
        )
        self.assertEqual(names, ("home-path", "token"))
        self.assertNotIn("jane", scrubbed)

    def test_redaction_is_idempotent(self):
        once, _ = redaction.redact("/Users" + "/jane/x")
        twice, names = redaction.redact(once)
        self.assertEqual(once, twice)
        self.assertEqual(names, ())


class TestAbsolutePathRedaction(unittest.TestCase):
    """Any absolute path is redacted, not only home-shaped ones.

    An absolute path names a machine's layout whoever's it is: an internal
    project root leaks as surely as a home directory. Anchors already fail
    closed on absolute paths, so this rule governs incidental strings --
    the diagnostic and log lines a provider echoes into a document.
    """

    def test_generic_absolute_path_is_redacted(self):
        scrubbed, names = redaction.redact(
            "failed reading /opt/acme-internal/secret-project/x.py"
        )
        self.assertNotIn("acme-internal", scrubbed)
        self.assertNotIn("secret-project", scrubbed)
        self.assertEqual(names, ("absolute-path",))

    def test_single_segment_absolute_path_is_redacted(self):
        scrubbed, names = redaction.redact("wrote /etc")
        self.assertEqual(scrubbed, "wrote [redacted:absolute-path]")
        self.assertEqual(names, ("absolute-path",))

    def test_relative_path_is_left_alone(self):
        scrubbed, names = redaction.redact("parsed src/app.py and pkg/mod.py")
        self.assertEqual(scrubbed, "parsed src/app.py and pkg/mod.py")
        self.assertEqual(names, ())

    def test_home_path_rule_wins_over_the_general_rule(self):
        # Pattern order decides which name a match reports. The specific
        # home-path rule runs first, so a home path must not come back
        # labelled absolute-path.
        scrubbed, names = redaction.redact(
            "failed to open " + "/Users" + "/jane/repo/app.py"
        )
        self.assertEqual(names, ("home-path",))
        self.assertIn("[redacted:home-path]", scrubbed)
        self.assertNotIn("[redacted:absolute-path]", scrubbed)

    def test_linux_home_path_rule_also_wins(self):
        scrubbed, names = redaction.redact("cwd " + "/home" + "/jane/repo")
        self.assertEqual(names, ("home-path",))
        self.assertNotIn("[redacted:absolute-path]", scrubbed)

    def test_absolute_path_redaction_is_idempotent(self):
        once, _ = redaction.redact("reading /opt/acme/x.py")
        twice, names = redaction.redact(once)
        self.assertEqual(once, twice)
        self.assertEqual(names, ())

    def test_redacted_home_path_remainder_is_not_re_redacted(self):
        # The home rule replaces only its own prefix and leaves the rest of
        # the path in place. A second pass must not then match that
        # remainder, or redaction would stop being idempotent.
        once, _ = redaction.redact("/Users" + "/jane/repo/app.py")
        twice, names = redaction.redact(once)
        self.assertEqual(once, twice)
        self.assertEqual(names, ())


if __name__ == "__main__":
    unittest.main()
