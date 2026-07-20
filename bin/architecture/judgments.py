"""architecture.judgments — `judgments.jsonl`: appending a decision, the
identity-commit ordering, and reading the log back with its integrity
rules (issue #228, epic #141).

`context_graph.atomic_io.append_line_atomic` gives durability, not crash
atomicity: a SIGKILL or ENOSPC mid-write leaves a truncated trailing line.
#228 forbids recovering identity from `index.json` or from the notes, both
of which still hold the data, so the log itself must say what survived.
The frozen rules this module implements:

  * a torn TRAILING line is truncated-and-reported, never silently skipped
    — skipping it would drop every identity after the tear, re-minting
    duplicates or routing them to reconciliation;
  * corruption anywhere else HARD ABORTS: the sole authority for meaning is
    damaged and the run must not guess;
  * the log is append-only and never rewritten in place, so reading it is
    side-effect free. A torn tail is REPORTED with the byte offset it
    starts at; truncating is a writer's decision, not a reader's.

"Torn" is positional and byte-level: only the final line, and only when the
file does not end in a newline. An unterminated final line that parses,
validates and verifies is intact — a crash between `write` and the newline
is indistinguishable from a complete record, and the checksum is what says
which it was. Any defect on a newline-TERMINATED line is mid-file class,
including on the last one.

The write side lives here too, because it is the same contract seen from
the other end: `append_judgment` refuses anything `load_judgments` would
hard-abort on, and `commit_identity_then` is the ordering primitive that
makes "the identity commit precedes any file write" a property of the code
rather than of each caller's discipline.
"""
import json
import os

from architecture import canonical
from architecture.state import (
    ArchStateError,
    ProjectIdMismatchError,
    validate_judgment,
)
from context_graph import atomic_io


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


class JudgmentsCorruptError(ArchStateError):
    """The judgments log is damaged somewhere other than its trailing line.

    Raises rather than returning findings, for the same reason
    ProjectIdMismatchError does: a caller that ignored a return value would
    project against a log whose surviving records no longer mean what they
    say. `.findings` carries the structured detail for CLI rendering."""


def load_judgments(path, project_id):
    """Read the log at `path`, asserting every record belongs to
    `project_id`. Returns

        {"records": [...],            # in FILE ORDER, the authority
         "findings": [...],           # non-fatal: torn tail, duplicates
         "truncated": bool,           # a torn trailing line was dropped
         "truncate_offset": int|None} # byte offset that torn line starts at

    A missing or empty file is a legitimate empty authority, not an error:
    a fresh project mints its first identity against one. Raises
    JudgmentsCorruptError for damage anywhere but the trailing line, and
    ProjectIdMismatchError for a record belonging to another project — the
    guarded scenario is a copied notes home."""
    text = _read(path)
    if not text:
        return _result([], [], False, None)

    lines, terminated = _split(text)
    records = []
    findings = []
    seen_record_ids = set()
    offset = 0

    for index, line in enumerate(lines):
        is_tail = index == len(lines) - 1 and not terminated
        if not line.strip():
            if _only_blanks_remain(lines, index) and terminated:
                break
            if is_tail:
                return _torn(records, findings, offset, index)
            raise JudgmentsCorruptError([_finding(
                "E_ARCH_JUDGMENTS_BLANK_LINE",
                "blank line at line %d: the log is machine-written, so a "
                "blank between records means a partial write" % (index + 1,),
                index=index)])

        record, defects = _parse(line, index)
        if defects:
            if is_tail:
                return _torn(records, findings, offset, index)
            raise JudgmentsCorruptError(defects)

        _require_project(record, project_id, index)

        record_id = record.get("record_id")
        if record_id in seen_record_ids:
            findings.append(_finding(
                "E_ARCH_JUDGMENTS_DUPLICATE_RECORD",
                "record_id %r appears more than once; a duplicated append "
                "folds to a no-op" % (record_id,),
                index=index, field="record_id"))
        seen_record_ids.add(record_id)
        records.append(record)

        if is_tail:
            findings.append(_finding(
                "E_ARCH_JUDGMENTS_UNTERMINATED_TAIL",
                "line %d has no trailing newline but is intact; a crash "
                "between the write and the newline left it complete"
                % (index + 1,),
                index=index))
        offset += len(line.encode("utf-8")) + 1

    return _result(records, findings, False, None)


