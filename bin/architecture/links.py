"""architecture.links — external-link allowlisting and preview at render
(#230 slice D2, epic #141 R5 / FC-7).

D owns external links AT RENDER. The allowlist is CALLER-SUPPLIED and
defaults to empty, so nothing external is clickable until an operator says
otherwise: `config.json` is child B's frozen contract (epic §B Frozen) and
cannot carry a D-owned policy key, which makes the storage location D3's
call rather than this slice's.

Two rendered forms, and the difference between them is the whole point:

    allowed  ->  [Repo](https://github.com/a/b) — <https://github.com/a/b>
    denied   ->  Repo — `https://github.com/a/b`

The denied form is a CODE SPAN, not bare text. A bare URL — and an
autolink `<url>` especially — is turned back into a clickable link by most
Markdown renderers, so "degrade to plain text" implemented naively would
still ship the clickable link it meant to withhold. A code span is inert.
The allowed form previews the destination beside the link so a reader can
see where it goes without trusting the link text.

Allowlisting is deliberately strict, because every relaxation here is a
way to make a hostile URL read as a friendly one:

- https only. http is downgradeable in transit.
- EXACT match on the whole netloc, case-folded. A parent host does NOT
  imply its subdomains, and `notgithub.com` / `github.com.evil.com` merely
  end in or begin with an allowlisted name. Because the comparison is
  against the entire netloc, a URL carrying userinfo, a port, or a
  trailing dot (`evil.com@github.com`, `github.com:8443`, `github.com.`)
  already compares unequal to a plain allowlisted host — no separate
  rejection rule is needed, and one that looked like it was doing the work
  here was dead code (mutation testing caught it).
- The ALLOWLIST ENTRIES are where those forms are policed instead: an
  entry carrying userinfo, a port, or a trailing dot is dropped, so a
  malformed entry can never legalize the form it names.
- No whitespace, parentheses, or angle brackets in the URL: those break
  out of Markdown's link destination syntax.

A URL that fails any rule is not an error — it renders in the denied form.
Only a malformed CALL (bad link text, non-string URL) raises.
"""
try:
    from urllib.parse import urlsplit
except ImportError:  # pragma: no cover - Python 2 is not supported
    from urlparse import urlsplit

__all__ = ["LinkRenderError", "is_allowed", "render_link"]

ALLOWED_SCHEME = "https"

# Characters that terminate or escape a Markdown link destination.
_URL_FORBIDDEN = frozenset(' \t\n\r()<>"')


class LinkRenderError(Exception):
    """The CALL is malformed — not merely a link that fails the allowlist."""


def _normalized_allowlist(allowlist):
    """Case-fold the allowlist and DROP every malformed entry.

    An entry carrying userinfo, a port, or a trailing dot is malformed
    policy: it can only ever legalize a host form that reads as one host
    and resolves as another. Dropping the bad entry rather than rejecting
    the whole allowlist keeps one typo from silently disabling the rest.
    """
    clean = set()
    for entry in (allowlist or ()):
        if not isinstance(entry, str):
            continue
        host = entry.strip().lower()
        if not host or "@" in host or ":" in host or host.endswith("."):
            continue
        clean.add(host)
    return frozenset(clean)


def is_allowed(url, allowlist=()):
    """True only for an https URL whose exact host is on `allowlist`.

    Never raises: a malformed URL is simply not allowed.
    """
    if not isinstance(url, str) or not url.strip():
        return False
    if any(ch in _URL_FORBIDDEN for ch in url):
        return False

    try:
        parts = urlsplit(url)
    except ValueError:
        return False

    if parts.scheme.lower() != ALLOWED_SCHEME:
        return False

    host = parts.netloc.lower()
    if not host:
        return False

    return host in _normalized_allowlist(allowlist)


def _escape_text(text):
    out = text.replace("\\", "\\\\")
    for ch in "[]":
        out = out.replace(ch, "\\" + ch)
    return out


def _code_span(value):
    """Wrap `value` in a fence longer than its longest backtick run, so a
    backtick inside the URL cannot close the span early."""
    longest = 0
    run = 0
    for ch in value:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = " " if value.startswith("`") or value.endswith("`") else ""
    return "%s%s%s%s%s" % (fence, pad, value, pad, fence)


def render_link(text, url, allowlist=()):
    """Render one external link, allowlisted and previewed."""
    if not isinstance(text, str) or not text.strip():
        raise LinkRenderError("link text must be a non-empty string")
    if "\n" in text or "\r" in text:
        raise LinkRenderError("link text must not contain a line break")
    if not isinstance(url, str) or not url.strip():
        raise LinkRenderError("link url must be a non-empty string")

    label = _escape_text(text)
    if is_allowed(url, allowlist):
        return "[%s](%s) — <%s>" % (label, url, url)
    return "%s — %s" % (label, _code_span(url))
