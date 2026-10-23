"""Endgame study tables: python3 study.py OUTDIR TAG[,TAG...] [RECORDED.jsonl ...]

Reads OUTDIR/<TAG>_<CFG>.jsonl for CFG in S1 S0 C0 C2 C1 and prints the report tables (markdown).
"""
import json, sys, statistics as st, math
from collections import Counter, defaultdict
EPS = 1e-6
outdir, tags = sys.argv[1], sys.argv[2].split(',')
recorded = sys.argv[3:]

def load(cfg):
    rows = {}
    for t in tags:
        try:
            for l in open(f'{outdir}/{t}_{cfg}.jsonl'):
                r = json.loads(l); rows[(r['seed'], r['fight'], r['decision'])] = r
        except FileNotFoundError:
            pass
    return rows

def kind(a):
    if a['label'].startswith('{ end turn'): return 'end turn'
    if 'drink potion' in a['label']: return 'potion'
    b, d = a.get('dBlock', 0) or 0, a.get('dDmg', 0) or 0
    if b > 0 and d > 0: return 'attack+block'
    if b > 0: return 'block'
    if d > 0: return 'attack'
    return 'other'

def q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(f * len(xs)))] if xs else float('nan')

CFG = {'C0': 'last turn, solved to its end (win score)',
       'C2': 'second-to-last turn, its own turn exact + Silver playout policy for 1 turn (lower) / 1-turn bound (upper)',
       'C1': 'second-to-last turn, solved through the last turn (win score)',
       'S0': 'lost fights, P(survive the next enemy turn)',
       'S1': 'lost fights, P(survive the next 2 enemy turns)'}
data = {c: load(c) for c in CFG}

# ---- dataset
if recorded:
    runs = {}; fights = {}
    for f in recorded:
        for l in open(f):
            r = json.loads(l)
            if 'summary' in r: runs[r['seed']] = r; continue
            fights[(r['seed'], r['fight'])] = (r['room'], r['won'], r['encounter'], r['act'])
    c = Counter((v[0], v[1]) for v in fights.values())
    print(f"Runs: {len(runs)} (won {sum(1 for r in runs.values() if r['won'])}); elite/boss fights recorded: {len(fights)} "
          f"(elite won {c[('ELITE', True)]}, elite lost {c[('ELITE', False)]}, boss won {c[('BOSS', True)]}, boss lost {c[('BOSS', False)]})")

# ---- feasibility
print('\n| config | roots | solved | over time limit | unsupported | median s | p90 s | max states |')
print('|---|---|---|---|---|---|---|---|')
for cfg, desc in CFG.items():
    rs = list(data[cfg].values())
    if not rs: continue
    for room in ('ELITE', 'BOSS', None):
        sub = [r for r in rs if room is None or r['room'] == room]
        if not sub: continue
        ok = sum(r['status'] == 'ok' for r in sub); tl = sum('time limit' in r['status'] for r in sub)
        un = sum(r['status'].startswith('unsupported') for r in sub)
        secs = [r['seconds'] for r in sub]
        stt = [max(r.get('lowerStates', 0), r.get('upperStates', 0)) for r in sub if r['status'] == 'ok']
        print(f"| {cfg} {room.lower() if room else 'all'} | {len(sub)} | {ok} ({100*ok/len(sub):.0f}%) | {tl} | {un} | {st.median(secs):.2f} | {q(secs,0.9):.1f} | {max(stt) if stt else 0:,} |")

# ---- won fights: proven bounds
def combine(a, b):
    """Tightest valid bounds per root from configs a and b (same roots, either may be missing or unsolved)."""
    out = {}
    for k in set(a) | set(b):
        ra, rb = a.get(k), b.get(k)
        oks = [r for r in (ra, rb) if r and r['status'] == 'ok']
        if not oks: out[k] = ra or rb; continue
        base = json.loads(json.dumps(oks[0]))
        for r in oks[1:]:
            for x, y in zip(base['actions'], r['actions']):
                assert x['bits'] == y['bits']
                x['lo'] = max(x['lo'], y['lo']); x['hi'] = min(x['hi'], y['hi'])
                if x['lo'] > x['hi'] + 1e-6: raise SystemExit(f'inconsistent bounds at {k}: {x}')
        lo = [x['lo'] for x in base['actions']]; hi = [x['hi'] for x in base['actions']]
        c = base['chosenIdx']
        base['bestLo'], base['bestHi'] = max(lo), max(hi)
        base['regretLo'] = max(0.0, max(lo) - hi[c]); base['regretHi'] = max(0.0, max(hi) - lo[c])
        base['combined'] = len(oks)
        out[k] = base
    return out

