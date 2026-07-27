#!/usr/bin/env bash
#
# run-test-suites.sh — discover and run every bin/test-*.sh suite.
#
# Convention, not configuration: any tracked bin/test-<name>.sh is a suite and
# runs automatically. Nothing needs registering in the Makefile or in
# .pre-commit-config.yaml, so a new suite cannot be written and then silently
# left out of the gate — which is exactly how eleven of them drifted out of
# commit-time coverage (#256, #257).
#
# Suites run in parallel, capped at BINDLE_TEST_JOBS (default: detected core
# count, capped at 8). Must stay bash-3.2-compatible (macOS system bash) — no
# `wait -n` (bash 4.3+) and no associative arrays — so concurrency is done in
# fixed-size batches: launch up to the job cap in the background, `wait` for
# that batch, then launch the next. A slow suite can only stall its own batch,
# not the whole run.
#
# Usage:
#   bin/run-test-suites.sh          # run every discovered suite
#   bin/run-test-suites.sh --list   # print the discovered suites, run nothing
#
# Exits non-zero if any suite fails, after running them all — one red suite
# should not hide the next.
#
set -uo pipefail # not -e: run every suite, then fail once

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

suites=()
while IFS= read -r f; do
  [ -n "$f" ] || continue
  suites+=("$f")
done < <(git ls-files 'bin/test-*.sh' | sort)

if [ "${1:-}" = "--list" ]; then
  printf '%s\n' "${suites[@]}"
  exit 0
fi

if [ "${#suites[@]}" -eq 0 ]; then
  echo "test suites: none discovered (expected bin/test-*.sh)" >&2
  exit 1
fi

echo "test suites: ${#suites[@]} discovered"

if [ -n "${BINDLE_TEST_JOBS:-}" ]; then
  jobs="$BINDLE_TEST_JOBS"
elif command -v nproc >/dev/null 2>&1; then
  jobs="$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
  jobs="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
else
  jobs=4
fi
[ "$jobs" -ge 1 ] 2>/dev/null || jobs=4
[ "$jobs" -le 8 ] 2>/dev/null || jobs=8

workdir="$(mktemp -d "${TMPDIR:-/tmp}/bindle-test-suites.XXXXXX")"
trap 'rm -rf "$workdir"' EXIT

run_one() {
  local suite="$1" idx="$2"
  local start end
  start="$(date +%s)"
  if [ ! -x "$suite" ]; then
    echo "not-executable" >"$workdir/$idx.status"
  elif "$suite" >"$workdir/$idx.log" 2>&1; then
    echo "pass" >"$workdir/$idx.status"
  else
    echo "fail" >"$workdir/$idx.status"
  fi
  end="$(date +%s)"
  echo $((end - start)) >"$workdir/$idx.elapsed"
}

run_start="$(date +%s)"
n="${#suites[@]}"
i=0
while [ "$i" -lt "$n" ]; do
  batch=()
  count=0
  while [ "$i" -lt "$n" ] && [ "$count" -lt "$jobs" ]; do
    batch+=("$i")
    i=$((i + 1))
    count=$((count + 1))
  done
  for idx in "${batch[@]}"; do
    run_one "${suites[$idx]}" "$idx" &
  done
  wait
done
run_total=$(($(date +%s) - run_start))

failed=()
failed_idx=()
i=0
while [ "$i" -lt "$n" ]; do
  s="${suites[$i]}"
  status="$(cat "$workdir/$i.status" 2>/dev/null || echo fail)"
  elapsed="$(cat "$workdir/$i.elapsed" 2>/dev/null || echo '?')"
  case "$status" in
    pass)
      printf '  ✓ %s (%ss)\n' "$s" "$elapsed"
      ;;
    not-executable)
      printf '  ✗ %s (not executable)\n' "$s"
      failed+=("$s")
      failed_idx+=("$i")
      ;;
    *)
      printf '  ✗ %s (%ss)\n' "$s" "$elapsed"
      failed+=("$s")
      failed_idx+=("$i")
      ;;
  esac
  i=$((i + 1))
done

echo
printf '  total: %ss wall (%d suites, %d parallel)\n' "$run_total" "$n" "$jobs"
echo
if [ "${#failed[@]}" -eq 0 ]; then
  printf '  ✓ all %d suites pass\n' "$n"
  exit 0
fi
printf '  %d of %d suites FAILED:\n' "${#failed[@]}" "$n"
printf '    %s\n' "${failed[@]}"
echo

# Print each failing suite's captured output (#470). Until this existed the
# runner captured every suite's output to "$workdir/$idx.log", printed only the
# NAMES, and deleted the workdir in its EXIT trap — so a red run's sole artifact
# was a name plus "re-run it directly". For a flake that hint is worse than
# nothing: re-running directly is exactly what makes the evidence disappear
# (observed 2026-07-26 — test-package-release-integrity.sh failed once inside a
# batch and passed twice immediately afterwards on identical content, and the
# failure itself was never seen).
#
# Bounded, and the bound is DISCLOSED rather than silent: a long log prints its
# tail and says how much it withheld, and every failing log is copied somewhere
# that outlives the EXIT trap so the full text is still readable.
log_lines="${BINDLE_TEST_LOG_LINES:-40}"
keep=""
for idx in "${failed_idx[@]}"; do
  s="${suites[$idx]}"
  log="$workdir/$idx.log"
  printf '  ── output: %s ──\n' "$s"
  if [ ! -f "$log" ]; then
    printf '    (no output captured — the suite was never executed)\n'
  elif [ ! -s "$log" ]; then
    printf '    (no output — the suite failed silently)\n'
  else
    [ -n "$keep" ] || keep="$(mktemp -d "${TMPDIR:-/tmp}/bindle-test-failures.XXXXXX")"
    dest="$keep/$(basename "$s" .sh).log"
    cp "$log" "$dest"
    total="$(wc -l <"$log" | tr -d ' ')"
    if [ "$total" -gt "$log_lines" ] 2>/dev/null; then
      printf '    (showing the last %s of %s lines — full log: %s)\n' \
        "$log_lines" "$total" "$dest"
    fi
    tail -n "$log_lines" "$log" | sed 's/^/    /'
  fi
  printf '  ── end: %s ──\n\n' "$s"
done

if [ -n "$keep" ]; then
  printf '  failing logs kept: %s\n' "$keep"
  echo
fi
exit 1
