# Low-sim Silver root prior: 32-pair online screen (pre-registration)

Frozen 2026-10-09 before any screen seed ran. Philipp's ask 2026-10-09 10:16 UTC
("could we try to run a very low sim search with the prior on 32 seeds? maybe
its not that good but very fast"). Follows §399 (2k screen, negative) and §404
(offline replay: priors help most at 256 sims).

- Code/binary: same as §399, commit 51937c6a, one_combat sha256 c3547dc4…
- Prior: v1 nat+pert `prior-natpert.compact.txt` (sha256 573305c4…), weight 400.
  Only v1 has a native scorer; the encoder (best offline at 256) and v2 do not.
- Seeds: 61000000..61000031 (32, fresh), A0, fair, keys skipped, default OOC
  policy, `bestbench SIMS 32 0 61000000`, OMP outer parallelism, 4 CPUs.
- Arms, all `STS_SILVER_EXACT_ROOT_BUDGETS=1` (flat exact budget):
  - A: plain, 256 sims.
  - B: prior w400, 256 sims.
  - C: plain, 2,000 sims (reference).
- Primary: wins B − A on the same seeds. Secondary: B − C, CPU s/run.
- Labels: SCREEN_PASS B − A ≥ +3 wins; SCREEN_NEGATIVE B − A ≤ 0;
  otherwise SCREEN_INCONCLUSIVE. n=32 detects only large effects.
- A pass only justifies proposing a larger paired confirmation; nothing ships
  before the CTM full retrain. Reported: paired win table, mean floor, wall and
  CPU s/run per arm, discordant seeds.
