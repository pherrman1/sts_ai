# usage: turns.py UNITS_DIR -- §711 fights: turns, HP lost, copy SD, potions, CPU per encounter (descriptive)
import glob,json,statistics as st,collections,sys
R=collections.defaultdict(list)
for p in glob.glob(sys.argv[1]+'/**/*.fights.json',recursive=True):
    x=json.load(open(p))
    for f in x['fights']:
        e=f['expert']; reps=[r for r in f['replicates'] if r['valid']]
        if not reps or e['exitHp'] is None or f['loggedFightsOnFloor']>1 or f['room'] not in 'EB': continue
        if f['act']==3 and f['floor']==51: continue
        won=[r for r in reps if r['won']]
        R[(f['act'],f['room'],f['encounter'])].append(dict(
          et=e['turns'], bt=st.mean(r['turns'] for r in reps), btw=st.mean(r['turns'] for r in won) if won else None,
          eloss=f['hp']-(0 if e['died'] else e['exitHp']), bloss=st.mean(f['hp']-(r['exitHp'] if r['won'] else 0) for r in reps),
          blossw=st.mean(f['hp']-r['exitHp'] for r in won) if won else None, ed=e['died'],
          bpu=st.mean(len(r['potionsUsed']) for r in reps), epu=e['potionsUsed'] or 0,
          cpu=st.mean(r['cpu'] for r in reps), deck=f['deck'], hp=f['hp'],
          sd=st.pstdev([f['hp']-(r['exitHp'] if r['won'] else 0) for r in reps])))
print(f"{'enc':28s} n  e_turn b_turn(won) | eloss bloss(won) diff | sd4 | potE potB | cpu/copy")
for k,v in sorted(R.items(),key=lambda kv:(kv[0][0],kv[0][1])):
    if len(v)<20: continue
    m=lambda key:st.mean(r[key] for r in v if r[key] is not None)
    print(f"{k[0]}{k[1]} {k[2][:25]:25s} {len(v):3d} {m('et'):5.2f} {m('btw'):5.2f} | {m('eloss'):5.1f} {m('blossw'):5.1f} {m('bloss')-m('eloss'):+5.1f} | {m('sd'):4.1f} | {m('epu'):.2f} {m('bpu'):.2f} | {m('cpu'):5.1f}")
