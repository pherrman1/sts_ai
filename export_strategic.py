#!/usr/bin/env python3
"""Export OOC strategic model weights for native C++ inference."""
import os, struct, sys
import numpy as np
import torch

PT = sys.argv[1] if len(sys.argv) > 1 else "selfplay/models/ooc_strategic.pt"
OUT = sys.argv[2] if len(sys.argv) > 2 else PT.replace(".pt", ".native")

if not os.path.exists(PT):
    print(f"[export-strategic] {PT} not found; skipping export "
          f"(trainer has not produced a checkpoint yet)")
    sys.exit(0)

ckpt = torch.load(PT, map_location="cpu", weights_only=False)
sd = ckpt["state_dict"]
mean = ckpt["mean"].astype(np.float32)
inv = ckpt["inv"].astype(np.float32)
NSTATE = sd["s.0.weight"].shape[1]
assert mean.shape[0] == NSTATE and inv.shape[0] == NSTATE

def w(name):
    return sd[name].numpy().astype(np.float32)

# V3 contract requires the Q head
missing_q = [n for n in ["q.0.weight", "q.0.bias", "q.2.weight", "q.2.bias"] if n not in sd]
if missing_q:
    print(f"[export-strategic] V3 requires the Q head; "
          f"checkpoint is missing keys: {missing_q}")
    sys.exit(1)

# Export weights binary
with open(OUT, "wb") as f:
    f.write(b"OOC_STRAT_V3")
    f.write(struct.pack("iiii", NSTATE, 256, 128, 32))
    f.write(mean.tobytes())
    f.write(inv.tobytes())
    for name in [
        "s.0.weight","s.0.bias","s.1.weight","s.1.bias","s.4.weight","s.4.bias",
        "a_bits.0.weight","a_bits.0.bias","a_bits.3.weight","a_bits.3.bias",
        "a_cat.0.weight","a_cat.0.bias","a_cat.2.weight","a_cat.2.bias",
        "cats.0.weight","cats.1.weight","cats.2.weight","cats.3.weight","cats.4.weight","cats.5.weight",
        "atype.weight","screen.weight",
        "pol.0.weight","pol.0.bias","pol.2.weight","pol.2.bias",
    ]:
        f.write(w(name).tobytes())
    for suffix in ["0.weight", "0.bias", "2.weight", "2.bias"]:
        for h in range(8):
            f.write(w(f"vals.{h}.{suffix}").tobytes())
    for name in ["q.0.weight", "q.0.bias", "q.2.weight", "q.2.bias"]:
        f.write(w(name).tobytes())

# Verify
def gelu_np(x):
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0/np.pi) * (x + 0.044715 * x**3)))

def layer_norm(x, w, b):
    eps = 1e-5
    mu = x.mean(); sigma = x.std()
    return (x - mu) / (sigma + eps) * w + b

def lin(x, w, b, out_dim):
    return x @ w.reshape(out_dim, -1).T + b

def native_fwd(state_vec, action_bits, cats, action_type, screen_id):
    x = np.clip((np.array(state_vec, np.float32) - mean) * inv, -8, 8)

    # s: Linear(NSTATE,256) -> LayerNorm -> GELU -> Dropout(eval=noop) -> Linear(256,128) -> GELU
    s = lin(x, w("s.0.weight"), w("s.0.bias"), 256)
    s = layer_norm(s, w("s.1.weight"), w("s.1.bias"))
    s = gelu_np(s)
    s = gelu_np(lin(s, w("s.4.weight"), w("s.4.bias"), 128))

    # a_bits: Linear(32,32) -> GELU -> Dropout(eval=noop) -> Linear(32,16)  (no final GELU)
    bits = np.array([(action_bits >> i) & 1 for i in range(32)], np.float32)
    b = gelu_np(lin(bits, w("a_bits.0.weight"), w("a_bits.0.bias"), 32))
    b = lin(b, w("a_bits.3.weight"), w("a_bits.3.bias"), 16)

    # a_cat: 6 cat embeddings (idx = clip(int(v)+1,0,511)) + atype embedding (idx = clip(int(t)+1,0,15))
    cat_in = np.concatenate(
        [w(f"cats.{i}.weight")[int(np.clip(cats[i] + 1, 0, 511))] for i in range(6)] +
        [w("atype.weight")[int(np.clip(action_type + 1, 0, 15))]])
    # a_cat: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
    a = gelu_np(lin(cat_in, w("a_cat.0.weight"), w("a_cat.0.bias"), 32))
    a = lin(a, w("a_cat.2.weight"), w("a_cat.2.bias"), 16)

    scr = w("screen.weight")[screen_id]
    z = np.concatenate([s, b, a, scr])

    # pol: Linear(168,96) -> GELU -> Linear(96,1)
    p = gelu_np(lin(z, w("pol.0.weight"), w("pol.0.bias"), 96))
    logit = float(lin(p, w("pol.2.weight"), w("pol.2.bias"), 1)[0])

    # q: Linear(168,96) -> GELU -> Linear(96,1) on the same z concat
    qh = gelu_np(lin(z, w("q.0.weight"), w("q.0.bias"), 96))
    q = float(lin(qh, w("q.2.weight"), w("q.2.bias"), 1)[0])

    # per-screen value heads: Linear(128,64) -> GELU -> Linear(64,1)
    vs = []
    for h in range(8):
        v = gelu_np(lin(s, w(f"vals.{h}.0.weight"), w(f"vals.{h}.0.bias"), 64))
        vs.append(float(lin(v, w(f"vals.{h}.2.weight"), w(f"vals.{h}.2.bias"), 1)[0]))
    return logit, vs, q

