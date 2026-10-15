import json,glob,sys,statistics as st
rows=[]
for f in sorted(glob.glob(sys.argv[1]+"/C-*.chest.jsonl")):
    for l in open(f): rows.append(json.loads(l))
scr={2:"REWARDS",4:"CARD_SELECT",5:"MAP"}
print("seed floor relic | map: with relic, without, delta (x2b) | rewards screen live: root, after relic | relic_map screen")
d=[]
for r in rows:
    wm,nm=r['relic_map']['x2b'],r['gold_map']['x2b']
    d.append(wm-nm)
    print(r['seed'],r['floor'],",".join(r['relics']),f"| {wm:.4f} {nm:.4f} {wm-nm:+.4f} | {r['root']['live']:.4f} {r['relic_screen']['live']:.4f} {r['leave']['live']:.4f} | {scr.get(r['relic_map']['screen'],r['relic_map']['screen'])}")
print("n",len(d),"mean delta %+.4f"%st.mean(d),"median %+.4f"%st.median(d),"pos",sum(x>1e-9 for x in d),"zero",sum(abs(x)<=1e-9 for x in d),"neg",sum(x< -1e-9 for x in d))
