#!/usr/bin/env python3
"""Export OOC strategic model weights for native C++ inference.

Writes the Q_win format (magic OOC_STRAT_V5) when the checkpoint carries the
probability-Q heads (q, q_hp, q_floor): the Q/aux outputs are sigmoided, so
gates read win-probability in [0,1].  Legacy checkpoints (no aux heads) still
export as OOC_STRAT_V3 (raw Q on the 10*labelWon+labelHp scale) so old
deployed artifacts and reference configs remain loadable.  Checkpoints that
also carry the map-DAG encoder (map_enc.* / map_adapter.*, 5.3.2) export as
OOC_STRAT_V6 = V5 layout + the encoder block; the C++ loader then scores
MAP-screen candidates via predictMapActionValue.
"""
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

# Q_win format (V5) iff the auxiliary probability heads are present.
has_aux = all(n in sd for n in ["q_hp.0.weight", "q_floor.0.weight"])
v5 = has_aux
# Map-DAG encoder (V6): V5 layout + the encoder block.
has_map = all(n in sd for n in ["map_enc.room.weight", "map_adapter.2.weight"])
if has_map and not v5:
    print("[export-strategic] map encoder requires the V5 aux heads; aborting")
    sys.exit(1)
v6 = has_map

# Export weights binary
with open(OUT, "wb") as f:
    f.write(b"OOC_STRAT_V6" if v6 else (b"OOC_STRAT_V5" if v5 else b"OOC_STRAT_V3"))
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
    if v5:
        for name in ["q_hp.0.weight", "q_hp.0.bias", "q_hp.2.weight", "q_hp.2.bias",
                     "q_floor.0.weight", "q_floor.0.bias", "q_floor.2.weight", "q_floor.2.bias"]:
            f.write(w(name).tobytes())
    if v6:
        # map-DAG encoder block: node embeddings, update MLP, readout MLP,
        # zero-init residual adapter (order matches OocStrategicNet).
        for name in ["map_enc.room.weight", "map_enc.row.weight",
                     "map_enc.col.weight", "map_enc.burning.weight",
                     "map_enc.update.0.weight", "map_enc.update.0.bias",
                     "map_enc.update.1.weight", "map_enc.update.1.bias",
                     "map_enc.update.3.weight", "map_enc.update.3.bias",
                     "map_enc.norm.weight", "map_enc.norm.bias",
                     "map_enc.readout.0.weight", "map_enc.readout.0.bias",
                     "map_enc.readout.1.weight", "map_enc.readout.1.bias",
                     "map_enc.readout.3.weight", "map_enc.readout.3.bias",
                     "map_adapter.0.weight", "map_adapter.0.bias",
                     "map_adapter.2.weight", "map_adapter.2.bias"]:
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

def silu_np(x):
    return x / (1.0 + np.exp(-x))

def map_enc_np(rooms, edges, special, px, py, chosen_x):
    """Route embedding for one legal child (mirrors FullMapGraphEncoder)."""
    rooms = np.asarray(rooms, np.int64).reshape(15, 7)
    edges = np.asarray(edges, np.int64).reshape(15, 7)
    special = np.asarray(special, np.int64).reshape(15, 7)
    rows = np.arange(15); cols = np.arange(7)
    base = (w("map_enc.room.weight")[rooms]
            + w("map_enc.row.weight")[rows][:, None, :]
            + w("map_enc.col.weight")[cols][None, :, :]
            + w("map_enc.burning.weight")[special])
    graph = np.zeros((15, 7, 32), np.float32)
    graph[14] = base[14]
    for y in range(13, -1, -1):
        node = np.zeros((7, 32), np.float32)
        for x in range(7):
            em = int(edges[y, x])
            children = [graph[y + 1, cx] for cx in range(7) if (em >> cx) & 1]
            if children:
                child = np.stack(children)
                mean = child.mean(0); maximum = child.max(0)
                degree = np.log1p(len(children)).astype(np.float32)
            else:
                mean = np.zeros(32, np.float32); maximum = np.zeros(32, np.float32)
                degree = np.float32(0.0)
            up_in = np.concatenate([base[y, x], mean, maximum, [degree]])
            h = silu_np(layer_norm(lin(up_in, w("map_enc.update.0.weight"),
                                       w("map_enc.update.0.bias"), 64),
                                   w("map_enc.update.1.weight"), w("map_enc.update.1.bias")))
            s = lin(h, w("map_enc.update.3.weight"), w("map_enc.update.3.bias"), 32)
            node[x] = layer_norm(base[y, x] + s, w("map_enc.norm.weight"), w("map_enc.norm.bias"))
        graph[y] = node
    root = py < 0
    row = 0 if root else min(py + 1, 14)
    if root:
        base_x = 0
    else:
        base_x = min(max(px, 0), 6)
    em = int(edges[min(max(py, 0), 14), base_x]) if not root else 0
    sel = []
    for x in range(7):
        if chosen_x >= 0 and x != chosen_x:
            continue
        if root:
            ok = int(edges[0, x]) > 0
        else:
            ok = (py < 14) and ((em >> x) & 1)
        if ok:
            sel.append(graph[row, x])
    if sel:
        nodes = np.stack(sel)
        mean = nodes.mean(0); maximum = nodes.max(0)
    else:
        mean = np.zeros(32, np.float32); maximum = np.zeros(32, np.float32)
    ro_in = np.concatenate([mean, maximum])
    h = silu_np(layer_norm(lin(ro_in, w("map_enc.readout.0.weight"),
                               w("map_enc.readout.0.bias"), 128),
                           w("map_enc.readout.1.weight"), w("map_enc.readout.1.bias")))
    return silu_np(lin(h, w("map_enc.readout.3.weight"), w("map_enc.readout.3.bias"), 96))

