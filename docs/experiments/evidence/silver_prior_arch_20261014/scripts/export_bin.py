import sys, struct, numpy as np, torch
sys.path.insert(0, "/root/arch"); sys.path.insert(0, "/home/user/sts_ai/tools")
import silver_az_mlp as M, arch, argparse
def roots_batch(ss, as_, ts):
    f = open("/root/arch/bench/roots.bin", "rb"); R = struct.unpack("i", f.read(4))[0]
    idx, w, off, act, card, tv, er = [], [], [], [], [], [], []
    n0 = 0
    encs = []
    for r in range(R):
        n = struct.unpack("i", f.read(4))[0]
        s = np.frombuffer(f.read(4 * M.S), np.float32); a = np.frombuffer(f.read(4 * n * M.A), np.float32).reshape(n, M.A)
        t = np.frombuffer(f.read(4 * n), np.int32)
        nz = np.flatnonzero(s); off.append(n0); n0 += len(nz); idx.append(nz); w.append(s[nz] * ss[nz])
        act.append(a * as_); c = a[:, M.CARD_COL].astype(np.int64) + 1; c[(c < 0) | (c >= M.NCARD)] = 0; card.append(c)
        tvv = np.zeros((n, M.NT))
        for e in range(n):
            if t[e] >= 0: tvv[e] = s[M.MON_OFF + t[e] * M.NT: M.MON_OFF + (t[e] + 1) * M.NT] * ts
        tv.append(tvv); er.append(np.full(n, r)); encs.append(min(max(int(round(float(s[1]))), 0), 127))
    T = lambda x, d: torch.from_numpy(np.concatenate(x).astype(d))
    return dict(idx=T(idx, np.int64), off=torch.tensor(off), w=T(w, np.float32), act=T(act, np.float32),
                card=T(card, np.int64), tv=T(tv, np.float32), eroot=T(er, np.int64), nroot=R,
                enc=torch.tensor(encs, dtype=torch.int64))
ck = torch.load(sys.argv[1], weights_only=False); out = sys.argv[2]
a = argparse.Namespace(**ck["args"]); st = {k: v.double().numpy() for k, v in ck["state"].items()}
ss, as_, ts = (np.array(x, np.float64) for x in ck["scales"])
blobs = [st["state.weight"] * ss[:, None]]
if a.tower: blobs += [st["tbias"], st["tproj.weight"].T]
blobs += [st["act.weight"].T * as_[:, None], st["card.weight"] @ st["cardproj.weight"].T, st["tgt.weight"].T * ts[:, None],
          st["act.bias"], st["hidden.0.weight"].T, st["hidden.0.bias"]]
if a.h3: blobs += [st["hidden.1.weight"].T, st["hidden.1.bias"]]
blobs += [st["out.weight"][0], st["out.bias"]]
if a.dot: blobs += [st["du.weight"].T, st["du.bias"], st["dv.weight"].T]
with open(out, "wb") as f:
    enc = getattr(a, "enc_emb", 0) or 0
    f.write(struct.pack("6i", a.h1, a.h2, a.h3, a.tower, a.dot, 1 if enc else 0))
    if enc: blobs.append(st["enc.weight"] @ st["encproj.weight"].T)
    for x in blobs: f.write(np.ascontiguousarray(x, np.float32).tobytes())
# torch reference logits for parity
net = arch.Net(a); net.load_state_dict(ck["state"]); net.eval()
b = roots_batch(ss, as_, ts)
with torch.no_grad(): np.savetxt(out + ".ref", net(b)[0].numpy().astype(np.float64))
