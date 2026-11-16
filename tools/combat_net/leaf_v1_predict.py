#!/usr/bin/env python3
"""Value-net-as-leaf V1: the Q head's per-edge values for the V0 roots, written into copies of leafbench's output.

usage: leaf_v1_predict.py MODEL_DIR TENSOR_DIR OUT_DIR LB.jsonl [LB.jsonl ...]

MODEL_DIR holds model.pt and eval.json (train.py --q-head). TENSOR_DIR is tensorize.py's output for the same roots
as the leafbench files (it needs decision.npy). Each leafbench row is matched on (seed, fight, decision); every edge
that has rollouts gets "qnet", the Q head's value of that edge in Silver score units, from one forward at the root.
A root whose tensorized edge list does not line up with leafbench's (more than E_MAX edges, so tensorize cut and
re-ordered them) or that is missing from TENSOR_DIR is written without qnet and counted. Writes OUT_DIR/<name of
each LB file> and prints the counts as JSON.
"""

import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M  # noqa: E402


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    mdir, tdir, odir, lbs = argv[0], argv[1], argv[2], argv[3:]
    os.makedirs(odir, exist_ok=True)
    cfg = json.load(open(os.path.join(mdir, "eval.json")))["config"]
    A = M.Arrays(tdir)
    if "decision" not in A.a:
        raise SystemExit("TENSOR_DIR has no decision.npy (re-run tensorize.py)")
    caps = A.meta["caps"]
    net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=caps["G_LEN"], m_num=caps["M_NUM"],
                      q_len=caps["Q_LEN"], a_len=caps["A_LEN"], aux=not cfg.get("no_aux", False),
                      value=not cfg.get("no_value", False), qhead=True)
    net.load_state_dict(torch.load(os.path.join(mdir, "model.pt"), map_location="cpu"))
    net.eval()
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    n = A.n
    ao = np.asarray(A.a["act_off"])
    q_all = np.full(int(ao[-1]), np.nan, np.float32)
    nc = np.diff(np.asarray(A.a["card_off"]))
    order = np.argsort(nc, kind="stable")
    with torch.no_grad():
        for s in range(0, n, 512):
            idx = np.sort(order[s:s + 512])
            b = M.collate(A, idx)
            q = net(b, want_q=True)[3].float().numpy()
            for i, r in enumerate(idx):
                k = ao[r + 1] - ao[r]
                q_all[ao[r]:ao[r + 1]] = q[i, :k]
    key = {}
    seeds, fights, decs = (np.asarray(A.a[k]) for k in ("seed", "fight", "decision"))
    for r in range(n):
        key[(int(seeds[r]), int(fights[r]), int(decs[r]))] = r
    cnt = {"rows": 0, "matched": 0, "missing": 0, "edgeMismatch": 0, "edgesWithQ": 0}
    for p in lbs:
        with open(p) as f, open(os.path.join(odir, os.path.basename(p)), "w") as g:
            for line in f:
                row = json.loads(line)
                cnt["rows"] += 1
                r = key.get((row["seed"], row["fight"], row["decision"]))
                if r is None:
                    cnt["missing"] += 1
                elif ao[r + 1] - ao[r] != len(row["edges"]):
                    cnt["edgeMismatch"] += 1
                else:
                    cnt["matched"] += 1
                    for e in row["edges"]:
                        if "rollouts" in e:
                            e["qnet"] = float(q_all[ao[r] + e["e"]])
                            cnt["edgesWithQ"] += 1
                g.write(json.dumps(row) + "\n")
    print(json.dumps(cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
