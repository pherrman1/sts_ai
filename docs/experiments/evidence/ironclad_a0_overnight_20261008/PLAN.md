# Ironclad A0 overnight campaign

Authorized execution of the supplied campaign charter and decision-audit addendum.
Objective: actual fair Ironclad Ascension-0 Act-3 victory, keys off.
Start: 2026-10-08 01:47 Europe/Berlin (2026-10-07 23:47 UTC).
Execution cap: 2026-10-08 09:47 Europe/Berlin. Confirmation/packaging reserve begins 07:23.

## Frozen campaign baseline

Fresh Codex-app-managed worktree `ironclad-overnight-20261008/sts_lightspeed`; branch `codex/ironclad-overnight-20261008`. Source `a4b3df35d170abba7860e8e854cc24cfd3579075`. Origin `git@github.com:pherrman1/sts_ai.git`. Pinned dependencies repaired through repository helper and verified. Two changes since charter reference are CTM research-candidate loading and declared HP domain; independently auditing their non-MCTS impact.

Bprod: V4 strategic live gates, MCTS off, learned stopping on, adaptive and exact-root off. Bflat: same OOC, learned stopping and adaptive off, exact 10,000 steps per searched root. Explicit fair mode, Act-3 cutoff, keys off, allocated reuse cap and controlled environment. No production defaults change.

## Resources and evidence

Ryzen 5 7500F: 6 cores / 12 threads; 31 GiB RAM, approximately 16 GiB available at launch. RTX 3060 Ti 8 GiB, approximately 6.5 GiB free, idle at launch. Four build jobs initially; one OpenMP/BLAS thread per game process. Worker count selected after canary throughput. One training job at most initially. Existing jobs and data are read-only.

Raw root: `build/overnight_20261008/` (ignored). Immutable named binary directories and model hashes recorded in per-wave manifests. Every game command passes through `tools/seed_guard.sh`; every launch has exclusive output paths, command/environment receipt, status, elapsed time, hashes. No protected historical TEST contents opened.

## Reserved source seeds

- Smoke only: 610080000..610080015 (16).
- Discovery: 610081000..610081031 (32).
- Development: 610082000..610082127 (128).
- Final confirmation reserve: 610083000..610083511 (512; untouched until champion/config/analysis/sample size frozen).
- Counterfactual source reserve: 610084000..610085999 (up to 2,000, only after separate reviewed cost/protocol).

These allocations were made before viewing outcomes. Exact arrays are in seeds.json. No matching ranges found in tracked experiment plans/manifests/scripts; independent local artifact inventory continues. Data partition siblings stay together. Smoke/discovery cannot become confirmation.

## Funnel and decisions

First canaries prove model loading, mode dispatch, provenance and trace neutrality. Wave 1 measures Bprod/Bflat and screens evidence-ranked single-factor alternatives on 32 paired discovery seeds. Discovery can select but cannot confirm. Next distinct hypotheses follow negative evidence while time remains; survivors get up to 128 fresh development pairs. Stop speculative work by reserve boundary.

Freeze one champion, exact artifacts, fixed sample size and analysis before opening confirmation. Target 512 pairs if throughput permits; select a smaller fixed cohort before any confirmation outcome if necessary. Preregistered 95% paired bootstrap interval uses paired_analysis.bootstrap_ci, 10,000 replicates, RNG 20261008; report both discordance directions, win rates, failures, missing pairs, CPU/wall and uncertainty. All required pairs must complete; candidate-dependent errors invalidate a clean comparison. Final superiority requires information/execution gates, positive lower interval bound and observed gain >=2 percentage points. No default flip or merge.

## Ownership and restart

Coordinator: profiles, manifests, launches, source edits/builds/commits, holdout latch, integration and final PR. Strategy: strategy/ evidence; learning: learning/; integrity: audit/. Workers do not alter shared code without explicit path ownership. Initial specialists investigate independently; integrity reviews protocols and candidate diffs. Coordinator also performs run-decision investigation then delegates bounded public cases. No active game jobs yet. Build process tracked by tool session 47744; build log `build/overnight-build.log`.

Durable knowledge impact: benchmark results go to experiment ledger and evidence, research disposition to current-research; any stable implementation facts go to canonical KB. Final README and complete hypothesis/decision tables are required.

## Pre-wave integrity update

Independent review confirmed original native fallback models split on actual unseen encounter identities. Original Bprod/Bflat smoke receipts are diagnostic only. Fair wave references Fprod/Fflat enable common eight-future marginalization; historical scores cannot qualify this new baseline. Default-off public invariance and source preservation tests pass. Separate opt-in shop deck-size correction reproduces a baseline-failing fixture and passes after correction. Final-boss binary objective is a separate exact-budget challenger; its focused Debug silver_searcher suite passes. Current code/teacher glue independently reviewed by integrity; terminal diff reviewed by strategy. First wave protocol and profiles are frozen before outcomes. No confirmation seeds executed.
