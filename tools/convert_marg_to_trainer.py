#!/usr/bin/env python3
"""Convert strategicmarggen diagnostic CSV to trainer-compatible M0/M1 CSVs.

Usage:
  python3 tools/convert_marg_to_trainer.py <diag.csv> <m0_out.csv> <m1_out.csv>

The diagnostic CSV has per-sample rows. This script:
1. Averages labelWon/labelHp/labelFloor/labelBootstrap over H samples per regime
2. Writes one row per action per decision (same format as strategicgen2)
3. M0 uses fixed-world averages, M1 uses marginalized averages
4. Both CSVs share identical non-label columns (seed,decIdx,screen,action,...,
   rich state, source terminal outcome)
"""
import csv, sys, os, numpy as np
from collections import defaultdict


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    diag_csv = sys.argv[1]
    m0_out = sys.argv[2]
    m1_out = sys.argv[3]

    # Load diagnostic
    rows = list(csv.DictReader(open(diag_csv)))
    if 'richState' not in rows[0]:
        print("ERROR: diagnostic CSV missing richState column. Re-run with updated binary.")
        sys.exit(1)

    # Group by (seed, decIdx) -> action -> regime -> list of (labelWon, labelHp, labelFloor, labelBootstrap)
    groups = defaultdict(lambda: defaultdict(lambda: {'fixed': [], 'marg': []}))
    dec_meta = {}
    for r in rows:
        key = (r['seed'], r['decIdx'])
        ai = int(r['actionIdx'])
        regime = r['regime']
        groups[key][ai][regime].append((
            float(r['labelWon']), float(r['labelHp']),
            float(r['labelFloor']), float(r['labelBootstrap'])))
        if key not in dec_meta:
            dec_meta[key] = {
                'screen': r['gateKind'],
                'state': r['richState'],
                'act': r['act'],
                'floor': r['floor'],
            }

    # Also need source terminal outcome. The diagnostic doesn't record this directly.
    # For now, use the max seen floor/utility as a proxy. In a real run, the source
    # program would record won/endFloor/endHp from the source run.
    # We'll use the last row's data as a stand-in.

    # Build action/candidate metadata. The diagnostic has actions but not the detailed
    # action/candidate columns. We'll use actionIdx as a proxy and mark chosen=0.
    # The action bits can't be reconstructed from the diagnostic alone.

    # Write M0
    with open(m0_out, 'w') as f0, open(m1_out, 'w') as f1:
        hdr = "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen," \
              + "ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor," \
              + "blueKey,greenKey,redKey,potionCount,potionCapacity,bossId," \
              + "won,endFloor,endHp,labelWon,labelHp,labelFloor,labelBootstrap\n"
        f0.write(hdr)
        f1.write(hdr)

        for key in sorted(groups):
            dec = groups[key]
            meta = dec_meta[key]
            n_actions = len(dec)
            if n_actions < 2:
                continue

            # Average over hidden samples
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

                # Action/candidate placeholders (can't reconstruct from diagnostic)
                action = ai  # proxy
                chosen = 0  # can't determine from diagnostic

                base = f"{key[0]},{key[1]},{meta['screen']},{action},-1,0,0,0,-1,-1,-1,{chosen},{meta['state']},0,0,0"

                f0.write(f"{base},{fw:.6f},{fh:.6f},{ff:.6f},{fb:.6f}\n")
                f1.write(f"{base},{mw:.6f},{mh:.6f},{mf:.6f},{mb:.6f}\n")

    print(f"wrote {m0_out} and {m1_out}")


if __name__ == "__main__":
    main()
