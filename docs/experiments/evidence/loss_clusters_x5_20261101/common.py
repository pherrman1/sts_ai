import os, sys, pickle, collections, glob
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../loss_mining_20261031'))
from names import ENC, CARD, RELIC, CTYPE  # noqa: E402

# Campaigns (share dir -> label) and the ledger entry each comes from. All A20, production combat of their date.
CAMPAIGNS = {
    'vchooser': ('value-chooser-ab', '§727'), 'r1': ('value-clean-labels-run1', '§720'),
    'keys': ('key-rules-ab', '§691'), 'expanch': ('expert-anchored-ab', 'expert-anchored A/B'),
    'maponly': ('ooc-map-only-search', '§683'), 'ctmcal': ('ctm-calibration-ab', '§676'),
    'qcap': ('gumbel-qcap-ab', '§693'), 'vlevel': ('value-level-ab', '§661'), 'cardrule': ('card-rule-ab', '§712'),
}
# r1 holds base games (salt 0) and forks; only base games are whole independent runs.
KEEP_ARMS = {'r1': {'base'}}

def load(workdir):
    G = []
    for lab in CAMPAIGNS:
        p = os.path.join(workdir, lab + '.pkl')
        if not os.path.exists(p): continue
        d = pickle.load(open(p, 'rb'))
        for g in d['games']:
            if lab in KEEP_ARMS and g['arm'] not in KEEP_ARMS[lab]: continue
            G.append(g)
    return G

def arm_rates(G):
    c = collections.defaultdict(lambda: [0, 0])
    for g in G:
        c[(g['camp'], g['arm'])][0] += g['kill']; c[(g['camp'], g['arm'])][1] += 1
    return c

def primary(G, margin=0.04):
    """Arms within `margin` of their campaign's best arm (drops arms that lost a gate badly)."""
    c = arm_rates(G); best = collections.defaultdict(float)
    for (cp, a), (k, n) in c.items(): best[cp] = max(best[cp], k / n)
    keep = {key for key, (k, n) in c.items() if k / n >= best[key[0]] - margin}
    return [g for g in G if (g['camp'], g['arm']) in keep], keep

def death_fight(g):
    if g['kill'] or not g['fights']: return None
    f = g['fights'][-1]
    return f if f['res'] == 2 or f['post'] <= 0 else None

def stage(f):
    e = ENC.get(f['enc'], str(f['enc']))
    if e in ('THE_HEART', 'SHIELD_AND_SPEAR'): return e
    if f['room'] == 'BOSS': return e
    if f['room'] == 'ELITE': return f'act{f["act"]} elite:' + e
    return f'act{f["act"]} {f["room"].lower()}'

def hpband(f):
    x = f['hp'] / f['maxhp']
    return '<50%' if x < .5 else '50-80%' if x < .8 else '>=80%'

def boot_ci(vals_by_seed, stat, B=2000, rng=None):
    """Seed-clustered bootstrap: vals_by_seed list of per-seed arrays."""
    rng = rng or np.random.default_rng(0)
    n = len(vals_by_seed); out = []
    for _ in range(B):
        idx = rng.integers(0, n, n); out.append(stat([vals_by_seed[i] for i in idx]))
    return np.percentile(out, [2.5, 97.5])
