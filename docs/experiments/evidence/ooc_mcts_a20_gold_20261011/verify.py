import pickle,csv,sys,json,collections
hdr,rows=pickle.load(open('gold_all.pkl','rb'))
n=len(hdr)-7  # strip won,endFloor,endHp + 4 labels
gold=collections.defaultdict(list)
for x in rows: gold[int(x[0])].append(x)
tot=bad=0; badseeds=set()
for f in sys.argv[1:]:
    with open(f) as fh:
        r=csv.reader(fh); h=next(r)
        mine=collections.defaultdict(list)
        for x in r:
            if x and x[0].isdigit(): mine[int(x[0])].append(x)
    for s,ms in mine.items():
        g=gold[s]
        for i,m in enumerate(ms):
            tot+=1
            if i>=len(g) or g[i][:n]!=m[:n]:
                bad+=1; badseeds.add(s)
                if bad<=3:
                    gi=g[i] if i<len(g) else []
                    diff=[(hdr[j],gi[j] if j<len(gi) else None,m[j]) for j in range(n) if j>=len(gi) or gi[j]!=m[j]][:8]
                    print('MISMATCH',s,i,diff)
print('rows',tot,'mismatch',bad,'seeds bad',sorted(badseeds)[:20], 'n seeds', len(badseeds))
