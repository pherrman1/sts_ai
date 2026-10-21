import sys, os, gzip, json, glob, re, random, torch
R = os.path.expanduser("~/h1distill/silverbot-84ab3ea"); sys.path[:0] = [R, R + "/build", os.path.expanduser("~/Documents/sts/az-gen2-sweep/tools/heart1")]
from silverbot import network
import student_inputs as si
torch.set_num_threads(2)
def trim(rec):
    y0 = rec["obs.mapY"]
    if y0 < 0: return rec
    keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    return {**rec, **{k: [rec[k][i] for i in keep] for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs")}}
files = [f for f in sorted(glob.glob(os.path.expanduser("~/Documents/sts/az-gen2-data/gen2/rows/*.gz"))) if int(re.search(r"-(\d+)\.capture", f).group(1)) % 8 == 7]
rows = []
for f in files:
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        if "record" in r: rows.append(r)
random.seed(0); rows = random.sample(rows, 3000)
def net_of(p):
    sd = torch.load(p, map_location="cpu", weights_only=True); d = sd["norm.w"].shape[0]
    n = si.ExtraInputsNN(network.ModelHP(dim=d, n_layers=sum(k.endswith(".norm1.w") for k in sd), mlp_dim_mult=sd["layers.0.mlp.w1.weight"].shape[0] // d, n_heads=int(sys.argv[2]) if len(sys.argv) > 2 else 4, use_value_head=True))
    n.load_state_dict(sd, strict=False); return n.eval()
def V(net, recs, trim_map=True):
    out = []
    with torch.no_grad():
        for i in range(0, len(recs), 256):
            ch = [trim(r) if trim_map else r for r in recs[i:i+256]]
            b = network.collate_fn([{**r, "chosen_idx": 0, "outcome": 0.0} for r in ch]); b["extra"] = si.extra_batch([{"record": r} for r in ch])
            out.append(torch.sigmoid(net(b)[1]))
    return torch.cat(out)
def mod(r, f):
    r = json.loads(json.dumps(r["record"])); fo = r["obs.fixed_observation"]; f(fo); return r
probes = {
 "curHP +5": lambda fo: fo.__setitem__(0, min(fo[0] + 5, fo[1])),
 "curHP -5": lambda fo: fo.__setitem__(0, max(fo[0] - 5, 1)),
 "maxHP +5 (and curHP +5)": lambda fo: (fo.__setitem__(1, fo[1] + 5), fo.__setitem__(0, fo[0] + 5)),
 "maxHP +5 only": lambda fo: fo.__setitem__(1, fo[1] + 5),
 "gold +50": lambda fo: fo.__setitem__(2, fo[2] + 50),
 "gold -50": lambda fo: fo.__setitem__(2, max(fo[2] - 50, 0)),
}
net = net_of(sys.argv[1]); trim_map = "notrim" not in sys.argv[3:]
base = V(net, [r["record"] for r in rows], trim_map)
for name, f in probes.items():
    recs = [mod(r, f) for r in rows]; changed = torch.tensor([m["obs.fixed_observation"] != r["record"]["obs.fixed_observation"] for m, r in zip(recs, rows)])
    d = (V(net, recs, trim_map) - base)[changed]; up = "+" in name.split()[1] if len(name.split()) > 1 else True
    wrong = (d < 0).float().mean() if "+" in name else (d > 0).float().mean()
    print(f"{name:26s} n={int(changed.sum()):5d}  mean dP(win) {100*d.mean():+.2f}pp  median {100*d.median():+.2f}pp  wrong-sign {100*wrong:.1f}%  worst {100*(d.min() if '+' in name else d.max()):+.2f}pp")
