"""#1058 offline gate: plan-scorer root filter vs g7f_E prior top-m on §797 G16 roots.

Inputs: roots_compact.jsonl.gz (tools/turn_plan/extract_roots.py; edges with prior / visits / qBacked, gumbelChoice)
and the plans of `one_combat turnplanenum` on roots_wire.jsonl.gz. Scorers are cross-fitted by run (5 folds by
seed hash). Prints and writes a JSON result (evidence turn_plan_root_filter_20261115).
"""
import argparse, gzip, json, math, collections, hashlib, sys
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--roots', required=True)
ap.add_argument('--plans', nargs='+', required=True)
ap.add_argument('--names', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--epochs', type=int, default=6)
ap.add_argument('--hidden', type=int, default=64)
ap.add_argument('--seed', type=int, default=20261115)
args = ap.parse_args()

import torch
torch.manual_seed(args.seed)
np.random.seed(args.seed)
torch.set_num_threads(4)

op = lambda p: gzip.open(p, 'rt') if p.endswith('.gz') else open(p)
names = json.load(op(args.names))['features']
F = len(names)

roots = {}
for l in op(args.roots):
    r = json.loads(l)
    roots[(r['seed'], r['fight'], r['decision'])] = r


def group(r):
    room, act = r['room'], r['act']
    if act == 4: return 'act4'
    if room == 'BOSS': return 'boss'
    if room == 'ELITE': return 'elite'
    return 'hallway'


def fold(seed):
    return int(hashlib.sha256(str(seed).encode()).hexdigest(), 16) % 5


# ---- load and join ----
R = []   # per usable root: dict
stats = collections.Counter()
enum = collections.defaultdict(list)   # group -> (nodes, plans, cpu, capped)
for path in args.plans:
    for l in op(path):
        p = json.loads(l)
        r = roots.get((p['seed'], p['fight'], p['decision']))
        if r is None: stats['no_root'] += 1; continue
        if 'error' in p: stats['error'] += 1; continue
        e = r['edges']; n = len(e); g = r.get('gumbelChoice', -1)
        grp = group(r)
        enum[grp].append((p['nodes'], len(p['plans']), p['cpu'], p['capped'], p['merges'], p['execs']))
        if n < 2 or g is None or g < 0: stats['no_pick'] += 1; continue
        if p['n'] != n or any(t < 0 for t in p['toRow']): stats['edge_mismatch'] += 1; continue
        q = [x['qBacked'] if (x.get('qBacked') is not None and x['visits'] > 0) else None for x in e]
        if q[g] is None: stats['pick_unvisited'] += 1; continue
        rec = dict(seed=r['seed'], grp=grp, n=n, g=g, q=q, vis=[x['visits'] for x in e],
                   prior=[max(x['prior'], 1e-12) for x in e], capped=p['capped'], fold=fold(r['seed']))
        if not p['capped']:
            pl = p['plans']
            rec['first'] = [x[0] for x in pl]
            rec['end'] = [x[1] for x in pl]
            rec['lp'] = [x[2] for x in pl]
            rec['bf'] = [x[3] for x in pl]
            rec['X'] = np.asarray([x[4:] for x in pl], dtype=np.float32)
            if any(len(f) == 0 for f in rec['first']): stats['plan_no_first'] += 1
            covered = set(i for f in rec['first'] for i in f)
            if len(covered) != n: stats['action_without_plan'] += 1
        R.append(rec)
        stats['used'] += 1
print('stats', dict(stats))

# ---- enumeration statistics (issue step 1) ----
enum_out = {}
for grp, v in sorted(enum.items()):
    a = np.asarray(v, dtype=float)
    enum_out[grp] = dict(roots=len(v), cap_rate=float(a[:, 3].mean()),
                         plans_median=float(np.median(a[a[:, 3] == 0, 1])) if (a[:, 3] == 0).any() else None,
                         plans_p90=float(np.percentile(a[a[:, 3] == 0, 1], 90)) if (a[:, 3] == 0).any() else None,
                         nodes_median=float(np.median(a[:, 0])), cpu_ms_mean=float(a[:, 2].mean() * 1e3),
                         cpu_ms_p99=float(np.percentile(a[:, 2], 99) * 1e3), merges_mean=float(a[:, 4].mean()))
print(json.dumps(enum_out, indent=1))

# ---- feature normalisation (from all plans; deterministic transform, no labels) ----
allX = np.concatenate([r['X'] for r in R if not r['capped'] and len(r['X'])])
mu = allX.mean(0); sd = allX.std(0) + 1e-6


def plan_inputs(r):
    X = (r['X'] - mu) / sd
    lp = np.asarray(r['lp'], dtype=np.float32)[:, None]
    lpr = np.log(np.asarray(r['prior'], dtype=np.float32))
    bfp = np.asarray([lpr[b] if b >= 0 else -30 for b in r['bf']], dtype=np.float32)[:, None]
    return np.concatenate([X, np.clip(lp, -30, 0) / 5, np.clip(bfp, -30, 0) / 5], 1)


class Scorer(torch.nn.Module):
    def __init__(self, d, h, use_prior):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(d, h), torch.nn.ReLU(), torch.nn.Linear(h, h), torch.nn.ReLU(),
                                       torch.nn.Linear(h, 1))
        self.use_prior = use_prior
        self.w = torch.nn.Parameter(torch.tensor(1.0 if use_prior else 0.0))

    def action_scores(self, X, pair_plan, pair_act, n_act, logprior):
        f = self.net(X).squeeze(-1)
        fp = f[pair_plan]
        m = torch.full((n_act,), -1e9).scatter_reduce(0, pair_act, fp, reduce='amax', include_self=True)
        s = torch.zeros(n_act).scatter_add(0, pair_act, torch.exp(fp - m[pair_act]))
        out = m + torch.log(s.clamp_min(1e-30))
        if self.use_prior: out = out + self.w * logprior
        return out


