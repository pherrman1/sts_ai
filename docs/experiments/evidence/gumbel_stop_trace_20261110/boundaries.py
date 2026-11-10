import csv,glob,os,collections,sys
S=os.path.dirname(os.path.abspath(__file__))
agg=collections.defaultdict(lambda:[0,0,0.0,0.0,0.0])
roots=0
for f in glob.glob(S+'/out/*-on.csv'):
    byroot=collections.defaultdict(list)
    for r in csv.DictReader(open(f)): byroot[(r['seed'],r['combat'],r['decision'])].append(r)
    for rs in byroot.values():
        roots+=1
        for r in rs:
            k=(int(r['phases']),int(r['boundary']))
            a=agg[k]; a[0]+=1; a[1]+=int(r['leader_is_final'])
            rc=float(r['root_cpu_seconds']); a[2]+=float(r['cpu_seconds']); a[3]+=rc
            a[4]+=int(r['spent'])/max(int(r['root_sims']),1)
print('roots',roots)
print('phases boundary n leader==final cpu_share sim_share')
for k in sorted(agg):
    n,h,c,rc,ss=agg[k]; print(k[0],k[1],n,f"{h/n:.3f}",f"{c/max(rc,1e-9):.3f}",f"{ss/n:.3f}")