def fold_judgments(records):
    """Fold records — in FILE ORDER — into

        {"by_arch_id":     {arch_id: [records, in file order]},
         "latest_by_kind": {arch_id: {kind: the last record of that kind}},
         "unkeyed":        [records naming no single node]}

    Last-write-wins is per (arch_id, kind), not per arch_id alone: the
    frozen rule is stated per arch_id, but a single winner per id would let
    a later `naming` record hide the `identity_allocation` that created it,
    and identity is exactly what the log exists to preserve. `decided_at`
    never participates — file order is the authority, so clock skew on a
    synced notes home cannot reorder meaning.

    Interprets nothing: which kinds make a node live, stale, or renamed is
    lifecycle, owned by #228's sibling child G. This only says which record
    of each class came last. An exact duplicate append is a no-op, as
    `canonical.stamp`'s idempotence intends."""
    by_arch_id = {}
    latest_by_kind = {}
    unkeyed = []
    seen_record_ids = set()

    for record in records:
        record_id = record.get("record_id")
        if record_id in seen_record_ids:
            continue
        seen_record_ids.add(record_id)

        arch_id = record.get("arch_id")
        if arch_id is None:
            unkeyed.append(record)
            continue
        by_arch_id.setdefault(arch_id, []).append(record)
        latest_by_kind.setdefault(arch_id, {})[record.get("kind")] = record

    return {"by_arch_id": by_arch_id, "latest_by_kind": latest_by_kind,
            "unkeyed": unkeyed}


def append_judgment(path, record):
    """Stamp `record` and append it as ONE line. Returns the stamped record.

    Refuses a record that would not read back: the log is the sole authority
    for meaning, and `load_judgments` hard-aborts on an invalid interior
    line, so writing one would poison every later read. Appending is the
    only mutation this surface has — the log is never compacted or
    rewritten in place."""
    stamped = canonical.stamp(record)
    findings = validate_judgment(stamped)
    if findings:
        raise JudgmentsCorruptError([_finding(
            "E_ARCH_JUDGMENTS_INVALID_RECORD",
            "refusing to append a record that would not read back",
        )] + list(findings))
    atomic_io.append_line_atomic(path, stamped)
    return stamped


def commit_identity_then(path, record, write):
    """Append the identity commit, and ONLY THEN call `write`.

    #228 freezes this ordering (mirroring `context_graph.review.py:202-204`,
    which allocates the id inside the judgment event). Either other ordering
    breaks a frozen invariant: appending AFTER the note writes leaves a
    crash with a written note whose identity was never recorded, forcing
    recovery to read arch_id back out of apply-state.json — making recovery
    metadata a semantic authority — or out of the note, which #228 forbids.
    With the identity committed first, a crash is always recoverable
    forward: the identity exists and a fresh re-plan re-renders it.

    `write` is the caller's write side (apply-state.json, the first note
    byte). It is invoked with no arguments and its return value is ignored;
    if the append fails it is never invoked at all."""
    stamped = append_judgment(path, record)
    write()
    return stamped


def _read(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _split(text):
    """Split into lines plus whether the file ends in a newline. The final
    element of a newline-terminated file's split is dropped: it is the
    terminator, not an empty line."""
    terminated = text.endswith("\n")
    lines = text.split("\n")
    if terminated:
        lines = lines[:-1]
    return lines, terminated


def _only_blanks_remain(lines, index):
    return all(not line.strip() for line in lines[index:])


def _parse(line, index):
    """Return (record, defects). A non-empty defects list means the line is
    corrupt; whether that aborts depends on where the line sits."""
    try:
        record = json.loads(line)
    except ValueError as exc:
        return None, [_finding(
            "E_ARCH_JUDGMENTS_UNPARSEABLE_LINE",
            "line %d is not valid JSON: %s" % (index + 1, exc),
            index=index)]
    record_findings = validate_judgment(record)
    if record_findings:
        defects = [_finding(
            "E_ARCH_JUDGMENTS_INVALID_RECORD",
            "line %d parses but is not a valid judgment record" % (index + 1,),
            index=index)]
        for finding in record_findings:
            defects.append(dict(finding, index=index))
        return None, defects
    return record, []


def _require_project(record, project_id, index):
    found = record.get("project_id")
    if found != project_id:
        raise ProjectIdMismatchError(
            found, project_id, "judgments.jsonl line %d" % (index + 1,))


def _torn(records, findings, offset, index):
    findings = findings + [_finding(
        "E_ARCH_JUDGMENTS_TORN_TAIL",
        "the trailing line (line %d) is torn and was not read; it starts at "
        "byte %d" % (index + 1, offset),
        index=index)]
    return _result(records, findings, True, offset)


def _result(records, findings, truncated, truncate_offset):
    return {"records": records, "findings": findings,
            "truncated": truncated, "truncate_offset": truncate_offset}