# Parity test vs PyTorch
import torch.nn as nn
class Tmp(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(NSTATE,256),nn.LayerNorm(256),nn.GELU(approximate="tanh"),
                               nn.Dropout(0.2),nn.Linear(256,128),nn.GELU(approximate="tanh"))
        self.a_bits = nn.Sequential(nn.Linear(32,32),nn.GELU(approximate="tanh"),nn.Dropout(0.2),nn.Linear(32,16))
        self.a_cat = nn.Sequential(nn.Linear(32,32),nn.GELU(approximate="tanh"),nn.Linear(32,16))
        self.cats = nn.ModuleList([nn.Embedding(512,4) for _ in range(6)])
        self.atype = nn.Embedding(16,8); self.screen = nn.Embedding(16,8)
        self.pol = nn.Sequential(nn.Linear(168,96),nn.GELU(approximate="tanh"),nn.Linear(96,1))
        self.q = nn.Sequential(nn.Linear(168,96),nn.GELU(approximate="tanh"),nn.Linear(96,1))
        self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128,64),nn.GELU(approximate="tanh"),nn.Linear(64,1))
                                   for _ in range(8)])
    def forward(self, x, bits, cat_idx, at, scr):
        s = self.s(x)
        b = self.a_bits(bits)
        cat_emb = torch.cat([self.cats[i](cat_idx[:, i]) for i in range(6)], 1)
        a = self.a_cat(torch.cat((cat_emb, self.atype(at)), 1))
        z = torch.cat((s, b, a, self.screen(scr)), 1)
        p = self.pol(z)
        q = self.q(z)
        vs = torch.stack([self.vals[h](s) for h in range(8)], 1)
        return p, vs, q
tmp = Tmp(); tmp.load_state_dict(sd); tmp.eval()

max_err_logit = 0.0; max_err_val = 0.0; max_err_q = 0.0
for i in range(32):
    np.random.seed(i); torch.manual_seed(i)
    sv = np.random.randn(NSTATE).astype(np.float32) * 2
    ab = np.random.randint(0, 2**32, dtype=np.uint32)
    cv = np.random.randint(0, 511, size=6)
    at = np.random.randint(0, 15); si = np.random.randint(0, 16)
    normed = np.clip((sv - mean) * inv, -8, 8).astype(np.float32)
    bits = np.array([(int(ab) >> j) & 1 for j in range(32)], np.float32)
    with torch.no_grad():
        py_logit, py_vals, py_q = tmp(torch.from_numpy(normed[None,:]),
                                      torch.from_numpy(bits[None,:]),
                                      torch.from_numpy((cv + 1).astype(np.int64)[None,:]),
                                      torch.tensor([at + 1]), torch.tensor([si]))
    na_logit, na_vals, na_q = native_fwd(sv, ab, cv.tolist(), at, si)
    err_logit = abs(py_logit.item() - na_logit)
    err_val = max(abs(py_vals[0, h].item() - na_vals[h]) for h in range(8))
    err_q = abs(py_q.item() - na_q)
    max_err_logit = max(max_err_logit, err_logit); max_err_val = max(max_err_val, err_val)
    max_err_q = max(max_err_q, err_q)
    # float32 accumulation tolerance: 1e-4 for the logit, 2e-4 for the value
    # heads (max over 8 heads) and the Q head (numpy-vs-torch op-order differences).
    assert err_logit < 1e-4 and err_val < 2e-4 and err_q < 2e-4, \
        f"mismatch sample {i}: py_logit={py_logit.item():.6f} native_logit={na_logit:.6f} err_val={err_val:.6f} err_q={err_q:.6f}"
print(f"exported {OUT}: 32 parity checks passed "
      f"(max err logit {max_err_logit:.2e}, value {max_err_val:.2e}, Q {max_err_q:.2e})")

print(f"file size: {os.path.getsize(OUT):,} bytes")
