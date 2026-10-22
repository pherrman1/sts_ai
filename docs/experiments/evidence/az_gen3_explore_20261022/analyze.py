"""AZ gen-3 exploration block analysis (descriptive): python3 -I analyze.py DIR -> JSON.
DIR is the --extract dir of `verify_campaign.py` (queue schedule) or holds static-schedule wWW.tar files."""
import sys, tarfile, json, gzip, re, glob, statistics, os
def sources(root):
    tars = sorted(glob.glob(root + '/w*.tar'))
    for path in tars:
        t = tarfile.open(path); yield t, {x.name: x for x in t.getmembers() if x.isfile()}
    if not tars:  # extracted queue layout: plain files anywhere under root
        yield None, {f: f for d, _, fs in os.walk(root) for f in (os.path.join(d, x) for x in fs)}
def rd(t, m, sfx):
    k = [n for n in m if n.endswith(sfx)]
    return (t.extractfile(m[k[0]]).read() if t else open(m[k[0]], 'rb').read()) if k else None
c = dict(seeds=0, valid=0, invalid=[], heart=0, act4=0, floors=[], wall=[], decisions=0, searched=0, fullBudget=0,
         early_floor_searched=0, sampled_roots=0, sampled_changed=0, sampled_q_better=0, sampled_q_worse=0,
         sampled_q_delta=[], fast_roots=0, fast_saved=0, overrides=0, paths=set())
for t, m in sources(sys.argv[1]):
    for s in sorted({re.search(r'E-(\d+)\.done$', n).group(1) for n in m if re.search(r'/E-\d+\.done$', n)}):
        c['seeds'] += 1
        done = (rd(t, m, f'E-{s}.done') or b'rc=-1 wall=0').decode(); rc = re.search(r'rc=(-?\d+)', done).group(1)
        j = rd(t, m, f'E-{s}.jsonl.gz')
        if rc != '0' or not j: c['invalid'].append((s, rc)); continue
        lines = gzip.decompress(j).splitlines(); foot = json.loads(lines[-1])
        if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'):
            c['invalid'].append((s, 'footer')); continue
        c['valid'] += 1; c['heart'] += bool(foot.get('heartKilled')); c['act4'] += foot.get('finalAct', 0) >= 4
        c['floors'].append(foot.get('finalFloor', 0)); c['wall'].append(int(re.search(r'wall=(\d+)', done).group(1)))
        path = []
        for x in lines[1:-1]:
            r = json.loads(x)
            if r.get('type') != 'decision': continue
            c['decisions'] += 1; root = r.get('root'); fl = r.get('floor') or 0  # Neow rows carry no floor
            if fl <= 6: path.append(str(r.get('selectedKey')))
            if not root or root.get('singleton') or root.get('aborted'): continue
            c['searched'] += 1; full = bool(root.get('fullBudget')); c['fullBudget'] += full
            if not full: c['fast_roots'] += 1; c['fast_saved'] += bool(root.get('savedSimulations'))
            cand = root.get('candidates', [])
            if cand and root.get('selectedId') != max(cand, key=lambda x: x['prior'])['id']: c['overrides'] += 1
            if fl <= 6:
                c['early_floor_searched'] += 1
                if 'playSampled' in root:
                    c['sampled_roots'] += 1
                    if root['playSampled'] and cand:
                        by = {x['id']: x for x in cand}; greedy = by.get(root.get('searchSelectedId'))
                        played = by.get(root.get('selectedId'))
                        c['sampled_changed'] += 1
                        if greedy and played:
                            dq = played['q'] - greedy['q']; c['sampled_q_delta'].append(dq)
                            c['sampled_q_better'] += dq > 0; c['sampled_q_worse'] += dq < 0
        c['paths'].add('|'.join(path))
v = max(c['valid'], 1)
out = dict(seeds=c['seeds'], valid=c['valid'], invalid=c['invalid'],
           heart_kills=c['heart'], heart_pct=100 * c['heart'] / v, act4=c['act4'], act4_pct=100 * c['act4'] / v,
           mean_floor=statistics.mean(c['floors']) if c['floors'] else 0,
           wall_s=dict(mean=statistics.mean(c['wall']) if c['wall'] else 0, max=max(c['wall'], default=0)),
           decisions=c['decisions'], searched_roots=c['searched'], full_budget_roots=c['fullBudget'],
           prior_overrides_pct=100 * c['overrides'] / max(c['searched'], 1),
           fast_root_early_stop_pct=100 * c['fast_saved'] / max(c['fast_roots'], 1),
           early_floors=dict(searched_roots=c['early_floor_searched'], sample_eligible=c['sampled_roots'],
                             played_not_greedy=c['sampled_changed'],
                             played_not_greedy_pct=100 * c['sampled_changed'] / max(c['sampled_roots'], 1),
                             q_better=c['sampled_q_better'], q_worse=c['sampled_q_worse'],
                             mean_q_delta=statistics.mean(c['sampled_q_delta']) if c['sampled_q_delta'] else 0),
           distinct_floor0_6_trajectories=len(c['paths']))
print(json.dumps(out, indent=1))
