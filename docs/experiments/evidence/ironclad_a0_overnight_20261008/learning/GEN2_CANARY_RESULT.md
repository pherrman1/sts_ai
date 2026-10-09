# Corrected four-source GEN2 diagnostic

The corrected GEN2 canary passed the collection contract, but **none of the three fixed action-selection rules demonstrated an evaluation gain**. The captured baseline action won all sixteen state/future evaluation pairs. Rollout selection also won 16/16; P0-s0 and F2-s0 each won 15/16. These are eight correlated source decisions from four runs with two evaluation draws each, not sixteen independent full runs and not a policy qualification.

| Frozen selection rule | Changed actions out of eight states | Evaluation wins out of sixteen | Equal-source mean paired gain |
|---|---:|---:|---:|
| Captured source action | — | 16 | reference |
| Rollout mean on k=0,1 | 2 | 16 | 0.0000 |
| P0-s0 mean sampled-MAP prediction | 5 | 15 | −0.0625 |
| F2-s0 mean sampled-MAP prediction | 6 | 15 | −0.0625 |

Both model rules differed adversely on the same retained CARD_REWARD state: source 610084000, decision 71, Act 2 floor 33. They selected Exhume (card 141), while the captured source action selected Juggernaut (card 202). The independent two-draw evaluation produced 1/2 wins for Exhume versus 2/2 for Juggernaut. This is one observed disagreement, insufficient to diagnose a general preference or identify its mechanism. The other seven state contrasts were zero. All four source-level rollout gains were zero; the model source-level gains were −0.25 for source 610084000 and zero for the other three sources.

The action-ranking disagreement is substantial, while outcome resolution is limited. Competing explanations remain: the captured actions are already good for these states; two selection and two evaluation draws are too noisy; the sampled retained states have high win probabilities; or historical feature/teacher mismatch harms the model rules. The four-source result does not distinguish those explanations and supports no training or installation decision.

All rules used only k=0,1 for selection, exact ties favoring the captured source action and then semantic key. The choice artifact was saved and hashed before a separate invocation evaluated k=2,3. Model scores were averages of post-link probabilities across the same two legitimately sampled post-action MAP states, using the ordered 457-feature exports. No realized evaluation MAP was used to rank actions. Historical P0/F2 models still retain E1 latent potion/rarity counters and privileged-teacher provenance; arithmetic parity does not make them qualified fair deployment artifacts.

The collection included four sources, eight states (four CARD_REWARD and four BOSS_RELIC), and 128 valid action/future branches with complete MAP joins. Source CPU cost was 62.46158 seconds, continuation CPU cost 1291.933931 seconds, and summed process wall time 1355.512620 seconds. Every source trajectory was valid. The tree profiles contained 38,267 rows, including 31,428 early nontrivial roots and 637 skipped singleton roots. Profiles bind the configured source/continuation teacher, but lack branch IDs needed to attribute coverage separately to every sibling.

The first verifier receipt remains INVALID because its original-source-only profile seed check contradicted the intentional GEN2 redraw. The narrow provenance correction and five focused tests were independently reviewed before a new `contract_receipt_v2.json` was written. No raw collection files were changed and no games were rerun. The original failed receipt, old verifier, old analysis version, and transition records remain available.

| Artifact | SHA256 |
|---|---|
| corrected contract receipt v2 | `bf2a82d869e809f6cd205a699d434b0f65c76daa3d6c8986a3e4e0619168bcf2` |
| frozen choices | `3a07120ae68e25ba93cda2f3924a20d24f4ecbbc78beaab362f59ae4eb339cc4` |
| independent evaluation result | `efa197f3b737825fae52595005cdaa8bd3fc3a980e77dfbe09785bfbe1e08bbc` |
| reviewed numerical analyzer | `b843837e259c9fbabce330922deb5e496cb712ef435a26b410e5375c9bf75f54` |
| reviewed corrected contract verifier | `8f9c9a790fa8cd350572de516df80120134a8fdb4072de661876fdd945f4d3aa` |

The independently reviewed numerical analyzer changed only its verifier SHA pin after the provenance correction. The separate proposed 32-source K8 tranche retains all three predeclared rules and uses new source seeds; it does not pool the four-source canary into a larger efficacy estimate. That proposal alone authorizes no execution.
