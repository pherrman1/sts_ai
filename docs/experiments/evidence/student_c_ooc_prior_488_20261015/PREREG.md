# §488 OOC MCTS with the distilled heart1 student C vs V4 as the tree prior, paired by seed (pre-registration, 2026-10-15)

Philipp, 2026-10-15 17:38Z: "k now start a thread which does on the same 64 seeds the ooc mcts but with arm C as the
prior. use 32 haiku workers again." So this is the §486 design with student C's weights in place of heart1's, on the
§486/§487 A20 seeds, 32 workers. Frozen with the run commit, binary hash, weights hash and brief hash before launch;
independent pre-launch review.

## What is known (baseline)
- §486 (same 64 A20 seeds, same stack): heart1 as the OOC MCTS tree prior cleared act 3 in 25/64 vs 10/64 with V4,
  +23.4 pp [+9.4, +37.5], McNemar p = 0.0026; floors NOT_SHOWN (−0.09 [−3.64, +3.23]); 8.7x wall time per run
  (4,310 vs 494 s; MCTS CPU 4,170 vs 430 s). Not replicated.
- §487 (same seeds): its control reproduced the §486 `v4` rows on 64/64 seeds.
- Student C (heart1-distill thread, data branch `claude/heart1-distill-data` at `68fe88be`,
  `results/C_d64_trim/student.pt`): silverbot's NN at dim 64, 2 layers, 4 heads, SwiGLU hidden 256, 272k parameters,
  trained in bf16 autocast (fp32 weights) on 884k heart1-labelled OOC MCTS tree nodes (capture seeds 108000000–063)
  with KL to heart1's softmax, on records whose map rows below the current floor are dropped ("trim"). Held-out
  seeds: top-1 agreement with heart1 93.0% (map 86.7%, rewards 94.5%, shop 88.5%), val KL 0.068; V4's top-1 agreement
  with heart1 on the same nodes is about 47%.
- This change (code commit in `CODE_COMMIT`): the native heart1 port reads the network size from the weights file
  and two optional meta tensors (`meta.n_heads`, `meta.trim_map`) that the exporter writes on request; with trim the
  forward drops the map rows below the current floor first, as the student's training data did. heart1's own export
  has no meta tensors and scores byte-identically to main's binary (3,000 captured tree-node records, AVX and
  scalar paths). The native student matches silverbot's torch forward on the same 3,000 records (max |Δ| 1.6e-5,
  argmax 3,000/3,000) and agrees with heart1's top-1 on 92.6% of them (held-out capture seeds 108000007 and
  108000039). About 1.5 ms per call vs about 31 ms for heart1 in the same scorer.

## Hypotheses
- H1 (primary): OOC MCTS with student C as the tree prior clears act 3 at A20 more often than with V4.
- H2 (key secondary): it reaches further (mean paired floor difference > 0). §486 showed floors are a poor fit for an
  act-3-stop run, so clears are primary here as in §487.
- Descriptive: how much of §486's heart1 effect the student keeps (student arm vs the §486 `heart1` arm on the same
  seeds), and its cost against both.