def prep(r):
    if 'inp' in r: return
    r['inp'] = plan_inputs(r)
    pp = [i for i, fs in enumerate(r['first']) for a in fs]
    pa = [a for fs in r['first'] for a in fs]
    r['pp'] = np.asarray(pp, dtype=np.int64); r['pa'] = np.asarray(pa, dtype=np.int64)
    r['lpr'] = np.log(np.asarray(r['prior'], dtype=np.float32))


def batch_of(rs, feat_mask):
    for r in rs: prep(r)
    po = np.cumsum([0] + [len(r['inp']) for r in rs])[:-1]
    ao = np.cumsum([0] + [r['n'] for r in rs])
    X = np.concatenate([r['inp'][:, feat_mask] for r in rs])
    pp = np.concatenate([r['pp'] + o for r, o in zip(rs, po)])
    pa = np.concatenate([r['pa'] + o for r, o in zip(rs, ao[:-1])])
    lpr = np.concatenate([r['lpr'] for r in rs])
    seg = [(int(a), r['n']) for r, a in zip(rs, ao[:-1])]
    tgt = np.asarray([a + r['g'] for r, a in zip(rs, ao[:-1])])
    return (torch.from_numpy(X), torch.from_numpy(pp), torch.from_numpy(pa), int(ao[-1]),
            torch.from_numpy(lpr), seg, torch.from_numpy(tgt))


def seg_logsoftmax_loss(s, seg, tgt):
    # per root CE: -s[tgt] + logsumexp(s[seg])
    starts = torch.tensor([a for a, _ in seg]); lens = torch.tensor([n for _, n in seg])
    rid = torch.repeat_interleave(torch.arange(len(seg)), lens)
    m = torch.full((len(seg),), -1e9).scatter_reduce(0, rid, s, reduce='amax', include_self=True)
    z = torch.zeros(len(seg)).scatter_add(0, rid, torch.exp(s - m[rid]))
    lse = m + torch.log(z)
    return (lse - s[tgt]).mean()


def train_predict(train, test, feat_mask, use_prior):
    d = int(feat_mask.sum())
    model = Scorer(d, args.hidden, use_prior)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    rng = np.random.default_rng(args.seed)
    bs = 512
    for ep in range(args.epochs):
        idx = rng.permutation(len(train))
        for b in range(0, len(idx), bs):
            rs = [train[i] for i in idx[b:b + bs]]
            X, pp, pa, na, lpr, seg, tgt = batch_of(rs, feat_mask)
            s = model.action_scores(X, pp, pa, na, lpr)
            loss = seg_logsoftmax_loss(s, seg, tgt)
            opt.zero_grad(); loss.backward(); opt.step()
    out = []
    with torch.no_grad():
        for b in range(0, len(test), 2048):
            rs = test[b:b + 2048]
            X, pp, pa, na, lpr, seg, tgt = batch_of(rs, feat_mask)
            s = model.action_scores(X, pp, pa, na, lpr).numpy()
            f = model.net(X).squeeze(-1).numpy()
            po = 0
            for r, (a0, n) in zip(rs, seg):
                out.append((s[a0:a0 + n], f[po:po + len(r['first'])]))
                po += len(r['first'])
    return out


# ---- scores per method ----
D = F + 2
mask_all = np.ones(D, dtype=bool)
mask_noprior = mask_all.copy(); mask_noprior[F:] = False
usable = [r for r in R if not r['capped']]
for r in R:
    r['score'] = {'prior': np.log(np.asarray(r['prior']))}
    if not r['capped']:
        # untrained plan prior: best line's g7f_E log prior over the plans each action starts
        s = np.full(r['n'], -1e9)
        for fs, lp in zip(r['first'], r['lp']):
            for a in fs: s[a] = max(s[a], lp)
        r['score']['planprior'] = s