def native_fwd(state_vec, action_bits, cats, action_type, screen_id, map_in=None):
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
    if map_in is not None:
        # V6 map-DAG route embedding + zero-init residual adapter (5.3.2).
        rooms, edges, special, px, py, chosen_x = map_in
        map_out = map_enc_np(rooms, edges, special, px, py, chosen_x)
        ad = gelu_np(lin(map_out, w("map_adapter.0.weight"), w("map_adapter.0.bias"), 168))
        z = z + lin(ad, w("map_adapter.2.weight"), w("map_adapter.2.bias"), 168)

    # pol: Linear(168,96) -> GELU -> Linear(96,1)
    p = gelu_np(lin(z, w("pol.0.weight"), w("pol.0.bias"), 96))
    logit = float(lin(p, w("pol.2.weight"), w("pol.2.bias"), 1)[0])

    # q: Linear(168,96) -> GELU -> Linear(96,1) on the same z concat.
    # V5 applies the sigmoid: the gate reads P(win) in [0,1].
    qh = gelu_np(lin(z, w("q.0.weight"), w("q.0.bias"), 96))
    q = float(lin(qh, w("q.2.weight"), w("q.2.bias"), 1)[0])
    if v5:
        q = float(1.0 / (1.0 + np.exp(-q)))

    # aux heads (V5 only): sigmoid probability outputs.
    q_hp = q_floor = None
    if v5:
        hh = gelu_np(lin(z, w("q_hp.0.weight"), w("q_hp.0.bias"), 96))
        q_hp = float(1.0 / (1.0 + np.exp(-float(lin(hh, w("q_hp.2.weight"), w("q_hp.2.bias"), 1)[0]))))
        hh = gelu_np(lin(z, w("q_floor.0.weight"), w("q_floor.0.bias"), 96))
        q_floor = float(1.0 / (1.0 + np.exp(-float(lin(hh, w("q_floor.2.weight"), w("q_floor.2.bias"), 1)[0]))))

    # per-screen value heads: Linear(128,64) -> GELU -> Linear(64,1)
    vs = []
    for h in range(8):
        v = gelu_np(lin(s, w(f"vals.{h}.0.weight"), w(f"vals.{h}.0.bias"), 64))
        vs.append(float(lin(v, w(f"vals.{h}.2.weight"), w(f"vals.{h}.2.bias"), 1)[0]))
    return logit, vs, q, q_hp, q_floor