## Arms (paired by seed, same binary, `arm_env.sh`)
- Both: the §486 arms literally: §433 `combo` (the §422 base: exact-10k Silver via the bestbench budget, V4 OOC gates
  at margin 1.0, `STS_COLLECT_KEYS=0`, `STS_REST_WIN=0`, `STS_STOP_AFTER_ACT=3`; live OOC MCTS with 4096 simulations,
  `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, 3 leaf combats, native leaf, `TEMPERATURE=1`, `CPUCT=1.5`, `MAX_DEPTH=32`, visits
  root selection, early stop), `STS_OOC_PUBLIC_FUTURES=8`, chain rollouts (`STS_OOC_MCTS_LEAF_POLICY=v4`). No CTM
  variables: the automatic A20 stack (ADR-0033). All other settings are the run commit's defaults (ADR-0030..0040).
- `v4`: `STS_OOC_MCTS_PRIOR=policy`. Run again on this binary so the pairing does not rest on an older one; expected
  to reproduce the §486 `v4` rows (checked, reported, descriptive).
- `studentc`: `STS_OOC_HEART1=studentc.bin` (sha256 in `student_weights.txt`) and `STS_OOC_MCTS_PRIOR=heart1`: the
  §486 heart1 prior path unchanged (V4 coverage rule, skip/bowl/gold/discard mapping, V4 fallback at nodes the
  encoding lacks), with the student's logits.
- No new option: the student runs through the existing default-off `STS_OOC_HEART1` and `STS_OOC_MCTS_PRIOR=heart1`.

## Seeds and runs
- A20 seeds 107000000–107000063 (`COHORTS`), the §486/§487 seeds. One `bestbench 10000 1 20 SEED` unit per seed and
  arm through `tools/seed_guard.sh` (`run_unit.sh`), 128 units. 32 cloud workers (`NWORKERS`, Philipp 17:38Z), each
  running 2 seeds in both arms, all 4 units at once.
- Smokes in this thread: 74072190–74072199 (190 used); reviewer 74072200–74072219. The smoke also reran §486 seed
  107000049 in the `v4` arm (its rows and all 48 OOC decisions in the trace equal §486's).
- Launch gate (reviewer): in the final-binary smoke the student scores at least 90% of prior builds
  (`heart1_prior_nodes` / all prior builds), the log shows `(dim 64, heads 4, hidden 256, layers 2, trim_map 1)`.
- Unit timeout: 8 h per unit, as in §486 (far above the expected unit time). Issue #544's endless Silver loop does not
  throw, so a hung unit ends at rc 124. Workers let the timeout fire and never kill units themselves.
- Dropped seeds: a `[bestbench-seed-failure]` (rc 1, no row) or a timeout (rc 124) drops that seed from both arms
  and lists it. INVALID if more than 1% of the seeds, and more than one seed, are dropped (here more than 1 of 64), if
  any other unit fails, or if a log lacks its arm's markers (the student load line and `prior=heart1` for studentc,
  `prior=policy` and no heart1 load for v4, `leaf_policy=v4` for both) (`tools/analyze_student_prior_488.py`).

## Analysis (`python3 tools/analyze_student_prior_488.py report.json DIR... --ref486 DIR...`)
- **Primary (A20):** act-3 clear difference studentc − v4, paired seed bootstrap 95% CI (10,000 resamples, RNG seed
  488 + ascension), **IMPROVED** if the lower CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise;
  discordant pairs and exact McNemar p.
- **Key secondary (A20):** mean paired floor difference with its CI (same resample indices, same labels).
- Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds and MCTS CPU
  per run, MCTS-owned and fallback shares, prior builds, the student's share of prior builds and its fallback
  reasons. Against §486 (`--ref486`, the extracted §486 worker `out/` folders): control rows vs §486 `v4` rows
  (reproduction), and studentc vs §486 `heart1` on the same seeds (clears, discordant pairs, McNemar p, floors, reached
  act 3, seconds and MCTS CPU per run). No label for the §486 comparison: it is across binaries and runs.
- No multiplicity correction; all statistics are reported.
- Limitation: the seeds are the ones on which §486 found the heart1 effect, and the V4 arm's result on them is known
  (10/64). A positive result says the student reproduces heart1's effect on these seeds; it is not an independent
  replication of §486.

## Decision rule
- Clears IMPROVED → student C is the candidate fast OOC MCTS tree prior. Before any default change (Philipp's call,
  a new ADR), a replication on fresh seeds.
- NOT_SHOWN → the V4 prior stays. With the §486 comparison: if the student arm's clears are near heart1's 25, the
  run was underpowered; if near V4's 10, distillation lost the effect or §486 was a fluke (**ambiguous** at 64 seeds;
  reported as such).
- WORSE → the V4 prior stays; the ledger records the result.

## Cost
- Smoke (this binary, seed 74072190, 3 units sharing 4 CPUs): `studentc` cleared act 3 in 647 s (103 OOC decisions,
  100 MCTS-owned, MCTS CPU 495 s, 4.95 s per owned decision, 94,780 prior builds, all scored by the student, no
  fallbacks); `v4` died on floor 42 in 312 s (2.99 s per owned decision). So the student prior costs about 1.65x V4
  per MCTS decision (about 2 ms per prior build including the encoding), against about 10x for heart1 in §486.
- **Inference:** about 1.7x the v4 arm per run plus longer runs where the student clears more, roughly 25 core-h in
  all (§486's v4 arm: 494 s per run). On 32 workers the slowest unit, a full clear, should take about 15–25 min;
  about 30 min per worker plus the build.