for name, fm, up in [('plan_mlp', mask_noprior, False), ('plan_mlp+prior', mask_all, True)]:
    for k in range(5):
        tr = [r for r in usable if r['fold'] != k]; te = [r for r in usable if r['fold'] == k]
        pred = train_predict(tr, te, fm, up)
        for r, (s, f) in zip(te, pred):
            r['score'][name] = s; r['planf_' + name] = f
        print('trained', name, 'fold', k, file=sys.stderr)


# ---- evaluation ----
def evaluate(rs, method, keep_rule):
    cnt = hit = 0; regret = saved = kept = 0.0
    for r in rs:
        n = r['n']; q = r['q']
        best = max(v for v in q if v is not None)
        if r['capped'] or method not in r['score']:
            ks = set(range(n))
        else:
            ks = keep_rule(r, r['score'][method])
        bk = max((q[i] for i in ks if q[i] is not None), default=-1e9)
        tv = sum(r['vis'])
        cnt += 1; hit += r['g'] in ks
        regret += best - bk if bk > -1e9 else best - min(v for v in q if v is not None)
        saved += sum(r['vis'][i] for i in range(n) if i not in ks) / tv if tv else 0
        kept += len(ks) / n
    return dict(roots=cnt, recall=hit / cnt, regret=regret / cnt, saved=saved / cnt, kept=kept / cnt)


def top_m(m_of):
    def rule(r, s):
        m = min(r['n'], max(1, m_of(r['n'])))
        return set(np.argsort(-s, kind='stable')[:m].tolist())
    return rule


def plan_topk_anchor(K, method):
    # spire-mentor: top-K plans by the plan scorer plus anchors (lethal, max damage, max block, prior greedy line)
    def rule(r, s):
        f = r.get('planf_' + method)
        if f is None: return set(range(r['n']))
        X = r['X']
        ii = names.index
        order = np.argsort(-f, kind='stable')[:K].tolist()
        anchors = set()
        won = np.where(X[:, ii('won')] > 0)[0]
        if len(won): anchors.add(int(won[0]))
        anchors.add(int(np.argmax(X[:, ii('enemy_hp_removed')])))
        anchors.add(int(np.argmax(X[:, ii('block_gained')])))
        anchors.add(int(np.argmax(r['lp'])))
        keep = set()
        for pi in set(order) | anchors:
            keep.update(r['first'][pi])
        return keep
    return rule


# Budget exchange rate (Inference): §797 uniform loss per decision 8k 0.57, 16k 0.51 -> 0.06 Q per doubling at 16k.
PER_DOUBLING = 0.06
rules = {'half': top_m(lambda n: math.ceil(n / 2)), 'n-1': top_m(lambda n: n - 1), 'n-2': top_m(lambda n: n - 2),
         'top4': top_m(lambda n: 4), 'top6': top_m(lambda n: 6)}
methods = ['prior', 'planprior', 'plan_mlp', 'plan_mlp+prior']
result = {'stats': dict(stats), 'enumeration': enum_out, 'per_doubling_Q': PER_DOUBLING, 'eval': {}}
for gname, rs in [('all', R)] + [(gg, [r for r in R if r['grp'] == gg]) for gg in ['hallway', 'elite', 'boss', 'act4']]:
    result['eval'][gname] = {}
    for rn, rule in rules.items():
        for m in methods:
            ev = evaluate(rs, m, rule)
            ev['budget_gain_est'] = PER_DOUBLING * math.log2(1 / max(1e-9, 1 - ev['saved']))
            ev['net_est'] = ev['budget_gain_est'] - ev['regret']
            result['eval'][gname][f'{rn}/{m}'] = ev
    for K in (3, 6):
        for m in ['plan_mlp', 'plan_mlp+prior']:
            ev = evaluate(rs, m, plan_topk_anchor(K, m))
            ev['budget_gain_est'] = PER_DOUBLING * math.log2(1 / max(1e-9, 1 - ev['saved']))
            ev['net_est'] = ev['budget_gain_est'] - ev['regret']
            result['eval'][gname][f'plantop{K}+anchors/{m}'] = ev
for gname, d in result['eval'].items():
    print('==', gname)
    for k, v in d.items():
        print(f"  {k:32s} recall {v['recall']:.4f} regret {v['regret']:.4f} saved {v['saved']:.3f} kept {v['kept']:.3f} "
              f"gain_est {v['budget_gain_est']:.4f} net {v['net_est']:+.4f}")
json.dump(result, open(args.out, 'w'), indent=1)
