"""Campfire-vs-HP audit (offline). Usage: python3 analyze.py m683.pkl g676.pkl > analyze.json

Inputs are extract.py pickles of the §683 (D/MAP/OFF) and §676 (A/C) unit tars. Choice = the MCTS
selected effect where recorded, else inferred from the next non-campfire state (Ruby bit, upgrade
count, HP). Row 14 of the Act-3 map (floor 49) is the pre-boss campfire; Coffee Dripper (relic 100)
runs are excluded where rest is the counterfactual. The kill/death deltas use an observational
logistic fit on boss-1 entry HP and max HP, so they are upper-bound style, not causal."""
import collections, json, pickle, sys
import numpy as np

class Logit:
    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0)
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]; w = np.zeros(Z.shape[1])
        for _ in range(50):
            p = 1 / (1 + np.exp(-Z @ w))
            w += np.linalg.solve(Z.T @ (Z * (p * (1 - p))[:, None]) + 1e-6 * np.eye(len(w)), Z.T @ (y - p))
        self.w = w; return self
    def p(self, X):
        return 1 / (1 + np.exp(-np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.w))

R = {}
for f in sys.argv[1:]: R.update(pickle.load(open(f, 'rb')))
ch = lambda x: x['eff'] or x['inferred']
DRIPPER = 100
rows = []
for (s, a), g in R.items():
    pre = [x for x in g['fires'] if x['floor'] == 49 and x['act'] == 3]
    b = [f for f in g['fights'] if f['act'] == 3 and f['room'] == 'BOSS']
    if not pre or not b: continue
    x = pre[0]
    hi = [y for y in g['fires'] if y['act'] == 3 and y['floor'] < 49 and y['hp'] / y['maxhp'] >= .6]
    rows.append(dict(arm=a, fr=x['hp'] / x['maxhp'], mx=x['maxhp'], c=ch(x), forced=x['by'] == 'heart_key',
                     dripper=DRIPPER in b[0]['relics'], b1=b[0]['hp'], dead3=any(f['out'] == 2 for f in b),
                     kill=bool(g['out']['heartKilled']), hi_earlier=bool(hi), hi_choice=ch(hi[-1]) if hi else None))
out = {}
for grp, arms in (('MAP', ('MAP',)), ('all5', ('MAP', 'D', 'A', 'C', 'OFF'))):
    rs = [r for r in rows if r['arm'] in arms]; nruns = sum(1 for k in R if k[1] in arms)
    X = np.array([[r['b1'], r['mx']] for r in rs], float)
    M = {t: Logit().fit(X, np.array([r[t] for r in rs], float)) for t in ('dead3', 'kill')}
    def cf(S, t):
        x0 = np.array([[r['b1'], r['mx']] for r in S], float)
        x1 = np.array([[min(r['mx'], r['b1'] + int(.3 * r['mx'])), r['mx']] for r in S], float)
        return round(100 * float((M[t].p(x1) - M[t].p(x0)).sum()) / nruns, 2)
    o = dict(runs=nruns, reach_preboss=len(rs), forced_share=round(float(np.mean([r['forced'] for r in rs])), 3))
    for lab, f in (('forced<60%', lambda r: r['forced'] and r['fr'] < .6 and not r['dripper']),
                   ('forced<60%+hi_earlier', lambda r: r['forced'] and r['fr'] < .6 and not r['dripper'] and r['hi_earlier']),
                   ('forced<70%', lambda r: r['forced'] and r['fr'] < .7 and not r['dripper']),
                   ('forced<70%+hi_earlier', lambda r: r['forced'] and r['fr'] < .7 and not r['dripper'] and r['hi_earlier'])):
        S = [r for r in rs if f(r)]
        o[lab] = dict(n=len(S), pct_runs=round(100 * len(S) / nruns, 2),
                      act3_boss_death=round(float(np.mean([r['dead3'] for r in S])), 3),
                      kill=round(float(np.mean([r['kill'] for r in S])), 3),
                      dDeath_pp_all_runs=cf(S, 'dead3'), dKill_pp_all_runs=cf(S, 'kill'),
                      earlier_hi_choice=dict(collections.Counter(str(r['hi_choice']) for r in S)))
    for lo, hi in ((0, .6), (.6, .8)):
        for c in ('recall', 'rest'):
            S = [r for r in rs if lo <= r['fr'] < hi and r['c'] == c and not r['dripper']]
            o[f'observed {lo}-{hi} {c}'] = dict(n=len(S), boss1_entry=round(float(np.mean([r['b1'] for r in S])), 1),
                                              act3_boss_death=round(float(np.mean([r['dead3'] for r in S])), 3),
                                              kill=round(float(np.mean([r['kill'] for r in S])), 3))
    # policy choices at < 60% HP in acts 2-4 (excluding the forced Ruby), split by Coffee Dripper
    pol = collections.Counter()
    for (s, a), g in R.items():
        if a not in arms: continue
        for x in g['fires']:
            if x['act'] < 2 or x['hp'] / x['maxhp'] >= .6 or x['by'] == 'heart_key': continue
            fs = [f for f in g['fights'] if f['floor'] < x['floor']]
            pol[f"act{x['act']} {ch(x)} {'dripper' if fs and DRIPPER in fs[-1]['relics'] else 'no_dripper'}"] += 1
    o['policy_choices_below_60pct'] = dict(sorted(pol.items()))
    a4 = collections.Counter(); hm = []
    for (s, a), g in R.items():
        if a not in arms: continue
        f4 = [x for x in g['fires'] if x['act'] == 4]
        if f4: a4[f"{ch(f4[0])} {'missing>=10' if f4[0]['maxhp'] - f4[0]['hp'] >= 10 else 'missing<10'}"] += 1
        fa = [f for f in g['fights'] if f['act'] == 4]
        if len(fa) >= 2: hm.append(fa[1]['maxhp'] - fa[1]['hp'])
    o['act4_campfire'] = dict(sorted(a4.items())); o['heart_entry_missing_hp_mean'] = round(float(np.mean(hm)), 1)
    out[grp] = o
print(json.dumps(out, indent=1))
