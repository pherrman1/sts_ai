# Heart readiness as an OOC signal: Stage 0 (offline, no seeds), 2026-10-25

**Question (Philipp, 2026-10-25 10:37Z, after §683's weak arrival-to-kill conversion):** "prefer decks that kill the
heart and not just survive the next fight." Stage 0 asks whether a *Heart-readiness* score of the current deck can
carry that preference: score every real fight row as if it were the Heart fight with the deployed Act-4 CTM survival
model (§527, `models/candidates/ctm_act4_survival_trees.txt`): set `encounter = THE_HEART`, and either keep the
actual HP (`rA`) or set HP to max HP (`rF`, deck strength without HP). No pre-registration document; the futility
rule was stated in the thread before the analysis ("if readiness doesn't separate Act-4 converters better than HP
alone, stop"), and the paired test below was added as the stricter check that a search leaf actually needs.

**Data:** 4,096 complete games with CTM rows: §683 (D/MAP/OFF × 1,024) and §676 (A/C × 512). `extract.py` scores
every fight row with a Python copy of the CompactTreeNet evaluator (features from `tools/ctm_act4_survival.py`);
`analyze.py` (across games, 5-fold CV logistic models grouped by seed, seed bootstrap) and `paired.py` (same seed,
two arms). Outputs `analyze.txt`, `stage0.json`, `paired.txt`; intermediate pickles `pickles.sha256`.
X2-B cannot be scored on stored records without replaying games (§685), so the baselines are HP, max HP, deck size,
upgrades, floor and gold, not the M0 leaf.

## 1. Sanity
On the 1,618 real Heart fights the model's own prediction has AUC 0.848 for winning the fight (curHp 0.734); with HP
set to max (`rF`) it is still 0.788, so the score carries deck strength apart from HP.

## 2. Across games: readiness predicts the final kill well beyond HP and deck size
CV AUC for the final Heart kill from the first fight of each act (ΔAUC = full model − HP-only, seed bootstrap):

| state | n | HP + max HP | + deck, upgrades, floor, gold | + readiness `rF` | ΔAUC [95% CI] |
|---|---|---|---|---|---|
| act-2 entry | 3,551 | 0.543 | 0.549 | 0.655 | +0.111 [+0.082, +0.143] |
| act-3 entry | 2,619 | 0.675 | 0.679 | 0.751 | +0.077 [+0.055, +0.098] |
| Act-4 entry (Shield and Spear) | 1,696 | 0.541 | 0.574 | 0.775 | +0.234 [+0.197, +0.270] |
| conversion given Act 4, from act-2 entry | 1,696 | – | 0.502 | 0.612 | +0.110 [+0.075, +0.145] |
| conversion given Act 4, from act-3 entry | 1,696 | – | 0.609 | 0.693 | +0.083 [+0.053, +0.113] |

So the literal futility rule does not fire: readiness separates Act-4 converters much better than HP alone.

## 3. Same seed, two arms: the decision's own deck change does not predict who kills
Paired arms are identical until their first different choice. Concordance = share of kill-discordant pairs in which
the killing arm has the larger value (0.5 = no signal; ties count ½; CI by pair bootstrap):

| where the two decks are compared | kill-discordant pairs | readiness `rF` | HP |
|---|---|---|---|
| first fight after the split | 625 | **0.497 [0.464, 0.532]** | 0.502 |
|  — split in act 1 / 2 / 3 (deck changed) | 155 / 176 / 55 | 0.471 / 0.494 / 0.545 | 0.506 / 0.537 / 0.491 |
|  — three fights later, split in act 1 / 2 / 3 | 294 / 236 / 74 | 0.556 / 0.517 / 0.574 | – |
| act-3 entry (both reached it) | 498 | 0.598 [0.561, 0.636] | 0.591 |
| Act-4 entry (both reached it) | 289 | 0.678 [0.625, 0.732] | 0.514 |

At the point where a search decision changes the deck, the readiness difference between the two children says
nothing about which one later kills the Heart; it becomes predictive only once the two runs have drifted far apart
(act 3, Act 4). The act-3 splits are the one hint (0.545 on 55 pairs, CI wide).

## 4. Mechanism check for §683
At Act-4 entry, MAP's decks are not weaker than OFF's on shared arrivals (Δlogit `rF` −0.02 [−0.12, +0.07], ΔHP −1.1).
The runs that only MAP brings to Act 4 have the same readiness as those only OFF brings (logit 0.195 vs 0.200),
both far below shared arrivals (0.68). **Inference:** MAP's lower kills per arrival (0.574 vs 0.610) is a selection
effect (search rescues weaker runs to Act 4), not search building worse Heart decks.

## Verdict
**STOP for a readiness leaf blend** (exploratory, stated rule plus the paired check). Readiness is a strong
*descriptor* of a run's Heart chances, but the deck differences that one OOC decision creates in acts 1–2, where the
search gain sits (§683), do not predict the kill (concordance 0.47–0.49). A blended leaf would mostly add noise there.
Possible narrow follow-ups (Philipp's call, none started): act-3-only readiness term (55 pairs, needs fresh paired
data), or using readiness as a Heart-strength feature in a future value head rather than as a leaf term.
Seeds: none (existing games only). Knowledge impact: none beyond this entry; no code or default change.
