import re,sys,glob,math,collections
acc=collections.defaultdict(lambda:[0,0.0,0])
for f in sorted(glob.glob(sys.argv[1]+'/*.err')):
    for l in open(f):
        m=re.match(r'\[rollsd\] act=(\d+) enc=(\d+) sd=([\d.eE+-]+) n=(\d+)',l)
        if m:
            a=int(m[1]);sd=float(m[3]);n=int(m[4]);r=acc[a];r[0]+=1;r[1]+=sd*sd*n;r[2]+=n
for a in sorted(acc):
    r=acc[a];print('act',a,'roots',r[0],'pooled within-edge sd %.1f'%math.sqrt(r[1]/r[2]))
