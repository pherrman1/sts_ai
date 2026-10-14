"""Fight-specific fine-tune of the gen-4 Silver MLP prior on one encounter's roots (offline)."""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, '/home/user/sts_ai/tools')
import silver_az_mlp as M
import torch

p = argparse.ArgumentParser()
p.add_argument('sub'); p.add_argument('out'); p.add_argument('--init', required=True)
p.add_argument('--scratch', action='store_true'); p.add_argument('--lr', type=float, default=2e-4)
p.add_argument('--epochs', type=int, default=60); p.add_argument('--patience', type=int, default=8)
p.add_argument('--wd', type=float, default=1e-2); p.add_argument('--dropout', type=float, default=0.35)
p.add_argument('--train-frac', type=float, default=1.0)
p.add_argument('--batch', type=int, default=512); p.add_argument('--seed', type=int, default=0)
p.add_argument('--value-weight', type=float, default=0.1)
a = p.parse_args()
torch.manual_seed(a.seed); rng = np.random.default_rng(a.seed); torch.set_num_threads(int(os.environ.get("NT","2")))
os.makedirs(a.out, exist_ok=True)
d = M.Data(a.sub)
init = torch.load(a.init)
scales = tuple(np.array(x, np.float32) for x in init['scales'])
tr, va, te = d.roots(M.TRAIN), d.roots((M.VAL,)), d.roots((M.TEST,))
if a.train_frac < 1:   # data-scaling: keep a seed-hashed fraction of the NEW (src >= 5) training seeds
    keep = (d.r_src[tr] < 5) | (((d.r_seed[tr] * 2654435761) % 1000) < a.train_frac * 1000)
    tr = tr[keep]

def per_root(net, roots, bs=4096):
    net.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(roots), bs):
            b = d.batch(roots[i:i + bs], scales, torch)
            lp = M.group_log_softmax(torch, net(b)[0], b['eroot'], b['nroot']).numpy()
            sh = b['share'].numpy(); er = b['eroot'].numpy()
            ce = -np.bincount(er, weights=sh * lp, minlength=b['nroot'])
            top = np.zeros(b['nroot'])
            for k in range(b['nroot']):
                m = er == k
                top[k] = np.argmax(lp[m]) == np.argmax(sh[m])
            out.append(np.stack([ce, top], 1))
    net.train()
    return np.concatenate(out)

gen = M.make_net(torch, init['h1'], init['h2']); gen.load_state_dict(init['state'])
net = M.make_net(torch, init['h1'], init['h2'], a.dropout)
if not a.scratch:
    net.load_state_dict(init['state'])
opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
rep = {'args': vars(a), 'roots': {'train': len(tr), 'val': len(va), 'test': len(te)}, 'epochs': []}
v0 = per_root(net, va)[:, 0].mean(); rep['epoch0_val_ce'] = float(v0)
best, best_state, since = v0 if not a.scratch else np.inf, {k: v.clone() for k, v in net.state_dict().items()}, 0
rep['best_epoch'] = -1
t0 = time.time()
for ep in range(a.epochs):
    perm = rng.permutation(tr)
    for i in range(0, len(perm), a.batch):
        b = d.batch(perm[i:i + a.batch], scales, torch)
        logit, v = net(b)
        lp = M.group_log_softmax(torch, logit, b['eroot'], b['nroot'])
        ce = -(b['share'] * lp).sum() / b['nroot']
        hv = b['has_val']
        mse = ((v[hv] - b['val'][hv]) ** 2).mean() if hv.any() else torch.zeros(())
        loss = ce + a.value_weight * mse
        opt.zero_grad(); loss.backward(); opt.step()
    vce = per_root(net, va)[:, 0].mean()
    rep['epochs'].append({'epoch': ep, 'val_ce': float(vce)}); print(ep, round(float(vce), 4), flush=True)
    if vce < best - 1e-4:
        best, since, rep['best_epoch'] = vce, 0, ep
        best_state = {k: v.clone() for k, v in net.state_dict().items()}
    else:
        since += 1
        if since >= a.patience: break
        for g in opt.param_groups: g['lr'] *= 0.5
net.load_state_dict(best_state)
rep['val_ce_best'] = float(best); rep['seconds'] = time.time() - t0
# Test fold 4: general gen-4 vs this net, paired by root; seed-cluster bootstrap of the CE difference.
G, F = per_root(gen, te), per_root(net, te)
seeds = d.r_seed[te] * 2 + d.r_var[te]
def summary(mask):
    if mask.sum() == 0: return None
    diff = F[mask, 0] - G[mask, 0]
    us, inv = np.unique(seeds[mask], return_inverse=True)
    s_sum = np.bincount(inv, weights=diff); s_n = np.bincount(inv)
    bs = []
    r = np.random.default_rng(1)
    for _ in range(2000):
        k = r.integers(0, len(us), len(us))
        bs.append(s_sum[k].sum() / s_n[k].sum())
    return {'roots': int(mask.sum()), 'seeds': len(us), 'gen4_ce': float(G[mask, 0].mean()), 'ft_ce': float(F[mask, 0].mean()),
            'gen4_top1': float(G[mask, 1].mean()), 'ft_top1': float(F[mask, 1].mean()),
            'd_ce': float(diff.mean()), 'd_ce_ci95': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
src = d.r_src[te]
rep['test'] = {'all': summary(np.ones(len(te), bool)),
               'teacher10k(orig+x5+g4)': summary(np.isin(src, [0, 1, 4])),
               'old(gen4 pack)': summary(src < 5), 'new(c95)': summary(src >= 5),
               **{d.tags[i]: summary(src == i) for i in range(len(d.tags))}}
torch.save({'state': best_state, 'h1': init['h1'], 'h2': init['h2'], 'scales': init['scales']}, os.path.join(a.out, 'model.pt'))
json.dump(rep, open(os.path.join(a.out, 'report.json'), 'w'), indent=1)
print(json.dumps(rep['test'], indent=1))
