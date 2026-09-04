# Repository health

Last verified: 2026-09-04 against baseline `3b314c3d85f02315de7666d8c6542b568190c6e6`.

`tools/repo_health.py` is a read-only, deterministic comparison of tracked
paths and current documentation links. It emits concise terminal output by
default and a sorted JSON report with `--json`.

The hard-failure policy is deliberately narrow. It fails for tracked paths
new since the baseline that classify as generated/build output or dated
per-session files under `docs/knowledge-base/decision-log/`; it also fails for
any broken local link in current documentation. Existing paths are never
deleted or rewritten by the checker. Active Markdown byte growth,
`apps/one_combat.cpp` byte growth, and new root-level `.py`/`.sh` files are
warnings only.

Classification is path-based and stable: build-like directories and compiled
extensions are generated/build output; dated decision-log paths are explicit
policy locations. External URLs, anchors, and absolute links are
not checked. Local links are resolved relative to their source document and
must name a tracked or existing path.

## Inventory snapshot

The static inventory snapshot is [repo-health-baseline.json](repo-health-baseline.json).
It contains only `schema_version`, `source_commit`, and metric values generated
by the current definitions; it is reference evidence, not a CLI report or CI
comparison source. CI compares the candidate with the event base commit passed
to the CLI. Generate a CLI report for inspection with:

```sh
python3 tools/repo_health.py --json --baseline "$BASE"
```

Each hard-failure category maps directly to a requested growth boundary, while
the three size/ergonomics signals remain warnings. The checker reads Git's
tracked path set and never scans ignored build or self-play data.
