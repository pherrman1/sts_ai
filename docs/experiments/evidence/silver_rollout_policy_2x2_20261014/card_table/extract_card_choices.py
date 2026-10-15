"""Extract (hand card options, Silver's chosen card) from gen-6 self-play root records.

Usage: python3 -I extract_card_choices.py REPO DATA_DIR OUT.json
Only PLAYER_NORMAL roots with >= 2 distinct playable (id, upgraded) card-play edges count.
Label = the (id, upgraded) whose card-play edges (summed over targets) have the most visits.
"""
import gzip, json, os, re, sys

repo, data, out = sys.argv[1:4]

# CardId numeric values from the enum order in include/constants/Cards.h.
src = open(os.path.join(repo, "include/constants/Cards.h")).read()
body = src[src.index("enum class CardId"):]
body = body[body.index("{") + 1:body.index("}")]
names = [t.strip().split("=")[0].strip() for t in body.split(",") if t.strip()]
card_id = {n: i for i, n in enumerate(names)}

cpp = open(os.path.join(repo, "src/sim/search/SilverRolloutAgent.cpp")).read()
blk = cpp[cpp.index("cardPlayPriorities = {"):]
blk = blk[:blk.index("};")]
play_order = re.findall(r"CardId::(\w+)", blk)
play_map = {card_id[n]: i + 1 for i, n in enumerate(play_order)}

sem = re.compile(r"sa/t=(\d+)/s=\d+/c=(\d+)_(-?\d+)_(\d+)_")
rows = []
for w in sorted(os.listdir(data)):
    d = os.path.join(data, w)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".jsonl.gz"):
            continue
        with gzip.open(os.path.join(d, f), "rt") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("kind") != "root" or r["wire"].get("inputState") != 1:
                    continue
                uid_upg = {c["uniqueId"]: bool(c["upgraded"]) for c in r["wire"].get("hand", [])}
                visits = {}
                for e in r["edges"]:
                    m = sem.match(e["semantic"])
                    if not m or m.group(1) != "1":
                        continue
                    cid, uid = int(m.group(2)), int(m.group(3))
                    key = (cid, uid_upg.get(uid, False))
                    visits[key] = visits.get(key, 0) + e["visits"]
                if len(visits) < 2:
                    continue
                label = max(visits, key=visits.get)
                rows.append({"w": w, "seed": r["seed"], "act": r["act"],
                             "opts": [list(k) for k in visits], "label": list(label)})
json.dump({"play_map": play_map, "rows": rows}, open(out, "w"))
print("rows", len(rows))
