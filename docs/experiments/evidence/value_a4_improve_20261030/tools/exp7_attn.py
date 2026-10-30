"""Philipp 12:39Z: heart1-like token encoding + attention. Typed tokens from tools/heart_record_encoder.py (deck, relics,
potions, map ahead), entity embedding + kind embedding + attrs -> 2-layer transformer encoder -> attention pool,
concat with dense globals (record dense + HP frac + entry-CTM logits + deck aggregates, standardized) -> MLP -> logit.
Same CV as exp1-6 (5 folds by seed x 3 reps, dev pool seed % 4 != 3, scored on core entries).
usage: VA4_DATA=DIR exp7_attn.py [core|all] [d_model] [layers]"""
import sys, os, json, pickle, numpy as np, torch, core, feats
from torch import nn
sys.path.insert(0, os.path.join(core.REPO, 'tools'))
import heart_record_encoder as H
torch.set_num_threads(4)
which = sys.argv[1] if len(sys.argv) > 1 else 'all'; DM = int(sys.argv[2]) if len(sys.argv) > 2 else 32; NL = int(sys.argv[3]) if len(sys.argv) > 3 else 1
d = core.build(2); es = core.entries(2); y, n, src = d['y'], d['n'], d['src']
recs = [e['entry']['record'] for e in es]
toks = [H.encode_record(r)[1] for r in recs]
K, Ent, At = H.pack_tokens([{'tokens': t} for t in toks]); mask = K > 0
dense0 = np.array([[v for k, v in H.encode_record(r)[0].items() if k.startswith('dense.')] for r in recs], np.float32)
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
G = np.hstack([dense0, d['X'][:, -1:], cp[:, None], lce, feats.eng(recs), np.c_[src == 'run1', d['strong']]]).astype(np.float32)
pool = (d['seed'] % 4) != 3; dev_core = pool & (src != 'extra')
trainmask = (src != 'extra') if which == 'core' else np.ones(len(y), bool)

class Net(nn.Module):
    def __init__(s, ng):
        super().__init__()
        s.ent = nn.Embedding(1536, DM); s.kind = nn.Embedding(11, DM); s.att = nn.Linear(8, DM)
        L = nn.TransformerEncoderLayer(DM, 4, 2 * DM, dropout=0.1, batch_first=True)
        s.enc = nn.TransformerEncoder(L, NL) if NL > 0 else None
        s.q = nn.Linear(DM, 1); s.g = nn.Sequential(nn.Linear(ng, 64), nn.ReLU())
        s.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(DM + 64, 64), nn.ReLU(), nn.Linear(64, 1))
    def forward(s, k, e, a, m, g):
        h = s.ent(e) + s.kind(k) + s.att(a)
        if s.enc is not None: h = s.enc(h, src_key_padding_mask=~m)
        w = s.q(h).squeeze(-1).masked_fill(~m, -1e9).softmax(-1)
        return s.head(torch.cat([(w.unsqueeze(-1) * h).sum(1), s.g(g)], -1)).squeeze(-1)

def fp(tr, te, iv):
    tr = tr[trainmask[tr]]; iv = iv[trainmask[iv]]
    mu, sd = G[tr].mean(0), G[tr].std(0) + 1e-6; Gs = np.clip((G - mu) / sd, -5, 5).astype(np.float32)
    T = lambda ii: [torch.tensor(x[ii]) for x in (K, Ent, At, mask, Gs)]
    preds = []
    for s in range(2):
        torch.manual_seed(s); net = Net(G.shape[1]); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-2)
        best = (1e9, None, 0); Tv = T(iv); yv = torch.tensor(y[iv], dtype=torch.float32); wv = torch.tensor(n[iv], dtype=torch.float32)
        rng = np.random.default_rng(s)
        for ep in range(60):
            net.train()
            for b in np.array_split(rng.permutation(tr), max(1, len(tr) // 128)):
                Tb = T(b); out = net(*Tb)
                loss = (nn.functional.binary_cross_entropy_with_logits(out, torch.tensor(y[b], dtype=torch.float32), reduction='none') * torch.tensor(n[b], dtype=torch.float32)).sum() / n[b].sum()
                opt.zero_grad(); loss.backward(); opt.step()
            net.eval()
            with torch.no_grad():
                v = float((nn.functional.binary_cross_entropy_with_logits(net(*Tv), yv, reduction='none') * wv).sum() / wv.sum())
            if v < best[0]: best = (v, {k: t.clone() for k, t in net.state_dict().items()}, ep)
            elif ep - best[2] >= 8: break
        net.load_state_dict(best[1]); net.eval()
        with torch.no_grad(): preds.append(torch.sigmoid(net(*T(te))).numpy())
    return np.mean(preds, 0)

P = core.oof(fp, d, pool)
tag = f'ATTN_{which}_d{DM}_l{NL}'
print(tag, json.dumps(core.score(P, d, dev_core)), flush=True)
pickle.dump(P, open(core.D + f'P_{tag}.pkl', 'wb'))
P6 = pickle.load(open(core.D + 'P_exp6.pkl', 'rb'))
for ref in ('GBM_all', 'ENS_all'):
    print(tag, '-', ref, core.paired(core.per_seed_loss(P, d, dev_core), core.per_seed_loss(P6[ref], d, dev_core), d, dev_core))
E3 = (P6['GBM_all'] + P6['LR_all'] + P) / 3
print('ENS3(+attn)', json.dumps(core.score(E3, d, dev_core)), core.paired(core.per_seed_loss(E3, d, dev_core), core.per_seed_loss(P6['ENS_all'], d, dev_core), d, dev_core))
