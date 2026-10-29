# Stage 0: per-state label variance, act-end rollout (M0 terminal, deaths 0) vs Bernoulli full-game outcome.
# Input: roots.jsonl.gz from data branch claude/sibling-noise-881-data (sibling-noise-881/roots.jsonl.gz).
import json,gzip,sys,statistics as st,collections
rows=[json.loads(l) for l in gzip.open(sys.argv[1])]
agg=collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
  acts=r['actions']
  keys=('all','act%d'%r['act'],r['screen'])
  for a in acts:
    ae=a['actEnd']; p=st.mean(ae)
    if 0<p<1:
      for k in keys:
        agg[k]['v'].append(st.pvariance(ae)); agg[k]['b'].append(p*(1-p)); agg[k]['p'].append(p)
        agg[k]['d'].append(sum(x==0 for x in ae)/len(ae))
  if len(acts)>=2:
    a,b=acts[0],acts[1]; pa,pb=st.mean(a['actEnd']),st.mean(b['actEnd'])
    d=[x-y for x,y in zip(a['actEnd'],b['actEnd'])]
    for k in keys: agg[k]['dv'].append(st.pvariance(d)); agg[k]['db'].append(pa*(1-pa)+pb*(1-pb))
print("group n mean_p death_share var_actEnd var_bernoulli ratio sib_diff_ratio")
for k,g in sorted(agg.items()):
  if len(g['b'])<30: continue
  print(k,len(g['b']),round(st.mean(g['p']),3),round(st.mean(g['d']),3),round(st.mean(g['v']),4),round(st.mean(g['b']),4),
        round(st.mean(g['v'])/st.mean(g['b']),3),round(st.mean(g['dv'])/st.mean(g['db']),3))
