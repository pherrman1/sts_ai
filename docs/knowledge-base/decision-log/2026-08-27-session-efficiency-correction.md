# 2026-08-27 — session-efficiency correction evidence

## Decision

Keep the checked-in Debug ccache preset's cross-worktree reuse claim and make
the benchmark canary require complete treatment and binary provenance.

## Evidence

- Two sibling worktrees were checked out at `d930c243a08bade8c165640e0cf6dca7ed5a2599`,
  each configured with `linux-gcc-debug-ccache` and separate build directories.
- After zeroing `$HOME/.cache/sts_ai/ccache` before the second build, the first
  `one_combat` build reported 61 cacheable calls, 0 hits, and 61 misses. The
  second reported 61 cacheable calls, 59 direct hits (96.72%), and 2 misses.
- The canary self-test now rejects missing or partial binary provenance, a
  wrong hash, omitted ascension/thread/fairPlay/searcher3 expectations,
  true/false mismatches, and an omitted Silver reuse-cap expectation.

## Status

Implemented on `chore/session-efficiency`; the guarded one-seed Silver
bestbench integration check passed against the built executable and its actual
SHA-256.
