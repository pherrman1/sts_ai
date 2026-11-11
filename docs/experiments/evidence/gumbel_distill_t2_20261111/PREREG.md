# Gumbel distillation T2: the distilled combat net as Silver prior, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-11 17:20 CET in the distillation thread ("Ja. Wir können vllt den prior anwenden
wenn wir doch mehr als 16 Aktionen haben? Kostet nicht viel aber macht diese Entscheidung vllt besser. Ansonsteng go
auf 40 workern") and 17:24 CET ("Let's go is gut") on the T2-P plan below. The gate reuses §775's seeds (no new
seeds). 40 workers; the coordinator starts them after the independent prelaunch review.

## Question

T1 (§787) distilled §775's G16 + max backup 4 teacher into CombatTokNet policy nets: the generalist P-V_f1 and, per
boss, a fine-tuned specialist (SPEC) or a net fine-tuned on all boss rows (BOSS-ALL). Offline they are closer to the
teacher than the generalist (9 of 11 bosses). Does the distilled policy help Silver play when it replaces the g7f_E
prior where it costs little CPU?

- Below the root, Silver's tree prior (g7f_E MLP, nodes with ≥ 8 visits) decides which lines get searched deeply.
  The teacher's final pick is the prior's top action in only about 45% of D2's roots (thread note 11-11), so a
  better prior there could move budget to the right lines. §773 only tested the net as root prior (NO_GAIN).
