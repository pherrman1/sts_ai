#!/usr/bin/env python3
"""Extract §727 chooser logs + outcomes. usage: extract.py OUT_PKL  (reads /mnt/project-files/value-chooser-ab/units/*.tar)"""
import tarfile, gzip, json, os, sys, pickle, io
D='/mnt/project-files/value-chooser-ab/units'
out=[]
for fn in sorted(os.listdir(D)):
    if not fn.endswith('.tar'): continue
    t=tarfile.open(os.path.join(D,fn))
    rec={}
    for m in t.getmembers():
        b=os.path.basename(m.name)
        if b.endswith('.chooser.jsonl.gz') or (b.endswith('.jsonl.gz') and not b.endswith('ctm.jsonl.gz') and b[0] in 'AB'):
            data=gzip.decompress(t.extractfile(m).read()).decode()
            rows=[json.loads(x) for x in data.splitlines() if x.strip()]
            if 'chooser' in b: rec['ch']=rows
            else:
                o=[r for r in rows if r.get('type')=='outcome']
                rec[b[0]]=o[-1] if o else None
        elif b.endswith('.done') and b[0].isdigit() and m.size>0:
            rec['done']=t.extractfile(m).read().decode(); rec['seed']=int(b.split('.')[0])
    out.append(rec)
pickle.dump(out,open(sys.argv[1],'wb'))
print(len(out))
