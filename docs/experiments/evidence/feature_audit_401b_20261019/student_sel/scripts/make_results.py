#!/usr/bin/env python3
"""Merge parity.json, perm_groups.json, perm_subs.json into results.json (issue #401 Stage 1, student_sel)."""
import hashlib, json, sys
S, OUT, SCRIPT = sys.argv[1:4]
sys.argv = ["x", "none", "", "", ""]
src = open(SCRIPT).read()
G = {}
exec(compile(src.split("# ---------------------------------------------------------------- permutation")[1].split("def make_perm")[0], "g", "exec"), G)
par = json.load(open(f"{S}/parity.json")); grp = json.load(open(f"{S}/perm_groups.json")); sub = json.load(open(f"{S}/perm_subs.json"))
summary = {"best_val_kl": 0.052153298056843135, "best_val_top1": 0.9410990403244716}
res = {
    "model": "student_sel", "issue": 401, "stage": 1,
    "artifact": {"deployed": "student_sel.bin", "sha256": "cf6bf7fb7c3147dcc5b106b1a946486e40bf27fee87c57bcc3262b5869d507c7",
                 "evaluated_checkpoint": "student.pt", "student_pt_sha256": "1f96f4bf51ccf6b8a30b0a3af0b6ec7062d6bc4571badddeb1cc46723b1b1773",
                 "source": "origin/claude/heart1-distill-data 5a7245aa results/E_d64_sel_xin/",
                 "note": "student.pt is the torch state dict that export_heart1_weights.py turned into student_sel.bin; parity.txt there shows torch-vs-native max diff 8.8e-6 on 390 records"},
    "code": {"silverbot": "daniel-ziegler/sts_lightspeed 84ab3ea (slaythespire module built locally)",
             "student_inputs.py": "sts_ai main b5dd5557 tools/heart1/student_inputs.py (identical to origin/main)",
             "script_sha256": hashlib.sha256(open(SCRIPT, "rb").read()).hexdigest()},
    "split": "distill.py held-out: capture files with seed % 8 == 7 (16 files: 8 old cap-a0/a20-1080000xx from "
             "/mnt/project-files/heart1-distill w02/w04/w06/w08, 8 new cap-a20-1111561xx from data-select-20261017 w01..w08); "
             "whole runs held out, so disjoint from training rows",
    "metric": "per-row KL(teacher softmax || student softmax) over the row's choice tokens (distill.py kl_rows); top-1 agreement with teacher argmax",
    "parity": {"logged": summary, "reproduced": {k: par[k] for k in ("n", "kl", "top1", "old", "new", "fast_vs_stock_maxdiff")},
               "per_screen": par["per_screen"],
               "note": "training eval used bf16 autocast on CUDA; this is fp32 CPU. Gate.txt native fp32 top-1: old 94.03%, new 94.12% (reproduced 94.04%, 94.12%)."},
    "value_head": par["value_head"],
    "permutation": {"groups_run": {"n_rows": grp["n"], "n_clusters": grp["n_clusters"], "repeats": 5, "baseline": grp["baseline"]},
                    "subfeatures_run": {"n_rows": sub["n"], "n_clusters": sub["n_clusters"], "repeats": 3, "baseline": sub["baseline"]},
                    "bootstrap": "1000 resamples of the 16 run/seed clusters (capture files), ratio of sums",
                    "groups": grp["groups"], "subfeatures": sub["subfeatures"]},
    "group_mapping": {name: {"scheme": spec[0], "stratify_by_count_of": spec[1], "inputs": [k if c is None else f"{k}[{c}]" for k, c in spec[2]]}
                      for name, spec in G["GROUPS"].items()},
    "aliases": {"SEL": "record select_screen_type (written into column 2 of every offered-card token)",
                "CARDS01": "choices.cards.value[..., 0:2] (offered card id, upgrades)",
                "fixed_obs.fixed_observation cols": "0 curHp, 1 maxHp, 2 gold, 3 floorNum, 4 toSelectCount (after boss/asc/keys split out)"},
}
json.dump(res, open(OUT, "w"), indent=1)
