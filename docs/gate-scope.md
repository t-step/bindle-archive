# Gate scope — what each check actually scans

Bindle's gates disagree with each other about what "the code" is. `make check`
reads git's *tracked* set, the pre-commit hooks read the *index*, `gitleaks
--history` reads *commits*, and your editor reads the *working tree*. Almost
every surprise below is that disagreement showing up as a green run that meant
nothing, or a red one that arrived a step later than expected.

[CONTRIBUTING.md](../CONTRIBUTING.md) says *which* gates make up the gate of
record and in what order to run them. This doc is the companion: what each one
can and cannot see, what it costs you when it can't, and the rules for adding a
new one. The capability ledger's own rules live in
[capability-inventory.md](capability-inventory.md).

## The four scopes

| Gate | Reads | Blind to |
|---|---|---|
| `make check` (`bin/check.sh`) | git-tracked files (`git ls-files`) | untracked files |
| pre-commit hooks | the staged content of this commit | unstaged working-tree edits |
| `bin/check-gitleaks.sh --staged` (pre-commit) | staged content | anything unstaged or untracked |
| `bin/check-gitleaks.sh --history` (`make check`) | every commit | staged content — not a commit yet |
| `bin/run-test-suites.sh` (`make test`, pre-commit) | tracked `bin/test-*.sh` | a new suite you haven't `git add`ed |
| `bin/check-inventory.py` (`make check`) | tracked `bin/**` `.sh`/`.py` + `docs/**/*.md` | untracked new files |

Two consequences are worth stating outright.

**A tracked-only gate is green *before* `git add` and red *after*.** A
pre-`git add` clean run proves nothing about what the commit will contain. This
shipped three home-path hits into `main` (PR #345): slice C1 scanned clean
pre-commit because `gitleaks git .` skips untracked files entirely, while
`make check`'s private-info scan — same blind spot — fired at commit time on
the same files once they were staged. Stage first, then scan.

**Neither gitleaks mode alone is the gate.** A history scan cannot see staged
content, and a staged scan cannot see history; that is why both call sites
exist (#354).

### Scope is disclosed — read the banner

`make check`, `bin/check-private-info.sh` and `bin/check-gitleaks.sh` all
report their *scope*, not just a verdict (#347, #354): a scanned count, plus a
`PARTIAL:` banner naming the files they skipped. A green run with no banner
really is whole-tree. A missing `gitleaks` binary prints `NOT RUN` and exits 0
— which is a pass, and says so.

`gitleaks` has no equivalent of the inline `private-ok` marker that
`bin/check-private-info.sh` honors. A fixture that needs one needs a
`.gitleaks.toml` path allowlist too.

## Four ways to get a green that means nothing

1. **`make check` passed on a file it never read.** It scans tracked files
   only, so a newly created but unstaged file passes `make check` and then
   fails pre-commit (which scans staged content). This happened to a plan doc:
   green while untracked, then red on private-info paths *and* link resolution
   (#55).
2. **`make check` passed and the commit still failed.** `make check` does not
   run the discovered `bin/test-*.sh` suites — only `make test` and the
   `bindle-test-suites` pre-commit hook do. A new `check.sh` section once
   passed `make check` while `bin/test-check-frontmatter.sh` was red. Run
   `bin/run-test-suites.sh` before believing "green".
3. **"all N suites pass" — and yours wasn't one of the N.**
   `bin/run-test-suites.sh` discovers suites via `git ls-files`, so a newly
   created but untracked `bin/test-*.sh` is silently not discovered, and the
   run still reports every suite passing. Measured once at 29 suite files on
   disk, 28 discovered, fully green. `git add` a new suite before trusting
   either the count or the green.
4. **The secret scan was clean about a file it never opened** — see the
   tracked-only rule above.

## Reading a red run

`bin/run-test-suites.sh` prints a failing suite's captured output, attributed
per suite (#470, PR #484). The output is bounded at 40 lines
(`BINDLE_TEST_LOG_LINES`) and the bound is *disclosed*, including the withheld
count; every failing log is copied to a directory that outlives the runner's
`EXIT` trap, and the path is printed. An empty log is reported as empty.

Do not re-run a red suite to find out why it failed. Read the output the runner
already gave you — for a flake, that is the only copy you will get.

## Commit-time mechanics

- **A deliberately-failing suite cannot be committed.** `git commit` runs the
  discovered-suite hook, so a RED suite blocks its own commit. RED is a
  recorded *run*, not a commit: write the suite, run it, record which
  assertions failed, then commit the suite and its implementation together.
  The two ways around it — weakening the suite, `--no-verify` — are both wrong.
  Worked examples: `bin/check-gitleaks.sh` (#354),
  `bin/check-pressure-series.sh` (#467).
- **A new `global/hooks/*.py` needs `chmod +x` before it will commit.** The
  `check-shebang-scripts-are-executable` hook blocks a file that has a shebang
  and no exec bit. Every hook already in that directory is executable; a
  freshly written one is not.
- **Format bash with `shfmt -i 2 -ci -w`.** Bare `shfmt -w` uses different
  defaults and still fails the gate — the managed hook runs `-i 2 -ci -d`.
- **A new `##` heading in a `skills/*/PRESSURE-TESTS.md` fails the series-field
  gate** unless the section declares `**Model:**`, `**Content:**` and
  `**Protocol:**` — including a section that records no reps at all (#467,
  #356). The escape is `<!-- not-a-series: reason -->`, and it must sit **on
  the heading line itself**: the check tests the grep hit line, not the line
  below it. First used in the repo by #465. See
  [pressure-testing-protocol.md](pressure-testing-protocol.md).

## Adding or changing a gate

**Guard every bash array expansion.** Write
`[ "${#arr[@]}" -gt 0 ]` before `for x in "${arr[@]}"`. Under bash 3.2 — the
macOS version `bin/check.sh` must run under — `"${arr[@]}"` on an *empty* array
is unbound under `set -u` and aborts the whole run. `PATH_REF_ALLOW` already
carried this guard; a new allowlist copied its shape but not its guard and
crashed `check.sh` the moment the list was emptied (#295).

**Expect SC2329 on dispatcher-invoked helpers.** shellcheck's "function never
invoked" fires on test-suite helpers called indirectly by name (`check "$desc"
contains …`), failing `make check`. House precedent is an inline
`# shellcheck disable=SC2329 # invoked indirectly, by name, via <dispatcher>`
— see `bin/doctor.sh` and `bin/install.sh`.

