"""g16mb+lq in a variant dir against g16mb (and production) of the first smoke, boss by boss, same copies."""
import glob, json, statistics as st, sys
S, var = sys.argv[1], sys.argv[2]
G, L = 'gsh16+flat16000+mb4', 'gsh16+flat16000+mb4+lq'
tot = []
for fj in sorted(glob.glob(f'{S}/v2smoke/{var}/*/*.fights.json')):
    u = fj.split('/')[-2]
    if not glob.glob(fj.replace('.fights.json', '.done')):
        continue
    base = {f['floor']: f for f in json.load(open(glob.glob(f'{S}/v2smoke/out/{u}/*.fights.json')[0]))['fights'] if 'arms' in f}
    for f in json.load(open(fj))['fights']:
        if 'arms' not in f or L not in f['arms']:
            continue
        b = base[f['floor']]
        lost = lambda reps: st.mean(f['hp'] - (r['exitHp'] if r['won'] else 0) for r in reps)
        cpu = lambda reps: sum(r['cpu'] for r in reps)
        dl = lost(f['arms'][L]) - lost(b['arms'][G])
        ratio = cpu(f['arms'][L]) / cpu(b['arms'][G])
        tot.append((dl, ratio))
        print(f"{u} {f['encounter']:<16} prod {lost(b['replicates']):6.1f}  g16mb {lost(b['arms'][G]):6.1f}  {var} {lost(f['arms'][L]):6.1f}"
              f"  diff {dl:+6.1f}  cpu ratio {ratio:4.2f}  fwd {sum(r.get('leafQForwards', 0) for r in f['arms'][L])}"
              f"  turns {[r['turns'] for r in f['arms'][L]]} vs {[r['turns'] for r in b['arms'][G]]}")
if tot:
    print(f'mean diff {st.mean(d for d, _ in tot):+.2f} over {len(tot)} bosses, mean cpu ratio {st.mean(r for _, r in tot):.2f}')
