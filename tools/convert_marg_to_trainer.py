#!/usr/bin/env python3
"""Convert strategicmarggen diagnostic CSV to trainer-compatible M0/M1 CSVs.

The diagnostic CSV now has all columns needed for the strategicHeader2() schema
including actionBits, actionType, c1-c3, cand1-cand3, richState, and source outcome.
"""
import csv, sys, numpy as np
from collections import defaultdict

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 tools/convert_marg_to_trainer.py <diag.csv> <m0_out.csv> <m1_out.csv>")
        sys.exit(1)

    rows = list(csv.DictReader(open(sys.argv[1])))
    
    # Group by (seed, decIdx) -> action -> regime -> list of (labelWon, labelHp, labelFloor, labelBootstrap)
    groups = defaultdict(lambda: defaultdict(lambda: {'fixed': [], 'marg': []}))
    dec_meta = {}
    for r in rows:
        key = (r['seed'], r['decIdx'])
        ai = int(r['actionIdx'])
        regime = r['regime']
        if regime not in ('fixed', 'marg'):
            continue
        groups[key][ai][regime].append((
            float(r['labelWon']), float(r['labelHp']),
            float(r['labelFloor']), float(r['labelBootstrap'])))
        if key not in dec_meta:
            dec_meta[key] = {
                'screen': r['gateKind'],
                'state': r['richState'],
                'act': r['act'],
                'floor': r['floor'],
                'sourceWon': r.get('sourceWon', '0'),
                'sourceFloor': r.get('sourceFloor', '0'),
                'sourceHp': r.get('sourceHp', '0'),
                'chosenIdx': r.get('chosenIdx', '-1'),
            }

    # Build action metadata lookup
    action_meta = {}
    for r in rows:
        key = (r['seed'], r['decIdx'], r['actionIdx'])
        if key not in action_meta:
            am = r.get('actionBits', '0') + ',' + r.get('actionType', '-1') + ',' + \
                 r.get('c1', '0') + ',' + r.get('c2', '0') + ',' + r.get('c3', '0') + ',' + \
                 r.get('cand1', '-1') + ',' + r.get('cand2', '-1') + ',' + r.get('cand3', '-1')
            action_meta[key] = am

    # Write M0 and M1
    with open(sys.argv[2], 'w') as f0, open(sys.argv[3], 'w') as f1:
        hdr = "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen," + \
              "ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor," + \
              "blueKey,greenKey,redKey,potionCount,potionCapacity,bossId," + \
              "won,endFloor,endHp,labelWon,labelHp,labelFloor,labelBootstrap\n"
        f0.write(hdr)
        f1.write(hdr)

        for key in sorted(groups):
            dec = groups[key]
            meta = dec_meta[key]
            n_actions = len(dec)
            if n_actions < 2:
                continue

            for ai in sorted(dec):
                fixed = dec[ai]['fixed']
                marg  = dec[ai]['marg']
                if not fixed or not marg:
                    continue

                fw = np.mean([x[0] for x in fixed])
                fh = np.mean([x[1] for x in fixed])
                ff = np.mean([x[2] for x in fixed])
                fb = np.mean([x[3] for x in fixed])
                mw = np.mean([x[0] for x in marg])
                mh = np.mean([x[1] for x in marg])
                mf = np.mean([x[2] for x in marg])
                mb = np.mean([x[3] for x in marg])

                am = action_meta.get((key[0], key[1], str(ai)), "0,-1,0,0,0,-1,-1,-1")
                chosen = "1" if str(ai) == meta.get('chosenIdx', '-1') else "0"

                base = f"{key[0]},{key[1]},{meta['screen']},{am},{chosen},{meta['state']}," \
                       f"{meta['sourceWon']},{meta['sourceFloor']},{meta['sourceHp']}"

                f0.write(f"{base},{fw:.6f},{fh:.6f},{ff:.6f},{fb:.6f}\n")
                f1.write(f"{base},{mw:.6f},{mh:.6f},{mf:.6f},{mb:.6f}\n")

    print(f"wrote {sys.argv[2]} and {sys.argv[3]}")

if __name__ == "__main__":
    main()
