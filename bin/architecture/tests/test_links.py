"""Tests for architecture.links — external-link allowlisting and preview
(#230 slice D2, epic #141 R5/FC-7).

The allowlist is CALLER-SUPPLIED and defaults to empty: `config.json` is
child B's frozen contract and cannot carry a D-owned policy key, so where
the list is stored is D3's call, not this slice's.

Two invariants carry the weight and both are easy to write vacuously:

- A DENIED LINK MUST NOT REMAIN CLICKABLE. Asserting the output merely
  lacks `](` also passes an implementation that emits a bare `<url>`
  autolink, which most Markdown renderers turn back into a link. Every
  denial test below therefore asserts the code-span form POSITIVELY.
- ALLOWED AND DENIED OUTPUT MUST DIFFER. A test that only checks the URL
  appears somewhere passes against an implementation that renders the two
  identically, so the pair is asserted as non-equal bytes.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from architecture import links

ALLOW = frozenset(["github.com"])


class IsAllowedTests(unittest.TestCase):
    def test_https_url_on_an_allowlisted_host_is_allowed(self):
        self.assertTrue(links.is_allowed("https://github.com/a/b", ALLOW))

    def test_host_not_on_the_allowlist_is_denied(self):
        self.assertFalse(links.is_allowed("https://evil.com/a", ALLOW))

    def test_empty_allowlist_denies_everything(self):
        self.assertFalse(links.is_allowed("https://github.com/a/b", frozenset()))

    def test_allowlist_defaults_to_empty(self):
        self.assertFalse(links.is_allowed("https://github.com/a/b"))

    def test_host_comparison_is_case_insensitive(self):
        self.assertTrue(links.is_allowed("https://GitHub.COM/a/b", ALLOW))

    def test_allowlist_entry_is_case_folded_too(self):
        """Folding only the URL leaves an uppercase ENTRY matching nothing."""
        self.assertTrue(
            links.is_allowed("https://github.com/a", frozenset(["GitHub.COM"])))

    def test_allowlist_entry_surrounding_whitespace_is_ignored(self):
        self.assertTrue(
            links.is_allowed("https://github.com/a", frozenset([" github.com "])))

    def test_http_is_denied_even_on_an_allowlisted_host(self):
        self.assertFalse(links.is_allowed("http://github.com/a/b", ALLOW))

    def test_non_http_schemes_are_denied(self):
        for url in ("javascript:alert(1)", "data:text/html,x",
                    "file:///etc/passwd", "ftp://github.com/a"):
            self.assertFalse(links.is_allowed(url, ALLOW), url)

    def test_protocol_relative_url_is_denied(self):
        self.assertFalse(links.is_allowed("//github.com/a/b", ALLOW))

    def test_userinfo_is_denied_even_when_the_host_is_allowlisted(self):
        """`https://evil.com@github.com/x` reads as evil.com to a human."""
        self.assertFalse(links.is_allowed("https://evil.com@github.com/x", ALLOW))

    def test_a_host_merely_ending_in_an_allowlisted_name_is_denied(self):
        self.assertFalse(links.is_allowed("https://notgithub.com/a", ALLOW))
        self.assertFalse(links.is_allowed("https://github.com.evil.com/a", ALLOW))

    def test_subdomains_are_not_implied_by_the_parent_host(self):
        self.assertFalse(links.is_allowed("https://docs.github.com/a", ALLOW))

    def test_explicit_port_is_denied(self):
        self.assertFalse(links.is_allowed("https://github.com:8443/a", ALLOW))

    def test_trailing_dot_host_is_denied(self):
        self.assertFalse(links.is_allowed("https://github.com./a", ALLOW))

    def test_allowlist_entry_carrying_a_port_matches_nothing(self):
        """The entry is malformed policy — it must not legalize the port."""
        allow = frozenset(["github.com:8443"])
        self.assertFalse(links.is_allowed("https://github.com:8443/a", allow))
        self.assertFalse(links.is_allowed("https://github.com/a", allow))

    def test_allowlist_entry_carrying_userinfo_matches_nothing(self):
        allow = frozenset(["evil.com@github.com"])
        self.assertFalse(links.is_allowed("https://evil.com@github.com/a", allow))
        self.assertFalse(links.is_allowed("https://github.com/a", allow))

    def test_allowlist_entry_with_a_trailing_dot_matches_nothing(self):
        allow = frozenset(["github.com."])
        self.assertFalse(links.is_allowed("https://github.com./a", allow))
        self.assertFalse(links.is_allowed("https://github.com/a", allow))

    def test_a_malformed_entry_does_not_disable_the_valid_ones(self):
        allow = frozenset(["github.com:8443", "github.com"])
        self.assertTrue(links.is_allowed("https://github.com/a", allow))
        self.assertFalse(links.is_allowed("https://github.com:8443/a", allow))

    def test_malformed_input_is_denied_rather_than_raising(self):
        for url in (None, 3, "", "   ", "https://", "https:// github.com/a"):
            self.assertFalse(links.is_allowed(url, ALLOW), repr(url))


class RenderLinkTests(unittest.TestCase):
    def test_allowed_link_renders_with_the_destination_previewed(self):
        self.assertEqual(
            links.render_link("Repo", "https://github.com/a/b", ALLOW),
            "[Repo](https://github.com/a/b) — <https://github.com/a/b>")

    def test_denied_link_renders_the_url_in_a_code_span(self):
        """A code span is inert — it cannot autolink and cannot be clicked."""
        self.assertEqual(
            links.render_link("Repo", "https://evil.com/a", ALLOW),
            "Repo — `https://evil.com/a`")

    def test_denied_output_contains_no_markdown_link_syntax(self):
        out = links.render_link("Repo", "https://evil.com/a", ALLOW)
        self.assertNotIn("](", out)

    def test_denied_output_contains_no_autolink_brackets(self):
        out = links.render_link("Repo", "https://evil.com/a", ALLOW)
        self.assertNotIn("<https", out)

    def test_allowed_and_denied_output_differ(self):
        url = "https://github.com/a/b"
        self.assertNotEqual(
            links.render_link("Repo", url, ALLOW),
            links.render_link("Repo", url, frozenset()))

    def test_url_containing_a_closing_paren_is_denied(self):
        """It would otherwise terminate the Markdown destination early."""
        out = links.render_link("Repo", "https://github.com/a(b)c", ALLOW)
        self.assertNotIn("](", out)

    def test_url_containing_whitespace_is_denied(self):
        out = links.render_link("Repo", "https://github.com/a b", ALLOW)
        self.assertNotIn("](", out)

    def test_backtick_in_a_denied_url_cannot_close_the_code_span(self):
        """The fence must outgrow the longest backtick run inside the URL.

        Asserted as exact bytes: the single-fenced form is a SUBSTRING of
        the correct double-fenced one, so assertNotIn passes against both.
        """
        out = links.render_link("Repo", "https://evil.com/`x", ALLOW)
        self.assertEqual(out, "Repo — ``https://evil.com/`x``")

    def test_url_that_starts_with_a_backtick_is_padded_inside_the_span(self):
        out = links.render_link("Repo", "`x", ALLOW)
        self.assertEqual(out, "Repo — `` `x ``")

    def test_link_text_bracket_is_escaped(self):
        out = links.render_link("Re]po", "https://github.com/a", ALLOW)
        self.assertIn("Re\\]po", out)

    def test_newline_in_link_text_is_rejected(self):
        with self.assertRaises(links.LinkRenderError):
            links.render_link("Re\npo", "https://github.com/a", ALLOW)

    def test_empty_link_text_is_rejected(self):
        with self.assertRaises(links.LinkRenderError):
            links.render_link("", "https://github.com/a", ALLOW)

    def test_non_string_link_text_is_rejected(self):
        with self.assertRaises(links.LinkRenderError):
            links.render_link(None, "https://github.com/a", ALLOW)

    def test_rendering_is_deterministic_for_identical_input(self):
        a = links.render_link("Repo", "https://github.com/a", ALLOW)
        b = links.render_link("Repo", "https://github.com/a", ALLOW)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
