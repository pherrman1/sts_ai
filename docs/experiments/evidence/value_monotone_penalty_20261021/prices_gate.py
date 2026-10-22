"""Teacher-gate items from prices.py meta + scores: -1/-3/-6 HP sign right, max HP (+5) and gold (+50) price > 0."""
import json, sys, numpy as np
meta = json.load(open(sys.argv[1])); z = [json.loads(l)['value'] for l in open(sys.argv[2])]
st = {}
for m, v in zip(meta, z): st.setdefault((m['seed'], m['floor']), {})[m['pert']] = 1 / (1 + np.exp(-v))
pos = {k for k, s in st.items() if 'hp-12' in s and (s['base'] - s['hp-12']) / 12 > 1e-4}
out = {f'hpSignRight-{d}': float(np.mean([s['base'] > s[f'hp-{d}'] for s in st.values() if f'hp-{d}' in s])) for d in (1, 3, 6)}
for p in ('mhp+5', 'gold+50'):
    out[p + ' >0 (pos-slope)'] = float(np.mean([st[k][p] > st[k]['base'] for k in pos if p in st[k]]))
    out[p + ' >0 (all)'] = float(np.mean([s[p] > s['base'] for s in st.values() if p in s]))
out['potion removed lowers value'] = float(np.mean([s[p] < s['base'] for s in st.values() for p in s if p.startswith('pot-')]))
out['parasite lowers value'] = float(np.mean([s['parasite'] < s['base'] for s in st.values()]))
print(json.dumps({k: round(v, 4) for k, v in out.items()}))