- At the Gumbel root, k = 16 candidates are sampled from the prior only when a root has more than 16 actions (1.1%
  of roots, §784); there the prior decides which actions are considered at all (Philipp's suggestion).

Why not the net everywhere: a native forward costs about 2.5 ms against about 50 µs per Silver simulation. The net
at every node with ≥ 8 visits (production) would cost about 6x CPU, and as leaf value about 50x. Leaf value is a
separate later test (it needs a calibration of the value classes to the Silver score first).

## The flags (code commit, default off)

- `STS_SILVER_COMBATNET_TREE_MIN_VISITS=K` (needs `STS_SILVER_COMBATNET_PRIOR_MODEL`): in the whole-run tree prior,
  a non-root node with at least two edges is re-scored once by the net when its simulation count reaches K; its
  prior (until then g7f_E) is replaced by softmax(logits / T) of the net. 0 / unset = off.
- `STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS=N` (needs `STS_SILVER_COMBATNET_PRIOR=1`): the net root prior (§773's
  hook) is used only at roots with at least N prior entries; smaller roots keep g7f_E. Unset = every root, as before.
- `STS_SILVER_COMBATNET_BOSS_MODELS=ENC=path,...`: per encounter (names checked against the engine's encounter
  list, no duplicates) another .ctn net for both uses; other encounters use `STS_SILVER_COMBATNET_PRIOR_MODEL`.
- Startup line `[silver] combat net T2: root prior from N actions, tree prior from K visits, M encounter models`;
  exit line `[silver] combat net T2 forwards: root=R tree=T` (whole process).

With none of them set, search is unchanged (smoke: §775's G16 games replay exactly).

## Arms (`run_unit.sh`)

Both arms: §775's environment (`gumbel_wholerun_20261108/run_unit.sh`): net-0420 (sha 8c0bd16c) as the whole
out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop gbt-0cac7cc64364, g7f_E root and tree prior
(weight 400, K = 8), boss-only prior playouts, Act 4 strong, rollouts with the g7f_E root table (unchanged in T2P).

| arm | combat | games |
|---|---|---|
| G16 | Gumbel root k 16 + max backup (min 4 visits) at a flat 16,000 in every fight (Act 4 strong's budgets in Act 4) | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| T2P | G16, plus: net tree prior at nodes with ≥ 256 visits; net root prior at roots with ≥ 17 actions; temperature 1 | this campaign |

Nets of T2P (T1 seed-1 runs, exported to .ctn on the PC, transfer ref ppo-xfer/t2-nets f9a30123; sha256 in
`nets.sha256` and the manifest; frozen copy on `/mnt/project-files/gumbel-distill/t2/nets/`):

| encounters | net | T1 reason |
|---|---|---|
| HEXAGHOST, SLIME_BOSS, THE_GUARDIAN, CHAMP, TIME_EATER, SHIELD_AND_SPEAR | SPEC (own boss) | SPEC best of the three on that boss |
| COLLECTOR, AWAKENED_ONE, DONU_AND_DECA, THE_HEART | BOSS-ALL | BOSS-ALL best |
| everything else (all non-boss fights, AUTOMATON) | P-V_f1 (generalist) | no specialist gain on AUTOMATON |

K = 256 was chosen before any T2P game for cost (smoke below), not tuned on outcomes. It is not varied in this
campaign.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order; smokes on §775's seeds 111378258,
111378266, 111378280, 111378283 (part of the gated block: these four T2P smoke games are not used, the campaign
plays them again). `units.txt`: first the 32 sentinel units `SEED G16` for 111378256-111378287 (lines 1-32), then
1,024 units `SEED T2P`. One game per unit. `run_unit.sh` refuses any seed outside 111378256-111379289.

## Sentinel and control reuse (§742)

The 32 sentinel games replay §775's G16 games with this binary (new flags unset). A game's fingerprint: rc, abort
flag, the whole .log except the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` and `[silver]
whole-run Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the controls.
Anything else = REUSE_INVALID: no verdict (CONTROL_INVALID); a G16 rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; a copy of §786's with the arm, its env keys, the gate direction and the forward counts changed; `--self-test` passes)

d = Heart kill T2P − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.
Universe: seeds whose T2P unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **gainer** (H0 0, H1 +2 pp), alpha 0.05, beta 0.05, look 64, cap = analysed seeds
(≤ 1,024), seeds gap-free in ascending order. PASS = **PASS**; H0 = **NOT_SHOWN**. At CAP the one-sided 95% seed
bootstrap bounds of mean d (10,000 resamples, seed 20261111) decide: **GAIN** if the lower bound > 0, **NOT_SHOWN** if
the upper bound < +2 pp, else **INCONCLUSIVE**. The 95% CI is always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run and Gumbel simulations per run, T2P / G16,
also corrected for machine speed by the sentinel; net forwards per run (root, tree).

**Expectation (inference, before any campaign game).** Cost: in the smoke T2P did about 17-20 tree forwards per
Gumbel root and cost 1.2-1.4x G16's CPU per root (two comparable seeds). Effect: §773's net root prior
gave no gain, and the policy is near-saturated offline (§787), so a gain of ≥ 2 pp is uncertain; a regression is
possible if the net misjudges states off the teacher's distribution (deep tree nodes are not root states).

**Power (inference).** T2P diverges from G16 at the first node that reaches 256 visits with a different net argmax,
which is in the first fight, so almost every seed is discordant. With §775's 41% Heart rate, the SPRT resolves a
true +4 pp and a true ≤ 0; a true +2 pp will probably reach CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

The primary's nonregression SPRT (−1.5 pp); T2P − D (§775's games) with 95% CI; per arm Heart kill, act-4 reach
(final floor ≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result. PASS or GAIN: the distilled net becomes the tree prior candidate for the next
step (K lower, leaf value as Q-init at heavy nodes, the next distillation round on T2P's own games) — Philipp's
call. NOT_SHOWN: the net prior does not improve the teacher's play at this cost; the leaf-value test is next.
INCONCLUSIVE: report, Philipp decides.

## Cost and schedule

About 1.3 × 146 ≈ 190 lane-hours plus 5 for the sentinel; 40 workers × 4 lanes, queue schedule, about 1.5-2 h
and up to the slowest single game (Heart runs up to about 2-3 h). Share: about 1,100 new files (tars, claims),
about 50 MB; nets 39 MB (frozen copy, 8 files).

## Smoke (local, this binary)

See `results/smoke.txt`: with the new flags unset the G16 arm replays §775's games (4 of 4), T2P is deterministic
(2 of 2 replays identical) and costs 1.2-1.4x G16's CPU per Gumbel root.
