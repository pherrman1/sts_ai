import tarfile, sys, io, lzma, csv, re, glob, collections, json
units=sorted(glob.glob('/mnt/project-files/gumbel-stop/data/units/*.tar'))
rows=[]; games=[]
for t in units:
    with tarfile.open(t) as tf:
        for m in tf.getmembers():
            n=m.name
            if n.endswith('.csv.xz'):
                data=lzma.decompress(tf.extractfile(m).read()).decode()
                r=csv.DictReader(io.StringIO(data))
                for d in r:
                    if d['boundary']=='0':
                        rows.append((int(d['seed']),int(d['combat']),int(d['floor']),int(d['act']),int(d['room']),int(d['legal_actions']),int(d['inherited_visits']),int(d['budget']),float(d['root_cpu_seconds']),int(d['root_sims']),int(d['phases']),int(d['candidates'])))
            elif n.endswith('.log') and '/G16-' in n:
                s=tf.extractfile(m).read().decode()
                mm=re.search(r'win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*cpu_sec/run=\s*([\d.]+)',s)
                if mm: games.append((n,float(mm.group(1)),float(mm.group(2)),float(mm.group(3))))
import pickle; pickle.dump((rows,games),open('/tmp/claude-0/s0/cpumap.pkl','wb'))
print(len(rows),len(games))
