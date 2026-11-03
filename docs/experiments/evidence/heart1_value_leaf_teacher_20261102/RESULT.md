# heart1 value head as a Silver combat leaf: teacher check (B2) result

Pre-registration: [README.md](README.md) (commit `22e79730`, pushed before any score was read). Offline only: no
seeds, no game runs, no GPU. One 4-core cloud container, 2026-11-02 10:50-12:53Z (11:50-13:53 CET).

## Provenance

| item | value |
| --- | --- |
| net | `/mnt/project-files/a20-ppo/heart1.bin`, sha256 `1e92f2a6b2432cc9a2c67c37a7d30566dcfc7a1d45f0877f5ef697078304563f` |
| scorer | `one_combat heart1score` (linux-gcc-release, run from the repo root), built from `d4b4a1bb` (the branch's first base, a stale local `origin/main`), binary sha256 `06f73731…`. Parity: the same command built from `70bd5865` (this branch merged with main `1c35bcb0`, binary `b02da741…`) gives identical values (max abs diff 0.0) on 3,000 random records |
| post-fight states | key-rules-ab (§691) archive `ARCHIVE-units.part00.tar.xz`, 2,048 complete games (R and F arms) |
| Heart entries | §721 `heart.pkl` (4,832 states) |
| build | `build_states.py` → 25,509 states, 328,146 records; `meta.json` sha256 `03b0838c…` |
| scores | value only, `/mnt/project-files/heart1-value-leaf-teacher/values.jsonl.gz` (uncompressed sha256 `c2dba45b…`) and `meta.json.gz`; `gates.json` there too |
| gates | `gates.py meta.json values.jsonl ../potion_price_probe_20261017/analysis.json gates.json` |

Primary set: 20,677 post-fight REWARDS states in acts 1-3. That is every elite (10,590), boss (2,905) and event fight
(1,182), plus 6,000 sampled hallway fights. 19,092 of 20,191 states with a 12-HP secant have a positive secant.
Deviation: the README named elite, boss and hallway fights only. The builder also kept every fight whose ctm
`roomClass` is OTHER (event fights). Without them the verdict does not change: elite, boss and hallway each fail T1
and T5 on their own (`gates.json`, `postfight:<room>`).

heart1's value is a raw shaped return in [0.17, 0.86], not a logit. The pre-registered sigmoid is monotone and nearly
linear on that range. Every number below is the same on the raw value to the stated precision (`gates.json`, `raw`).

## Gates (primary set)

| # | gate | heart1 | pass | gen 1b (2026-10-21) |
| --- | --- | --- | --- | --- |
| T1 | −3 HP lowers V in ≥ 95% | **82.7%** | **FAIL** | 89% |
| T2 | max HP +5 raises V in ≥ 90% | 92.6% | pass | wrong sign |
| T3 | Fairy ≥ 30 HP | 35.0 HP | pass | 13.1 |
| T4 | per-type r ≥ 0.5 with §510 (26 types) | 0.755 | pass | 0.02 |
| T5 | median abs(1-HP price − 1) ≤ ⅓ (secant units) | **1.50** | **FAIL** | n/a |

**Verdict: FAIL (T1, T5).** Per the decision rule, there is no heart1 leaf and no B3.

## Detail

- **HP resolution is the failure.** −1/−3/−6/−12/−24 HP lowers V in 67/83/91/95/96% of states. The 1-HP price in
  units of the state's own 12-HP secant has median 1.03 but p10 −2.9 and p90 +4.3. Single HP steps are noise around
  a correct average. Silver's close leaf decisions turn on 1-3 HP, so a leaf that reads heart1's HP slope would add
  noise exactly there. Per room: T1 is 86% hallway, 84% elite, 71% boss. Per act: 88/81/76% in acts 1/2/3. HP gets
  worse where it matters most.
- **Potions are where heart1 knows something.** Fairy is 35 HP (§510: 44; formula 11 + 0.3 max HP ≈ 33 at 75 max
  HP). Max HP is +1.6 HP per point (p10 +0.2), the right sign, unlike gen 1b and V_A4/V_H.
- **T4 is mostly the Fairy.** Post hoc, not pre-registered: without the Fairy, the per-type correlation with §510 is
  r = 0.37 (rank 0.29, 25 types). It ranks Attack, Blood, Skill and Power high and Elixir and Speed low, like §510.
  But it prices Block, Essence of Steel and Swift at +5 to +9 HP where §510 measured ≈ 0 or below. The median
  non-Fairy potion is 5.8 HP (p10 −1.1, p90 16.4), which is below §510's 7.8 and the formula's 11.
- **Heart entries (descriptive)** fail more: T1 75.8%, T2 70.1%, T5 1.89. T3 (40.5 HP) and T4 (0.77) pass. The
  non-Fairy potion price there is 11.2 HP.

## Reading

- heart1's value head is a better teacher than gen 1b (the earlier heart1-format head checked on 2026-10-21) on
  everything except HP. It knows the Fairy, prices max HP with the right sign, and partly knows which potions matter.
- It does not resolve the 1-3 HP differences a combat leaf has to rank. This matches the literature page's (B):
  critics fit levels, not sibling differences.
- **Inference:** the useful content is a per-type potion table (Fairy ≈ 35, strong vs weak potion types). That is a
  bounded, targeted term in the spirit of B1/§724, not a V leaf. It is untested in play. §510's measured per-type
  prices are the better source for such a table, and per-type potion weights were never gated.
- Rerun `build_states.py` + `gates.py` on the own A20 PPO critic once it exists. Its reward is 1{Heart} + PBRS, not
  floor shaping.
