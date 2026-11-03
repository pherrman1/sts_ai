# heart1 value head as a Silver combat leaf: teacher check (B2), pre-registration

Philipp, 2026-11-02 10:40Z: take the 2026-11-01 research result on using the heart1 net's value head as Silver's
leaf value and try it. The result is
[ppo-and-combat-leaf-literature.md](../../../knowledge-base/research/ppo-and-combat-leaf-literature.md) part (B):
no source supports a raw learned run value as an inner-planner leaf. Its ranked plan is B2 first: the §721 teacher
check on a PPO critic. B3 is a shrunk, clipped V-price leaf behind a default-off flag plus a fight-level gate, and it
runs only if B2 passes. This directory is B2 for the critic that exists today: heart1's value head.

Offline only: no seeds, no game runs, no GPU. CPU in one cloud container.

## Candidate

- Net: `/mnt/project-files/a20-ppo/heart1.bin`, sha256 `1e92f2a6b2432cc9…` (full hash in `RESULT.md`), the
  external PPO net (daniel-ziegler/sts_lightspeed). Its value head was trained on a shaped reward (floor/190 + key
  and Heart bonuses, mostly non-A20 games; see [a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md)).
  So V is not P(Heart kill), but the leaf only uses relative prices, and those are what is checked here.
- Scorer: `one_combat heart1score` built from this branch's main base. The value is read as sigmoid(logit), as in the
  2026-10-21 gen 1b check (`prices.py`, copied unchanged from `/mnt/project-files/silver-leaf-eval/ooc-label-leaf/`).

## States

1. **Primary: post-fight states in acts 1-3.** The first REWARDS-screen state (screen 2) on every fight floor
   (from the `.ctm.jsonl` fight list) of the 2,048 complete key-rules-ab games (§691 campaign, archive
   `/mnt/project-files/key-rules-ab/ARCHIVE-units.part00.tar.xz`). These are the states that Silver's leaf prices at
   fight end. Every elite and boss state, plus a random 6,000 hallway states (seed 20261102).
2. **Secondary: Heart entries.** §721's 4,832 Heart-entry states
   (`/mnt/project-files/combat-gap-probe/va4-teacher/heart/heart.pkl`), where Shield & Spear's leaf would apply.

Perturbations and HP equivalents are those of `prices.py`: HP −1/−3/−6/−12/−24, +6; max HP ±5 with HP fixed;
gold ±50; each held potion removed; Parasite added; Strike removed. ΔV is converted to HP by the state's own
12-HP secant; states whose secant is not positive are dropped from the HP equivalents and counted.

## Gates (fixed before any score is read)

The teacher gate of the 2026-10-21 note (`DESIGN.md` there; gen 1b failed all four), plus the KB's 1-HP
resolution item. Evaluated on the primary set:

| # | Gate | Pass if |
| --- | --- | --- |
| T1 | −3 HP lowers V | in ≥ 95% of states |
| T2 | max HP +5, HP fixed | V rises in ≥ 90% of states |
| T3 | Fairy (removed) | median ≥ 30 HP-eq |
| T4 | per-type potion prices (types with n ≥ 30 here and n ≥ 100 in §510) | Pearson r ≥ 0.5 with §510's `altFloor` HP-eq |
| T5 | 1-HP resolution (KB B2: SE of the 1-HP price ≤ ⅓ of the formula's) | median over states of abs(ΔV(1 HP)/secant − 1) ≤ 1/3 |

**Decision rule:** all five pass → propose B3 (a default-off Silver leaf flag that uses shrunk, clipped heart1
prices at elite/boss fight end, then a fight-level gate; any seeds and workers need Philipp's go). Any gate fails →
no heart1 leaf; the negative result goes to the ledger and the check is rerun on the own A20 PPO critic once it
exists. The Heart-entry set is descriptive.
