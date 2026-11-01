"""Extract a compact per-game table from campaign unit tars on the project share (read-only, no seeds).
usage: extract_all.py CAMPAIGN_DIR LABEL OUT.pkl
One record per complete game: campaign, arm, seed, outcome, and per fight (from the CTM rows) act, floor, encounter,
room, entry/exit HP, max HP, potions, deck, relics, outcome. Arms are the file prefixes (A-<seed>.jsonl.gz ...).
"""
import sys, os, io, json, gzip, tarfile, pickle, re
def rows(b):
    return [json.loads(x) for x in gzip.decompress(b).decode().splitlines() if x.strip()]
def pots(l): return [p for p in l if p not in (0, 1)]
def main(cdir, label, outp):
    games, envs = [], {}
    tars = sorted(f for f in os.listdir(os.path.join(cdir, 'units')) if f.endswith('.tar'))
    for t in tars:
        try: tf = tarfile.open(os.path.join(cdir, 'units', t))
        except Exception as e: print('bad tar', t, e, file=sys.stderr); continue
        files = {}
        for m in tf.getmembers():
            n = os.path.basename(m.name)
            if m.isfile() and (n.endswith('.jsonl.gz') or n.endswith('.env')):
                files[m.name] = tf.extractfile(m).read()
        for name, b in files.items():
            n = os.path.basename(name)
            mm = re.match(r'^([A-Za-z0-9]+)-(\d+)\.jsonl\.gz$', n)
            if not mm: continue
            arm, seed = mm.group(1), int(mm.group(2))
            cname = name.replace('.jsonl.gz', '.ctm.jsonl.gz')
            if cname not in files: continue
            envn = name.replace('.jsonl.gz', '.env')
            if arm not in envs and envn in files: envs[arm] = files[envn].decode(errors='replace')
            try: g = rows(b); c = rows(files[cname])
            except Exception as e: print('bad', name, e, file=sys.stderr); continue
            out = [r for r in g if r.get('type') == 'outcome']
            if not out or not out[-1].get('complete'): continue
            o = out[-1]
            fights = []
            for r in c:
                tr = r['transition']; pre, post = tr['pre'], tr['post']
                fights.append(dict(act=r['act'], floor=r['floor'], enc=r['encounter'], room=r['roomClass'],
                    hp=pre['curHp'], maxhp=pre['maxHp'], post=post['curHp'], res=tr['combatOutcome'],
                    pots=pots(pre['potions']), postpots=pots(post['potions']), cap=pre['potionCapacity'],
                    deck=[(d['id'], d['upgraded']) for d in pre['deck']], relics=[x['id'] for x in pre['relics']],
                    gold=pre.get('gold')))
            asc = None
            for r in g:
                if r.get('type') == 'state': asc = r.get('ascension', asc); break
            games.append(dict(camp=label, arm=arm, seed=seed, unit=t, kill=bool(o['heartKilled']), fact=o['finalAct'],
                              ffloor=o['finalFloor'], fhp=o['finalHp'], asc=asc, fights=fights))
    pickle.dump(dict(games=games, envs=envs), open(outp, 'wb'))
    print(label, len(tars), 'tars', len(games), 'games', sorted(set(x['arm'] for x in games)))
if __name__ == '__main__': main(*sys.argv[1:])
