"""Assemble results.json for the g7f_E #401 Stage 1 audit from the phase outputs.
usage: assemble.py OUT_DIR SCRIPTS_DIR RESULTS.json"""
import sys, json, hashlib, glob, os
od, sd, outp = sys.argv[1:4]
L = lambda f: json.load(open(os.path.join(od, f)))
par, gr, sub = L("parity.json"), L("perm_groups.json"), L("perm_sub.json")
single = L("perm_single.json") if os.path.exists(os.path.join(od, "perm_single.json")) else {"groups": []}
E = L("enum_names.json")
def pretty(c):
    for p, t in (("hd", "card"), ("dr", "card"), ("ds", "card"), ("ex", "card"), ("pot", "potion"), ("r", "relic")):
        if c.startswith(p) and c[len(p):].isdigit():
            return f"{c} ({E[t][int(c[len(p):])]})"
    return c
slim = lambda g: {k: g[k] for k in ("group", "kind", "repeats", "d_ce", "d_top1", "d_value_mse", "d_ce_window", "d_ce_g7a4",
                                    "d_top1_window", "d_top1_g7a4", "d_ce_by_tag", "repeat_spread_d_ce", "per_repeat")}
res = {
 "model": "g7f_E", "issue": "#401 Stage 1 grouped permutation importance",
 "artifact": {"path": "models/combat_policy_mlp_g7f_E.txt (main b5dd5557)", "sha256": par["artifact_sha256"],
              "value_head": "runs/g7f_E/model.pt @ origin/claude/silver-gen7-act4-data 0168b72d (not exported; used only for value MSE)"},
 "data": {"pack": "pack-g7f.npz (sha256 bdaf4f68...) from pack-g7f.npz.gz.part00..02 @ 0168b72d",
          "split": "validation fold r_seed % 5 == 3 (silver_az_mlp.Data / arch_dev.py VAL; the fold train.json reports and early-stopping/best-epoch selection used). Test fold 4 not touched.",
          "roots": gr["baseline"]["roots"], "edges": gr["baseline"]["edges"], "clusters_(source,r_seed)": gr["baseline"]["clusters"],
          "roots_by_tag": gr["baseline"]["roots_by_tag"]},
 "parity": par,
 "baseline": gr["baseline"],
 "metric": "per-root CE of the softmax prior vs search-visit shares (as train.json val); top-1 = argmax prior == argmax visits (first max); value-head MSE vs won*(53+endHp)/100 (roots with a value). d = permuted - baseline (CE up = worse; top1 down = worse).",
 "scheme": {"state": "one random permutation of all 582,140 validation roots per repeat; root r receives the group's raw columns from root pi[r]; encounter/monster-id/intent embeddings and target-slot features recomputed from the permuted raw state",
            "candidate": "roots permuted within strata of equal candidate count (22 singleton roots stay fixed); edge j of root r gets the group's columns (targeting group: also the target slot) of edge j of the partner root; visit labels stay",
            "repeats": "5 (groups, subgroups), 3 (single features)",
            "ci": "95% percentile CI, 1,000 cluster-bootstrap resamples over (source, r_seed) clusters of the per-root delta averaged over repeats; window = orig,x5,g3-g6 (gen-6 window, A0), g7a4 = Act-4 A20 roots"},
 "group_columns": {k: [pretty(c) for c in v] for k, v in gr["group_columns"].items()},
 "groups": [slim(g) for g in sorted(gr["groups"], key=lambda g: -g["d_ce"][0])],
 "subgroups": [slim(g) for g in sorted(sub["groups"], key=lambda g: -g["d_ce"][0])],
 "single_features": [dict(slim(g), name=pretty(g["group"])) for g in sorted(single["groups"], key=lambda g: -g["d_ce"][0])],
 "scripts_sha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in sorted(glob.glob(sd + "/*.py"))},
}
json.dump(res, open(outp, "w"), indent=1)
f = lambda x, d=4: f"{x[0]:+.{d}f} [{x[1]:+.{d}f}, {x[2]:+.{d}f}]"
for sec in ("groups", "subgroups", "single_features"):
    print("==", sec)
    for g in res[sec]:
        print(f"{g.get('name', g['group'])[:60]:60s} {f(g['d_ce'])} t1 {f(g['d_top1'])} v {g['d_value_mse'][0]:+.4f} win {g['d_ce_window'][0]:+.4f} a4 {g['d_ce_g7a4'][0]:+.4f} sd {g['repeat_spread_d_ce'][2]:.5f}")
