# Gen-6 gate table: every arm evaluated by tools/silver_az_mlp.py with its own stored scales.
import json, sys
import numpy as np, torch
sys.path.insert(0, "/home/user/sts_ai/tools")
import silver_az_mlp as M
torch.set_num_threads(4)
data = M.Data(sys.argv[1]); arms = dict(a.split("=", 1) for a in sys.argv[3:])
def load(p):
    c = torch.load(p, weights_only=False); n = M.make_net(torch, c["h1"], c["h2"])
    n.load_state_dict(c["state"]); n.eval()
    return n, [np.asarray(s, np.float32) for s in c["scales"]]
nets = {k: load(v) for k, v in arms.items()}
val = data.roots((M.VAL,)); t_all = data.roots((M.TEST,)); t_orig = data.roots((M.TEST,), data.tags[0])
def probs(net, sc, roots, bs=4096):
    out = []
    with torch.no_grad():
        for i in range(0, len(roots), bs):
            b = data.batch(roots[i:i + bs], sc, torch)
            out.append(np.exp(M.group_log_softmax(torch, net(b)[0], b["eroot"], b["nroot"]).numpy()))
    return np.concatenate(out)
rep = {}
pref = probs(*nets["gen5"], t_all)
e_ptr = np.concatenate([[0], np.cumsum(data.r_nedge[t_all])])
for k, (net, sc) in nets.items():
    r = {"val": M.evaluate(torch, net, data, val, sc)["ce"], "fold4_orig": M.evaluate(torch, net, data, t_orig, sc)["ce"],
         "fold4_all": M.evaluate(torch, net, data, t_all, sc)["ce"],
         "fold4_by_source": {t: M.evaluate(torch, net, data, data.roots((M.TEST,), t), sc)["ce"] for t in data.tags}}
    r["tv_vs_gen5_fold4_all"] = float(np.add.reduceat(np.abs(probs(net, sc, t_all) - pref), e_ptr[:-1]).sum() / 2 / len(t_all))
    rep[k] = r; print(k, json.dumps(r), flush=True)
json.dump(rep, open(sys.argv[2], "w"), indent=1)
