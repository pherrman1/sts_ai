import pickle, sys, collections
sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from names import *
for f in sys.argv[1:]:
    G=pickle.load(open(f,'rb')); n=len(G)
    kills=sum(g['o']['kill'] for g in G)
    print(f'== {f}: n={n} kill={kills/n:.3f}')
    endc=collections.Counter(); deathfight=collections.Counter(); noctm=0
    for g in G:
        if g['o']['kill']: endc['kill']+=1; continue
        fs=g['fights']; last=fs[-1] if fs else None
        if last and last['post']<=0:
            endc[f"act{last['act']}_{last['room']}"]+=1
            deathfight[ENC.get(last['enc'],last['enc'])]+=1
        else:
            endc[f"nonfight act{g['o']['act']} hp{g['o']['hp']} fl{g['o']['floor']}"]+=1
    for k,v in sorted(endc.items(), key=lambda x:-x[1])[:20]: print(f'  {k:40s} {v:5d} {v/n*100:5.1f}%')
    print('  deaths by encounter:')
    # per-encounter death rate
    fought=collections.Counter(); died=collections.Counter()
    for g in G:
        for fi in g['fights']:
            e=ENC.get(fi['enc'],fi['enc']); fought[e]+=1; died[e]+= fi['post']<=0
    for e,v in deathfight.most_common(30): print(f'  {e:28s} deaths {v:4d} ({v/n*100:4.1f}% of runs)  fought {fought[e]:5d} death rate {died[e]/fought[e]*100:5.1f}%')
