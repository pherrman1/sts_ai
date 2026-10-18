"""Export an arch.py checkpoint (128/64-style 2-layer net, optional --enc-emb/--mon-emb) to the
combat_policy_mlp_v1 text format, or v2 with trailing tables (enc / mon_id / mon_dmg), write a
silversynthfeatures-style prefix for the bench roots, and torch reference logits for parity.
usage: export_native.py CKPT.pt OUT.txt NAMES.json ROOTS.bin PREFIX"""
import sys, json, struct, argparse, numpy as np, torch
sys.path.insert(0, "/home/philippherrmann/Documents/sts/gen7-gpu/data")
import silver_az_mlp as M, arch_dev as arch
ck_path, out, names_path, roots_path, prefix = sys.argv[1:6]
ck = torch.load(ck_path, map_location="cpu", weights_only=False)
a = argparse.Namespace(**ck["args"])
assert not a.tower and not a.h3 and not a.dot, "only the factorized 2-layer layout exports"
st = {k: v.double().numpy() for k, v in ck["state"].items()}
ss, as_, ts = (np.array(x, np.float64) for x in ck["scales"])
W = {"state_w": st["state.weight"] * ss[:, None], "action_w": st["act.weight"].T * as_[:, None],
     "card": st["card.weight"] @ st["cardproj.weight"].T, "target_w": st["tgt.weight"].T * ts[:, None],
     "b1": st["act.bias"], "w2": st["hidden.0.weight"], "b2": st["hidden.0.bias"], "w3": st["out.weight"][0],
     "b3": st["out.bias"]}
extra = []
if getattr(a, "enc_emb", 0):
    extra.append(("enc", st["enc.weight"] @ st["encproj.weight"].T))
if getattr(a, "mon_emb", 0):
    d = a.mon_emb
    extra.append(("mon_id", st["monid.weight"] @ st["monproj.weight"][:, :d].T))
    extra.append(("mon_dmg", st["monint.weight"] @ st["monproj.weight"][:, d:].T))   # arch.py "intent" = incoming damage
names = json.load(open(names_path))
with open(out, "w") as f:
    f.write(f"combat_policy_mlp_{'v2' if extra else 'v1'}\nh1 {a.h1}\nh2 {a.h2}\nnstate {M.S}\nnaction {M.A}\nncard {M.NCARD}\nntarget {M.NT}\n")
    for n in names: f.write(f"feat {n}\n")
    for key in ("state_w", "action_w", "card", "target_w", "b1", "w2", "b2", "w3", "b3"):
        f.write(key + "\n" + " ".join(f"{x:.9g}" for x in np.asarray(W[key], np.float32).ravel()) + "\n")
    for key, tab in extra:
        f.write(f"{key} {tab.shape[0]}\n" + " ".join(f"{x:.9g}" for x in np.asarray(tab, np.float32).ravel()) + "\n")
# feature prefix + torch reference over the bench roots
fr = open(roots_path, "rb"); R = struct.unpack("i", fr.read(4))[0]
nnz, idx, val, meta = [], [], [], []
idxb, wb, offb, actb, cardb, tvb, erb, encb, monb = [], [], [], [], [], [], [], [], []
n0 = 0
for r in range(R):
    n = struct.unpack("i", fr.read(4))[0]
    s = np.frombuffer(fr.read(4 * M.S), np.float32); acts = np.frombuffer(fr.read(4 * n * M.A), np.float32).reshape(n, M.A)
    t = np.frombuffer(fr.read(4 * n), np.int32)
    nz = np.flatnonzero(s); nnz.append(len(nz)); idx.append(nz); val.append(s[nz]); meta.append({"k": "state"})
    for e in range(n):
        anz = np.flatnonzero(acts[e]); nnz.append(len(anz)); idx.append(anz + M.S); val.append(acts[e][anz])
        meta.append({"k": "act", "tgt": int(t[e]), "visits": 1})
    offb.append(n0); n0 += len(nz); idxb.append(nz); wb.append(s[nz] * ss[nz]); actb.append(acts * as_)
    c = acts[:, M.CARD_COL].astype(np.int64) + 1; c[(c < 0) | (c >= M.NCARD)] = 0; cardb.append(c)
    tvv = np.zeros((n, M.NT))
    for e in range(n):
        if t[e] >= 0: tvv[e] = s[M.MON_OFF + t[e] * M.NT: M.MON_OFF + (t[e] + 1) * M.NT] * ts
    tvb.append(tvv); erb.append(np.full(n, r))
    encb.append(min(max(int(round(float(s[1]))), 0), arch.ENC_MAX - 1))
    m = np.zeros(10, np.int64)
    for k, col in enumerate(arch.ID_COLS + arch.INTENT_COLS):
        if s[col] != 0: m[k] = int(round(float(s[col]))) + (1 if k < 5 else 0)
    monb.append(np.clip(m, 0, arch.MON_MAX - 1))
np.array(nnz, np.uint32).tofile(prefix + ".nnz"); np.concatenate(idx).astype(np.uint16).tofile(prefix + ".idx")
np.concatenate(val).astype(np.float32).tofile(prefix + ".val")
with open(prefix + ".meta.jsonl", "w") as f:
    for m in meta: f.write(json.dumps(m) + "\n")
T = lambda x, d: torch.from_numpy(np.concatenate(x).astype(d))
b = dict(idx=T(idxb, np.int64), off=torch.tensor(offb), w=T(wb, np.float32), act=T(actb, np.float32),
         card=T(cardb, np.int64), tv=T(tvb, np.float32), eroot=T(erb, np.int64), nroot=R,
         enc=torch.tensor(encb), mon=torch.from_numpy(np.stack(monb)))
net = arch.Net(a); net.load_state_dict(ck["state"]); net.eval()
with torch.no_grad(): np.savetxt(out + ".torch_logits", net(b)[0].numpy().astype(np.float64))
print("exported", out, "roots", R, "tables", [k for k, _ in extra])
