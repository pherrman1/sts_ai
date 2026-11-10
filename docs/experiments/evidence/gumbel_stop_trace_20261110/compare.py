import re,sys,glob,os,csv,collections
S=os.path.dirname(os.path.abspath(__file__))
def key(log,err):
    t=open(log).read()+open(err).read()
    best=re.search(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+)\s+avg_hp_end=\s*([\d.]+)",t,re.M)
    ppo=re.search(r"\[heart1_ppo\] seed=\d+ decisions=(\d+) single=(\d+) fallbacks=(\d+)",t)
    g=re.search(r"\[silver\] whole-run Gumbel roots=(\d+) sims=(\d+)",t)
    return (best.groups() if best else None, ppo.groups() if ppo else None, g.groups() if g else None)
rows=[]
for d in sorted(glob.glob(S+'/out/*.done')):
    tag=os.path.basename(d)[:-5]; arm,seed,mode=tag.split('-')
    rc=open(d).read().split()[1]
    o=f"{S}/../u/out/units/{seed}_low/{arm}-{seed}"
    a=key(o+'.log',o+'.err'); b=key(f"{S}/out/{tag}.log",f"{S}/out/{tag}.err")
    extra=''
    if mode=='on':
        r=list(csv.DictReader(open(f"{S}/out/{tag}.csv")))
        roots={(x['combat'],x['decision']) for x in r}
        extra=f" trace_rows={len(r)} traced_roots={len(roots)}"
    print(tag,rc,'SAME' if a==b and a[0] else 'DIFF',a,b if a!=b else '',extra)
