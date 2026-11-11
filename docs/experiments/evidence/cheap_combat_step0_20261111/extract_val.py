import subprocess, gzip, json, sys, os, pickle, numpy as np
from multiprocessing import Pool
G='/tmp/claude-0/s0/t1'
def split(s): return (s*2654435761)%(2**32)%10
def files():
    out=[]
    for p in ['p0','p1','p2','p3']:
        for n in subprocess.run(['git','-C',G,'ls-tree','-r','--name-only','refs/x/'+p],capture_output=True,text=True).stdout.split():
            if n.endswith('.jsonl.gz'): out.append((p,n))
    return out
def work(pn):
    p,n=pn
    raw=subprocess.run(['git','-C',G,'show',f'refs/x/{p}:{n}'],capture_output=True).stdout
    recs=[]; lines=[]
    for line in gzip.decompress(raw).splitlines():
        d=json.loads(line)
        if split(int(d['seed']))!=1: continue
        lines.append(line)
        if d.get('kind')!='root' or d.get('skipped'): continue
        E=d['edges']
        if len(E)<2: continue
        recs.append(dict(seed=d['seed'],fight=d['fight'],act=d['act'],room=d['room'],enc=d['encounter'],turn=d['turn'],
            g=d.get('gumbelChoice',-1),prior=[e.get('prior',0.0) for e in E],q=[e.get('q') for e in E],qb=[e.get('qBacked') for e in E],
            sims=[e.get('childSims',0) for e in E]))
    return recs,lines
if __name__=='__main__':
    F=files(); print(len(F),flush=True)
    allr=[]; 
    with Pool(8) as pool, gzip.open('/tmp/claude-0/s0/val_rows.jsonl.gz','wb') as out:
        for recs,lines in pool.imap_unordered(work,F,chunksize=4):
            allr+=recs
            for l in lines: out.write(l+b'\n')
    pickle.dump(allr,open('/tmp/claude-0/s0/val_roots.pkl','wb')); print(len(allr))
