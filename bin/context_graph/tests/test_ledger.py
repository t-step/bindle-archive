import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import ledger, config


class LedgerIO(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"
        config.init_project(self.notes_home, self.slug)
        self.path = ledger.judgments_path(self.notes_home, self.slug)

    def test_missing_file_reduces_to_empty(self):
        self.assertEqual(ledger.load_judgments(self.path), [])

    def test_append_then_load_roundtrip_preserves_order(self):
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 1})
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 2})
        loaded = ledger.load_judgments(self.path)
        self.assertEqual([e["n"] for e in loaded], [1, 2])

    def test_path_is_under_context_dir(self):
        self.assertTrue(self.path.endswith(os.path.join(".bindle", "context", "judgments.jsonl")))

    def test_malformed_line_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        with self.assertRaises(ledger.LedgerError):
            ledger.load_judgments(self.path)


def _ev(subject, key, decision, subject_type="edge"):
    e = {"schema_version": 1, "subject_type": subject_type, "subject_key": subject,
         "candidate_key": key, "decision": decision, "decided_at": "2026-07-17T00:00:00Z"}
    if subject_type == "identity_anchor":
        e["assigned_id"] = "context-node:bindle:" + "1" * 32
        e["entry_fingerprint"] = "sha256:" + "2" * 64
    return e


class ReduceJudgments(unittest.TestCase):
    def eff_key(self, state, subject):
        got = state["effective"].get(subject)
        return got["candidate_key"] if got else None

    def test_rejected_key_stays_suppressed_after_other_candidate_accepted(self):
        # A stays suppressed; B effective.
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "rejected"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)
        self.assertIn("candidate:sha256:" + "a" * 64, state["rejected_keys"])

    def test_accept_a_reject_b_a_remains_effective(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "rejected")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "a" * 64)

    def test_accept_a_accept_b_retire_a_b_remains(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "a" * 64, "retired")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)
        self.assertIn("candidate:sha256:" + "a" * 64, state["retired_keys"])

    def test_accept_a_retire_a_then_accept_changed_b(self):
        events = [_ev("S", "candidate:sha256:" + "a" * 64, "accepted"),
                  _ev("S", "candidate:sha256:" + "a" * 64, "retired"),
                  _ev("S", "candidate:sha256:" + "b" * 64, "accepted")]
        state = ledger.reduce_judgments(events)
        self.assertEqual(self.eff_key(state, "S"), "candidate:sha256:" + "b" * 64)

    def test_reject_of_effective_revokes_it(self):
        key = "candidate:sha256:" + "a" * 64
        events = [_ev("S", key, "accepted"), _ev("S", key, "rejected")]
        state = ledger.reduce_judgments(events)
        self.assertIsNone(self.eff_key(state, "S"))

    def test_malformed_event_reported_not_guessed(self):
        events = [{"schema_version": 1, "decision": "accepted"}]  # no subject_key
        state = ledger.reduce_judgments(events)
        self.assertIn("E_JUDGMENT_MALFORMED", [f["code"] for f in state["findings"]])
        self.assertEqual(state["effective"], {})
        self.assertEqual(state["rejected_keys"], set())

    def test_stale_illegal_accepted_event_not_effective(self):
        key = "candidate:sha256:" + "a" * 64
        events = [_ev("S", key, "accepted")]
        state = ledger.reduce_judgments(events, revalidate=lambda e: False)
        self.assertIsNone(self.eff_key(state, "S"))
        self.assertIn("stale_illegal_judgment", [f["code"] for f in state["findings"]])

    def test_stale_illegal_accept_clears_prior_effective_acceptance(self):
        # A accepted+effective, then B (same subject) is stale/illegal:
        # B is not installed AND it clears A's prior effective acceptance.
        a_key = "candidate:sha256:" + "a" * 64
        b_key = "candidate:sha256:" + "b" * 64
        events = [_ev("S", a_key, "accepted"), _ev("S", b_key, "accepted")]
        state = ledger.reduce_judgments(
            events, revalidate=lambda e: e["candidate_key"] != b_key)
        self.assertIsNone(state["effective"].get("S"))
        self.assertIn("stale_illegal_judgment", [f["code"] for f in state["findings"]])
