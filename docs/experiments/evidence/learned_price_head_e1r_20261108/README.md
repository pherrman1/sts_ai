# E1-R of the learned price head (2026-11-08)

Potion prices from reward luck: every combat reward's potion roll has a known chance, so dropped − chance is a luck
draw without any replay. E1's 8,192 source runs are played again (same games, §764) with the rolls logged.

- `PREREG.md`: question, setup, gates, analysis and decision (frozen before launch).
- `units.txt`: E1's 512 units of 16 source seeds (111780000-111788191; no new seeds).
- `run_unit.sh`: `one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,rewards=1 -` in E1's environment, with
  row checks.
- `campaign.manifest`: code commit, binary, workers (4), share (`/mnt/project-files/learned-price-head/e1r`).
- `BRIEF-worker.md`: the worker brief.
- `analyze.py E1R_UNITS E1_UNITS OUT.json`: gates, boss-reward potion value, Fairy contrast, descriptives.
- `selftest_analyze.py [GAMES]`: synthetic check with the engine's drop rule (recovers the value and the Fairy
  contrast, shows the mid-act attenuation, UNRESOLVED without an effect).

Generator: `apps/one_combat/fight_end_pairs.cpp` (`rewards=`), KB `docs/knowledge-base/research/fight-end-pairs.md`.
