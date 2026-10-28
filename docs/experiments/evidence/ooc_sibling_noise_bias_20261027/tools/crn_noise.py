"""Sibling-difference noise on the §644 common-seed capture (post-hoc M0 leaf), top-3 prior actions per root."""
import gzip, json, sys, math
import numpy as np
SCREEN = {1: 'EVENT', 2: 'CARD_REWARD', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'TREASURE', 7: 'REST', 8: 'SHOP'}
GAPS = (0.01, 0.02, 0.05, 0.10)
data = json.load(gzip.open(sys.argv[1], 'rt'))
key = sys.argv[2] if len(sys.argv) > 2 else 'cal'
rng = np.random.default_rng(881)

def pair_stats(a, b):
    """a, b: rows x 32 matrices (captured children x repeats). Single-sample D = random child of A minus random child
    of B, repeat stream r (paired) or independent streams r != r' (unpaired)."""
    a, b = np.asarray(a), np.asarray(b)
    ma, mb = a.mean(0), b.mean(0)          # per-repeat child-mean
    va, vb = a.var(0), b.var(0)            # child spread per repeat
    d_r = ma - mb
    mean = d_r.mean()
    # paired: E_r[va+vb+(ma-mb)^2] - mean^2
    var_p = (va + vb + d_r ** 2).mean() - mean ** 2
    # unpaired: Var(A sample) + Var(B sample), each over (child, repeat)
    var_u = a.var() + b.var()
    # child-mean-only (rollout noise at a fixed child set), paired / unpaired
    var_pc = d_r.var()
    var_uc = ma.var() + mb.var()
    rev = float(np.mean(np.sign(d_r) != np.sign(mean))) if mean != 0 else float('nan')
    # reversal of single-sample paired D (child sampled): Monte Carlo
    ia = rng.integers(0, a.shape[0], 512); ib = rng.integers(0, b.shape[0], 512); ir = rng.integers(0, 32, 512)
    ds = a[ia, ir] - b[ib, ir]
    rev1 = float(np.mean(np.sign(ds) != np.sign(mean))) if mean != 0 else float('nan')
    return dict(mean=mean, sdP=math.sqrt(max(var_p, 0)), sdU=math.sqrt(max(var_u, 0)), sdPc=math.sqrt(max(var_pc, 0)),
                sdUc=math.sqrt(max(var_uc, 0)), seP32=math.sqrt(max(var_p, 0) / 32), rev=rev1, revChildMean=rev,
                stoch=int(a.shape[0] > 1 or b.shape[0] > 1))

pairs = []
for seed, roots in sorted(data.items()):  # sorted: the Monte Carlo reversal draws use one RNG
    for r in roots:
        acts = r['actions']
        for j in range(1, len(acts)):
            st = pair_stats(acts[0][key], acts[j][key])
            st.update(seed=int(seed), decision=r['decision'], screen=SCREEN.get(r['screen'], str(r['screen'])), act=r['act'],
                      floor=r['floor'], rank=j, nLegal=r['nLegal'], split='VAL' if int(seed) % 4 == 3 else 'TRAIN',
                      qgap=(acts[0]['q'] or 0) - (acts[j]['q'] or 0) if acts[0]['q'] is not None else None,
                      vis=(acts[0]['visits'], acts[j]['visits']))
            pairs.append(st)
json.dump(pairs, gzip.open(sys.argv[1].replace('.json.gz', f'.pairs_{key}.json.gz'), 'wt'))

def summarize(ps, label):
    if not ps: return
    a = lambda k: np.array([p[k] for p in ps], dtype=float)
    sdP, sdU, mean = a('sdP'), a('sdU'), np.abs(a('mean'))
    ok = sdP > 0
    ratio = np.median((sdP[ok] / sdU[ok]) ** 2)
    pooled_ratio = (sdP ** 2).sum() / (sdU ** 2).sum()
    snr = mean / np.where(sdP > 0, sdP, np.nan)
    snrU = mean / np.where(sdU > 0, sdU, np.nan)
    nown = (1.96 / snr) ** 2; nownU = (1.96 / snrU) ** 2
    rms_sdP = math.sqrt((sdP ** 2).mean()); rms_sdU = math.sqrt((sdU ** 2).mean())
    roots = len({(p['seed'], p['decision']) for p in ps}); seeds = len({p['seed'] for p in ps})
    gapn = ' '.join(f'{int(g*100)}pp:{(1.96*rms_sdP/g)**2:.0f}/{(1.96*rms_sdU/g)**2:.0f}' for g in GAPS)
    print(f'{label:12s} seeds {seeds:3d} roots {roots:5d} pairs {len(ps):5d} | |D| med {np.median(mean)*100:.2f}pp '
          f'| sd1 paired {rms_sdP*100:.1f}pp unpaired {rms_sdU*100:.1f}pp CRN var ratio pooled {pooled_ratio:.2f} '
          f'med {ratio:.2f} | rev1 {np.nanmean(a("rev")):.2f} | SNR med P {np.nanmedian(snr):.2f} U {np.nanmedian(snrU):.2f} '
          f'| n(own gap) med P {np.nanmedian(nown):.0f} U {np.nanmedian(nownU):.0f}; >1024 P {np.nanmean(nown>1024):.2f} U {np.nanmean(nownU>1024):.2f} '
          f'| |D|<1pp {np.mean(mean<0.01):.2f} <2pp {np.mean(mean<0.02):.2f} | n for gap (P/U) {gapn} | stochastic {np.mean(a("stoch")):.2f}')

for split in ('VAL', 'ALL'):
    sel = [p for p in pairs if split == 'ALL' or p['split'] == split]
    print(f'== {split} ({key}) ==')
    summarize(sel, 'pooled')
    for s in ('CARD_REWARD', 'MAP', 'REST', 'SHOP', 'EVENT', 'BOSS_RELIC', 'TREASURE', 'CARD_SELECT'):
        summarize([p for p in sel if p['screen'] == s], s)
