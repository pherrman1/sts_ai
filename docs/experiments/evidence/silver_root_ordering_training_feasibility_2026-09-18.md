# Silver root ordering tail and training-data feasibility audit (2026-09-18)

## Scope

This is a read-only audit of the frozen A/B/G/H replay and existing local root
and teacher artifacts. It runs no gameplay, replay, teacher generation, model
training, or runtime qualification.

## Harmful-tail review

The largest positive root-level `G-A` regret delta is `+1.514772` at root
`14/2/23/36/3`, source seed `14`, Act `2`, floor `23`, encounter `36`, with
seven legal actions. The state is a normal `PLAYER_NORMAL` combat root: Ironclad
has 59/80 HP and 3 energy against a single 160-HP monster. Its hand actions
are Evolve, Intimidate, Seeing Red, Havoc, Blood for Blood, and Heavy Blade,
plus End Turn.

The frozen 10k-A action-Q ordering is:

```text
Seeing Red 52.560875, Havoc 48.414994, Evolve 45.427285,
Intimidate 44.361117, Blood for Blood 43.384098,
Heavy Blade 38.871250, End Turn 14.724167
```

The independent 25k-B ordering instead selects Havoc and has Q values:

```text
Havoc 49.455004, Evolve 40.891224, Intimidate 40.141159,
Blood for Blood 38.679521, Heavy Blade 37.453288,
Seeing Red 34.832137, End Turn 22.286094
```

Across the four common replicates, A selects Evolve, Evolve, Evolve, Evolve;
G selects Blood for Blood, Evolve, Evolve, Evolve. Their B-regrets are
respectively `[8.5638, 0, 8.5638, 0]` for A and
`[14.6229, 0, 8.5638, 0]` for G. H has the same selected actions and regrets
on this root. This is therefore a treatment-sensitive early-allocation case
with a substantial Teacher-A/Teacher-B disagreement, not an invalid action
surface or provenance failure. It remains a harmful-tail example requiring
review before training authorization.

## Reusable 10k-A labels

Deduplicating by `root_id` across the preserved local teacher artifacts gives
128 unique root states with valid 10k-A labels. Each label contains the full
legal action set and one 10k-A Q/visit record per action.

| Artifact population | Unique 10k-A roots | Source-seed coverage |
| --- | ---: | --- |
| Earlier seed-0 mechanism pool | 64 | source seed `0` only |
| A/B/G/H ablation pool | 64 | source seeds `1..32`, two roots each |
| **Deduplicated total** | **128** | **33 source-seed trajectories** |

The ablation pool overlaps the prior 16- and 32-seed confirmation label files;
those are not additional roots. The seed-0 pool and ablation pool are disjoint
by `root_id`. The ablation's 64 roots are all `PLAYER_NORMAL`; the seed-0
pool's 64 roots are also all `PLAYER_NORMAL`.

For the 128 unique 10k-A labels, recorded per-label teacher wall time totals
48.100342 seconds, with mean `0.375784` seconds, median `0.325646` seconds,
p90 `0.765684` seconds, and maximum `1.111597` seconds. This is label-process
time from the existing `wall_micros` fields, not an end-to-end estimate for
capturing new gameplay roots. At the observed mean, 64, 128, and 256 additional
10k-A labels would require approximately 24, 48, and 96 seconds of teacher
time, respectively, before capture, serialization, feature conversion, and
validation overhead.

## Existing feature representation

The reusable roots contain `silver_leaf_wire_v1` state snapshots, exact native
legal-action semantics/fingerprints, and the 10k-A action labels. They do not
yet contain materialized model feature vectors.

The existing Silver policy/value Phase-A representation is directly aligned
with this target and supports visible `PLAYER_NORMAL` parents:

- 1,766 canonical state features;
- exact root effective-gold and max-HP scalars, producing 1,768 model state
  inputs;
- 22 canonical action features, for 1,788 canonical policy features;
- exact semantic legal-action identity and Silver-native order.

The implementation is in `apps/silver_policy_value_phase_a.cpp` and the
feature contract is documented in
`docs/experiments/evidence/silver_policy_value_phase_a_2026-09-16.md`. The
existing Phase-A CLI consumes `silver_leaf_corpus_v1`, while these root files
are selected-root wire snapshots, so a small offline conversion adapter (or a
bounded extension to the converter) is still needed to materialize features.
That conversion requires no new 10k-A labels.

## Feasibility conclusion

The data plumbing for a compact best-action scorer is favorable: 128 reusable
10k-A-labeled roots already exist, all in the supported `PLAYER_NORMAL` state,
with an established state-plus-action representation. The statistical
independence is less favorable: 64 roots come from one seed-0 trajectory and
the remaining 64 cover only 32 source seeds. The current pool is therefore
adequate for an offline conversion smoke test and feature-schema audit, but is
not a strong source-grouped training/validation corpus by itself.

Creating more labels is cheap once independent root states exist; the measured
10k-A teacher cost is roughly `0.376` seconds per root. The expensive and
scientifically important part is obtaining fresh independent source-seed
trajectories and qualifying their roots, not the teacher search. No model
training or new data collection is authorized by this audit.

## Provenance

- Ablation roots: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- Ablation teachers: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- Ablation replay: `f54759089049267102c088d60c57c169f50448b5f166a7e7cc735d554513c1af`
- Frozen underlying Silver/root-mechanism provenance: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`
- Replay executable SHA-256: `ba607f78f5b3432edb5ef0db3e1412197a38af4ef7d2c2b0e5aae49884541239`

**Knowledge impact:** current research status and feasibility evidence only;
no model, runtime, gameplay, or default change.
