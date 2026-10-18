#!/usr/bin/env python3
"""Gen-7 offline gate (PLAN.md, fixed before any data): evaluate arch_dev.py checkpoints on the gen-7 pack,
each with its own stored scales, on the same splits (fold 3 = val, fold 4 = test; Act-4 folds = sourceSeed % 5).
Gate: gen 7 fold-4 orig CE <= g6_E fold-4 orig CE + 0.005 AND gen 7 fold-4 g7a4 CE < g6_E fold-4 g7a4 CE.
usage (from the branch root): STS_TOOLS=. python3 gen7/gate_g7.py --pack pack-g7.npz --device cuda \
    --ref results/g6_E/model.pt --new runs/g7_E/model.pt --out gen7/gate.json"""
import argparse, json, os, sys, types
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("STS_TOOLS", ROOT)
import arch_dev as A
torch = A.torch
M = A.M


def load(path):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    a = types.SimpleNamespace(**ck["args"])
    net = A.Net(a)
    net.load_state_dict(ck["state"])
    scales = tuple(np.array(x, np.float32) for x in ck["scales"])
    return a, net.to(A.DEV), scales


def report(path, data, enc, mon):
    a, net, scales = load(path)
    A.ENC = enc if getattr(a, "enc_emb", 0) else None
    A.MON = mon if getattr(a, "mon_emb", 0) else None
    out = {"model": path, "args": {k: getattr(a, k) for k in ("name", "pack", "h1", "h2", "enc_emb", "mon_emb")}}
    out["val_fold3_all"] = A.evaluate(net, data, data.roots((M.VAL,)), scales)
    out["test_fold4_all"] = A.evaluate(net, data, data.roots((M.TEST,)), scales)
    out["test_fold4_by_source"] = {t: A.evaluate(net, data, data.roots((M.TEST,), t), scales) for t in data.tags}
    print(json.dumps(out), flush=True)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True); p.add_argument("--device", default="cpu")
    p.add_argument("--ref", required=True); p.add_argument("--new", required=True)
    p.add_argument("--out", required=True); p.add_argument("--threads", type=int, default=4)
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    A.DEV = torch.device(a.device)
    data = M.Data(a.pack)
    assert "g7a4" in data.tags, data.tags
    enc, mon = A.encounter_ids(data), A.monster_ids(data)
    ref, new = report(a.ref, data, enc, mon), report(a.new, data, enc, mon)
    ro, no = ref["test_fold4_by_source"]["orig"]["ce"], new["test_fold4_by_source"]["orig"]["ce"]
    r4, n4 = ref["test_fold4_by_source"]["g7a4"]["ce"], new["test_fold4_by_source"]["g7a4"]["ce"]
    gate = {"orig_fold4_ce": {"ref": ro, "new": no, "limit": ro + 0.005, "pass": no <= ro + 0.005},
            "g7a4_fold4_ce": {"ref": r4, "new": n4, "pass": n4 < r4}}
    gate["pass"] = gate["orig_fold4_ce"]["pass"] and gate["g7a4_fold4_ce"]["pass"]
    json.dump({"ref": ref, "new": new, "gate": gate}, open(a.out, "w"), indent=1)
    print("GATE", json.dumps(gate), flush=True)


if __name__ == "__main__":
    main()
