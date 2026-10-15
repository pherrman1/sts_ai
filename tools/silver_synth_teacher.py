#!/usr/bin/env python3
"""Freeze the flat exact-10k native Silver teacher for `one_combat silversynthgen`.

usage: python3 tools/silver_synth_teacher.py GIT_SHA BINARY OUT.json

Run from the repository root at GIT_SHA. Pass the teacher's `environment`
to one_combat exactly (the generator checks it)."""
import hashlib
import json
import sys
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    git_sha, binary, out = sys.argv[1:4]
    assert len(git_sha) == 40, "GIT_SHA must be a full 40-character SHA"
    teacher = {
        "teacher_id": f"silver-flat-exact10k-synth-{git_sha[:8]}",
        "git_sha": git_sha,
        "executable_sha256": sha256(binary),
        "combat_backend": "native_silver",
        "rng_regime": "project_fair",
        "search_configuration": {
            "budget_policy": "flat_exact", "simulation_budgets": [10000],
            "exploration_parameter": 25.0, "exploration_parameter_chance": 25.0,
            "chance_widening_c": 3.7028, "chance_widening_alpha": 0.52389,
            "end_turn_widening_c": 3.7028, "end_turn_widening_alpha": 0.52389,
            "reuse_cap_mode": "allocated", "reuse_cap": 32768,
            "sequential_halving": False, "pruning": False, "learned_visit_puct": False,
            "direct_learned_leaf": False, "adaptive": False,
        },
        "environment": {
            "STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
            "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
            "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
            "STS_EXECUTABLE_GIT_SHA": git_sha,
        },
        "model_artifacts": [
            {"role": role, "path": path, "sha256": sha256(path)}
            for role, path in [("ooc_floor_value", "models/v_rich_trees.txt"),
                               ("ooc_win_value", "models/v_win_trees.txt")]
        ],
    }
    Path(out).write_text(json.dumps(teacher, indent=2) + "\n")


if __name__ == "__main__":
    main()
