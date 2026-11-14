"""Prior recall dump (offline, 2026-11-14): per validation root (T1 split h == 1) the g7f_E root prior, the T2
distilled net's policy logits (T2's routing: SPEC / BOSS-ALL per boss, P-V_f1 elsewhere), visits, Q, max-backed Q,
gumbelChoice and chosen, per kept edge. Run on the PC (GPU). Writes ~/Documents/sts/t1/t4recall/t4recall.npz."""
import hashlib, json, os, subprocess, sys, tempfile
import numpy as np, torch
CN = os.path.expanduser("~/Documents/sts/t1wt/tools/combat_net")
sys.path.insert(0, CN)
import model as M
from train import split_of
T1 = os.path.expanduser("~/Documents/sts/t1"); OUT = f"{T1}/t4recall"; os.makedirs(OUT, exist_ok=True)
# T2's nets (docs/experiments/evidence/gumbel_distill_t2_20261111/nets.sha256) and the T1 run dirs they came from
NETS = {"pv_f1": ("P-V_f1", "ac5fce0e68345b5ed7dfd3240c2334c6b4a3a92389405aba8a21d1897ed02a10"),
        "bossall": ("BOSS-ALL", "56285bbd607c6ab09bce19a1cf16788582fdad2d20282a636133cba8d4cfe4ff"),
        "spec_CHAMP": ("SPEC_CHAMP", "9afb06b29c2c2d1a7f980e77a3190e4144095f7a7df17c78f00fb89f2fd33dcb"),
        "spec_HEXAGHOST": ("SPEC_HEXAGHOST", "436ba93c44cc6d5be9c76bd325db288a18a5d2c1fb99e728d432b124aeb3d859"),
        "spec_SHIELD_AND_SPEAR": ("SPEC_SHIELD_AND_SPEAR", "53ed5ae1904baab5db99b7a0434eec00981cc4eaf734592589d73366d00f139e"),
        "spec_SLIME_BOSS": ("SPEC_SLIME_BOSS", "124058b9b46872b0396719a7e25bc1688cdd21c21181cfdac3b89f67cb033506"),
        "spec_THE_GUARDIAN": ("SPEC_THE_GUARDIAN", "0c5bcc468b24befd9674b1cc71684b34f318ef0a7f2264df24838660060019c7"),
        "spec_TIME_EATER": ("SPEC_TIME_EATER", "b1c3ecc7b0f264d0500bc912694daa5cf365571ebc03ad24e1e6f772c8aa0bb8")}
ROUTE = {"HEXAGHOST": "spec_HEXAGHOST", "SLIME_BOSS": "spec_SLIME_BOSS", "THE_GUARDIAN": "spec_THE_GUARDIAN",
         "CHAMP": "spec_CHAMP", "TIME_EATER": "spec_TIME_EATER", "SHIELD_AND_SPEAR": "spec_SHIELD_AND_SPEAR",
         "COLLECTOR": "bossall", "AWAKENED_ONE": "bossall", "DONU_AND_DECA": "bossall", "THE_HEART": "bossall"}
prov = {}
for k, (d, sha) in NETS.items():   # identity check: re-export each run dir and compare with T2's .ctn sha256
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([sys.executable, f"{CN}/export_native.py", f"{T1}/out/{d}", f"{td}/x.ctn"], check=True,
                       stdout=subprocess.DEVNULL)
        got = hashlib.sha256(open(f"{td}/x.ctn", "rb").read()).hexdigest()
    prov[k] = {"dir": d, "sha_expected": sha, "sha_reexport": got, "match": got == sha}
    print(k, d, "MATCH" if got == sha else "MISMATCH", flush=True)
A = M.Arrays(f"{T1}/tensor"); caps = A.meta["caps"]; encs = A.meta["encounters"]
seeds = np.asarray(A.a["seed"]); multi = np.asarray(A.a["multi"])
val = np.nonzero((split_of(seeds) == 1) & (multi == 1))[0]
enc = np.asarray(A.a["encounter"])[val]
o = np.asarray(A.a["act_off"]); nc = np.diff(np.asarray(A.a["card_off"]))
logit = np.full(o[-1], np.nan, np.float32)   # per edge of the whole tensor, filled for val rows
def load(d):
    cfg = json.load(open(f"{T1}/out/{d}/eval.json"))["config"]
    net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                      a_len=caps["A_LEN"], aux=not cfg["no_aux"], value=not cfg["no_value"]).cuda().eval()
    net.load_state_dict(torch.load(f"{T1}/out/{d}/model.pt", map_location="cuda")); return net
netof = np.array([ROUTE.get(encs[e], "pv_f1") for e in enc])
for k in NETS:
    rows = val[netof == k]
    if len(rows) == 0: continue
    net = load(NETS[k][0]); order = rows[np.argsort(nc[rows], kind="stable")]
    with torch.no_grad():
        for s in range(0, len(order), 1024):
            idx = np.sort(order[s:s + 1024]); b = {kk: v.cuda() for kk, v in M.collate(A, idx).items()}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lg, _, _ = net(b)
            lg = lg.float().cpu().numpy()
            for i, r in enumerate(idx):
                logit[o[r]:o[r + 1]] = lg[i, :o[r + 1] - o[r]]
    print(k, len(rows), "rows", flush=True); del net; torch.cuda.empty_cache()
ed = np.concatenate([np.arange(o[r], o[r + 1]) for r in val])
off = np.concatenate([[0], np.cumsum(o[val + 1] - o[val])])
g = lambda n: np.asarray(A.a[n])
np.savez_compressed(f"{OUT}/t4recall.npz", row=val, off=off, logit=logit[ed], prior=g("prior")[ed].astype(np.float32),
                    visits=g("visits")[ed].astype(np.float32), q=g("q")[ed].astype(np.float32),
                    qb=g("qb")[ed].astype(np.float32), gumbelChoice=g("gumbelChoice")[val], chosen=g("chosen")[val],
                    act=g("act")[val], elite_boss=g("elite_boss")[val], encounter=enc, seed=seeds[val],
                    net=netof, encounters=np.array(encs))
json.dump({"rows": int(len(val)), "edges": int(len(ed)), "nets": prov, "split": "h == 1, multi == 1",
           "amp": "bf16", "code": "t1wt tools/combat_net"}, open(f"{OUT}/INFO.json", "w"), indent=1)
print("done", len(val), len(ed))
