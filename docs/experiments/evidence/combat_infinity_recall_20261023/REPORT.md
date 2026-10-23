# Combat infinity phase 2: realistic constructed recall

## Verdict and scope

The preregistered **constructed-fixture decision rule passes**. Static-exhaust
Dropkick and energy-positive Sundial Dropkick certify actual simulator victory;
matched near misses and encounter guards produce no false certification. The
positives require 7–11 nodes, reach depth 4, and witnesses of 2–6 actions under
unchanged v0 limits. This is a small deterministic near-infinity qualification,
not an estimate of natural occurrence, population recall, public-root label
quality, or gameplay improvement.

Actual baseline: merged #839, `45eb23a7ed88869f3ea54d22d70f37e3cf93b22e`.
Both prerequisite review corrections were present before starting:
PRODUCTIVE_CYCLE_CANDIDATE and the audited Ironclad/card-domain/no-Shard gate.
Execution used the single fresh Codex-app-managed worktree
`infinity-realistic-recall/sts_lightspeed`, task branch
`research/infinity-realistic-recall`. Its pinned submodules were repaired with
the repository lifecycle tool before building. No nested worktree was created.
A later remote check found main at `5c30b0d28f20e2323dc530c077c5e5e17b4b7b73`
(#841 CTM fine-tune tooling/artifacts/evidence); it changes no oracle, simulator,
CMake input or affected maintained KB. The original source baseline was retained.
The shared ledger received a separate chronological entry on main; this task
uses a placeholder entry and leaves historical entries unchanged.

## Exact fixture constructions

All roots are quiet concrete Ironclad states with explicit no-Shard provenance,
empty queues, no potions, no player powers and one visible enemy. Unless noted:
turn 1, ascension 0, player HP/maxHP 80, block 0, energy 1; 200-HP Cultist with
Incantation intent and Vulnerable 2. Physical Dropkick #0 is in hand, #1 on top
of draw; discard and stasis are empty. RNG seeds for ai/cardRandom/misc/monsterHP/
potion/shuffle are respectively 1/2/3/4/5/6, inherited from #839. These are
constructed fixtures, not a new combat/run-seed cohort. No model is loaded.

- **Minimal Dropkick:** exactly the preceding root.
- **Static exhaust Dropkick:** add physical IDs 2–8 to exhaust, in this order:
  Strike, Strike, Defend, Defend, Bash, Anger, True Grit. Normal unupgraded costs;
  no pending effects. This represents an already exhausted-down deck; it does
  not simulate the earlier exhaustion process.
- **Broken Dropkick:** same seven exhausted cards; remove only Vulnerable.
  One play deals 5 damage, draws/refunds nothing, and leaves no legal card.
- **Energy positive, no exhaust:** minimal root plus Sundial (counter 0),
  initial energy 7, and Dropkick #0 base/current cost 0 (a persistent Madness-like
  reduction); #1 stays cost 1. After four warmup plays, the six-play period
  restores physical card zones and Sundial counter 0, deals 42 damage and gains
  7 energy (11 to 18). The oracle with exact energy misses it even without exhaust.
- **Energy positive, exhaust:** same engine plus the seven static exhausted
  cards. This is the combined realistic positive.
- **Energy negative, exhaust:** change only #0's persistent cost from 0 to 3
  (base and current fields together are one economic variable). This is a
  controlled cost perturbation, not a naturally collected cost-3 Dropkick claim.
  The six-play period after four warmup plays deals 42 damage and loses 2 energy
  (5 to 3). Legal play ends after 12 actions with energy 1 and enemy HP 116.
- **Time Eater:** Dropkick root, replace enemy with simulator-initialized A0
  Time Eater (456 HP), actual Time Warp, counter 1, Head Slam intent,
  Vulnerable 2. The turn is forced after 11 plays. The legacy Cultist/Time Warp
  fixture is also retained unchanged in `--fixtures`.
- **Awakened One:** retain #839's constructed 200-HP phase-1 identity fixture.
  The witness triggers half-dead/rebirth state, then cannot target the monster.
  This checks the retained phase-break case, not a fully reproduced natural boss root.
- **Heart:** simulator `initHp` and `preBattleAction` at A20, 800 HP, actual Beat
  of Death 2 and Invincible 200, Debilitate intent, Vulnerable 2; seven exhausted
  cards, energy 1, player HP 80. A complete scripted trace reaches Invincible 0
  after 29 plays and dies after 40 plays, with 600 enemy HP left. The matched
  12-player-HP case dies after 6 plays. No Heart-specific oracle logic exists.

The suggested zero-cost Pommel Strike+ / Shrug / Sundial engine was also played
through the simulator. Its six-play diagnostic accumulates 24 block. That is an
additional changing control coordinate, so this experiment does not extend block
equality or the RNG card whitelist for it. The Dropkick construction isolates energy.

## Ablation and normalization

[PREREG.md](PREREG.md) records the accepted contrast and fixed budgets.
[MATRIX.md](MATRIX.md) gives classifications and final metrics;
[matrix.json](matrix.json) contains all 40 arm/fixture rows with explicit nulls,
CPU time, reach/witness lengths, nodes, period deltas, replay result, repetitions,
actions and rejection reasons, including player-HP deltas and maximum search depth. The raw `*-recall.jsonl` files retain every
candidate/witness and diagnostic trace. A NONE classification has no discovered
witness; a separately measured six-play trace is not reported as an oracle witness.

