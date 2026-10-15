# Generation-6 self-play data: frozen configuration (2026-10-14)

Philipp 11:14Z: "Yeh let's do gen 6 with 40k" (answering "gen 6 at 40k ... roughly 4 h on 8 workers"); N = 8.
Same as gen 5 (`../gen5/FROZEN.md`; commit f73e6ad7, binary b4586cfc) except:
- Teacher 40,000 sims, prior gen 5 (`../gen5/model/combat_policy_mlp_gen5.txt`, 5e9f975a…9e8a), 128/64.
- Seeds (coordinator): natural 97000000-97000511, perturbed 97001000-97001511.
- Stall rule (as §467's worker): a unit whose one_combat runs > 7,200 s gets a gdb backtrace and is killed (rc 137),
  no rerun (gen 5 at 20k: median unit 700 s, max 2,178 s; expected max at 40k ~4,400 s). Worker runs from a
  sha-checked local copy of worker.sh/env.sh; restart and keep-alive rules as §467's brief.
- Worker-script checks (seeds 74070002-006): stall path (STALL=20 s) gives backtrace + rc 137; normal path (UNITS=4, PER=1, 74070003-006) 4/4 rc 0, 85-546 s, outputs gzipped + manifests.
- Smoke (worker env + timeout wrapper, 1 run each): 74066030 natural rc 0, 434 roots, 302 s; 74066031 perturbed
  rc 0, 500 roots, 560 s; manifests producer f73e6ad7, teacher silver-az-40000-k8-rb0-5e9f975a.
  Seed 74070000 (natural) also run as an extra smoke.
- Outputs per worker: `wWW.tar` + `wWW.DONE.txt` here.
