# Post-hoc diagnostic (not pre-registered): variance decomposition of the pilot per corrected fight set.
# usage: python decomp.py V_PREFIX source_tars.sha256 REPLAYS.jsonl.gz ...
import sys, json, gzip, numpy as np
sys.path.insert(0, 'tools')
import aivat_estimate as ae
model, feat, sha = ae.load_model(sys.argv[1])
srcs = [l.split()[1] for l in open(sys.argv[2])]
runs = ae.runs_from_units(['/mnt/project-files/ctm-calibration-ab/units/'+s for s in srcs])
reps = {}
for p in sys.argv[3:]:
    for line in gzip.open(p,'rt'):
        r = json.loads(line)
        if r['replicate']>0: reps.setdefault((r['arm'],r['sourceSeed'],r['fightIdx']),[]).append(r)
pend=[]; vals={}
for (arm,seed),(y,fights) in runs.items():
    for f in fights:
        k=(arm,seed,f['fightIdx'])
        if k not in reps: continue
        posts=[('real',f['transition']['post'],f['transition']['combatOutcome'])]+[(i,r['post'],r['combatOutcome']) for i,r in enumerate(reps[k])]
        for t,post,o in posts:
            if o!=1: vals[(k,t)]=0.0
            elif f['encounter']==ae.HEART: vals[(k,t)]=1.0
            else: pend.append(((k,t),feat(post,f['act'],f['floor'])))
pr=model.predict_proba(np.array([x for _,x in pend]))[:,1]
for (key,_),p in zip(pend,pr): vals[key]=float(p)
def cls(f):
    if f['encounter']==ae.HEART: return 'HEART'
    return 'BOSS' if f['roomClass']=='BOSS' else 'OTHER'
seeds=sorted({s for a,s in runs})
out={}
for sel in ['all','HEART','BOSS+HEART']:
    D=[];L=[];W=[]
    for s in seeds:
        d=0;l=0;w=0
        for arm,sg in (('C',1),('A',-1)):
            y,fights=runs[(arm,s)]
            d+=sg*y
            for f in fights:
                k=(arm,s,f['fightIdx'])
                if k not in reps: continue
                c=cls(f)
                if sel=='HEART' and c!='HEART': continue
                if sel=='BOSS+HEART' and c=='OTHER': continue
                rv=[vals[(k,i)] for i in range(len(reps[k]))]
                l+=sg*(vals[(k,'real')]-np.mean(rv))
                w+=np.var(rv,ddof=1)/len(rv)  # replay-mean noise
        D.append(d);L.append(l);W.append(w)
    D,L=np.array(D),np.array(L)
    c=np.cov(D,L); bopt=c[0,1]/c[1,1]
    sd=lambda b: np.std(D-b*L,ddof=1)/np.std(D,ddof=1)
    out[sel]={'ratio_b0.8':sd(0.8),'beta_opt':bopt,'ratio_bopt':sd(bopt),'corr':c[0,1]/np.sqrt(c[0,0]*c[1,1]),
              'var_raw':c[0,0],'var_luck':c[1,1],'replaymean_noise_var':float(np.mean(W))}
print(json.dumps(out,indent=1))
