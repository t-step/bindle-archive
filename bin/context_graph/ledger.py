"""context_graph.ledger — append-only judgments.jsonl persistence and the
effective-state reducer (issue #184). The ledger is never edited or truncated;
every write is one fsync'd line (design section 5). The reducer is pure over an
ordered event list plus an injected revalidation callback (no compiler import
here — orchestration in context_graph.review supplies the current graph)."""
import json
import os

from context_graph import atomic_io, config

JUDGMENTS_FILENAME = "judgments.jsonl"


class LedgerError(Exception):
    def __init__(self, message, findings=None):
        super().__init__(message)
        self.findings = findings or [{"code": "E_LEDGER", "message": message}]


def judgments_path(notes_home, slug):
    return os.path.join(config.context_dir(notes_home, slug), JUDGMENTS_FILENAME)


def load_judgments(path):
    """Return the ordered list of events. Missing file -> []. A malformed line
    raises LedgerError rather than being silently guessed past."""
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except ValueError as exc:
                raise LedgerError("malformed judgments.jsonl line %d: %s" % (lineno, exc))
    return events


def append_judgment(path, event):
    """Append one event as a single fsync'd JSONL line (append-only)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_io.append_line_atomic(path, event)


_DECISIONS = ("accepted", "rejected", "retired")


def reduce_judgments(events, revalidate=None):
    """Reduce an ordered append-only event list into effective state. Pure over
    (events, revalidate). See the reducer rules in the #184 plan / design
    section 11 and the binding amendment's reducer state machine."""
    effective = {}
    rejected_keys = set()
    retired_keys = set()
    findings = []

    for index, ev in enumerate(events):
        if not isinstance(ev, dict) or not all(
            k in ev for k in ("subject_type", "subject_key", "candidate_key", "decision")
        ) or ev["decision"] not in _DECISIONS:
            findings.append({"code": "E_JUDGMENT_MALFORMED",
                             "message": "event %d missing required fields or bad decision" % index,
                             "index": index})
            continue

        subject = ev["subject_key"]
        key = ev["candidate_key"]
        decision = ev["decision"]

        if decision == "accepted":
            if revalidate is not None and revalidate(ev) is False:
                findings.append({"code": "stale_illegal_judgment",
                                 "message": "accepted event %d endpoint no longer legal" % index,
                                 "index": index})
                # An illegal accepted event contributes no effective edge and
                # clears any prior effective acceptance for this subject.
                effective.pop(subject, None)
                continue
            effective[subject] = {"subject_type": ev["subject_type"],
                                  "candidate_key": key, "event": ev}
        elif decision == "rejected":
            rejected_keys.add(key)
            cur = effective.get(subject)
            if cur is not None and cur["candidate_key"] == key:
                effective.pop(subject, None)
        elif decision == "retired":
            retired_keys.add(key)
            cur = effective.get(subject)
            if cur is not None and cur["candidate_key"] == key:
                effective.pop(subject, None)

    return {"effective": effective, "rejected_keys": rejected_keys,
            "retired_keys": retired_keys, "findings": findings}
