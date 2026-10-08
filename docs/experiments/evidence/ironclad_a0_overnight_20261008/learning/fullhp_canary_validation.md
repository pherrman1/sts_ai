# Full-health candidate runtime gate

**RUNTIME_GATE_PASS** for all five frozen canary invocations. This is a custody, default-behavior parity, and action-exposure check; it makes no win-rate or strength claim.

The new default-off `Fprod_0` exactly matches the prior corrected baseline on seed 610080001: every gameplay CSV field except elapsed seconds, all 177 OOC/battle trace rows, all 454 tree-profile rows except `combat_id`, and every floor-profile count after removing only time fields. The new binary, source, model files, exact guarded commands, controlled environments, output bytes/hashes, metadata, public scorer-use receipts, loaded-model banners, learned-stop profiles, and new flag banners all passed. All five subprocesses completed with exit zero. The new FullHp flag appeared only in the two authorized candidate invocations; ShopOff's strategic shop gate was disabled as declared.

The clearest same-state exposure is seed 610080001, Act 1 floor 15. Baseline and FullHp have exactly the same serialized public pre-state: 72/72 HP, REST screen, no Dream Catcher, and baseline-legal REST and SMITH. The baseline strategic record owns action bits `0|1` and chooses bit `0` (REST), producing REST→MAP without a deck upgrade. FullHp retains only bit `1` (SMITH), owns that action, opens CARD_SELECT, and the following selector changes Whirlwind to Whirlwind+. Thus the action identity is supported by the owned strategic record, with the actual upgrade independently supported by deck multisets. `takeIdx=0` in the filtered candidate means its first retained action, SMITH; it does not mean REST.

| Evidence | Locator |
|---|---|
| Smoke baseline REST | `build/overnight_20261008/fullhp_canary/Fprod_0.trace.jsonl:63` and `Fprod_0.strategic.jsonl:21` |
| Smoke candidate SMITH | `build/overnight_20261008/fullhp_canary/FullHp_1.trace.jsonl:63` and `FullHp_1.strategic.jsonl:21` |
| Original named baseline REST | `build/overnight_20261008/fullhp_canary/Fprod_3.trace.jsonl:165` and `Fprod_3.strategic.jsonl:54` |
| Named candidate SMITH/Immolate upgrade | `build/overnight_20261008/fullhp_canary/FullHp_4.trace.jsonl:174` and `FullHp_4.strategic.jsonl:61` |

The original named source, 610081015 at Act 3 floor 44, still occurs under the corrected Recall policy. Its baseline pre-state exactly matches the earlier frozen public packet, and the strategic record explicitly chooses REST. FullHp chooses SMITH at that floor and visibly upgrades Immolate. That later pair is not an isolated same-state contrast: FullHp has already changed earlier campfires and therefore reaches floor 44 with a different deck.

The integrity reviewer independently located the named source's first divergence at Act 2 floor 23, OOC index 80, serialized trace row 94 (one-based). The preceding 93 rows and the public pre-state are identical; HP is 80/80. The baseline owns REST with margin 3.993057; the candidate's filtered action list contains only SMITH. The subsequent upgrade-target gate declines its own margin check, so the full-health intervention does not prescribe a particular card target. This corroboration is recorded separately in `audit/fullhp_canary_independent_review.json`.

The public-state predicate is supported by full HP, positive maximum HP, REST screen, absence of Dream Catcher, and the baseline's explicit legal action list containing both REST and SMITH. The trace does not serialize `restRoomResolved` directly; legal-action availability and the executed screen transition provide runtime evidence for the unresolved actionable screen. No unsupported semantic action is inferred solely from an unchanged deck.

## Custody

- Frozen manifest: `0c3ec718578f5f3fb20027bbbdd52e507324f9c0b5eedf46fed3909e56f35653`
- Producer source: `b229f3ff2443b0decaacaa762d2a0c429f7e9d47`
- Immutable binary: `a8516aaae94c3ed91d5671ba5477c704ff1a42e53ce83061e1dddb846081d23a`
- Consolidated machine validation `learning/fullhp_canary_validation.json`: `77255f8c4eedc57350a4f5d064279307a0e45b2a74a767538ca8092ca14c88d4`
- Reproducible read-only validator `learning/validate_fullhp_canary.py`: `033c4ed9ba6bae51209995099118555f38ce6f78b9ef79895450c23c57c04bf9`
- Independent corroboration `audit/fullhp_canary_independent_review.json`: `48cb6c5adfd9dd2e38a8c9cd8e396018d33d749dc2606403e0e743d7bead3984`

No game commands were launched during this validation. No GEN2 tranche numerical analysis or confirmation access occurred.