# Parity test vs PyTorch
import torch.nn as nn
class FullMap(nn.Module):
    """Copy of the trainer's FullMapGraphEncoder for the parity test."""
    def __init__(self):
        super().__init__()
        self.room = nn.Embedding(10, 32); self.row = nn.Embedding(15, 32)
        self.col = nn.Embedding(7, 32); self.burning = nn.Embedding(2, 32)
        self.update = nn.Sequential(nn.Linear(97, 64), nn.LayerNorm(64), nn.SiLU(), nn.Linear(64, 32))
        self.norm = nn.LayerNorm(32)
        self.readout = nn.Sequential(nn.Linear(64, 128), nn.LayerNorm(128), nn.SiLU(), nn.Linear(128, 96), nn.SiLU())
        self.register_buffer("row_ids", torch.arange(15))
        self.register_buffer("col_ids", torch.arange(7))
        self.register_buffer("edge_bits", torch.arange(7))

    @staticmethod
    def masked_pool(nodes, mask):
        weight = mask.float()
        mean = (nodes * weight.unsqueeze(-1)).sum(1) / weight.sum(1, keepdim=True).clamp_min(1.0)
        maximum = nodes.masked_fill(~mask.unsqueeze(-1), -1e9).max(1).values
        maximum = torch.where(mask.any(1, keepdim=True), maximum, torch.zeros_like(maximum))
        return mean, maximum

    def forward(self, rooms, edges, special, position):
        batch = rooms.shape[0]
        rooms = rooms.long().view(batch, 15, 7); edges = edges.long().view(batch, 15, 7)
        special = special.long().view(batch, 15, 7)
        base = (self.room(rooms) + self.row(self.row_ids)[None, :, None, :]
                + self.col(self.col_ids)[None, None, :, :] + self.burning(special))
        adjacency = ((edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        encoded_rows = [base[:, 14]]
        for y in range(13, -1, -1):
            child = encoded_rows[-1]; edge = adjacency[:, y]
            mean = torch.bmm(edge.float(), child) / edge.sum(2, keepdim=True).clamp_min(1.0)
            expanded = child[:, None, :, :].expand(-1, 7, -1, -1)
            maximum = expanded.masked_fill(~edge.unsqueeze(-1), -1e9).max(2).values
            maximum = torch.where(edge.any(2, keepdim=True), maximum, torch.zeros_like(maximum))
            degree = torch.log1p(edge.sum(2, keepdim=True).float())
            encoded_rows.append(self.norm(base[:, y] + self.update(
                torch.cat((base[:, y], mean, maximum, degree), 2))))
        graph = torch.stack(list(reversed(encoded_rows)), 1)
        px = position[:, 0].long().clamp(0, 6); py = position[:, 1].long()
        chosen_x = position[:, 2].long(); safe_y = py.clamp(0, 14)
        batch_ids = torch.arange(batch, device=rooms.device)
        current_edges = edges[batch_ids, safe_y, px]
        child_mask = ((current_edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        root_mask = edges[:, 0] > 0
        future_mask = torch.where((py < 0).unsqueeze(1), root_mask, child_mask)
        singleton = self.col_ids[None, :] == chosen_x.unsqueeze(1)
        future_mask = torch.where((chosen_x >= 0).unsqueeze(1), future_mask & singleton, future_mask)
        future_mask = future_mask & (py < 14).unsqueeze(1)
        future_y = (py + 1).clamp(0, 14)
        future_nodes = graph[batch_ids, future_y]
        mean, maximum = self.masked_pool(future_nodes, future_mask)
        return self.readout(torch.cat((mean, maximum), 1))

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
        if v5:
            self.q_hp = nn.Sequential(nn.Linear(168,96),nn.GELU(approximate="tanh"),nn.Linear(96,1))
            self.q_floor = nn.Sequential(nn.Linear(168,96),nn.GELU(approximate="tanh"),nn.Linear(96,1))
        self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128,64),nn.GELU(approximate="tanh"),nn.Linear(64,1))
                                   for _ in range(8)])
        if v6:
            self.map_enc = FullMap()
            self.map_adapter = nn.Sequential(nn.Linear(96,168),nn.GELU(approximate="tanh"),nn.Linear(168,168))
    def forward(self, x, bits, cat_idx, at, scr, map_in=None):
        s = self.s(x)
        b = self.a_bits(bits)
        cat_emb = torch.cat([self.cats[i](cat_idx[:, i]) for i in range(6)], 1)
        a = self.a_cat(torch.cat((cat_emb, self.atype(at)), 1))
        z = torch.cat((s, b, a, self.screen(scr)), 1)
        if map_in is not None:
            rooms, edges, special, position = map_in
            z = z + self.map_adapter(self.map_enc(rooms, edges, special, position)) \
                    * (scr == 5).float().unsqueeze(1)
        p = self.pol(z)
        q = torch.sigmoid(self.q(z)) if v5 else self.q(z)
        q_hp = q_floor = None
        if v5:
            q_hp = torch.sigmoid(self.q_hp(z))
            q_floor = torch.sigmoid(self.q_floor(z))
        vs = torch.stack([self.vals[h](s) for h in range(8)], 1)
        return p, vs, q, q_hp, q_floor
tmp = Tmp(); tmp.load_state_dict(sd); tmp.eval()

def random_map_input(rng):
    rooms = np.random.randint(0, 10, size=105).astype(np.int64)
    edges = np.zeros(105, np.int64)
    for i in range(105):
        y, x = i // 7, i % 7
        if y < 14:
            m = 0
            for cx in range(7):
                if np.random.rand() < 0.35:
                    m |= 1 << cx
            edges[i] = m
    special = np.zeros(105, np.int64)
    if np.random.rand() < 0.5:
        special[np.random.randint(0, 105)] = 1
    px = int(np.random.randint(0, 7))
    py = int(np.random.randint(-1, 14))
    # chosen child: pick a legal child of (py, px) when possible
    chosen_x = -1
    if py >= 0:
        em = int(edges[min(py, 14) * 7 + px])
        legal = [x for x in range(7) if (em >> x) & 1]
        if legal:
            chosen_x = int(np.random.choice(legal))
    else:
        legal = [x for x in range(7) if edges[x] > 0]
        if legal:
            chosen_x = int(np.random.choice(legal))
    if chosen_x < 0:
        chosen_x = int(np.random.randint(0, 7))
    return rooms, edges, special, px, py, chosen_x

