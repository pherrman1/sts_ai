import tarfile, gzip, sys, os, collections, json
root='/mnt/project-files'
camps=sys.argv[1:]
for c in camps:
    d=f'{root}/{c}/units'; cnt=collections.Counter(); seeds=0
    for f in sorted(os.listdir(d)):
        if not f.endswith('.tar'): continue
        try: t=tarfile.open(f'{d}/{f}')
        except Exception as e: cnt['BADTAR']+=1; continue
        seeds+=1
        for m in t.getmembers():
            if m.name.endswith('.ctm.jsonl.gz'):
                arm=os.path.basename(m.name).split('-')[0]
                cnt[arm]+=sum(1 for _ in gzip.open(t.extractfile(m)))
    print(c, seeds, dict(cnt), sum(v for k,v in cnt.items() if k!='BADTAR'), flush=True)
