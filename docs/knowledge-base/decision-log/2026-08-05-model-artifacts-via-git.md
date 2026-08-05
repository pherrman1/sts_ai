# 2026-08-05 — deployable models tracked via git; trainer state stays ignored

**Date:** 2026-08-05. **Task:** enable model handoff between machines through
git instead of manual artifact sync.

## Decisions

1. **`selfplay/models/*.native` is now git-tracked.** `.gitignore` un-ignores
   the deployable native exports (tok net 792 KB, strategic 1.6 MB — far
   under GitHub's 100 MB hard limit) while `*_state.bin` (2.8–7.1 GB each),
   `.pt`/`.npz`/`.torchscript` checkpoints, buffers, and CSVs stay ignored.
   Precedent: `build/*.txt` trees are already tracked.
2. **A retrained artifact ships in the same commit as its sha256 + docs
   update.** The GPU agent's V4 retrain (issue 36) therefore arrives on
   other machines via `git pull`; benchmark reference hashes in
   `current-baselines.md` stay verifiable against the tree.
3. **Server sync stays scp-based** (`sts-test` is not a git sync point); the
   git path covers machine-to-machine handoff, not the GCP benchmark box.

## Rationale

- Measured sizes: `.native` 792K–1.6M, `.pt` ~817K; only `*_state.bin`
  (2.8–7.1 GB) and buffers exceed what git can or should carry
  (**Inference** — GitHub limits: 50 MB warning, 100 MB hard reject).
- The `.native` format is the deployed one (`one_combat` reads it); nothing
  on the inference path needs the ignored checkpoints.

## Alternatives considered

- **Track everything** (incl. `_state.bin`) — rejected: 77 GB, GitHub
  hard-rejects >100 MB, LFS free quota (1 GB) cannot hold them.
- **Keep all handoffs manual (scp)** — rejected: the user's machine-to-
  machine workflow needs pull-only replication; docs already reference
  artifact hashes that only exist on the producer machine.

## Evidence

- `.gitignore` (`selfplay/models/` + `!` re-include patterns);
  `git check-ignore` verified: `ooc_strategic_tok_final.native` NOT ignored,
  `*_state.bin` still ignored; `AGENTS.md` repository-map note.

## Status and follow-up

- **Closed.** The current `ooc_strategic_tok_final.native` and
  `ooc_strategic.native` are committed with this change; future retrains
  commit the new `.native` blob (same filename, new content) plus their
  sha256/docs updates.
- Watch: GitHub hard-rejects files >100 MB — if a future export grows past
  ~50 MB, revisit (LFS or split artifacts) before committing.
