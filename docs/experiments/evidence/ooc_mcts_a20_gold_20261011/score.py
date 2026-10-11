"""§425 scoring: OOC MCTS root picks vs A20 gold labels (labelFloor).

top1 = pick equals the gold-best option (first argmax in row order, the GOLD-RESULT definition;
random = 1/n). tieshare = credit 1/k when the pick is one of k tied best options. regret = best label minus
the picked option's label (floors). Only target decisions whose replayed state matches the gold run
row for row (all rows of the seed up to and including the decision) are scored.
"""
import pickle, json, glob, sys, random, collections, os, csv
G = os.path.expanduser('~/g')
hdr, rows = pickle.load(open(f'{G}/gold_all.pkl', 'rb'))
NF = len(hdr) - 7
iL, iA, iC = hdr.index('labelFloor'), hdr.index('action'), hdr.index('chosen')
iS, iF = hdr.index('screen'), hdr.index('floor')
dec = collections.defaultdict(dict)   # (seed,dec) -> bits -> (floor, chosen)
meta = {}
goldseed = collections.defaultdict(list)
for x in rows:
    goldseed[int(x[0])].append(x)
    if len(x) > iL and x[iL] != '':
        k = (int(x[0]), int(x[1]))
        dec[k][int(x[iA])] = (float(x[iL]), x[iC] == '1')
        meta[k] = (int(x[iS]), int(x[iF]))
multi = {k: v for k, v in dec.items() if len(v) > 1}
def argbest(k): return max(dec[k], key=lambda b: dec[k][b][0])

def valid_targets(arm):
    ok = set()
    for f in glob.glob(f'{G}/out/{arm}/*.csv'):
        s = int(os.path.basename(f).split('.')[0])
        mine = [x for x in csv.reader(open(f)) if x and x[0].isdigit()]
        g = goldseed[s]
        good = 0
        while good < len(mine) and good < len(g) and mine[good][:NF] == g[good][:NF]: good += 1
        # a decision is valid if all its rows lie inside the matching prefix
        last = collections.defaultdict(int)
        for i, x in enumerate(mine): last[int(x[1])] = i
        for d, i in last.items():
            if i < good: ok.add((s, d))
    return ok

def load(arm):
    picks, info = collections.defaultdict(list), collections.defaultdict(list)
    for f in glob.glob(f'{G}/out/{arm}/*.jsonl'):
        for l in open(f):
            r = json.loads(l); k = (r['seed'], r['decIdx'])
            picks[k].append(r['selectedBits'] if r['selected'] else None); info[k].append(r)
    return picks, info

def boot(vals, B=10000, seed=425):
    rng = random.Random(seed); n = len(vals); m = sum(vals) / n
    bs = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return [m, bs[int(0.025 * B)], bs[int(0.975 * B) - 1]]

def per_decision(k, choice):   # choice: list of bits (equal weight) -> (top1, tieshare, regret)
    lab = dec[k]; best = max(v[0] for v in lab.values()); nb = sum(v[0] == best for v in lab.values())
    ab = argbest(k)
    return (sum(b == ab for b in choice) / len(choice),
            sum((lab[b][0] == best) / nb for b in choice) / len(choice),
            sum(best - lab[b][0] for b in choice) / len(choice))

report = {'definition': __doc__.strip()}
def emit(name, picker, ks, paired_with=None):
    v = [per_decision(k, picker(k)) for k in ks]
    out = {'n': len(ks)}
    for j, m in enumerate(['top1', 'tieshare', 'regretFloors']): out[m] = boot([x[j] for x in v])
    if paired_with:
        w = [per_decision(k, paired_with(k)) for k in ks]
        out['deltaTop1VsHeuristic'] = boot([a[0] - b[0] for a, b in zip(v, w)])
        out['deltaRegretVsHeuristic'] = boot([a[2] - b[2] for a, b in zip(v, w)])
    report[name] = out
    f = lambda a: f'{a[0]:.3f} [{a[1]:.3f},{a[2]:.3f}]'
    extra = f"  dTop1 {f(out['deltaTop1VsHeuristic'])} dRegret {f(out['deltaRegretVsHeuristic'])}" if paired_with else ''
    print(f'{name:40s} n={len(ks):4d} top1 {f(out["top1"])} tie {f(out["tieshare"])} regret {f(out["regretFloors"])}{extra}')

def heur(k):
    c = [b for b, v in dec[k].items() if v[1]]; return c[:1] if c else None
def rnd(k): return list(dec[k].keys())
keys = sorted(multi)
emit('ALL409 random (expected)', rnd, keys)
emit('ALL409 heuristic (gold-run choice)', heur, [k for k in keys if heur(k)])
for arm in sys.argv[1:]:
    picks, info = load(arm)
    valid = valid_targets(arm)
    have = [k for k in keys if k in picks and k in valid]
    print(f'\n== {arm}: multi-option targets {len(keys)}, searched {sum(k in picks for k in keys)}, state-verified {len(have)}')
    report[arm + ' counts'] = {'multi': len(keys), 'searched': sum(k in picks for k in keys), 'verified': len(have),
        'verifiedAll524': sum(1 for k in dec if k in picks and k in valid)}
    def mapped(k): return [b for b in picks[k] if b is not None and b in dec[k]]
    owned = [k for k in have if len(mapped(k)) == len(picks[k])]
    notowned = collections.Counter()
    for k in have:
        for r in info[k]:
            if not r['selected']: notowned['no_selection:' + (r['abortReason'] or 'boundary')[:60]] += 1
            elif r['selectedBits'] not in dec[k]: notowned['selected_bits_not_a_labeled_option'] += 1
    print('   not owned (per search):', dict(notowned))
    report[arm + ' notOwnedPerSearch'] = dict(notowned)
    hk = [k for k in have if heur(k)]
    emit(f'{arm}: random, verified', rnd, have)
    emit(f'{arm}: heuristic, verified', heur, hk)
    def live(k):
        h = heur(k); return [b if (b is not None and b in dec[k]) else h[0] for b in picks[k]]
    emit(f'{arm}: MCTS live (fallback=heuristic)', live, hk, paired_with=heur)
    ok = [k for k in owned if heur(k)]
    emit(f'{arm}: MCTS owned only', mapped, ok, paired_with=heur)
    names = {0: 'EVENT', 1: 'EVENT', 2: 'REWARDS', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'REST', 7: 'SHOP'}
    for scr in sorted({meta[k][0] for k in ok}):
        ks = [k for k in ok if meta[k][0] == scr]
        if len(ks) >= 15: emit(f'{arm}: owned, screen {scr}', mapped, ks, paired_with=heur)
    agree = [sum(b == heur(k)[0] for b in mapped(k)) / len(mapped(k)) for k in ok]
    stab = [max(collections.Counter(mapped(k)).values()) / len(mapped(k)) for k in ok]
    print(f'   agreement with heuristic {sum(agree)/len(agree):.3f}; same pick across searches (modal share) {sum(stab)/len(stab):.3f}')
    report[arm + ' agreementWithHeuristic'] = sum(agree) / len(agree)
    report[arm + ' modalShareAcrossSearches'] = sum(stab) / len(stab)
json.dump(report, open(f'{G}/report.json', 'w'), indent=1)
