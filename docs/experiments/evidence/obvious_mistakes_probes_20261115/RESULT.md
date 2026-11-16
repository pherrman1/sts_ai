# Paired probes for the four pilot patterns (issue #1056): result

Date: 2026-11-15 23:10 to 2026-11-16 06:50 CET, 8 cloud workers (32 lanes). Ledger: §TBD. Pre-registration:
[PREREG.md](PREREG.md) (frozen in run commit 3c123c6 before the run; prelaunch review J PASS). Descriptive; no gate,
no default change.

## Question

The obvious-mistakes pilot (`../obvious_mistakes_pilot_20261115/RESULT.md`) flagged four out-of-combat patterns where
the PPO actor (net-0420) looked wrong or where its critic seemed to disagree with it: smith instead of rest before the
Act-1 boss, elites at <= 50 % HP, taking Corruption, taking a runic boss relic. Does the alternative give more Heart
kills than the production choice, from the same §782 states and with the same hidden future?

## Run

512 units (128 states per pattern, drawn by hash from §782's 1,024 G16 games, see PREREG), each two full games: A =
the alternative (the actor's best allowed token), B = production, both with the hidden future redrawn by salt 1 after
the decision. Binary 32c21093 (code 6de313e = ebd446b3 + the `ppo:` force key), §775's G16 arm.

- **Validity: 512 of 512 units valid.** No drop, no timeout, no abort, no ineligible unit (every elite state had a
  non-elite path), no invalid unit: both games of every pair replay §782's trace exactly up to the decision, B's
  decision equals §782's and A's forced token differs from it. 512 unique unit tars, 8 DONE.json files with the frozen
  identity (run 3c123c6, code 6de313e, binary 32c21093). Results: [results/summary.json](results/summary.json).
- Mean game wall about 11 min (both arms), about 150 core-hours in all.

## Result (primary: Heart kills, A minus B)

| pattern | pairs | Heart B (production) | Heart A (alternative) | A better : B better | A − B, 95 % | sign p | Holm p | reading |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| smith → rest | 128 | 71 (55.5 %) | 72 (56.2 %) | 18 : 17 | +0.8 pp [−8.3, +9.9] | 1.00 | 1.00 | NOT_SHOWN |
| elite → non-elite path | 128 | 51 (39.8 %) | 40 (31.2 %) | 10 : 21 | −8.6 pp [−17.0, −0.2] | 0.071 | 0.28 | NOT_SHOWN |
| Corruption → other card | 128 | 87 (68.0 %) | 76 (59.4 %) | 13 : 24 | −8.6 pp [−17.8, +0.6] | 0.099 | 0.30 | NOT_SHOWN |
| runic → other relic | 128 | 75 (58.6 %) | 70 (54.7 %) | 14 : 19 | −3.9 pp [−12.7, +4.9] | 0.49 | 0.97 | NOT_SHOWN |

No pattern reads ALTERNATIVE_BETTER or PRODUCTION_BETTER at the pre-registered Holm level. No point estimate favours
the alternative by more than one percentage point; three favour production, two of them by about 9 pp.

## Secondary (descriptive)

| pattern | survive the act, A − B | final floor, A − B | critic at next decision, A − B | critic prefers A | critic sign = outcome sign (discordant pairs) | actor p(production) |
|---|---:|---:|---:|---:|---:|---:|
| smith | +3.9 pp [−1.6, +9.4] | +2.1 [−0.2, +4.4] | −0.005 | 53/128 | 20/35 | 0.98 |
| elite | +3.1 pp [−5.3, +11.5] | +0.2 [−2.7, +3.2] | −0.006 (n 115) | 40/115 | 18/29 | 0.95 |
| corruption | +1.6 pp [−1.5, +4.6] | −0.7 [−2.3, +0.8] | −0.063 [−0.076, −0.049] | 30/128 | 31/37 | 0.93 |
| runic | 0 | −0.9 [−3.0, +1.2] | −0.049 [−0.059, −0.039] | 19/128 | 17/33 | 0.92 |

(Elite: in 13 pairs the production game died in the elite fight itself, in 2 of them the alternative also died in
its next fight; without a later decision there is no critic value, so the critic gap has n 115 and leaves out
exactly the pairs where the elite killed the run.
Runic: the boss relic is taken at the act end, so "survive the act" is the same in both arms by construction.)

## Interpretation (inference)

- **The pilot's actor-critic disagreement does not hold up when measured in pairs.** For Corruption and the runic
  relics the critic, compared state against counterfactual state at the next decision, prefers the production choice
  (Corruption by 0.063, runic by 0.049, in about 80 % of states), so actor and critic agree. The pilot's "the critic
  drops after taking Corruption" was a drop against the pre-decision screen, not a preference against Corruption; the
  alternative card drops it more. On Corruption the critic's sign also matches the realised outcome in 31 of 37
  discordant pairs.
- **None of the four looks like a mistake of the net.** Resting instead of smithing before the Act-1 boss gains a few
  floors on average but no Heart kills (+0.8 pp). Avoiding the elite at low HP helps act survival slightly (+3 pp, not
  shown) and costs Heart kills (−8.6 pp, not shown after Holm): the elite's relic seems worth the risk in these states.
  Corruption and the runic relics also lean towards the production choice.
- Power: with 128 pairs only differences of about 10 pp are visible. The data rule out large gains from flipping any of
  these four decisions; they do not rule out small effects either way.
- Consequence for the pilot catalogue: the "misconception" entries built on these four patterns are not confirmed; the
  smith, elite, Corruption and runic cases are better read as defensible. Critic drops after a decision are weak
  evidence even with a transition baseline (as the pilot already said); paired forks are the measurement that counts.

## Files

PREREG.md, make_units.py, units.txt, run_unit.sh, analyze.py, campaign.manifest, BRIEF-worker.md;
results/summary.json (per pattern and per unit). Raw unit tars (about 46 MB unpacked) on the project share under
`obvious-mistakes-probes/units/`. Command: `python3 -I analyze.py UNITS_DIR units.txt SRC_DIR results/summary.json`
with UNITS_DIR = the unpacked tars' `out/units` and SRC_DIR = §782's unpacked unit tars.
