#!/usr/bin/env python3
"""Gen-7f offline sanity gate (PLAN-train.md, fixed before training): g7f_E on its own pack (pack-g7f, active power
features) vs g7_E on its own pack (pack-g7, legacy features), same splits (fold 3 = val, fold 4 = test; Act-4 folds =
sourceSeed % 5). Pass: g7f_E fold-4 CE <= g7_E fold-4 CE + 0.005 on both orig and g7a4.
usage (from the branch root): STS_TOOLS=. python3 gen7f/gate_g7f.py --ref-pack pack-g7.npz --ref runs/g7_E/model.pt \
    --new-pack pack-g7f.npz --new runs/g7f_E/model.pt --device cuda --out gen7f/gate.json"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "gen7"))
os.environ.setdefault("STS_TOOLS", ROOT)
import arch_dev as A
import gate_g7 as G
M = A.M


def main():
    p = argparse.ArgumentParser()
    for k in ("--ref-pack", "--ref", "--new-pack", "--new", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--device", default="cpu"); p.add_argument("--threads", type=int, default=4)
    a = p.parse_args()
    A.torch.set_num_threads(a.threads)
    A.DEV = A.torch.device(a.device)
    res = {}
    for name, pack, model in (("ref", a.ref_pack, a.ref), ("new", a.new_pack, a.new)):
        data = M.Data(pack)
        assert "g7a4" in data.tags, data.tags
        res[name] = G.report(model, data, A.encounter_ids(data), A.monster_ids(data))
        res[name]["pack"] = pack
        del data
    gate = {}
    for src in ("orig", "g7a4"):
        r, n = res["ref"]["test_fold4_by_source"][src]["ce"], res["new"]["test_fold4_by_source"][src]["ce"]
        gate[f"{src}_fold4_ce"] = {"ref": r, "new": n, "limit": r + 0.005, "pass": n <= r + 0.005}
    gate["pass"] = all(v["pass"] for v in gate.values())
    res["gate"] = gate
    json.dump(res, open(a.out, "w"), indent=1)
    print("GATE", json.dumps(gate), flush=True)


if __name__ == "__main__":
    main()
