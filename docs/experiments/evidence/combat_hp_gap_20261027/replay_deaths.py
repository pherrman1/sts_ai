"""The #868 X-arm games that died while still following the expert's log, next to the expert's own fight there.

usage: python3 -I replay_deaths.py <expert_replay_ab_units_dir> <expert_fights.jsonl> <repo_root> <out.json>

In-log death: X game died (final HP 0; the Emerald-key defect games end alive and are excluded), replay never stopped (stopFloor -1, no stop reason), final floor below the expert's
floorReached. At the death floor the X game had the expert's exact deck, relics, path and potion rewards (the replay
stops at the first offer or action that differs), but its own HP and its own potion use so far.
"""
import json, sys, glob, os, re, collections, statistics as st

units, ef, repo, out = sys.argv[1:5]
t = open(os.path.join(repo, 'include/constants/MonsterEncounters.h')).read()
m = re.search(r'enum class MonsterEncounter[^{]*\{(.*?)\};', t, re.S)
ENC = [x.strip().split('=')[0].strip() for x in re.sub(r'//[^\n]*', '', m.group(1)).split(',') if x.strip()]
E = collections.defaultdict(dict)
for l in open(ef):
    r = json.loads(l); E[r['run']][r['floor']] = r
rows = []
for f in sorted(glob.glob(os.path.join(units, '**', 'X-*.json'), recursive=True)):
    x = json.load(open(f)); rid = os.path.basename(f)[2:-5]
    b = json.load(open(f.replace('/X-', '/B-'))) if os.path.exists(f.replace('/X-', '/B-')) else None
    rp = x['replay']
    if x['heartKilled'] or x['finalHp'] > 0 or rp['stopFloor'] >= 0 or rp['stopReason'] or x['finalFloor'] >= x['expert']['floorReached']:
        continue
    fl = x['finalFloor']; e = E[rid].get(fl)
    prior = [E[rid][g] for g in sorted(E[rid]) if g < fl]
    rows.append(dict(run=rid, floor=fl, act=x['finalAct'], bot_death_enc=ENC[x['deathEncounter']] if x.get('deathCombat', -1) >= 0 else None,
                     expert_enc=e['enc'] if e else None, expert_room=e['room'] if e else None,
                     expert_entry_hp=e['entry_hp'] if e else None, expert_entry_maxhp=e['entry_maxhp'] if e else None,
                     expert_gross=e['gross'] if e else None, expert_net=e['net'] if e else None,
                     expert_uses_here=e['uses'] if e else None, expert_inv_entry=e['inv_entry'] if e and e['inv_ok'] else None,
                     expert_uses_before=sum(p['uses'] for p in prior), expert_won_run=x['expert']['victory'],
                     B_heart=bool(b and b['heartKilled']), B_floor=b['finalFloor'] if b else None))
json.dump(rows, open(out, 'w'), indent=1)
print(len(rows), 'in-log deaths')
print('non-combat (no death encounter):', sum(1 for r in rows if r['bot_death_enc'] is None))
print('by act', collections.Counter(r['act'] for r in rows))
print('by expert room', collections.Counter(r['expert_room'] for r in rows))
print('by encounter', collections.Counter(r['expert_enc'] for r in rows).most_common(12))
c = [r for r in rows if r['expert_entry_hp'] is not None and r['bot_death_enc']]
print('expert entry HP frac median', st.median(r['expert_entry_hp'] / r['expert_entry_maxhp'] for r in c),
      'expert net loss median', st.median(r['expert_net'] for r in c if r['expert_net'] is not None),
      'expert gross median', st.median(r['expert_gross'] for r in c))
print('expert gross >= 50% of max HP:', sum(1 for r in c if r['expert_gross'] >= 0.5 * r['expert_entry_maxhp']), 'of', len(c))
print('expert used a potion in that fight:', sum(1 for r in c if r['expert_uses_here']), 'of', len(c))
print('B on the same seed killed the Heart', sum(r['B_heart'] for r in rows), '; B died at or before that floor',
      sum(1 for r in rows if r['B_floor'] is not None and r['B_floor'] <= r['floor'] and not r['B_heart']))
