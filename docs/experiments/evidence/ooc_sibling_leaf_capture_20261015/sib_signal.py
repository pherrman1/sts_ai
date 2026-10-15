"""Within-parent signal analysis. For each parent node, demean leaf values (T = mean of R repeat rollouts,
candidates r0 / x2b / heart1 / l5 / scores). Signal variance of E[rollout3] within parents = var(T) - mean(Tse^2).
Reports corr(c, T), and the disattenuated corr(c, E[rollout3]) = cov(c,T)/sqrt(var(c)*signal)."""
import json, sys, collections, gzip, math
sys.path.insert(0, __import__('os').path.dirname(__file__))
from sib_metrics2 import load

def analyse(rows, names):
    groups = collections.defaultdict(list)
    for r in rows: groups[r['key']].append(r['c'])
    acc = {k: [0.0, 0.0, 0.0, 0] for k in names}  # sum cT, cc, n
    tt = 0.0; noise = 0.0; n_all = 0
    for g in groups.values():
        if len(g) < 2: continue
        ks = [k for k in names if all(k in c for c in g)]
        mt = sum(c['T'] for c in g) / len(g)
        for c in g:
            tt += (c['T'] - mt) ** 2; noise += c['Tse'] ** 2 * (len(g) - 1) / len(g); n_all += 1
        for k in ks:
            mk = sum(c[k] for c in g) / len(g)
            a = acc[k]
            for c in g:
                a[0] += (c[k] - mk) * (c['T'] - mt); a[1] += (c[k] - mk) ** 2; a[3] += 1
    signal = (tt - noise) / n_all
    out = {'leaves': n_all, 'varT': tt / n_all, 'noiseVar': noise / n_all, 'signalVar': signal}
    for k, (ct, cc, _, n) in acc.items():
        if not n: continue
        out[k] = {'corrWithT': ct / math.sqrt(cc * tt) if cc else None,
                  'corrWithExpected': (ct / n) / math.sqrt((cc / n) * signal) if cc and signal > 0 else None}
    return out

if __name__ == '__main__':
    rows = list(load(sys.argv[2:]))
    names = ['r0', 'x2b', 'heart1', 'l5'] + sorted({k for r in rows for k in r['c']} - {'T', 'Tse', 'r0', 'half_a', 'half_b', 'l5', 'x2b', 'heart1'})
    rep = {'all': analyse(rows, names), 'byParentScreen': {}}
    for s in sorted({r['screen'] for r in rows}):
        sub = [r for r in rows if r['screen'] == s]
        rep['byParentScreen'][str(s)] = analyse(sub, names)
    json.dump(rep, open(sys.argv[1], 'w'), indent=1)
    def show(name, o):
        print(f"{name}: leaves {o['leaves']} signal share {o['signalVar']/o['varT']:.2f} | " + "  ".join(
            f"{k} {o[k]['corrWithExpected']:.2f}" for k in names if k in o and o[k]['corrWithExpected'] is not None))
    show('all', rep['all'])
    for s, o in rep['byParentScreen'].items(): show('screen ' + s, o)