**Check who copies `check.sh` into a fixture repo before requiring a file to
exist.** `bin/test-check.sh` and `bin/test-check-frontmatter.sh` build minimal
throwaway repos; a new existence requirement fails their clean-exit regression
floors and couples every fixture builder to that file. Prefer skipping on
absence when another gate already owns existence (`capabilities.json`'s
`related_docs` → `bin/check-inventory.py`).

**A hook without `pass_filenames: false` receives every tracked matching
file** under `pre-commit run --all-files`, not just staged content. Before
believing a "this hook never scans X" claim, read that hook's own registration
in `.pre-commit-config.yaml` — not `check.sh`'s internals. That reading
disproved #279.

**A hook whose *test code* needs a runtime dependency uses `language: python`
plus `additional_dependencies`.** Most `bin/test-*.sh` hooks are
`language: script`; `bindle-test-suites` is not, because a discovered suite
(`bin/test-context-graph-schema.sh`) imports `jsonschema` and pre-commit only
provisions it for a python hook. This makes the dependency actually get
exercised under pre-commit's isolated venv even when a bare local `make test`
skips those tests because the developer's interpreter lacks the package.
Verify by running the single hook with `--verbose` and confirming the gated
tests report `ok`, not `skipped`.

**A new module emitting `E_*` finding codes fails
`bin/test-check-finding-codes.sh`** until every code is either classified in
`schemas/<surface>/v1/invariant-coverage.json` (`schema-and-native` when a JSON
Schema can express it, `native-only` when only the native validator can) or
listed in `excluded_codes` *with a reason*. It fired once on six new codes: two
index-node invariants classified, four `E_ARCH_APPLY_*` run outcomes excluded
because they report a run rather than a document. `make check` runs the gate
too, but `bin/run-test-suites.sh` reaches it first.

## Two gates that read more than you'd guess

**The link checker greps every markdown link target in a file, including
targets inside fenced code blocks**, and resolves each one relative to that
file's own directory (#55). It has no idea a fence is a fence. So an *example*
link in a plan or spec whose directory differs from the target trips
`make check`: a doc under `docs/plans/` illustrating a link to
`provider-interop.md` sends the checker looking for
`docs/plans/provider-interop.md`.

This paragraph tripped it while being written — the first draft quoted the
bracket-paren pattern inline, and the checker dutifully tried to resolve the
ellipsis inside it. For a cross-doc reference inside a body, name the file in
inline code (`provider-interop.md`, § "…") or use a repo-absolute `/docs/…`
link, and don't write a literal example link at all.

**The "Bindle-root path refs" check reads only the installed instruction
assets** — `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md`, frontmatter
skipped. Inside those, a bare `bin/<script>.sh` in an inline-code span fails:
installed assets run from the cwd of whatever project you are in, not from the
Bindle checkout, so a bare repo-relative path misresolves there (#113).
Qualify it as `<bindle>/bin/<script>.sh`, or add a commented `PATH_REF_ALLOW`
entry for a purely descriptive mention. Ordinary docs — including this one —
are outside the check's scope and may name scripts bare.
