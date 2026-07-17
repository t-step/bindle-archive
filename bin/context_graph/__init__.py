"""context_graph — the v1 provider-neutral context-graph interchange
contract (issue #180, epic #140). See docs/context-graph-schema.md for the
human-readable companion and docs/design/2026-07-16-context-graph-schema.md
for the frozen design record. Stdlib-only at runtime; no re-exports —
import explicit submodule paths (context_graph.ids, .relationships,
.canonical, .validation)."""

SCHEMA_VERSION = 1
