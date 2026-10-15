# Frozen potion-generation support correction

Baseline: `3057ea79f8a678ba13f9f2ea2b4834850fa2dd87` (main when the fresh app
worktree was created). Source identities, verified data/model hashes, complete
integrity/accounting and raw counts are in the [JSON packet](potion_generation_support_2026-09-14.json).
The [maintained contract](../../knowledge-base/behavior/combat-potion-generation.md)
contains the generation-route audit and simulator limitations.

This is a seed-free census of the unchanged frozen corpus. No fit, tuning,
new data, gameplay, sampling or win-rate run. The six frozen model identities
and prepared representation are verified before loading the support metadata.
Corpus and original source split hashes were revalidated:

- Corpus: `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`
- Split: `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`

Manifest and companion provenance agree: 25,000 requested sources, 24,999
completed, one quarantined source, zero quarantined rows; 510,030 captured
rows, 491,897 victories and 18,133 deaths. Prepared row/source/fight order,
original split membership, source-set completeness and global eligibility
are checked. Every historical support slice and fallback-reason count
reproduces the existing composed-transition packet exactly.

## Support accounting

| Slice | Rows | Old support | New support | Old fallback | New fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overall | 510,030 | 322,644 (63.260%) | 413,799 (81.132%) | 187,386 | 96,231 |
| Original TRAIN | 408,183 | 258,206 (63.257%) | 331,225 (81.146%) | 149,977 | 76,958 |
| Original VALIDATION | 50,406 | 32,274 (64.028%) | 41,120 (81.578%) | 18,132 | 9,286 |
| Original TEST | 51,441 | 32,164 (62.526%) | 41,454 (80.586%) | 19,277 | 9,987 |
| Act 1 | 238,946 | 178,806 (74.831%) | 197,156 (82.511%) | 60,140 | 41,790 |
| Act 2 | 171,452 | 95,578 (55.746%) | 136,142 (79.405%) | 75,874 | 35,310 |
| Act 3 | 99,632 | 48,260 (48.438%) | 80,501 (80.798%) | 51,372 | 19,131 |
| Event | 7,826 | 4,577 (58.485%) | 6,567 (83.913%) | 3,249 | 1,259 |
| Elite | 118,335 | 75,844 (64.093%) | 99,505 (84.088%) | 42,491 | 18,830 |
| Monster | 329,935 | 210,013 (63.653%) | 262,549 (79.576%) | 119,922 | 67,386 |
| Boss | 53,934 | 32,210 (59.721%) | 45,178 (83.765%) | 21,724 | 8,756 |
| TEST Act 1 | 24,046 | 17,952 (74.657%) | 19,854 (82.567%) | 6,094 | 4,192 |
| TEST Act 2 | 17,249 | 9,404 (54.519%) | 13,519 (78.376%) | 7,845 | 3,730 |
| TEST Act 3 | 10,146 | 4,808 (47.388%) | 8,081 (79.647%) | 5,338 | 2,065 |
| TEST Event | 787 | 454 (57.687%) | 659 (83.736%) | 333 | 128 |
| TEST Elite | 11,962 | 7,621 (63.710%) | 10,011 (83.690%) | 4,341 | 1,951 |
| TEST Monster | 33,243 | 20,846 (62.708%) | 26,220 (78.874%) | 12,397 | 7,023 |
| TEST Boss | 5,449 | 3,243 (59.516%) | 4,564 (83.758%) | 2,206 | 885 |

Of the previous 116,302 `potion_not_certified` rows, 113,094 (97.242%) recover
potion certification. 91,155 (78.378% of the previous rejection set) recover
full support; 21,939 recover certification but retain independent fallbacks.
The remaining 3,208 certification failures coincide with Entropic Brew rows.
Explicit Alchemize remains excluded and is covered by focused parity tests.

The 96,231 remaining full fallbacks exactly match the original global
eligibility set. Reason counts overlap and must not be summed:

| Remaining reason | Rows |
| --- | ---: |
| `entropic_brew` | 3,208 |
| `gold_mutating_card` | 2,640 |
| `gold_mutating_encounter` | 27,664 |
| `gold_mutating_potion` | 21,698 |
| `gold_mutating_relic` | 6,824 |
| `potion_not_certified` | 3,208 |
| `pre_smoke_bomb_used` | 26 |
| `pre_stolen_gold_nonzero` | 19,048 |
| `ritual_dagger` | 13,926 |
| `smoke_bomb` | 3,765 |
| `writhing_mass` | 4,477 |

## Hard validation and limits

**Zero potion creations, swaps or substitutions on all 413,799 supported
rows, including deaths.** Each changed identity must be consumption to empty
in an active pre-state slot. The audit writes the complete counterexample and
stops immediately on a violation. Inherited potion RNG copy-through, exact
misc RNG initialization replay, victorious persistent copy-through and native
relic trajectory constraints also have zero contradictions.

Support is decided from visible pre-state before consulting outcomes.
These census counts correct consumption support; they do not remeasure
component accuracy or exposure on the recovered rows. Historical distribution
qualification remains restricted to the previously measured 32,164-row TEST
subset. Expanded support has no new gameplay or distribution qualification.

## Reproduction and focused verification

```
python3 -m tools.combat_transition_potion_support_audit --output /tmp/potion-support-audit.json
python3 -m unittest tests.test_combat_transition_native_contract tools.test_combat_transition_frozen_composition tools.test_combat_transition_composed
cmake --preset linux-gcc-release-ccache -DCMAKE_CXX_COMPILER_LAUNCHER=
cmake --build --preset linux-gcc-release-ccache-build --target one_combat combat_transition_runtime_probe -j 6
ctest --test-dir build/linux-gcc-release-ccache --output-on-failure -R 'combat_transition_(frozen_composition_selftest|composed_selftest|native_contract|potion_decoder_selftest|relic_trajectory_selftest|runtime_loader)'
UV_CACHE_DIR=/tmp/sts-potion-uv-cache bash tools/agent/doctor.sh
```

Outcomes: full census passed; 32 focused Python/native tests passed; both
executables built; 6/6 affected CTests passed; environment doctor passed.
Shared-cache writes were read-only under this sandbox; disabling the compiler
launcher and using a writable uv cache repaired those environment failures.
The first audit attempt failed on a local script path typo before the support
pass; the repaired complete run supplies this packet. Existing compiler/LTO
warnings remain. No local full CTest or gameplay seeds were run; Linux GCC CI
is the authoritative repository verification at the draft PR handoff.
