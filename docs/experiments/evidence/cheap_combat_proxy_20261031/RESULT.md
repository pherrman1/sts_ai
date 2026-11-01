# Cheap-combat proxy check (roadmap X1): result, 2026-11-01 (§739)

Pre-registration: [PREREG.md](PREREG.md) (frozen in e1f94b4; arms moved to the main binary in 930cd7f2 before any
campaign game was read). Analysis: `analyze.py` as frozen, run on the 6,144 games (`games.csv`, `result.json`).

**Verdict: VALID at Silver 1,000, INCONCLUSIVE at Silver 200.**

## Data

- 1,024 seeds 111382000-111383023 (§691's, USED; replays) × 6 arms; every game rc 0, none missing.
- Binary `d39c2b9895fc6070` (main `6c96c25`), student_sel `cf6bf7fb`, `STS_OOC_MCTS=0` in every arm.
- Cheap arms (R/F × 1000/200): local, one 4-CPU cloud container, 4 lanes; two container restarts, lanes resumed with
  finished seeds skipped (a seed was re-run whole if any of its 4 games was missing).
- Same-runner production control (RP/FP): worker campaign `control/`, 8 workers, `verify_campaign.py`: 1,024 units OK,
  0 missing, 0 bad, 0 duplicates, one run commit `930cd7f27f08`.

## Heart kills, F − R paired over 1,024 seeds (95% seed bootstrap)

| Combat | R | F | D = F − R | Verdict | DiD vs same-runner production | Mean wall per game (R / F) |
|---|---|---|---|---|---|---|
| Silver 1,000 flat | 12.3% | 16.8% | **+4.49 pp [+2.34, +6.64]** | **VALID** | −1.27 pp [−4.39, +1.95] | 18.4 s / 20.5 s |
| Silver 200 flat | 6.7% | 9.1% | +2.34 pp [+0.49, +4.20] | INCONCLUSIVE (point < +3.03) | −3.42 pp [−6.45, −0.39] | 2.9 s / 3.2 s |
| Production (P, this runner) | 19.6% | 25.4% | +5.76 pp [+3.13, +8.50] | (reference) | | 224.9 s / 276.8 s |
| §691 (heartoutcomegen runner) | | | +6.05 pp [+3.42, +8.59] | (pre-registered reference) | | |

Act 3 cleared (floor ≥ 52; this also counts keyless act-3 clears that end at the Act-4 door, so it is not
"reached Act 4"): Silver 1,000 26.1% → 29.3%, +3.22 pp [+0.49, +5.86]; Silver 200 14.0% → 17.0%, +3.03 pp
[+0.78, +5.27]; production 32.3% → 39.3%, +6.93 pp [+4.10, +9.77].

## Reading

- **The runner change is harmless for this effect.** On this runner (bestbench, student_sel alone) production combat
  gives +5.76 pp, within 0.3 pp of §691's +6.05, at similar levels (§691 rigid 20.7%, flexible 26.8%).
- **Silver 1,000 keeps about 78% of the effect** (+4.49 vs +5.76) at about 1/13 of the CPU per pair (39 s vs 502 s).
  Its paired test has nearly the same power per pair (z ≈ 4.1 vs 4.2: weaker Heart rates also mean fewer discordant
  pairs), so for this kind of OOC effect a gate at Silver 1,000 costs ≈ 12× less CPU for the same power
  (Inference: one effect). The DiD excludes neither 0 nor a −4 pp attenuation.
- **Silver 200 shrinks the effect to ~40%** (DiD −3.4 pp, CI excludes 0) and needs ~2.9× the pairs for the same power;
  at 1/82 of the CPU per pair that is still ~29× cheaper per unit of power, but the attenuation means its estimates are
  biased toward 0 and a small effect can vanish. Not a stand-in for production estimates.
- **Scope.** One effect, mostly an act-1 Sapphire-chest choice (§691), an OOC decision whose value may not depend much
  on combat skill. The pass licenses cheap combat for **ranking OOC policy changes**, not for measuring combat changes
  or absolute win rates (levels drop from 19.6-25.4% to 12.3-16.8%). A second effect (e.g. a deck-building one) would
  be needed before trusting it for card or path choices whose value depends on how well fights are played.

## Decision (as pre-registered)

Silver 1,000 VALID → PPO self-play and cheap OOC screens may use flat Silver 1,000 combat; confirm every adopted
change at production combat before it becomes a default. Silver 200: not licensed (INCONCLUSIVE); at most a coarse
pre-screen. Roadmap phase 3 keeps its cheap-combat cost estimate (Silver 1,000 ≈ 39 s per pair of games).

## Cost

Cheap arms 1,024 × 44.9 s ≈ 12.8 core-h; control 1,024 × 501.8 s ≈ 143 core-h. Seeds: none new.
The cheap walls come from one local container and the control's from 8 worker containers (speed varies up to ~3×
across containers), so the 1/13 CPU ratio is approximate; its order is safe.
