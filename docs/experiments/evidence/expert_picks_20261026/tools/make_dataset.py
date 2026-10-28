"""Distill rows for the expert-anchored student.

usage: make_dataset.py ALPHA OUTDIR decisions.jsonl scores.jsonl meta.jsonl bot_records.jsonl bot_scores.jsonl

Expert rows (card rewards, rest, smith, shop removal, boss relic; runs whose replayed deck is within 2 cards):
target = log((1 - ALPHA) * p_student + ALPHA * e), e uniform over the tokens carrying the expert's label.
Bot rows (gen-3 trajectories): target = student_sel's own logits (anchor). Files are named -<seed>.capture so
distill.py's seed % 8 == 7 validation split holds out whole expert runs (bucket by md5 of the run id).
"""
import collections, gzip, hashlib, json, math, os, sys

alpha = float(sys.argv[1]); out = sys.argv[2]
dec, sco, meta, brec, bsco = sys.argv[3:8]
os.makedirs(out, exist_ok=True)
TYPES = {"card_reward_monster", "card_reward_elite", "card_reward_boss", "rest", "smith", "shop_remove", "boss_relic"}
if os.environ.get("NO_REST") == "1": TYPES.discard("rest")
ok = {json.loads(l)["run"] for l in open(meta) if json.loads(l)["deck_diff"] <= 2}

files = {}
def w(name, row):
    f = files.get(name)
    if f is None: f = files[name] = gzip.open(os.path.join(out, name), "wt")
    f.write(json.dumps(row) + "\n")

n = collections.Counter()
for dl, sl in zip(open(dec), open(sco)):
    d = json.loads(dl)
    if d["type"] not in TYPES or d["run"] not in ok: continue
    lg = json.loads(sl)["logits"]; m = max(lg); e = [math.exp(x - m) for x in lg]; z = sum(e); p = [x / z for x in e]
    lab = d["labels"][d["expert"]]
    hit = [i for i, l in enumerate(d["labels"]) if l == lab]
    tgt = [math.log((1 - alpha) * p[i] + (alpha / len(hit) if i in hit else 0.0) + 1e-12) for i in range(len(p))]
    bucket = int(hashlib.md5(d["run"].encode()).hexdigest(), 16) % 40
    w(f"exp-{900000000 + bucket}.capture.jsonl.gz", {"record": d["record"], "logits": tgt, "act": d["record"]["obs.act"],
                                                     "expert_run": d["run"], "expert_type": d["type"], "wing_boots_counter": 1})
    n["expert_val" if bucket % 8 == 7 else "expert_train"] += 1
for bl, sl in zip(open(brec), open(bsco)):
    b = json.loads(bl)
    w(f"bot-{b['seed']}.capture.jsonl.gz", {"record": b["record"], "logits": json.loads(sl)["logits"], "act": b["act"], "wing_boots_counter": 1})
    n["bot_val" if b["seed"] % 8 == 7 else "bot_train"] += 1
for f in files.values(): f.close()
print(dict(n), len(files), "files")