The sequence was unchanged merged detector + fixture harness → A-only → A+B.
Each arm has its own source/binary hashes and a full compressed source patch against the
baseline (`gzip -dc ARM.patch.gz | git apply` on that baseline), making the ablation reproducible without maintaining runtime modes
for obsolete algorithms. `--recall-probe` prints the same fixture roots without
asserting successful final classifications; `--recall-fixtures` asserts them.
The final regression harness adds guard diagnostics; the analyzer verifies
that all detector/replay results and node counts equal the frozen A+B arm.

**A, active-zone singleton-shuffle qualification:** count exactly two physical
Dropkick/Flash of Steel cards across hand/draw/discard. Reject occupied stasis.
Retain the original no-player-powers and Burning Blood/Sundial-only relic
restriction. A played one-card draw card is out of the piles, so any shuffle has
at most one active card. Exhaust cannot enter that cycling engine. Exhaust is
never removed from full control equality or the domain/history-counter audit;
card payload, physical ID and size mutations still reject. Other RNG streams
remain exact. No new card, relic or power family is added to the quotient.
A real two-action period matches with static exhaust; mutating its exhausted
payload prevents the match. Root immutability and other-RNG/stasis regressions pass.

**B, energy dominance:** set energy to zero only in normalized comparison copies.
Require actual candidate end energy >= candidate start energy. At each complete
replay period require energy >= the preceding period's energy. Keep actual
energy/cost/legality untouched in the simulator copy. All other control fields
retain the merged equality policy; no new HP, block, powers or counter ordering
is introduced. Exact semantic witness replay and actual same-turn victory
remain authoritative. A forced six-action replay of the matched negative
rejects `energy_decreased`; discovery never admits that decreasing candidate.

The Heart has no discovered candidate because player HP and Invincible remain
exact. Separately forcing its two-action witness through the existing replay
routine rejects `control_state_changed` after one period. Its full manual trace
confirms that both simulator mechanics prevent a same-turn kill. Thus discovery
and replay guards are reported separately, rather than claiming that a replay
was attempted by discovery when it was not.

Bounds remain depth 24, nodes 2,000, candidates 16, replay periods 128,
actions per candidate 1,024 and total replay actions 4,096. Positive fixtures use
at most 11 nodes, depth 10 and 25 replay actions. Legacy budget regressions still
exercise 2,000 nodes/depth 24 and repetition-cap rejection. The 80-HP Heart
negative reaches depth 24 without a candidate; no budget was raised to rescue it.

## Verification and provenance

Release build on Linux, GCC 13.3.0, CMake Release/ccache preset, `-j2`, target
`combat-infinity-oracle`. Process CPU (`std::clock`) is timed only around oracle
search and certification. One measurement per fixture/arm; no statistical speed
claim or Debug-vs-Release timing comparison. All final positives take under
0.25 ms in the retained measurement; max across the ten final fixtures is
0.623 ms (Heart). No broad tests or game-seed sweep was run.

Executed focused commands:

```sh
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build -j2 --target combat-infinity-oracle
bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --fixtures
bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --recall-probe
bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --recall-fixtures
ctest --test-dir build/linux-gcc-release-ccache -R '^combat_infinity_(oracle|recall)$' --output-on-failure
python3 docs/experiments/evidence/combat_infinity_recall_20261023/analyze.py
python3 docs/experiments/evidence/combat_infinity_recall_20261023/analyze.py --check
git diff --check
```

Both focused CTests pass; raw CTest output is in [focused-ctest.txt](focused-ctest.txt).
Thirteen legacy cases retain their verdicts, including all domain guards.
Ten phase-2 cases yield four CERTIFIED_KILL, one rejected
PRODUCTIVE_CYCLE_CANDIDATE and five NONE. Analyzer: PASS all ablation verdicts,
fixed budgets and final/A+B detector parity. Compiler emitted only the usual
serial LTO note. `*-sha256.txt` records each source/binary identity;
`patch-verification.json` confirms that all five compressed arm/development patches
reconstruct their recorded source hashes from the merged baseline;
[provenance.json](provenance.json) records toolchain/build inputs.

Two development problems are retained explicitly: a turn-only cost modification
reset in piles, so the negative was initially energy-positive; the first A
implementation incorrectly tested empty() on the fixed two-slot stasis array,
regressing the minimal baseline. Neither output is counted as an experimental
arm. The construction and implementation were corrected, A was rerun in
isolation, then B was tested. See `development-*-result.txt`, raw probe output,
and patches. No engine code or search limits changed to repair these problems.

Reporting completion regenerates the full matrix solely from the retained raw
JSONL. `--check` compares the generated JSON/Markdown bytes with the committed
artifacts without rewriting them. No fixtures were rerun, CPU measurements
replaced, oracle behavior changed, or scientific verdict revised.

Knowledge impact: updated research status, the oracle's maintained normalization
contract, and the chronological experiment ledger. Production executable source
lists are unchanged. No AZ, models/artifacts, targets/losses, Silver defaults,
OOC MCTS, rewards or gameplay defaults were changed.

## Scientific conclusion and remaining boundary

R1: static exhaust was the measured false-negative cause and the active-zone
qualification repairs it without ignoring exhaust mutations. R2: an actual
Sundial cycle repeats all tested control coordinates except energy (+7); exact
energy misses it, while nondecreasing-energy matching plus untouched replay
certifies victory. The matched negative cannot certify. R3: for these already
near-infinite roots the original limits have ample headroom; no broad search or
major state abstraction was necessary.

These results support a separately requested small public-root/information-set
annotation pilot. They do not implement or qualify it. Concrete draw piles
remain mandatory, hidden/public-root determinization was not tested, and the
real run's hidden order must never become a privileged label. Whole-combat/run
discovery, natural recall, other draw engines, states with accumulating block,
new card/relic/power shuffle families and other characters remain unsupported or
unqualified. No model integration, training, follow-up pilot or merge is part
of this worktree.
