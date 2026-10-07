#!/usr/bin/env python3
"""Freeze a #418 Stage 0 combattransitiongen teacher for one built binary.

usage: python3 make_teacher.py ARM BINARY REPO_ROOT OUT.json
ARM is exact10k or learned. git_sha is fixed to the frozen Stage 0 SHA;
executable_sha256 is the given binary (each machine freezes its own build).
"""
import hashlib, json, sys
from pathlib import Path

FROZEN_SHA = "46153506cf183adcf422a0877310caa7747c1782"
arm, binary, repo, out = sys.argv[1:5]
if arm not in ("exact10k", "learned"):
    sys.exit("ARM must be exact10k or learned")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
search = {
    "simulation_budgets": [10000], "exploration_parameter": 25.0,
    "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
    "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
    "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
    "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
    "learned_visit_puct": False, "direct_learned_leaf": False, "adaptive": False,
    "particles": "not_applicable_silver_private_chance_search",
    "belief": "not_applicable_silver_private_chance_search",
}
env = {"STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
       "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
       "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
       "STS_EXECUTABLE_GIT_SHA": FROZEN_SHA}
if arm == "learned":
    search.update(budget_policy="learned_stop", learned_stop_model="gbt-770201c31f7b",
                  learned_stop_threshold=0.0323)
    env.update(STS_SILVER_EXACT_ROOT_BUDGETS="0", STS_SILVER_LEARNED_STOP="1")
models = [("ooc_floor_value", "models/v_rich_trees.txt"), ("ooc_win_value", "models/v_win_trees.txt")]
teacher = {
    "teacher_id": f"silver-ordinary-fair-{'learnedstop' if arm == 'learned' else 'exact10k'}-ctm-stage0-{FROZEN_SHA[:8]}",
    "git_sha": FROZEN_SHA, "executable_sha256": sha(binary),
    "combat_backend": "native_silver", "rng_regime": "project_fair",
    "search_configuration": search, "environment": env,
    "model_artifacts": [{"role": r, "path": p, "sha256": sha(Path(repo) / p)} for r, p in models],
}
Path(out).write_text(json.dumps(teacher, indent=2) + "\n")
print(out)
