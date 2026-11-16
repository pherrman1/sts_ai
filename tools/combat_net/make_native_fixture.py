#!/usr/bin/env python3
"""Fixture for the native combat net check (combat plan stage 3, 2026-11-08).

usage: make_native_fixture.py OUT_DIR ROWS.jsonl.gz [ROWS.jsonl.gz ...] [--rows N] [--seed S] [--q-head]
       make_native_fixture.py --npz TOOL MODEL.ctn PARITY.npz TAG

First form: picks N silverazgen root rows (wire + edges' semantics), runs them through the training path (wire_encoder
-> tensorize.py -> model.collate, one row at a time) and an untrained net (export_native.py --random 16 2 2 SEED), and
writes OUT_DIR/combat_tok_net_tiny.ctn and OUT_DIR/combat_tok_net_fixture.json for
`combat-tok-net-tool check` (ctest combat_tok_net_parity; with --q-head the files are combat_tok_net_tiny_q.ctn
and combat_tok_net_q_fixture.json, a net with the per-edge Q head, for ctest combat_tok_net_q_parity). The rows cover the rarer groups first (queues, a card
select screen, status pairs, several monsters, potions, a card being played), then a seeded sample.

Second form: forwards the 32 collated rows of a PC parity file (`in_*` tensors and TAG's PyTorch outputs) through
`TOOL forward MODEL.ctn` and prints the largest differences.
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wire_encoder as we  # noqa: E402
import tensorize as tz  # noqa: E402


def root_rows(paths):
    for p in paths:
        with gzip.open(p, "rt") as f:
            for line in f:
                r = json.loads(line)
                if r.get("kind") != "root" or not r.get("wire"):
                    continue
                sem = [e["semantic"] for e in r["edges"]]
                if not sem or any(not s for s in sem) or len(sem) > tz.E_MAX:
                    continue
                yield {"wire": r["wire"], "semantics": sem}


def features(row):
    w = row["wire"]
    x = we.encode(w)
    return {
        "queue": len(x["queues"]) > 0,
        "select": int(w["cardSelect"]["task"]) != 0,
        "status": any(isinstance(s, list) for s in x["pstatus"]),
        "monsters3": len(x["monsters"]) >= 3,
        "potion": any(p for p in x["potions"]),
        "playing": int(w["curCardQueueItem"]["card"]["id"]) != 0,
        "limbo": any(int(c["id"]) for c in w["limbo"]),
        "target": any("/x=-1/" not in s for s in row["semantics"]),
        "selcards": any(not s.endswith("/sel=") for s in row["semantics"]),
    }


def expect_arrays(rows, tiny_net):
    import torch
    import model as M
    with tempfile.TemporaryDirectory() as tmp:
        packed = os.path.join(tmp, "p.jsonl.gz")
        with gzip.open(packed, "wt") as f:
            for r in rows:
                f.write(json.dumps({
                    "x": we.encode(r["wire"]),
                    "edges": [{"a": we.parse_semantic(s), "visits": 1, "q": 0.0} for s in r["semantics"]],
                    "chosen": -1, "value": {"won": True, "endHp": 1, "preMaxHp": 1},
                    "aux": {"hpLoss1": 0.0, "hpLoss2": 0.0}, "seed": 0, "encounter": "X", "act": 1,
                    "room": "MONSTER"}) + "\n")
        arr = os.path.join(tmp, "arr")
        with open(os.devnull, "w") as null:
            old = sys.stdout
            sys.stdout = null
            try:
                tz.main([arr, packed])
            finally:
                sys.stdout = old
        A = M.Arrays(arr)
        out = []
        for i in range(len(rows)):
            b = M.collate(A, [i])
            with torch.no_grad():
                outs = tiny_net(b, want_q=True) if tiny_net.q_on else tiny_net(b)
                lg, vl, ax = outs[:3]
            nc, na = int(b["card_mask"].sum()), int(b["act_mask"].sum())
            sm = b["smap"][0].tolist()
            while sm and sm[-1][0] <= 0:
                sm.pop()
            out.append({
                "glob": b["glob"][0].tolist(), "relics": b["relics"][0].tolist(), "sbits": b["sbits"][0].tolist(),
                "smap": sm, "mcat": b["mcat"][0].tolist(), "mnum": b["mnum"][0].tolist(),
                "nmon": int(b["nmon"][0]), "potions": b["potions"][0].tolist(),
                "queues": b["queues"][0, :int(b["nqueue"][0])].tolist(), "cards": b["cards"][0, :nc].tolist(),
                "actions": b["actions"][0, :na].tolist(), "logits": lg[0, :na].tolist(), "value": vl[0].tolist(),
                "aux": ax[0].tolist(), **({"q": outs[3][0, :na].tolist()} if tiny_net.q_on else {})})
        return out


def make_fixture(args):
    import export_native as ex
    rows = list(root_rows(args.rows_files))
    rng = np.random.default_rng(args.seed)
    order = list(rng.permutation(len(rows)))
    feats = {}
    pick = []
    for want in ("queue", "select", "status", "monsters3", "potion", "playing", "limbo", "target", "selcards"):
        for i in order:
            if i in pick:
                continue
            if i not in feats:
                feats[i] = features(rows[i])
            if feats[i][want]:
                pick.append(i)
                break
    for i in order:
        if len(pick) >= args.rows:
            break
        if i not in pick:
            pick.append(i)
    chosen = [rows[i] for i in sorted(pick)]
    os.makedirs(args.out, exist_ok=True)
    net = ex.random_net(16, 2, 2, args.seed, args.q_head)
    tag = "_q" if args.q_head else ""
    ex.write(net, 16, 2, 2, os.path.join(args.out, f"combat_tok_net_tiny{tag}.ctn"))
    exp = expect_arrays(chosen, net)
    covered = {k: sum(features(r)[k] for r in chosen) for k in features(chosen[0])}
    fixture = {"source": "tools/combat_net/make_native_fixture.py", "seed": args.seed,
               "covered": covered, "rows": [dict(r, expect=e) for r, e in zip(chosen, exp)]}
    with open(os.path.join(args.out, "combat_tok_net_q_fixture.json" if args.q_head else "combat_tok_net_fixture.json"),
              "w") as f:
        json.dump(fixture, f, separators=(",", ":"))
    print(json.dumps({"rows": len(chosen), "candidates": len(rows), "covered": covered}))


def check_npz(tool, model, npz, tag):
    z = np.load(npz)
    n = z["in_glob"].shape[0]
    rows = []
    for i in range(n):
        nc, na = int(z["in_card_mask"][i].sum()), int(z["in_act_mask"][i].sum())
        rows.append({
            "glob": z["in_glob"][i].tolist(), "relics": z["in_relics"][i].tolist(), "sbits": z["in_sbits"][i].tolist(),
            "smap": z["in_smap"][i].tolist(), "mcat": z["in_mcat"][i].tolist(), "mnum": z["in_mnum"][i].tolist(),
            "nmon": int(z["in_nmon"][i]), "potions": z["in_potions"][i].tolist(),
            "queues": z["in_queues"][i, :int(z["in_nqueue"][i])].tolist(), "cards": z["in_cards"][i, :nc].tolist(),
            "actions": z["in_actions"][i, :na].tolist()})
    with tempfile.TemporaryDirectory() as tmp:
        inp, outp = os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
        with open(inp, "w") as f:
            json.dump({"rows": rows}, f)
        subprocess.run([tool, "forward", model, inp, outp], check=True)
        got = json.load(open(outp))["rows"]
    err = {"logits": 0.0, "value": 0.0, "aux": 0.0}
    for i, g in enumerate(got):
        na = int(z["in_act_mask"][i].sum())
        err["logits"] = max(err["logits"], float(np.abs(np.array(g["logits"]) - z[tag + "_policy_logits"][i, :na]).max()))
        err["value"] = max(err["value"], float(np.abs(np.array(g["value"]) - z[tag + "_value_logits"][i]).max()))
        err["aux"] = max(err["aux"], float(np.abs(np.array(g["aux"]) - z[tag + "_aux"][i]).max()))
    print(json.dumps({"tag": tag, "rows": n, "maxAbsErr": err}))
    return 0 if max(err.values()) < 1e-3 else 1


def main(argv):
    if argv and argv[0] == "--npz":
        return check_npz(*argv[1:5])
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("rows_files", nargs="+")
    ap.add_argument("--rows", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20261108)
    ap.add_argument("--q-head", action="store_true", help="a tiny net with the per-edge Q head (Q parity fixture)")
    make_fixture(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