max_err_logit = 0.0; max_err_val = 0.0; max_err_q = 0.0
max_err_qhp = 0.0; max_err_qfloor = 0.0; max_err_map = 0.0
for i in range(32):
    np.random.seed(i); torch.manual_seed(i)
    sv = np.random.randn(NSTATE).astype(np.float32) * 2
    ab = np.random.randint(0, 2**32, dtype=np.uint32)
    cv = np.random.randint(0, 511, size=6)
    at = np.random.randint(0, 15); si = np.random.randint(0, 16)
    map_in = map_in_t = None
    if v6:
        rooms, edges, special, px, py, chosen_x = random_map_input(i)
        si = 5   # MAP screen rows carry the graph input
        map_in = (rooms, edges, special, px, py, chosen_x)
        pos = torch.tensor([[px, py, chosen_x]])
        map_in_t = (torch.from_numpy(rooms)[None, :], torch.from_numpy(edges)[None, :],
                    torch.from_numpy(special)[None, :], pos)
    normed = np.clip((sv - mean) * inv, -8, 8).astype(np.float32)
    bits = np.array([(int(ab) >> j) & 1 for j in range(32)], np.float32)
    with torch.no_grad():
        py_logit, py_vals, py_q, py_qhp, py_qfloor = tmp(torch.from_numpy(normed[None,:]),
                                      torch.from_numpy(bits[None,:]),
                                      torch.from_numpy((cv + 1).astype(np.int64)[None,:]),
                                      torch.tensor([at + 1]), torch.tensor([si]),
                                      map_in_t)
    na_logit, na_vals, na_q, na_qhp, na_qfloor = native_fwd(sv, ab, cv.tolist(), at, si, map_in)
    err_logit = abs(py_logit.item() - na_logit)
    err_val = max(abs(py_vals[0, h].item() - na_vals[h]) for h in range(8))
    err_q = abs(py_q.item() - na_q)
    max_err_logit = max(max_err_logit, err_logit); max_err_val = max(max_err_val, err_val)
    max_err_q = max(max_err_q, err_q)
    if v5:
        max_err_qhp = max(max_err_qhp, abs(py_qhp.item() - na_qhp))
        max_err_qfloor = max(max_err_qfloor, abs(py_qfloor.item() - na_qfloor))
    # float32 accumulation tolerance: 1e-4 for the logit (2e-4 with the V6 map
    # adapter path, whose matmuls add op-order noise; the logit is not the
    # deployed gate output), 2e-4 for the value heads and the Q head.
    logit_tol = 2e-4 if v6 else 1e-4
    assert err_logit < logit_tol and err_val < 2e-4 and err_q < 2e-4, \
        f"mismatch sample {i}: py_logit={py_logit.item():.6f} native_logit={na_logit:.6f} err_val={err_val:.6f} err_q={err_q:.6f}"
    if v5:
        assert max_err_qhp < 2e-4 and max_err_qfloor < 2e-4, \
            f"aux mismatch sample {i}: qhp={max_err_qhp:.6f} qfloor={max_err_qfloor:.6f}"
if v6:
    # Direct map-path parity: the numpy route embedding vs the torch encoder.
    for i in range(8):
        np.random.seed(100 + i); torch.manual_seed(100 + i)
        rooms, edges, special, px, py, chosen_x = random_map_input(100 + i)
        pos = torch.tensor([[px, py, chosen_x]])
        with torch.no_grad():
            torch_map = tmp.map_enc(torch.from_numpy(rooms)[None, :],
                                    torch.from_numpy(edges)[None, :],
                                    torch.from_numpy(special)[None, :], pos)[0]
        numpy_map = map_enc_np(rooms, edges, special, px, py, chosen_x)
        max_err_map = max(max_err_map, float(np.abs(torch_map.numpy() - numpy_map).max()))
    assert max_err_map < 2e-4, f"map-path mismatch: {max_err_map:.6f}"
print(f"exported {OUT} ({'OOC_STRAT_V6 Q_win + map-DAG' if v6 else ('OOC_STRAT_V5 Q_win' if v5 else 'OOC_STRAT_V3')}): "
      f"32 parity checks passed (max err logit {max_err_logit:.2e}, value {max_err_val:.2e}, Q {max_err_q:.2e}"
      + (f", Q_HP {max_err_qhp:.2e}, Q_floor {max_err_qfloor:.2e}" if v5 else "")
      + (f", map {max_err_map:.2e}" if v6 else "") + ")")

print(f"file size: {os.path.getsize(OUT):,} bytes")
