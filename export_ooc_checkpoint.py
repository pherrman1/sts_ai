#!/usr/bin/env python3
"""Export OOC checkpoint model weights for native C++ inference."""
import struct, sys
import numpy as np
import torch

PT = sys.argv[1] if len(sys.argv) > 1 else "selfplay/models/ooc_checkpoint.pt"
OUT = sys.argv[2] if len(sys.argv) > 2 else PT.replace(".pt", ".native")

ckpt = torch.load(PT, map_location="cpu", weights_only=False)
sd = ckpt["state_dict"]
mean = ckpt["mean"].astype(np.float32)
inv = ckpt["inv"].astype(np.float32)

def w(name):
    return sd[name].numpy().astype(np.float32)

# Export weights binary
with open(OUT, "wb") as f:
    f.write(b"OOC_CHKPT_V1")
    f.write(struct.pack("iiii", 1017, 256, 128, 32))
    f.write(mean.tobytes())
    f.write(inv.tobytes())
    for name in [
        "s.0.weight","s.0.bias","s.1.weight","s.1.bias","s.4.weight","s.4.bias",
        "a.0.weight","a.0.bias","a.3.weight","a.3.bias",
        "screen.weight","act_emb.weight",
        "h.0.weight","h.0.bias","h.2.weight","h.2.bias",
    ]:
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

def native_fwd(state_vec, action_bits, screen_id, act_val):
    x = np.clip((np.array(state_vec, np.float32) - mean) * inv, -8, 8)

    # s: Linear(1017,256) -> LayerNorm -> GELU -> Dropout(eval=noop) -> Linear(256,128) -> GELU
    s = lin(x, w("s.0.weight"), w("s.0.bias"), 256)
    s = layer_norm(s, w("s.1.weight"), w("s.1.bias"))
    s = gelu_np(s)
    s = gelu_np(lin(s, w("s.4.weight"), w("s.4.bias"), 128))

    # a: Linear(32,32) -> GELU -> Dropout(eval=noop) -> Linear(32,16)  (no final GELU)
    bits = np.array([(action_bits >> i) & 1 for i in range(32)], np.float32)
    a = gelu_np(lin(bits, w("a.0.weight"), w("a.0.bias"), 32))
    a = lin(a, w("a.3.weight"), w("a.3.bias"), 16)

    scr = w("screen.weight")[screen_id]
    act = w("act_emb.weight")[act_val]
    z = np.concatenate([s, a, scr, act])

    # h: Linear(156,96) -> GELU -> Linear(96,1)
    h = gelu_np(lin(z, w("h.0.weight"), w("h.0.bias"), 96))
    return float(lin(h, w("h.2.weight"), w("h.2.bias"), 1)[0])

# Parity test vs PyTorch
import torch.nn as nn
class Tmp(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(1017,256),nn.LayerNorm(256),nn.GELU(),
                               nn.Dropout(0.2),nn.Linear(256,128),nn.GELU())
        self.a = nn.Sequential(nn.Linear(32,32),nn.GELU(),nn.Dropout(0.2),nn.Linear(32,16))
        self.screen = nn.Embedding(16,8); self.act_emb = nn.Embedding(4,4)
        self.h = nn.Sequential(nn.Linear(156,96),nn.GELU(),nn.Linear(96,1))
    def forward(self, x, b, scr, a):
        return self.h(torch.cat((self.s(x),self.a(b),self.screen(scr),self.act_emb(a)),1))
tmp = Tmp(); tmp.load_state_dict(sd); tmp.eval()

max_err = 0.0
for i in range(32):
    np.random.seed(i); torch.manual_seed(i)
    sv = np.random.randn(1017).astype(np.float32) * 2
    ab = np.random.randint(0, 2**32, dtype=np.uint32)
    si = np.random.randint(0, 16); ai = np.random.randint(0, 4)
    normed = np.clip((sv - mean) * inv, -8, 8).astype(np.float32)
    bits = np.array([(int(ab) >> j) & 1 for j in range(32)], np.float32)
    with torch.no_grad():
        py_v = tmp(torch.from_numpy(normed[None,:]),
                   torch.from_numpy(bits[None,:]),
                   torch.tensor([si]), torch.tensor([ai])).item()
    na_v = native_fwd(sv, ab, si, ai)
    max_err = max(max_err, abs(py_v - na_v))
    assert abs(py_v - na_v) < 5e-3, f"mismatch sample {i}: py={py_v:.6f} native={na_v:.6f}"
print(f"exported {OUT}: 32 parity checks passed (max err {max_err:.2e})")

total = sum(1 for _ in open(OUT, "rb"))  # just rough size
import os
print(f"file size: {os.path.getsize(OUT):,} bytes")
