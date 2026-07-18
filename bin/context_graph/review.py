"""context_graph.review -- orchestration for #184's propose/confirm/candidates.
Glues the #183 deterministic preview, proposal validation, and the append-only
ledger. `propose` writes nothing and never locks; `confirm` takes the
single-writer lock and appends exactly one judgment event."""
from context_graph import compiler, proposals


class ReviewError(Exception):
    """Raised only when the current graph itself cannot be compiled (missing
    or malformed #191 configuration, an unreadable map). `.findings` mirrors
    `compiler.CompilerError.findings` so the CLI can render it uniformly with
    every other findings-shaped error."""

    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = findings or [{"code": "E_REVIEW", "message": message}]


def _preview(notes_home, slug, repo_roots, github_adapter):
    try:
        return compiler.compile_preview(
            notes_home, slug, repo_roots=repo_roots, github_adapter=github_adapter)
    except compiler.CompilerError as exc:
        raise ReviewError("cannot compile current graph", findings=exc.findings) from exc


def propose(notes_home, slug, proposal, repo_roots=None, github_adapter=None):
    """Validate an edge proposal against a FRESH #183 preview. Returns
    {"candidate": dict|None, "subject_key": str|None, "findings": [dict]}.
    Writes nothing; takes no lock (design section 4, L266-272)."""
    preview = _preview(notes_home, slug, repo_roots, github_adapter)
    return proposals.validate_edge_proposal(proposal, preview)
