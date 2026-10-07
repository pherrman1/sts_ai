#!/usr/bin/env python3
"""Freeze the learned-stop V4 teacher for the counterfactual OOC pilot.
usage: python3 make_teacher.py FROZEN_SHA BINARY POLICY.json OUT.json
POLICY.json comes from `one_combat vwinrefreshpolicyspec` under run.sh's environment."""
import hashlib, json, sys
from pathlib import Path
sha_frozen, binary, policy_path, out = sys.argv[1:5]
assert len(sha_frozen) == 40
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
policy = json.loads(Path(policy_path).read_text())
env = {"STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
       "STS_SILVER_EXACT_ROOT_BUDGETS": "0", "STS_SILVER_REUSE_CAP_MODE": "allocated",
       "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
       "STS_SILVER_LEARNED_STOP": "1", "STS_EXECUTABLE_GIT_SHA": sha_frozen,
       "STS_OOC_STRATEGIC_TOK_NN": "selfplay/models/ooc_strategic_tok_final.native",
       "STS_OOC_STRATEGIC_REST": "1", "STS_OOC_STRATEGIC_EVENT": "1", "STS_OOC_STRATEGIC_SHOP": "1",
       "STS_OOC_STRATEGIC_TREASURE": "1", "STS_OOC_STRATEGIC_BOSS_RELIC": "1",
       "STS_OOC_STRATEGIC_MARGIN": "1.0", "STS_COLLECT_KEYS": "0", "STS_REST_WIN": "0"}
teacher = {
    "teacher_id": f"silver-ordinary-fair-learnedstop-v4-oocpilot-{sha_frozen[:8]}",
    "git_sha": sha_frozen, "executable_sha256": sha(binary),
    "combat_backend": "native_silver", "rng_regime": "project_fair",
    "search_configuration": {
        "budget_policy": "learned_stop", "learned_stop_model": "gbt-770201c31f7b",
        "learned_stop_threshold": 0.0323,
        "simulation_budgets": [10000], "exploration_parameter": 25.0,
        "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
        "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
        "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
        "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
        "learned_visit_puct": False, "direct_learned_leaf": False, "adaptive": False},
    "environment": env,
    "model_artifacts": [{"role": a["role"], "path": a["path"], "sha256": a["sha256"]}
                        for a in policy["model_artifacts"]],
    "ooc_policy": policy,
}
Path(out).write_text(json.dumps(teacher, indent=2) + "\n")
