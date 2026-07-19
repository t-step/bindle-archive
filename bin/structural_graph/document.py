"""structural_graph.document -- single-document load for the #227 interchange.

Runs a parsed document through a fixed pipeline and returns one explicit
state. The order is contractual: fail-closed precedes everything, because a
document from an unknown schema version cannot be meaningfully validated
against v1 rules and continuing would turn fail-closed into best-effort.

Load outcome and freshness are orthogonal. A stale document still loads --
FC-4 requires an outage to carry forward rather than delete -- so freshness
is a separate key, not a member of the status enum.

This module writes nothing. It reads the document and, when a checkout is
configured, git HEAD. No network access.
"""

import json
import os
import subprocess

from context_graph import ids
from structural_graph import coverage
from structural_graph import redaction
from structural_graph import schema
from structural_graph import validation


def _result(status, freshness, findings, facts):
    return {
        "status": status,
        "freshness": freshness,
        "findings": findings,
        "facts": facts,
    }


def _git_head(checkout):
    """Return HEAD at checkout, or None when it cannot be determined."""
    env = dict(os.environ)
    for var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR",
    ):
        env.pop(var, None)
    try:
        out = subprocess.check_output(
            ["git", "-C", checkout, "rev-parse", "HEAD"],
            env=env,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.decode("utf-8").strip()


def _find_binding(cfg, binding_id):
    for repo in (cfg or {}).get("repositories") or []:
        if repo.get("binding_id") == binding_id:
            return repo
    return None


def _anchor_findings(doc):
    """Findings for anchors that cannot be normalized within the root.

    Only reached after validate_document has returned no findings, so
    validation.py's root type check already guarantees doc["root"] is a
    string -- no `or ""` default needed (or safe) here. #227's review
    finding: that default used to fold every falsy root (0, False, [],
    {}, None) into the legal "" value before this check ran, hiding the
    malformed value from it.
    """
    out = []
    root = doc.get("root")
    if redaction.normalize_path(root, "") is None and root != "":
        out.append(
            validation.finding(
                "E_SG_UNNORMALIZABLE_ANCHOR",
                "document root is not a safe repository-relative path",
                None,
                "root",
            )
        )
        return out
    checks = (
        ("files", "path", "files[].path"),
        ("symbols", "path", "symbols[].path"),
    )
    for collection, key, field in checks:
        for index, item in enumerate(doc.get(collection) or []):
            if redaction.normalize_path(item.get(key), root) is None:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor is not a safe repository-relative path within root",
                        index,
                        field,
                    )
                )
    for index, entry in enumerate(doc.get("coverage") or []):
        prefix = entry.get("path_prefix")
        if prefix == root:
            continue
        if redaction.normalize_path(prefix, root) is None:
            out.append(
                validation.finding(
                    "E_SG_UNNORMALIZABLE_ANCHOR",
                    "coverage prefix is not a safe path within root",
                    index,
                    "coverage[].path_prefix",
                )
            )
    # Anchors are exempt from redaction -- rewriting a symbol id would break
    # the edges that reference it. So a non-path anchor carrying a secret has
    # no safe outcome and fails the document closed instead.
    for collection, key, field in (
        ("symbols", "id", "symbols[].id"),
        ("symbols", "name", "symbols[].name"),
    ):
        for index, item in enumerate(doc.get(collection) or []):
            scrubbed, names = redaction.redact(item.get(key))
            if names:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor matches a secret pattern and cannot be redacted",
                        index,
                        field,
                    )
                )
    for index, edge in enumerate(doc.get("edges") or []):
        for key in ("source", "target"):
            scrubbed, names = redaction.redact(edge.get(key))
            if names:
                out.append(
                    validation.finding(
                        "E_SG_UNNORMALIZABLE_ANCHOR",
                        "anchor matches a secret pattern and cannot be redacted",
                        index,
                        "edges[]." + key,
                    )
                )
    return out


def _redact_incidental(doc):
    """Return a copy of doc with every non-anchor string redacted."""
    def walk(node, path):
        if isinstance(node, dict):
            return dict((k, walk(v, path + [k])) for k, v in node.items())
        if isinstance(node, list):
            return [walk(v, path + ["[]"]) for v in node]
        if isinstance(node, str):
            field = ".".join(path).replace(".[]", "[]")
            if schema.is_anchor(field):
                return node
            scrubbed, _ = redaction.redact(node)
            return scrubbed
        return node

    return walk(doc, [])


def load_object(doc, cfg):
    """Load an already-parsed document. Returns a result dict."""
    # A non-dict document (list, int, string, None -- all legal JSON) must be
    # classified before the version gate runs: the gate has no schema_version
    # key to find on anything but a dict and would report a missing-version
    # finding, mislabeling a corrupt document as merely needing a migration.
    # validate_document already has the accurate finding for this shape.
    if not isinstance(doc, dict):
        return _result(
            "malformed", "freshness_unknown", validation.validate_document(doc), None
        )

    gate = validation.version_findings(doc)
    for found in gate:
        if found["code"] in (
            "E_SG_MISSING_SCHEMA_VERSION",
            "E_SG_UNSUPPORTED_SCHEMA_VERSION",
        ):
            return _result("unsupported_version", "freshness_unknown", [found], None)

    findings = validation.validate_document(doc)
    if findings:
        return _result("malformed", "freshness_unknown", findings, None)

    binding_id = doc.get("binding_id")
    try:
        parsed = ids.parse_typed_id(binding_id)
        shape_ok = parsed.get("type") == "repository_binding"
    except ids.MalformedIdError:
        shape_ok = False
    if not shape_ok:
        return _result(
            "malformed",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MALFORMED_BINDING_ID",
                    "binding_id is not a well-formed repository-binding id",
                    None,
                    "binding_id",
                )
            ],
            None,
        )

    repo = _find_binding(cfg, binding_id)
    if repo is None:
        return _result(
            "deconfigured",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_BINDING_NOT_CONFIGURED",
                    "binding_id is not among the project's configured bindings",
                    None,
                    "binding_id",
                )
            ],
            None,
        )

    # root: guaranteed a string by validate_document above, same as in
    # _anchor_findings -- no `or ""` default needed or safe here (#227).
    # capabilities/coverage: `or []` here is unreachable for malformed
    # input, not masking -- validate_document already returned malformed
    # above if either is present but not a list (or has a non-dict/
    # non-string element), so by this point each is a real list, and
    # `[] or []` is `[]` when the document legitimately declares none.
    tiling = coverage.tiling_findings(
        doc.get("root"), doc.get("capabilities") or [], doc.get("coverage") or []
    )
    if tiling:
        return _result("malformed", "freshness_unknown", tiling, None)

    anchors = _anchor_findings(doc)
    if anchors:
        return _result("malformed", "freshness_unknown", anchors, None)

    facts = _redact_incidental(doc)

    checkout = repo.get("local_checkout_path")
    if not checkout:
        freshness = "freshness_unknown"
    else:
        head = _git_head(checkout)
        if head is None:
            freshness = "freshness_unknown"
        elif head == doc.get("source_commit"):
            freshness = "current"
        else:
            freshness = "stale"

    return _result("loaded", freshness, [], facts)


def load(path, cfg):
    """Load a document from disk. Never writes."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except FileNotFoundError:
        return _result(
            "unavailable",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MISSING_FIELD", "document is not present", None, None
                )
            ],
            None,
        )
    except (ValueError, OSError):
        return _result(
            "malformed",
            "freshness_unknown",
            [
                validation.finding(
                    "E_SG_MISSING_FIELD", "document is not readable JSON", None, None
                )
            ],
            None,
        )
    return load_object(doc, cfg)
