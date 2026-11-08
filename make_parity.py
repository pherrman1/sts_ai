"""Parity fixture for the C++ combat-net inference path: 32 fixed D1 gate-holdout rows (split 0), their collated
input tensors and the float32 CPU outputs (no autocast) of N_d1 and polonly_d1.
usage: python3 -P make_parity.py REPO D1_ARR N_DIR POLONLY_DIR OUT.npz"""
import sys, json, numpy as np, torch
repo, data, ndir, pdir, out = sys.argv[1:6]
sys.path.insert(0, repo + "/tools/combat_net")
import model as M, train as T
A = M.Arrays(data); caps = A.meta["caps"]
seeds = np.asarray(A.a["seed"]); hold = np.nonzero(T.split_of(seeds) == 0)[0]
rows = np.sort(np.random.default_rng(20261108).choice(hold, 32, replace=False))
b = M.collate(A, rows)
res = {"rows": rows.astype(np.int64)}
for k, v in b.items(): res["in_" + k] = v.numpy()
torch.set_num_threads(1)
for tag, d in (("N_d1", ndir), ("polonly_d1", pdir)):
    cfg = json.load(open(d + "/eval.json"))["config"]
    net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                      a_len=caps["A_LEN"], aux=not cfg["no_aux"], value=not cfg["no_value"])
    net.load_state_dict(torch.load(d + "/model.pt", map_location="cpu")); net.eval()
    with torch.inference_mode():
        lg, vl, ax = net(b)
    res[tag + "_policy_logits"] = lg.float().numpy(); res[tag + "_value_logits"] = vl.float().numpy(); res[tag + "_aux"] = ax.float().numpy()
np.savez(out, **res)
print(json.dumps({k: [list(v.shape), str(v.dtype)] for k, v in res.items()}))
