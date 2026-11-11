"""T3 calibration dump: N_f1 value-class probabilities next to search Q on T1's validation split (h = 1)."""
import json, os, sys
import numpy as np, torch
sys.path.insert(0, os.path.expanduser("~/Documents/sts/t1wt/tools/combat_net"))
import model as M
from train import split_of
T1 = os.path.expanduser("~/Documents/sts/t1"); OUT = f"{T1}/t3cal"
A = M.Arrays(f"{T1}/tensor"); caps = A.meta["caps"]
seeds = np.asarray(A.a["seed"]); val = np.nonzero(split_of(seeds) == 1)[0]
cfg = json.load(open(f"{T1}/out/N_f1/eval.json"))["config"]
net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                  a_len=caps["A_LEN"], aux=not cfg["no_aux"], value=not cfg["no_value"]).cuda().eval()
net.load_state_dict(torch.load(f"{T1}/out/N_f1/model.pt", map_location="cuda"))
nc = np.diff(np.asarray(A.a["card_off"])); order = val[np.argsort(nc[val], kind="stable")]
P = np.zeros((len(val), M.VALUE_BINS + 1), np.float16); pos = {r: k for k, r in enumerate(val)}
nll_sum = 0.0
with torch.no_grad():
    for s in range(0, len(order), 1024):
        idx = order[s:s + 1024]
        b = {k: v.cuda() for k, v in M.collate(A, idx).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            _, vlog, _ = net(b)
        vlog = vlog.float()
        nll_sum += float(torch.nn.functional.cross_entropy(vlog, M.value_class(b["won"], b["endFrac"]), reduction="sum"))
        P[np.searchsorted(val, idx)] = torch.softmax(vlog, -1).cpu().numpy().astype(np.float16)
o = np.asarray(A.a["act_off"]); q = np.asarray(A.a["q"]); qb = np.asarray(A.a["qb"]); vis = np.asarray(A.a["visits"]).astype(np.float64)
n = len(val); rootQ = np.full(n, np.nan, np.float32); rootQb = rootQ.copy(); rootV = np.zeros(n, np.float32)
qBest = rootQ.copy(); vBest = np.zeros(n, np.float32); nE = np.zeros(n, np.int16)
for k, r in enumerate(val):
    a, e = o[r], o[r + 1]; nE[k] = e - a
    v = vis[a:e]; qq = q[a:e]; qqb = qb[a:e]; rootV[k] = v.sum()
    m = (v > 0) & ~np.isnan(qq)
    if m.any(): rootQ[k] = (v[m] * qq[m]).sum() / v[m].sum()
    mb = (v > 0) & ~np.isnan(qqb)
    if mb.any(): rootQb[k] = (v[mb] * qqb[mb]).sum() / v[mb].sum()
    if e > a:
        j = int(np.argmax(v)); qBest[k] = qq[j]; vBest[k] = v[j]
cols = {c: np.asarray(A.a[c])[val] for c in ["won", "endFrac", "score", "hp", "maxHp", "act", "elite_boss", "encounter", "seed", "fight", "multi"]}
pot = np.asarray(A.a["potions"])[val]
npot = (pot >= 2).sum(1).astype(np.int8)   # Potion enum: 0 INVALID (unwritten slot), 1 EMPTY_POTION_SLOT
gx = np.asarray(A.a["glob"])[val, 59 + 15].astype(np.float64)   # glob = slog(global[59] + player[38]); player[15] = gold
gold = np.rint(np.sign(gx) * np.expm1(np.abs(gx))).astype(np.int16)   # float16 slog: +-~0.2 % rounding
ROOMS = np.array(["MONSTER", "ELITE", "BOSS", "OTHER"])
room = ROOMS[np.asarray(A.a["elite_boss"])[val].astype(int)]
np.savez_compressed(f"{OUT}/t3cal_val.npz", row=val.astype(np.int64), p=P, rootQ=rootQ, rootQb=rootQb, rootVisits=rootV,
                    nEdges=nE, npot=npot, gold=gold, room=room, qBest=qBest, visitsBest=vBest, **cols)
json.dump(A.meta, open(f"{OUT}/meta.json", "w"), indent=1)
info = {"rows": int(n), "value_nll": nll_sum / n, "checkpoint": f"{T1}/out/N_f1/model.pt", "split": "h == 1 (train.py split_of)",
        "amp": "bf16", "version": 2, "npot": "count of potion slots with id >= 2 (0 INVALID = unwritten slot, 1 EMPTY_POTION_SLOT)", "gold": "player.gold decoded from glob[:, 74] (float16 slog, rounding about +-0.2 %)", "room": "from elite_boss code (0 MONSTER, 1 ELITE incl. MONSTER_ELITE, 2 BOSS, 3 OTHER); the raw room string is not in the tensor", "code": "tools/combat_net at 2abe6aa7d", "cols": {c: str(cols[c].dtype) for c in cols}}
json.dump(info, open(f"{OUT}/INFO.json", "w"), indent=1); print(json.dumps(info))