def score(name, rows):
    rs = [r for r in rows.values() if r and r['status'] == 'ok' and r['won']]
    if not rs: return []
    opt = [r for r in rs if r['regretHi'] <= EPS]
    cert = [r for r in rs if r['regretLo'] > EPS]
    small = [r for r in cert if r['regretLo'] < 0.5]
    und = [r for r in rs if r['regretHi'] > EPS and r['regretLo'] <= EPS]
    gaps = [r['regretHi'] for r in und]
    fights = len({(r['seed'], r['fight']) for r in rs})
    print(f"\n**{name}** ({len(rs)} solved roots of won fights, {fights} fights): proven optimal {len(opt)} ({100*len(opt)/len(rs):.0f}%), "
          f"certified mistakes {len(cert)} (sum {sum(r['regretLo'] for r in cert):.2f} points; {len(small)} of them under 0.5), "
          f"undetermined {len(und)} (regret upper bound median {q(gaps,0.5):.1f}, p90 {q(gaps,0.9):.1f}); "
          f"certified loss per fight {sum(r['regretLo'] for r in cert)/fights:.3f} points")
    big = sorted([r for r in cert if r['regretLo'] >= 0.5], key=lambda r: -r['regretLo'])
    if big:
        print('\n| seed | fight | turn | HP | Silver | best | certified regret | Silver visits share |')
        print('|---|---|---|---|---|---|---|---|')
    for r in big:
        ch = r['actions'][r['chosenIdx']]; best = max(r['actions'], key=lambda a: a['lo'])
        vis = sum(a.get('visits', 0) or 0 for a in r['actions'])
        share = (ch.get('visits', 0) or 0) / vis if vis else float('nan')
        print(f"| {r['seed']} | {r['encounter']} | {r['turn']} | {r['hp']}/{r['maxHp']} | {kind(ch)}: {ch['label'][2:48]} | {kind(best)}: {best['label'][2:48]} | "
              f"{r['regretLo']:.2f} (≤ {r['regretHi']:.2f}) | {share:.0%} |")
    pair = Counter((kind(r['actions'][r['chosenIdx']]), kind(max(r['actions'], key=lambda a: a['lo']))) for r in cert)
    if cert:
        print('\nCertified mistakes by kind (Silver -> best): ' + ', '.join(f'{a} -> {b}: {n}' for (a, b), n in pair.most_common()))
    return cert

print('\n### Won fights')
c0 = data['C0']
score('Last turn (C0)', c0)
second = combine(data['C1'], data['C2'])
score('Second-to-last turn (C1 with C2 bounds where tighter)', second)
score('Second-to-last turn, C1 alone', data['C1'])
score('Second-to-last turn, C2 alone', data['C2'])

# ---- Silver Q bias on exact actions
def qbias(rows, label):
    by = defaultdict(list); pairs = []
    for r in rows.values():
        if not r or r['status'] != 'ok' or not r['won']: continue
        ex = [a for a in r['actions'] if a.get('silverQ') is not None and abs(a['hi'] - a['lo']) < 1e-6 and (a.get('visits') or 0) >= 50]
        for a in ex: by[kind(a)].append(a['silverQ'] - a['lo'])
        for a in ex:
            if kind(a) != 'attack': continue
            for b in ex:
                if kind(b) in ('block', 'attack+block'): pairs.append((a['silverQ'] - b['silverQ']) - (a['lo'] - b['lo']))
    if not by: return
    print(f'\n{label}: Silver edge Q minus exact value (actions solved exactly, >= 50 visits)')
    print('\n| action kind | n | mean | median |')
    print('|---|---|---|---|')
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f'| {k} | {len(v)} | {st.mean(v):+.2f} | {st.median(v):+.2f} |')
    if pairs:
        se = st.pstdev(pairs) / math.sqrt(len(pairs)) if len(pairs) > 1 else float('nan')
        print(f'\nAttack vs block in the same root: Silver Q gap minus exact gap {st.mean(pairs):+.2f} ± {se:.2f} (n {len(pairs)} pairs; positive = Silver favours the attack more than it should)')
qbias(c0, 'Last turn')
qbias(second, 'Second-to-last turn')

# ---- lost fights: survival
print('\n### Lost fights')
for cfg in ('S0', 'S1'):
    rs = [r for r in data[cfg].values() if r['status'] == 'ok']
    if not rs: continue
    worse = [r for r in rs if r['bestLo'] - r['actions'][r['chosenIdx']]['lo'] > 0.01]
    fights = {(r['seed'], r['fight']) for r in rs}
    print(f"\n**{cfg}: {CFG[cfg]}** ({len(rs)} solved roots, {len(fights)} fights): Silver's choice lowers the survival probability at {len(worse)} roots "
          f"(in {len({(r['seed'], r['fight']) for r in worse})} fights; mean drop {st.mean([r['bestLo'] - r['actions'][r['chosenIdx']]['lo'] for r in worse]) if worse else 0:.3f})")
    if worse:
        print('\n| seed | fight | turn (to end) | HP | Silver | P(survive) | best | P(survive) |')
        print('|---|---|---|---|---|---|---|---|')
    for r in sorted(worse, key=lambda r: (r['seed'], r['fight'], r['decision'])):
        ch = r['actions'][r['chosenIdx']]; best = max(r['actions'], key=lambda a: a['lo'])
        print(f"| {r['seed']} | {r['encounter']} | {r['turn']} ({r['turnsToEnd']}) | {r['hp']}/{r['maxHp']} | {kind(ch)}: {ch['label'][2:44]} | {ch['lo']:.2f} | {kind(best)}: {best['label'][2:44]} | {best['lo']:.2f} |")
    if worse:
        pair = Counter((kind(r['actions'][r['chosenIdx']]), kind(max(r['actions'], key=lambda a: a['lo']))) for r in worse)
        print('\nBy kind (Silver -> best): ' + ', '.join(f'{a} -> {b}: {n}' for (a, b), n in pair.most_common()))
