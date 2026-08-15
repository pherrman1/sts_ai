# Phase-12 M0 vs M1 autopsy

Date: 2026-08-15  
Branch: `phase12-m0-m1-autopsy`  
Starting/ending source SHA: `9ad865bd52e3d02ac272d122b80618a86756d5c3`  
Status: closed post-hoc analysis; no retraining, gameplay, or new seeds

## Conclusion

M0 and M1 have identical policy supervision: policy CE uses the existing
`chosen` action. Marginalization changed the auxiliary Q supervision only. The
trainer's relevant label target is exactly:

`Q_target = 10 * labelWon + labelHp`.

Across 39,870 matched decision groups, M0/M1 Q-target argmax differed on
16,958 (42.53%); the exact top-two ordering reversed on 3,314 (8.31%). The
change was concentrated in SHOP, EVENT, CARD, TREASURE, and REST. BOSS_RELIC
was nearly unchanged. Mean target separation fell from 6.906 to 5.773.

The strict models propagated only part of that change: predicted-Q argmax
disagreement was 9,679/39,870 (24.28%), while policy-logit argmax disagreement
was 1,954/39,870 (4.90%). Policy entropy was essentially unchanged, and M1's
policy-logit margin was only 0.33 lower overall. M1 was not less faithful to
its own Q targets by all-input Q top-1 (25.66% vs M0 25.55%); strict held-out
metrics likewise do not show a clear M1 Q-learning failure. Therefore the
strongest supported interpretation is **substantial auxiliary-Q relabeling
with limited policy propagation**, making auxiliary-Q/representation coupling
plausible but not proving it caused the weaker 64-seed gameplay point estimate.

The strict gameplay result remains M0 23/64 (35.9%) vs M1 16/64 (25.0%), paired
M1−M0 −10.9pp, CI approximately [−25.0,+3.1]pp. The interval crosses zero.

## Verified semantics and provenance

`fixed` evaluates each action against the detached state's existing hidden
encounter list. `marg` evaluates each action over H hidden-world resamples via
`resampleRemainingActEncounters`; continuation seeds are shared across actions
for common-random-number pairing. The converter independently averages
`labelWon`, `labelHp`, `labelFloor`, and `labelBootstrap` for each action and
regime.

`train_strategic_tok.py` uses `chosen` for policy group cross-entropy and the
absolute Q target above for Q MSE. `q_top1` compares predicted-Q argmax with
Q-target argmax. `val_pol_ce` is policy-logit CE against `chosen`; reported
`margin` is policy-logit top1−top2. `labelFloor` and `labelBootstrap` are
carried through the CSV but do not enter the current policy, value, or Q loss.

Corrected datasets: 210,838 rows and 39,870 groups; screen codes are CARD=1,
EVENT=2, BOSS_RELIC=3, UPGRADE_SELECT=4, TREASURE=5, REST=6, SHOP=7.

Exact strict artifacts were recovered from `/tmp` and hash-verified:

| artifact | path | SHA256 |
|---|---|---|
| strict M0 checkpoint | `/tmp/strict_m0_best_ce.pt` | `e600d1bfebbebb5c6b4059eb7f29dcb1c08b9a318178c43c6d77d5744f369b2e` |
| strict M1 checkpoint | `/tmp/strict_m1_best_ce.pt` | `3c98841018f5c6742238c4c192b22a6d2a35f352615e10e4f8e3941a72fd2102` |
| strict M0 native | `/tmp/strict_m0_best_ce.native` | `97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a` |
| strict M1 native | `/tmp/strict_m1_best_ce.native` | `80995be6e626b7f0278d6ac376d34718863480ef51783f20bd526f3f098c91f0` |

## Label/Q comparison

| screen | groups | Q argmax diff | top-two reversal | M0 margin | M1 margin | M1−M0 mean margin |
|---|---:|---:|---:|---:|---:|---:|
| ALL | 39,870 | 42.53% | 8.31% | 6.906 | 5.773 | −1.132 |
| CARD | 2,832 | 32.95% | 21.79% | 13.268 | 11.080 | −2.188 |
| EVENT | 27,568 | 44.91% | 6.25% | 6.056 | 5.005 | −1.051 |
| BOSS_RELIC | 696 | 1.58% | 1.01% | 8.855 | 8.853 | −0.002 |
| UPGRADE_SELECT | 1,084 | 47.97% | 38.65% | 2.080 | 1.966 | −0.113 |
| TREASURE | 1,294 | 30.68% | 30.68% | 11.874 | 8.458 | −3.416 |
| REST | 3,260 | 26.29% | 10.61% | 9.231 | 8.294 | −0.937 |
| SHOP | 3,136 | 60.62% | 6.51% | 5.398 | 4.641 | −0.757 |

