# Provenance-backed historical public-root annotation pilot

**Annotation feasibility PASS; useful natural infinity signal NOT ESTABLISHED.**
All16 fixed historical A0 Champ roots pass existing support checks. All64 K=4
worlds return NONE, with no damaging candidate or certified kill. Twelve worlds
at decisions1,2,5 hit the 2,000-node cap and are inconclusive. The remaining52
worlds have no candidate in the bounded supported search; this is not an
unrestricted proof of absence or a validated negative training label.

Baseline `e41dcef5b734b5187d9552c1e41b9f8b6b5ef1cd`; preregistration/input freeze
commit `28c28eecd` preceded execution. Existing #844 branch/worktree retained.
The oracle/adapter source, CMake and executable match the already independently
reviewed adapter evidence hashes (source `f10c7dc5…`, binary `28e942c2…`). No
implementation, matcher, RNG quotient, bound, model or gameplay change.

## Provenance and public input

The prior [provenance investigation](../combat_infinity_public_20261023/PROVENANCE_OPTIONS.md)
identified this existing corrected-canary archive. `prepare.py` rechecks the
exact receipt, public/OOC traces, run metadata, protocol manifest, executable
and historical producer source before extracting inputs. The single matching
battle is seed610081002/act2/floor33/Champ/fight13, OOC trace line123. The full
pre/post owned relic inventory agrees and has no Prismatic Shard. The historical
seed is used only to bind the artifacts; it is never a sampling seed.

The fixed first16 basic normal/public decisions are
1,2,3,5,6,7,9,10,11,12,13,14,15,16,18,20. They were proposed before annotation and
frozen in [PREREG.md](PREREG.md)/[manifest.json](manifest.json). There was no root
replacement, outcome filtering, new gameplay or collection. No natural
eligibility was assumed from the basic preflight; the unchanged oracle then
confirmed all4 sampled worlds per root supported.

Only source `public_wire` plus the custody-backed no-Shard assertion enters the
adapter. `isolatedSearchSeed` and `observedGeneration` are zeroed in the input.
Actual hidden draw order/RNG is not used. The unchanged adapter derives each
world seed from the canonical public hash and k, drains a copied information-set
pile through Silver's `CardPile::drawTop`, and preserves post-drain RNG.
The analyzer independently checks all64 derived seeds and sampled physical-card
multisets against public input, plus the exact frozen input hashes.

## Execution and costs

Four batches of four preserve the unchanged CLI root cap4. K=4, depth24,
nodes2000, candidates16, replayperiods128, actions/candidate1024 and total replay
actions4096 remain fixed per world. `run.py` refuses output overwrite/retry,
revalidates custody, and invokes each batch through:

```sh
timeout 30s bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --public-roots docs/experiments/evidence/combat_infinity_natural_20261024/inputs-BATCH.jsonl
```

All four commands exit0, stderr empty, on their first execution. Receipts retain
exact argv, wall/child CPU measurements, frozen protocol SHA and output hashes.
No rerun, cap increase, new fixture test or recompilation was needed.

| Measurement | Observed |
|---|---:|
| Eligible / unsupported roots | 16 / 0 |
| Annotated natural worlds | 64 |
| Certified worlds / damaging candidate worlds | 0 / 0 |
| Node-cap worlds / roots | 12 / 3 |
| Depth-cap / candidate-cap worlds | 0 / 0 |
| Nodes total / maximum depth reached | 39,664 / 8 |
| Oracle CPU total | 103.835 ms |
| Oracle CPU median / maximum per world | 0.1605 / 6.190 ms |
| Four-command wall total | 137.640 ms |
| Four-command child user+system CPU total | 136.995 ms |
| Largest batch wall | 87.341 ms |
| Replay actions / repetitions | 0 / 0 |

These are one-pass local observations, not a throughput benchmark. The total
includes only the four annotation commands; extraction/custody validation is
outside that timing. No certification replay occurs without a candidate.
[Per-root matrix](MATRIX.md), [expanded sidecars](expanded-sidecars.json) and
[RESULT.json](RESULT.json) retain the distinction between bounded observations
and scientific usefulness. All roots have certified/candidate fraction0.0,
minimum reach null and representative witness null. No synthetic witness is
substituted for a natural candidate.

## Disagreement and manual interpretation

All16 roots have different sampled physical draw orders across K worlds. Six
roots have different node/depth/cap search diagnostics across worlds. There is
**no classification or candidate/certified-fraction disagreement**: all64 are
NONE. Nontrivial sampled orders therefore did not produce useful label
variation in this sample. Decisions1,2,5 hit the node cap in all4 worlds (depth7–8,
not the depth24 limit); do not interpret their zero fractions as absence.

No natural witness exists to inspect. Instead, [manual-examples.json](manual-examples.json)
records public state examples for decisions1,11,20:

- Decision1: turn0, energy5, playerHP69, ChampHP420; eight-card hand including
  Fire Breathing, Shrug It Off+, Reaper+, Infernal Blade, Clash and basic cards.
  Each world explores2,000nodes, with no cycle before the cap.
- Decision11: turn1, energy4, playerHP75, ChampHP395; hand Shrug It Off twice,
  Strike, Shockwave+ and Bash. Draw samples change explored nodes88–358, but
  no damaging recurrence is found.
- Decision20: turn2, energy0, playerHP69, ChampHP342; hand Perfected Strike+
  and Flame Barrier+. Each world explores one node, consistent with no playable
  positive-cost card at that boundary.

These inventories are larger ordinary combat states, with no Dropkick in the
three displayed public inventories and no Sundial in the complete run relic
inventory. **Inference:** they are poor positive-coverage examples for the
specific constructed engines already qualified. This is not a proof that no
other infinity exists. Selection was for existing custody and a fixed public
sequence, not for enrichment toward an infinite.

## Scientific conclusion and next boundary

The provenance obstacle can be overcome with existing paired artifacts, and
public-conditioned natural-root annotation works cheaply for this tiny sample.
The original four native8 roots remain unsupported/null in their original
report; this different, provenance-backed experiment does not relabel them.

The experiment finds no natural candidate, establishes no natural prevalence,
recall, calibration, current-policy coverage or training utility, and supplies
no demonstrated positive natural label. One historical A0 encounter has
correlated roots under an older policy. Stop at this pilot: no model probing,
training or broad sample/search extension. A next data decision should seek a
small provenance-complete sample with explicit near-infinity relevance or
current-policy relevance, rather than turn capped NONE into negative labels.
No collection was launched and no producer patch is required by this result.

## Verification

```sh
python3 docs/experiments/evidence/combat_infinity_natural_20261024/prepare.py --check
python3 docs/experiments/evidence/combat_infinity_natural_20261024/analyze.py --check
python3 docs/experiments/evidence/combat_infinity_public_20261023/analyze.py --check
python3 docs/experiments/evidence/combat_infinity_recall_20261023/analyze.py --check
git diff --check
```

Only the four frozen public-root batches execute simulator worlds. Subsequent
checks regenerate reporting from those raw outputs; no fixture/gameplay reruns.
Independent interpretation/evidence review is recorded on the PR. Existing
GitHub billing/spending-limit CI failure is external to implementation; no
manual CI dispatch. Knowledge impact: new chronological experiment evidence
and maintained current research coverage updated; original results preserved.
