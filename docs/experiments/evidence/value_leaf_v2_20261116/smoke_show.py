import json, glob, sys, statistics as st
S = sys.argv[1]
keys = ('won', 'exitHp', 'exitMaxHp', 'turns', 'decisions', 'simulations', 'potionsUsed')
for fj in sorted(glob.glob(S + '/v2smoke/out/*/*.fights.json')):
    u = fj.split('/')[-2]
    if not glob.glob(fj.replace('.fights.json', '.done')):
        continue
    x = json.load(open(fj))
    refs = glob.glob(f'{S}/v2smoke/ref772/out/units/{u}_g16mb/*.fights.json')
    refb = {f['floor']: f for f in json.load(open(refs[0]))['fights'] if 'arms' in f and f['room'] == 'B'} if refs else {}
    for f in x['fights']:
        if 'arms' not in f:
            continue
        print(u, f['floor'], f['encounter'], 'entry hp', f['hp'])
        for name, reps in [('prod', f['replicates'])] + list(f['arms'].items()):
            lost = st.mean(f['hp'] - (r['exitHp'] if r['won'] else 0) for r in reps)
            cpu = sum(r['cpu'] for r in reps); sims = sum(r['simulations'] for r in reps)
            lv = sum(r.get('leafQValues', 0) for r in reps); fw = sum(r.get('leafQForwards', 0) for r in reps)
            print('  %-24s lost %5.1f  turns %s  cpu %6.1f  us/sim %5.1f  leaf/fwd %s  exit %s' % (
                name, lost, [r['turns'] for r in reps], cpu, 1e6 * cpu / max(1, sims), round(lv / fw, 2) if fw else '-',
                [r['exitHp'] if r['won'] else 'D' for r in reps]))
        rf = refb.get(f['floor'])
        if rf:
            sp = [all(json.dumps(a.get(k)) == json.dumps(b.get(k)) for k in keys) for a, b in zip(f['replicates'], rf['replicates'])]
            sg = [all(json.dumps(a.get(k)) == json.dumps(b.get(k)) for k in keys) for a, b in zip(f['arms']['gsh16+flat16000+mb4'], rf['arms']['gsh16+flat16000+mb4'])]
            print('  repro: prod vs 772', sp, ' g16mb vs 772', sg)