Overall Q-margin Δ quantiles (5/25/50/75/95%) were −16.748/−1.721/0/+0.897/
+11.143: heterogeneous rather than a uniform shift. Overall raw action-row
M1−M0 mean / median / mean absolute change was `labelWon`
+0.00092/0/0.05412, `labelHp` +0.03409/0/7.87884, `labelFloor`
+0.01736/0/1.34098, and `labelBootstrap` +0.00065/0/0.05488. Within-decision
centered mean absolute changes were 0.04483, 6.14232, 1.13598, and 0.05108,
respectively. These centered values show relative action reshaping rather than
global offsets.

## Model comparison on identical inputs

| screen | groups | policy diff | predicted-Q diff | policy margin M0/M1 | entropy M0/M1 |
|---|---:|---:|---:|---:|---:|
| ALL | 39,870 | 4.90% | 24.28% | 5.867 / 5.536 | 0.372 / 0.371 |
| CARD | 2,832 | 11.02% | 17.62% | 0.502 / 0.545 | 0.874 / 0.863 |
| EVENT | 27,568 | 3.90% | 25.97% | 7.428 / 6.852 | 0.263 / 0.271 |
| BOSS_RELIC | 696 | 11.35% | 14.08% | 1.144 / 1.031 | 0.804 / 0.856 |
| UPGRADE_SELECT | 1,084 | 33.30% | 47.79% | 0.545 / 0.540 | 2.242 / 2.246 |
| TREASURE | 1,294 | 2.55% | 3.32% | 0.757 / 1.089 | 0.617 / 0.561 |
| REST | 3,260 | 0.00% | 5.18% | 3.517 / 3.553 | 0.177 / 0.166 |
| SHOP | 3,136 | 3.00% | 38.07% | 4.435 / 5.096 | 0.233 / 0.187 |

All-input predicted-Q top1 fidelity was 25.55% M0 vs 25.66% M1. The strict
held-out trainer metrics are a separate population: Q top1 0.251409 vs
0.249154, policy CE 0.501773 vs 0.498305, and policy top1 0.792266 vs
0.790982. Thus M1's better policy CE cannot explain its weaker gameplay.

## Cross-classification

For each group: A = Q-target argmax same, B = policy argmax same, C = predicted-Q
argmax same.

| A | B | C | groups |
|---|---|---|---:|
| same | same | same | 17,732 |
| same | same | different | 5,187 |
| different | same | same | 4,492 |
| different | same | different | 12,459 |

The remaining four combinations had zero count in the exact cross-tab. The
important pattern is that Q-target changes often propagate to predicted Q, but
policy argmax changes are much rarer.

## Representative cases

Action values below are raw action-bit IDs; they are not manually decoded, so no
gameplay claim is made from them.

| seed/decision | screen | M0 top | M1 top | signal |
|---|---|---|---|---|
| 810000/119 | EVENT | 0/402653184 tied at 82 | 805306368/0 at 65/57 | two actions lose 25 Q points |
| 810000/14 | EVENT | 256/268435456 at 84.00 | 512 at 80.44 | common tops fall 5.33 |
| 810000/21 | EVENT | 0 at 73.21 | 256 at 68.63 | action 256 gains 8.25 |
| 810000/45 | CARD | 0 at 90.71 | 1 at 89.96 | near-tie reversal |
| 810000/51 | EVENT | 134217728/402653184 at 96.45 | 256 at 88.29 | common tops lose 23.5 |
| 810000/61 | EVENT | 805306368 at 88.05 | 512 at 77.42 | top loses 15.17 |
| 810000/73 | EVENT | 512 at 96.14 | 256 at 96.12 | top loses 6.15 |
| 810000/91 | EVENT | 805306368 at 74.24 | 0/402653184 at 67.78 | alternative gains 13.25 |
| 810001/101 | EVENT | 805306368 at 55 | 0 at 53.75 | HP-only reversal |
| 810001/17 | EVENT | 256 at 86.50 | 805306368 at 82.20 | top loses 17.5 HP |

## What this rules out and does not establish

This rules out “M0/M1 policy-target disagreement” as an explanation: policy
labels are identical. It also does not support a global policy-flattening story,
because entropy is unchanged and policy-margin differences are modest. It does
not show a clear M1 failure to learn its Q target. It does support recording
auxiliary-Q interference/representation coupling as a plausible mechanism.

It does **not** establish that any screen or listed action caused a loss, nor
that the −10.9pp point estimate is causal; no gameplay traces were collected
and the confidence interval crosses zero.

## Decision

**STOP the M0/M1 investigation.** Carry this mechanism into the separate general
OOC research review. No M2, retraining, new seeds, gameplay tracing, or label
generation change is justified by this autopsy.