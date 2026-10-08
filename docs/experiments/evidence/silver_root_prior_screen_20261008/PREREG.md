# Synthetic Silver root prior: 32-pair online screen (pre-registration)

Frozen 2026-10-08 before any screen seed ran. Follows ledger §397 (Gate B pass)
and ASSESSMENT.md section 7. Philipp's go: 2026-10-08 12:58 UTC ("lets go.").

- Code: commit 51937c6a (branch claude/project-thread-jqf7eh), one_combat
  sha256 c3547dc4…, built Release in this container.
- Prior: `prior-natpert.compact.txt` (sha256 573305c4…), exported from the §397
  nat+pert prior with exact margin parity (2,000 rows), and native-vs-offline
  replay parity on 300 test roots (identical runs). Weight w = 400 (§397).
- Seeds: 56003000..56003031 (32), A0, fair play, keys skipped, default OOC
  policy, `bestbench SIMS 32 0 56003000`, OMP outer parallelism over seeds.
- Arms, all with `STS_SILVER_EXACT_ROOT_BUDGETS=1` (flat exact budget, no
  learned stopping, no boss multiplier):
  - A: plain, 2,000 sims.
  - B: prior (`STS_SILVER_ROOT_PRIOR`, weight 400), 2,000 sims.
  - C: plain, 10,000 sims.
- Primary contrast: wins B − A on the same seeds. Secondary: B − C.
- Labels:
  - SCREEN_PASS: B − A ≥ +3 wins and B ≥ C − 2 wins.
  - SCREEN_NEGATIVE: B − A ≤ 0.
  - SCREEN_INCONCLUSIVE: otherwise.
- A pass only justifies proposing a larger paired confirmation (new seeds, size
  agreed with Philipp); it is not a promotion. Nothing ships before the CTM full
  retrain lands; learned stopping is not combined with the prior here.
- Reported alongside: paired win table, mean floor, CPU s/run per arm,
  discordant seeds.
