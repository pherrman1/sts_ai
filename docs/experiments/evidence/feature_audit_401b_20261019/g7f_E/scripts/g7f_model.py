"""Forward pass of the deployed combat_policy_mlp_v2 artifact (models/combat_policy_mlp_g7f_E.txt) in torch,
mirroring arch_dev.Net / export_native.py; the value head (not exported) comes from runs/g7f_E/model.pt.
Inputs are RAW pack values (the artifact folds the per-column scales)."""
import numpy as np, torch

S, A, NCARD, NT = 1766, 22, 372, 9
MON_OFF = 1664
CARD_COL = 4
ENC_MAX = MON_MAX = 128
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INTENT_COLS = [1668, 1677, 1686, 1695, 1704]


def load_artifact(path):
    tok = open(path).read().split()
    assert tok[0] == "combat_policy_mlp_v2"
    h1, h2 = int(tok[2]), int(tok[4])
    names = [tok[13 + 2 * k + 1] for k in range(S + A)]
    i = 13 + 2 * (S + A)
    shapes = {"state_w": (S, h1), "action_w": (A, h1), "card": (NCARD, h1), "target_w": (NT, h1),
              "b1": (h1,), "w2": (h2, h1), "b2": (h2,), "w3": (h2,), "b3": (1,)}
    W = {}
    for key, shape in shapes.items():
        assert tok[i] == key, (tok[i], key)
        n = int(np.prod(shape)); W[key] = np.array(tok[i + 1:i + 1 + n], np.float32).reshape(shape); i += 1 + n
    for key in ("enc", "mon_id", "mon_dmg"):
        assert tok[i] == key, (tok[i], key); rows = int(tok[i + 1]); n = rows * h1
        W[key] = np.array(tok[i + 2:i + 2 + n], np.float32).reshape(rows, h1); i += 2 + n
    assert i == len(tok)
    return {k: torch.from_numpy(v) for k, v in W.items()}, names


def load_value_head(ckpt_path):
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    st = ck["state"]
    return {k: st[k].float() for k in ("v1.weight", "v1.bias", "v2.weight", "v2.bias", "act.bias")}, ck


def derived(st_idx, st_val, st_ptr, n):
    """Per-root encounter id, monster ids/intents (arch_dev.encounter_ids/monster_ids) and the dense
    5x9 monster slot block (target features), all from the sparse raw state."""
    root = np.repeat(np.arange(n), np.diff(st_ptr))
    idx = st_idx
    enc = np.zeros(n, np.int64)
    m = idx == 1
    enc[root[m]] = np.rint(st_val[m]).astype(np.int64)
    enc = np.clip(enc, 0, ENC_MAX - 1)
    mon = np.zeros((n, 10), np.int64)
    for k, c in enumerate(ID_COLS + INTENT_COLS):
        m = idx == c
        mon[root[m], k] = np.rint(st_val[m]).astype(np.int64) + (1 if k < 5 else 0)
    mon = np.clip(mon, 0, MON_MAX - 1)
    blk = np.zeros((n, 5 * NT), np.float32)
    m = (idx >= MON_OFF) & (idx < MON_OFF + 5 * NT)
    blk[root[m], idx[m] - MON_OFF] = st_val[m]
    return enc, mon, blk


class Model:
    def __init__(self, art_path, ckpt_path):
        self.W, self.names = load_artifact(art_path)
        self.V, self.ck = load_value_head(ckpt_path)
        W = self.W
        self.bag = torch.nn.EmbeddingBag(S, W["state_w"].shape[1], mode="sum")
        self.bag.weight.data = W["state_w"].clone()

    @torch.no_grad()
    def forward(self, st_idx, st_val, st_ptr, nedge, e_act, e_tgt, bs=16384):
        """Returns per-edge logits (float32 np) and per-root value predictions."""
        n = len(nedge)
        enc, mon, blk = derived(st_idx, st_val, st_ptr, n)
        e_ptr = np.concatenate([[0], np.cumsum(nedge, dtype=np.int64)])
        W = self.W
        logits = np.empty(e_ptr[-1], np.float32); values = np.empty(n, np.float32)
        for a in range(0, n, bs):
            b = min(n, a + bs)
            s0, s1 = st_ptr[a], st_ptr[b]
            hs = self.bag(torch.from_numpy(st_idx[s0:s1].astype(np.int64)),
                          torch.from_numpy((st_ptr[a:b] - s0).astype(np.int64)),
                          per_sample_weights=torch.from_numpy(st_val[s0:s1].astype(np.float32)))
            hs = hs + W["enc"][torch.from_numpy(enc[a:b])]
            mid = torch.from_numpy(mon[a:b, :5]); mint = torch.from_numpy(mon[a:b, 5:])
            pres = (mid > 0).float().unsqueeze(2)
            hs = hs + ((W["mon_id"][mid] + W["mon_dmg"][mint]) * pres).sum(1)
            # value head (model.pt): vin = relu(hs + act.bias); act.bias == b1
            vin = torch.relu(hs + self.V["act.bias"])
            v = torch.relu(vin @ self.V["v1.weight"].T + self.V["v1.bias"]) @ self.V["v2.weight"].T + self.V["v2.bias"]
            values[a:b] = v.squeeze(1).numpy()
            e0, e1 = e_ptr[a], e_ptr[b]
            act = torch.from_numpy(e_act[e0:e1].astype(np.float32))
            card = e_act[e0:e1, CARD_COL].astype(np.int64) + 1
            card[(card < 0) | (card >= NCARD)] = 0
            eroot = np.repeat(np.arange(b - a), nedge[a:b])
            tgt = e_tgt[e0:e1].astype(np.int64)
            tv = np.zeros((e1 - e0, NT), np.float32)
            has = np.flatnonzero(tgt >= 0)
            if len(has):
                cols = tgt[has][:, None] * NT + np.arange(NT)[None, :]
                tv[has] = blk[a + eroot[has][:, None], cols]
            pre = (hs[torch.from_numpy(eroot)] + W["b1"] + act @ W["action_w"] + W["card"][torch.from_numpy(card)]
                   + torch.from_numpy(tv) @ W["target_w"])
            h2 = torch.relu(torch.relu(pre) @ W["w2"].T + W["b2"])
            logits[e0:e1] = (h2 @ W["w3"] + W["b3"]).numpy()
        return logits, values


def root_stats(logits, share, nedge):
    """Per-root CE vs visit shares, top-1 hit (first maximum of both, as silver_az_mlp.root_metrics)."""
    e_ptr = np.concatenate([[0], np.cumsum(nedge, dtype=np.int64)])
    starts = e_ptr[:-1]
    eroot = np.repeat(np.arange(len(nedge)), nedge)
    lg = logits.astype(np.float64)
    mx = np.maximum.reduceat(lg, starts)
    z = np.add.reduceat(np.exp(lg - mx[eroot]), starts)
    logp = lg - mx[eroot] - np.log(z)[eroot]
    ce = -np.add.reduceat(share * logp, starts)
    pos = np.arange(len(lg)) - starts[eroot]
    big = np.int64(1 << 40)
    am_p = np.minimum.reduceat(np.where(lg == mx[eroot], pos, big), starts)
    smx = np.maximum.reduceat(share, starts)
    am_s = np.minimum.reduceat(np.where(share == smx[eroot], pos, big), starts)
    return ce, (am_p == am_s).astype(np.float64)
