import re,sys,glob,math,collections
acc=collections.defaultdict(lambda:[0,0.0,0])
# usage: rollsd_pool.py DIR (reads DIR/*.err) or rollsd_pool.py FILE (e.g. results/rollsd_lines.txt, prefixed lines)
import os
files=sorted(glob.glob(sys.argv[1]+'/*.err')) if os.path.isdir(sys.argv[1]) else [sys.argv[1]]
for f in files:
    for l in open(f):
        m=re.search(r'\[rollsd\] act=(\d+) enc=(\d+) sd=([\d.eE+-]+) n=(\d+)',l)
        if m:
            a=int(m[1]);sd=float(m[3]);n=int(m[4]);r=acc[a];r[0]+=1;r[1]+=sd*sd*n;r[2]+=n
for a in sorted(acc):
    r=acc[a];print('act',a,'roots',r[0],'pooled within-edge sd %.1f'%math.sqrt(r[1]/r[2]))
