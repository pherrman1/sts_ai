#!/usr/bin/env python3
"""Distill heart1 (recorded token logits) into a smaller silverbot NN.

Trainer of the heart1-distill thread (student C, 2026-10-15), moved into the repo with card-select support.
Input: STS_OOC_HEART1_CAPTURE rows (apps/one_combat/heart1_policy.h), gzipped JSON lines with "record",
teacher "logits" over the record's choice tokens and "token_bits". The 2026-10-15 capture rows also carry
the V4 prior ("v4", "src_bits"); newer rows carry "kind" (node/select) and the serving net's logits ("serve").

usage: distill.py SILVERBOT_REPO OUTDIR --data a.capture.jsonl.gz ... [--dim 64 --layers 2 --mult 2 --heads 4]
  [--trim-map] [--epochs 8] [--device cuda] [--workers 6] [--amp] [--init student.pt] [--select-repeat 1]
  [--extra-inputs] [--compact] [--value-weight 1 --anchor-weight 1 --select last]
AZ-loop rows (az_targets.py convert) may carry null entries in "logits" (tokens without a search target: masked
out of the policy loss) and a value target "z" (1 = the run killed the Heart); rows may carry only "z".
--value-weight W adds W * BCE(value head logit, z); --anchor-weight A adds A * KL(--init student || student) over
all of the row's choice tokens (a frozen copy of --init). Validation then also reports value BCE/AUC per act.
--select last keeps the last epoch instead of the best validation epoch (keeps the validation split clean for a gate);
--select fold holds out the files with seed % --val-mod == --select-mod (default --val-mod - 2) from training and keeps
the epoch with the lowest training objective (policy KL + weighted value BCE + weighted anchor KL) on them.
Validation = held-out seeds: files whose seed (from "-<seed>.capture" in the name) has seed % --val-mod ==
--val-mod - 1. Loss: KL(teacher softmax || student softmax) over the row's choice tokens (temperature 1).
Reports val KL and top-1 agreement with the teacher per screen and card-select type, and the agreement of
V4 / the serving net where rows carry them. --sr-data/--sr-weight add a sibling-ranking loss on the value head:
groups of one decision's children (sr_groups.py) whose 64-rollout3 targets give the order. SILVERBOT_REPO is daniel-ziegler/sts_lightspeed built at 84ab3ea
(silverbot.network imports its compiled module). The student exports with export_heart1_weights.py."""
import argparse, collections, gzip, json, math, os, random, re, sys, time, zlib
ap = argparse.ArgumentParser()
ap.add_argument("repo"); ap.add_argument("out"); ap.add_argument("--data", nargs="+", required=True)
ap.add_argument("--dim", type=int, default=128); ap.add_argument("--layers", type=int, default=2)
ap.add_argument("--mult", type=int, default=2); ap.add_argument("--heads", type=int, default=4)
ap.add_argument("--trim-map", action="store_true", help="drop map rows below the current floor")
ap.add_argument("--epochs", type=int, default=8); ap.add_argument("--bs", type=int, default=256)
ap.add_argument("--lr", type=float, default=1e-3); ap.add_argument("--wd", type=float, default=0.01)
ap.add_argument("--threads", type=int, default=4); ap.add_argument("--workers", type=int, default=0)
ap.add_argument("--max-train", type=int, default=0); ap.add_argument("--device", default="cpu")
ap.add_argument("--seed", type=int, default=0); ap.add_argument("--val-mod", type=int, default=8)
ap.add_argument("--amp", action="store_true", help="bf16 autocast forward (TF32 matmuls); loss/metrics fp32")
ap.add_argument("--init", help="start from this student state dict (fine-tune) instead of random weights")
ap.add_argument("--select-repeat", type=int, default=1, help="repeat card-select training rows this often")
ap.add_argument("--compact", action="store_true", help="keep training rows compressed in RAM (large captures)")
ap.add_argument("--value-weight", type=float, default=0.0, help="weight of the value-head BCE on rows with z")
ap.add_argument("--anchor-weight", type=float, default=0.0, help="weight of KL(frozen --init || student)")
ap.add_argument("--anchor-ref", help="anchor/report KL against this checkpoint instead of --init (any size)")
ap.add_argument("--anchor-ref-heads", type=int, default=4)
ap.add_argument("--select", choices=("best", "last", "fold"), default="best")
ap.add_argument("--select-mod", type=int, help="--select fold: seed %% --val-mod of the selection files")
ap.add_argument("--cache", help="encode every row to tensors once and keep them in DIR (memory-mapped, reused across "
                "runs on the same data and flags); epochs then do no Python record encoding")
ap.add_argument("--patience", type=int, default=0,
                help="stop after this many epochs without a better selection score (0 = run all --epochs)")
ap.add_argument("--value-k", type=int, default=0,
                help="with --cache: each epoch trains on all rows with policy targets plus K value-only rows sampled "
                     "per run (capture file), fresh each epoch, seeded by --seed and the epoch")
ap.add_argument("--val-at-end", action="store_true",
                help="evaluate the validation fold only once, for the chosen epoch (needs --select fold)")
ap.add_argument("--pack", action="store_true",
                help="drop padding: slice every token component to the batch's longest row (same function as the "
                     "fixed-size forward up to float rounding; the native forward drops padding the same way)")
ap.add_argument("--stop-after", type=int, default=0, help="benchmark: stop after this many epochs")
ap.add_argument("--value-teacher-alpha", type=float, default=0.0,
                help="value target = alpha * row['teacher_v'] + (1 - alpha) * z (soft BCE) on rows with z; 0 = z only")
ap.add_argument("--value-target-field", default="teacher_v",
                help="row field mixed into the value target by --value-teacher-alpha (rows without it keep z)")
ap.add_argument("--aux-weight", type=float, default=0.0,
                help="training-only auxiliary heads on the pooled trunk (passed next boss, reached act 4: BCE; final "
                     "floor / 55: MSE), this total weight split evenly; saved to aux.pt, never in student.pt (needs --pack)")
ap.add_argument("--cf-teacher", help="counterfactual value deltas: frozen teacher checkpoint (raw heart1 .pt, ExtraInputsNN-loadable)")
ap.add_argument("--cf-heads", type=int, default=8)
ap.add_argument("--cf-weight", type=float, default=0.0,
                help="weight of the counterfactual delta loss: per batch one monotone.py rule of --cf-rules (round robin), "
                     "random deltas on --cf-rows rows; loss = sum((dv_student - slope * dv_teacher)^2) / sum((slope * "
                     "dv_teacher)^2) on value logits, fp32 without TF32 (1 = a student flat in the variable)")
ap.add_argument("--cf-rules", default="hp,mhp,gold")
ap.add_argument("--cf-slope", type=float, default=1.3586671352386475,
                help="teacher logit -> calibrated logit slope (calibration_h1raw.json b)")
ap.add_argument("--cf-rows", type=int, default=64, help="rows per batch that get a counterfactual copy")
ap.add_argument("--cf-report", action="store_true", help="report counterfactual delta agreement of the chosen epoch")
ap.add_argument("--mono-weight", type=float, default=0.0, help="weight of the value monotonicity hinge (monotone.py)")
ap.add_argument("--mono-rules", default=",".join(("hp", "mhp", "gold", "potion", "curse")))
ap.add_argument("--mono-report", action="store_true", help="report monotonicity violations of the chosen epoch")
ap.add_argument("--extra-inputs", action="store_true",
                help="student_inputs.ExtraInputsNN: zero-initialised relic counter, act and card misc inputs")
ap.add_argument("--sr-data", help="sibling-ranking groups (sr_groups.py jsonl.gz): each group's value logits learn the "
                "order of its rows' 64-rollout3 targets")
ap.add_argument("--sr-weight", type=float, default=0.0, help="weight of the sibling-ranking loss (RankNet, |dt|-weighted)")
ap.add_argument("--sr-groups", type=int, default=16, help="sibling groups per training step")
ap.add_argument("--sr-per-action", type=int, default=2, help="rows per action drawn from a group per step")
ap.add_argument("--sr-holdout", type=int, default=6, help="groups whose source seed %% 8 equals this are held out (report)")
ap.add_argument("--sr-workers", type=int, default=2)
a = ap.parse_args()
if a.anchor_weight and not (a.init or a.anchor_ref): sys.exit("--anchor-weight needs --init or --anchor-ref")
if a.pack and not a.extra_inputs: sys.exit("--pack needs --extra-inputs")
if a.sr_weight and not a.sr_data: sys.exit("--sr-weight needs --sr-data")
if a.value_teacher_alpha and a.cache: sys.exit("--value-teacher-alpha is uncached only")
if a.value_k and (a.max_train or a.select_repeat > 1): sys.exit("--value-k with --max-train/--select-repeat")
if a.val_at_end and a.select != "fold": sys.exit("--val-at-end needs --select fold")
if a.anchor_ref and not a.extra_inputs: sys.exit("--anchor-ref needs --extra-inputs")
if (a.cf_weight or a.cf_report) and not (a.cf_teacher and a.extra_inputs): sys.exit("--cf-weight/--cf-report need --cf-teacher and --extra-inputs")
sys.path.insert(0, a.repo); sys.path.insert(0, os.path.join(a.repo, "build"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_provenance import row_wing_boots_counter, single_wing_boots_counter
import torch, torch.nn.functional as F
from silverbot import network
torch.set_num_threads(a.threads); torch.manual_seed(a.seed); random.seed(a.seed)
if a.amp: torch.backends.cuda.matmul.allow_tf32 = True; torch.backends.cudnn.allow_tf32 = True
SECTIONS = (("cards_offered.cards", 96), ("relics_offered", 3), ("potions_offered", 5), ("fixed_actions", 5), ("paths_offered", 7))
WIDTH = sum(w for _, w in SECTIONS)
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
# GameContext::CardSelectScreenType order (include/game/GameContext.h)
SELECTS = ["INVALID", "TRANSFORM", "TRANSFORM_UPGRADE", "UPGRADE", "REMOVE", "DUPLICATE", "OBTAIN", "BOTTLE", "BONFIRE_SPIRITS"]

def is_skip(b): return b == 0x30000000 or (((b >> 27) & 7) == 0 and ((b >> 8) & 0xFF) == 5)

def trim(rec):
    y0 = rec["obs.mapY"]
    if y0 < 0: return rec
    keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    rec = dict(rec)
    for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs"):
        rec[k] = [rec[k][i] for i in keep]
    return rec

def seed_of(path):
    m = re.search(r"-(\d{6,})\.capture", path); return int(m.group(1)) if m else 0

def group_of(r):
    s = r["screen"]
    if s == 4: return "card_select:" + SELECTS[r["record"]["select_screen_type"]].lower()
    return SCREENS.get(s, str(s))

wing_boots_counters = set()

def slim(r):
    """The fields evaluate() reads from a held-out row whose tensors are already encoded."""
    rec = r["record"]
    return {**r, "record": {k: rec[k] for k in ("select_screen_type", "obs.act") if k in rec}}

def load(paths, compact=False, slim_rows=False):
    """compact: keep each training row as its zlib-compressed JSON (unpacked in collate), so 3M+ rows fit in RAM."""
    rows = []
    for p in paths:
        op = gzip.open if p.endswith(".gz") else open
        with op(p, "rt") as f: lines = [json.loads(line) for line in f]
        final_floor = max((r["record"]["obs.fixed_observation"][3] for r in lines if "record" in r), default=0)
        if True:
            for r in lines:
                if "record" not in r: continue
                lg, z = r.get("logits"), r.get("z")
                if lg is not None and sum(x is not None for x in lg) < 2: lg = None
                if lg is None and z is None: continue
                rec = r["record"]
                wing_boots_counters.add(row_wing_boots_counter(r))
                row = {"record": trim(rec) if a.trim_map else rec, "logits": lg, "z": z,
                       "token_bits": r.get("token_bits"), "v4": r.get("v4"), "src_bits": r.get("src_bits"),
                       "serve": r.get("serve"), "screen": r.get("screen", rec["screen_state"]),
                       "act": r.get("act", 0), "deck_misc": r.get("deck_misc"), "seed": seed_of(p),
                       "teacher_v": r.get("teacher_v"), "final_floor": final_floor,
                       **{k: r[k] for k in ("root_v", "nstep_v", "root_v_cal", "nstep_v_cal") if k in r}}
                if slim_rows: row = slim(row)
                if compact:
                    row = (row["screen"], zlib.compress(json.dumps(
                        {k: row.get(k) for k in ("record", "logits", "z", "act", "deck_misc", "screen", "token_bits", "v4", "src_bits", "serve", "teacher_v", "final_floor", "root_v", "nstep_v", "root_v_cal", "nstep_v_cal")}).encode(), 1), row["logits"] is not None)
                rows.append(row)
    return rows

def screen_of(r): return r[0] if isinstance(r, tuple) else r["screen"]
def unpack(r): return json.loads(zlib.decompress(r[1])) if isinstance(r, tuple) else r

files = sorted(a.data)
val_files = [f for f in files if seed_of(f) % a.val_mod == a.val_mod - 1]
select_mod = (a.val_mod - 2 if a.select_mod is None else a.select_mod) if a.select == "fold" else None
if select_mod is not None and select_mod % a.val_mod == a.val_mod - 1: sys.exit("--select-mod is the validation fold")
sel_files = [f for f in files if select_mod is not None and seed_of(f) % a.val_mod == select_mod]
if select_mod is not None and not sel_files: sys.exit(f"--select fold: no files with seed % {a.val_mod} == {select_mod}")
train_files = [f for f in files if f not in val_files and f not in sel_files]
cache_dir = None
if a.cache:
    import hashlib
    h = hashlib.sha256()
    for f in files:
        h.update(os.path.basename(f).encode()); h.update(hashlib.sha256(open(f, "rb").read()).digest())
    h.update(json.dumps([a.trim_map, a.extra_inputs, a.val_mod, select_mod, a.max_train, a.seed if a.max_train else 0,
                         a.select_repeat, open(os.path.abspath(__file__), "rb").read().decode()
                         .split("def collate", 1)[1].split("def to_dev", 1)[0]]).encode())
    cache_dir = os.path.join(a.cache, h.hexdigest()[:16]); os.makedirs(cache_dir, exist_ok=True)
    print("cache", cache_dir, flush=True)

train_meta = os.path.join(cache_dir, "train.json") if cache_dir else None
if train_meta and os.path.exists(train_meta):  # encoded: the training rows themselves are not needed in RAM
    meta = json.load(open(train_meta)); train = None; n_train = meta["n"]
    wing_boots_counters.update(meta["wing_boots_counters"])
else:
    train, train_counts_ = [], []
    for f in train_files:  # per file, so --value-k knows each row's run
        part = load([f], compact=a.compact); train += part; train_counts_.append(len(part))
    if a.max_train: random.shuffle(train); train = train[:a.max_train]
    if a.select_repeat > 1: train += [r for r in train if screen_of(r) == 4] * (a.select_repeat - 1)
    n_train = len(train)
cached = lambda name: bool(cache_dir) and os.path.exists(os.path.join(cache_dir, name + ".pt"))
val = load(val_files, compact=a.compact, slim_rows=cached("val"))
sel = load(sel_files, compact=a.compact, slim_rows=cached("select"))
wing_boots_counter = single_wing_boots_counter(wing_boots_counters)
print(f"train {n_train} rows / {len(train_files)} files, val {len(val)} rows / {len(val_files)} files, "
      f"wing_boots_counter {wing_boots_counter}" + (f", select {len(sel)} rows / {len(sel_files)} files" if sel_files else ""),
      flush=True)

def positions(rec):
    pos, off = [], 0
    for key, width in SECTIONS:
        pos += list(range(off, off + len(rec[key]))); off += width
    return pos

def collate(rows):
    rows = [unpack(r) for r in rows]
    b = network.collate_fn([{**r["record"], "chosen_idx": 0, "outcome": 0.0} for r in rows])
    if a.extra_inputs: b["extra"] = student_inputs.extra_batch(rows)
    mask = torch.zeros(len(rows), WIDTH, dtype=torch.bool); tgt = torch.full((len(rows), WIDTH), -1e9)
    full = torch.zeros(len(rows), WIDTH, dtype=torch.bool)
    for i, r in enumerate(rows):
        p = positions(r["record"]); full[i, p] = True
        for pos, l in zip(p, r["logits"] or []):
            if l is not None: mask[i, pos] = True; tgt[i, pos] = l
    z = torch.tensor([-1.0 if r.get("z") is None else float(r["z"]) for r in rows])
    if a.value_teacher_alpha:  # soft value target; rides in the batch dict (the model ignores unknown keys)
        F_ = a.value_target_field
        b["value_target"] = torch.tensor([-1.0 if r.get("z") is None else float(r["z"]) if r.get(F_) is None else
                                          a.value_teacher_alpha * float(r[F_]) + (1 - a.value_teacher_alpha) * float(r["z"])
                                          for r in rows])
    if a.aux_weight:
        BOSS = {1: 16, 2: 33, 3: 50}
        def aux_of(r):
            if r.get("z") is None or r.get("final_floor") is None: return [-1.0, -1.0, -1.0]
            act = int(r.get("act") or r["record"].get("obs.act", 0) or 0); ff = r["final_floor"]
            boss = float(r["z"]) if act >= 4 else float(ff > BOSS.get(act, 50))
            return [boss, float(ff >= 51 or r["z"] == 1), ff / 55.0]
        b["aux_target"] = torch.tensor([aux_of(r) for r in rows])
    return b, mask, tgt, full, z

def to_dev(x):
    if isinstance(x, dict): return {k: to_dev(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return type(x)(to_dev(v) for v in x)
    return x.to(a.device, non_blocking=True) if hasattr(x, "to") else x

def tree(x, f):
    if isinstance(x, dict): return {k: tree(v, f) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return type(x)(tree(v, f) for v in x)
    return f(x)

def shrink(t):
    """Smallest integer dtype that holds t exactly (cache size); restored by grow()."""
    if t.dtype not in (torch.int32, torch.int64) or not t.numel(): return t
    lo, hi = int(t.min()), int(t.max())
    for d in (torch.int8, torch.int16, torch.int32):
        if torch.iinfo(d).min <= lo and hi <= torch.iinfo(d).max: return t.to(d)
    return t

def encode(rows, path, n):
    """All rows collated once (collate_fn pads to fixed maxima, so rows are independent): the batch tree with each
    leaf concatenated over rows, integer leaves shrunk; saved to path and memory-mapped back."""
    if not os.path.exists(path):
        rng = torch.get_rng_state()  # iterating a DataLoader draws a base seed; keep the training shuffle unchanged
        dl = torch.utils.data.DataLoader(rows, batch_size=1024, shuffle=False, collate_fn=collate,
                                         num_workers=min(a.workers, 4))
        flat = [b for b in dl]; torch.set_rng_state(rng)
        dtypes = tree(flat[0], lambda t: str(t.dtype))
        def zipcat(xs):
            if isinstance(xs[0], dict): return {k: zipcat([x[k] for x in xs]) for k in xs[0]}
            if isinstance(xs[0], (list, tuple)): return type(xs[0])(zipcat([x[i] for x in xs]) for i in range(len(xs[0])))
            return shrink(torch.cat(xs))
        data = zipcat(flat); del flat
        torch.save({"data": data, "dtypes": dtypes, "n": len(rows)}, path + ".tmp"); os.replace(path + ".tmp", path)
        if path.endswith("train.pt"):
            json.dump({"n": len(rows), "wing_boots_counters": sorted(wing_boots_counters, key=str)}, open(train_meta, "w"))
        print(f"cache wrote {path} ({os.path.getsize(path) / 1e6:.0f} MB)", flush=True)
    c = torch.load(path, mmap=True, weights_only=True)
    if c["n"] != n: sys.exit(f"cache {path}: {c['n']} rows, data has {n}")
    return c

def train_counts():
    """Rows per training file, in load() order (sidecar of the cache; one parse of the files if missing)."""
    if not cache_dir: return train_counts_
    path = os.path.join(cache_dir, "train_counts.json")
    if not os.path.exists(path):
        json.dump([len(load([f])) for f in train_files], open(path, "w"))
    return json.load(open(path))

class CachedLoader:
    """Batches gathered from the encoded tensors; the index order comes from a DataLoader over row indices, which
    draws the same shuffle as loader() over the rows themselves."""
    def __init__(self, c, shuffle, value_k=0):
        self.c, self.n, self.shuffle, self.value_k = c, c["n"], shuffle, value_k
        self.set_rows(range(self.n))
        if value_k:
            counts = train_counts()
            if sum(counts) != self.n: sys.exit(f"train_counts {sum(counts)} != cache rows {self.n}")
            pol = c["data"][1].any(-1)
            self.policy = pol.nonzero().squeeze(1)
            self.value_only, off = [], 0
            for k in counts:
                v = (~pol[off:off + k]).nonzero().squeeze(1) + off; off += k
                self.value_only.append(v)
            self.size = len(self.policy) + sum(min(len(v), value_k) for v in self.value_only)
            self.set_epoch(0)
    def set_rows(self, rows):
        self.idx = torch.utils.data.DataLoader(rows, batch_size=a.bs, shuffle=self.shuffle,
                                               collate_fn=lambda ix: torch.tensor(ix))
    def set_epoch(self, ep):
        if not self.value_k: return
        g = torch.Generator().manual_seed(a.seed * 100003 + ep)
        pick = [v[torch.randperm(len(v), generator=g)[:self.value_k]] for v in self.value_only]
        self.set_rows(torch.cat([self.policy] + pick).sort().values.tolist())
    def __len__(self): return len(self.idx)
    def __iter__(self):
        for ix in self.idx:
            yield self.gather(self.c["data"], self.c["dtypes"], ix)
    def gather(self, d, dt, ix):
        if isinstance(d, dict): return {k: self.gather(d[k], dt[k], ix) for k in d}
        if isinstance(d, (list, tuple)): return type(d)(self.gather(x, y, ix) for x, y in zip(d, dt))
        return d[ix].to(getattr(torch, dt.split(".")[-1]))

def loader(rows, shuffle, name=None):
    if cache_dir and name:
        return CachedLoader(encode(rows, os.path.join(cache_dir, name + ".pt"), n_train if rows is None else len(rows)), shuffle,
                            a.value_k if name == "train" else 0)
    if name == "train" and a.value_k: return SubsetLoader(rows)
    return torch.utils.data.DataLoader(rows, batch_size=a.bs, shuffle=shuffle, collate_fn=collate,
                                       num_workers=a.workers, persistent_workers=a.workers > 0, pin_memory=a.device != "cpu")

def has_policy(r): return r[2] if isinstance(r, tuple) else r["logits"] is not None

class SubsetLoader:
    """--value-k without --cache: the same per-epoch row choice as CachedLoader (all rows with policy targets plus K
    value-only rows per training file, seeded by --seed and the epoch) over the in-RAM rows."""
    def __init__(self, rows):
        self.rows, counts, off = rows, train_counts(), 0
        pol = torch.tensor([has_policy(r) for r in rows])
        self.policy = pol.nonzero().squeeze(1); self.value_only = []
        for k in counts:
            self.value_only.append((~pol[off:off + k]).nonzero().squeeze(1) + off); off += k
        self.set_epoch(0)
    def set_epoch(self, ep):
        g = torch.Generator().manual_seed(a.seed * 100003 + ep)
        pick = [v[torch.randperm(len(v), generator=g)[:a.value_k]] for v in self.value_only]
        ix = torch.cat([self.policy] + pick).sort().values.tolist()
        self.dl = torch.utils.data.DataLoader(torch.utils.data.Subset(self.rows, ix), batch_size=a.bs, shuffle=True,
                                              collate_fn=collate, num_workers=a.workers, pin_memory=a.device != "cpu")
    def __len__(self): return len(self.dl)
    def __iter__(self): return iter(self.dl)

H = network.ModelHP(dim=a.dim, n_layers=a.layers, mlp_dim_mult=a.mult, n_heads=a.heads, use_value_head=True)
if a.extra_inputs:
    import student_inputs
net = (student_inputs.ExtraInputsNN(H) if a.extra_inputs else network.NN(H)).to(a.device)
if a.init:
    # A plain student loads into ExtraInputsNN with only the zero-initialised x_* inputs missing.
    missing, unexpected = net.load_state_dict(torch.load(a.init, map_location=a.device), strict=False)
    if unexpected or any(not k.startswith("x_") for k in missing): sys.exit(f"--init mismatch: {missing} {unexpected}")
ref = None
if a.anchor_ref:  # a reference of any size, for reporting anchor KL (and the anchor term) against it
    rng = torch.get_rng_state()  # building the reference must not move the training RNG
    rs = torch.load(a.anchor_ref, map_location=a.device, weights_only=True); rdim = rs["norm.w"].shape[0]
    ref = student_inputs.ExtraInputsNN(network.ModelHP(
        dim=rdim, n_layers=sum(1 for k in rs if k.endswith(".norm1.w")), n_heads=a.anchor_ref_heads,
        mlp_dim_mult=rs["layers.0.mlp.w1.weight"].shape[0] // rdim, use_value_head=True)).to(a.device)
    missing, unexpected = ref.load_state_dict(rs, strict=False)
    if unexpected or any(not k.startswith("x_") for k in missing): sys.exit(f"--anchor-ref mismatch: {missing} {unexpected}")
    torch.set_rng_state(rng)
elif a.anchor_weight or a.init:  # with --anchor-weight 0 the frozen --init only reports anchor KL in evaluate()
    import copy
    ref = copy.deepcopy(net)
if ref is not None:
    ref.eval()
    for p in ref.parameters(): p.requires_grad_(False)
nparam = sum(p.numel() for p in net.parameters()); print("student params", nparam, flush=True)
cf_rules = [r for r in a.cf_rules.split(",") if r]; mono_rules = [r for r in a.mono_rules.split(",") if r]
teacher = None
if a.cf_weight or a.cf_report or a.mono_weight or a.mono_report:
    import monotone
    if any(r not in monotone.RULES for r in cf_rules + mono_rules): sys.exit(f"rules: one of {monotone.RULES}")
    if any(r not in monotone.EVAL for r in cf_rules): sys.exit(f"--cf-rules: one of {tuple(monotone.EVAL)}")
    mono_empty, mono_curses = monotone.ids(network.sts)
    mono_g = torch.Generator(device=a.device).manual_seed(a.seed * 100019 + 7)  # off the training RNG
    cf_g = torch.Generator(device=a.device).manual_seed(a.seed * 100019 + 11)
if a.cf_teacher:
    rng = torch.get_rng_state()
    ts = torch.load(a.cf_teacher, map_location=a.device, weights_only=True); tdim = ts["norm.w"].shape[0]
    teacher = student_inputs.ExtraInputsNN(network.ModelHP(
        dim=tdim, n_layers=sum(1 for k in ts if k.endswith(".norm1.w")), n_heads=a.cf_heads,
        mlp_dim_mult=ts["layers.0.mlp.w1.weight"].shape[0] // tdim, use_value_head=True)).to(a.device)
    missing, unexpected = teacher.load_state_dict(ts, strict=False)
    if unexpected or any(not k.startswith("x_") for k in missing): sys.exit(f"--cf-teacher mismatch: {missing} {unexpected}")
    teacher.eval(); torch.set_rng_state(rng)
    for p in teacher.parameters(): p.requires_grad_(False)
aux = None
if a.aux_weight:
    if not a.pack: sys.exit("--aux-weight needs --pack")
    aux = torch.nn.Linear(a.dim, 3).to(a.device); torch.nn.init.zeros_(aux.weight); torch.nn.init.zeros_(aux.bias)
opt = torch.optim.AdamW(list(net.parameters()) + (list(aux.parameters()) if aux is not None else []), lr=a.lr, weight_decay=a.wd)
train_dl, val_dl = loader(train, True, "train"), loader(val, False, "val")
sel_dl = loader(sel, False, "select") if sel else None
del train
if cache_dir: val[:] = [slim(r) if isinstance(r, dict) else r for r in val]; sel[:] = [slim(r) if isinstance(r, dict) else r for r in sel]
sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * len(train_dl), pct_start=0.05)

def sr_load(path):
    """(train, holdout) lists of (source seed, [(action, target, packed row)]); rows use the training-row layout."""
    tr, ho = [], []
    with gzip.open(path, "rt") as f:
        for line in f:
            g = json.loads(line); rows = []
            for r in g["rows"]:
                rec = trim(r["record"]) if a.trim_map else r["record"]
                row = {"record": rec, "logits": None, "z": None, "act": g["act"], "deck_misc": None,
                       "screen": rec["screen_state"]}
                rows.append((r["action"], float(r["target"]), (row["screen"], zlib.compress(json.dumps(row).encode(), 1), False)))
            (ho if g["seed"] % 8 == a.sr_holdout else tr).append((g["seed"], rows))
    return tr, ho

class SRSteps(torch.utils.data.Dataset):
    """Step i of the sibling-ranking stream: --sr-groups groups and up to --sr-per-action rows per action, drawn with an
    RNG seeded by (--seed, i), so the stream depends neither on workers nor on the training RNG."""
    def __init__(self, groups, n): self.groups, self.n = groups, n
    def __len__(self): return self.n
    def __getitem__(self, i):
        rng = random.Random(a.seed * 1000003 + i); rows, gid, tgt = [], [], []
        for k in range(a.sr_groups):
            by = collections.defaultdict(list)
            for act, t, row in self.groups[rng.randrange(len(self.groups))][1]: by[act].append((t, row))
            for act in sorted(by):
                for t, row in rng.sample(by[act], min(len(by[act]), a.sr_per_action)):
                    rows.append(row); gid.append(k); tgt.append(t)
        return collate(rows)[0], torch.tensor(gid), torch.tensor(tgt)

def sr_loss(v, gid, t):
    """RankNet over all row pairs of a group, weighted by the target gap: sum (t_i - t_j)+ softplus(v_j - v_i) / sum gaps."""
    w = (t[:, None] - t[None, :]).clamp(min=0) * (gid[:, None] == gid[None, :])
    return (w * F.softplus(v[None, :] - v[:, None])).sum() / w.sum().clamp(min=1e-8)

def sr_report(groups):
    """§577 sibling concordance on held-out groups: per action mean target and mean sigmoid(value); pairs of actions with
    distinct targets, prediction ties count 0.5; mean per source, then over sources."""
    net.eval(); per = collections.defaultdict(list)
    with torch.no_grad():
        for i in range(0, len(groups), 32):
            chunk = groups[i:i + 32]; rows = [row for _, g in chunk for _, _, row in g]
            vs = torch.cat([torch.sigmoid(outputs_of(net, to_dev(collate(rows[j:j + 512])[0]))[1]).cpu()
                            for j in range(0, len(rows), 512)]).tolist(); o = 0
            for seed, g in chunk:
                by = collections.defaultdict(lambda: ([], []))
                for act, t, _ in g: by[act][0].append(t); by[act][1].append(vs[o]); o += 1
                tt = [sum(x) / len(x) for x, _ in by.values()]; pp = [sum(y) / len(y) for _, y in by.values()]
                pairs = [.5 if pp[x] == pp[y] else float((pp[x] - pp[y]) * (tt[x] - tt[y]) > 0)
                         for x in range(len(tt)) for y in range(x) if abs(tt[x] - tt[y]) > 1e-8]
                if pairs: per[seed].append(sum(pairs) / len(pairs))
    net.train()
    return {"groups": len(groups), "sources": len(per),
            "concordance": round(sum(sum(c) / len(c) for c in per.values()) / max(len(per), 1), 4)}

sr_train = sr_hold = sr_it = None
if a.sr_data:
    sr_train, sr_hold = sr_load(a.sr_data)
    print(f"sibling-rank groups train {len(sr_train)} holdout {len(sr_hold)}", flush=True)
    if a.sr_weight:
        sr_it = iter(torch.utils.data.DataLoader(SRSteps(sr_train, a.epochs * len(train_dl)), batch_size=None,
                                                 num_workers=a.sr_workers, persistent_workers=a.sr_workers > 0))

OBS_KEYS = ("deck", "relics", "potions", "map_nodes"); CHOICE_KEYS = ("cards", "relics", "potions", "fixed", "paths")
CHOICE_OFFSETS = [sum(w for _, w in SECTIONS[:i]) for i in range(len(SECTIONS))]

def cut(x, n):
    if isinstance(x, dict): return {k: cut(v, n) for k, v in x.items()}
    return x[:, :n]

def packed_forward(model, b):
    """student_inputs.ExtraInputsNN.forward on a batch whose token components are cut to their longest row (rows are
    left-aligned, padding is key-masked, embeddings carry no sequence position), logits put back at the fixed
    SECTIONS layout with -inf elsewhere."""
    lens = {k: max(int((~b[k]["mask"]).sum(1).max()), 1) for k in OBS_KEYS}
    clens = {k: max(int((~b["choices"][k]["mask"]).sum(1).max()), 1) for k in CHOICE_KEYS}
    pb = {**b, **{k: cut(b[k], lens[k]) for k in OBS_KEYS},
          "choices": {k: cut(b["choices"][k], clens[k]) for k in CHOICE_KEYS}}
    ex = b["extra"]; nd, nr = lens["deck"], lens["relics"]; fixed_tok = nd + nr + lens["potions"]
    obs_embed, obs_mask = model.obs_embed(pb)
    choice_embed, choice_mask = model.choice_embed(pb["choices"])
    obs_embed = obs_embed.clone()
    obs_embed[:, :nd] = obs_embed[:, :nd] + model.x_deck_misc(ex["deck_misc"][:, :nd])
    obs_embed[:, nd:nd + nr] = obs_embed[:, nd:nd + nr] + model.x_relic_counter(ex["relic_counter"][:, :nr])
    obs_embed[:, fixed_tok] = obs_embed[:, fixed_tok] + model.x_act(ex["act"])
    x = torch.cat([obs_embed, choice_embed], dim=1); pos_mask = torch.cat([obs_mask, choice_mask], dim=1)
    for i, l in enumerate(model.layers):
        x = torch.utils.checkpoint.checkpoint(l, x, pos_mask, use_reentrant=False) if i < len(model.layers) - 1 \
            else l(x, pos_mask)
    xn = model.norm(x)
    lg = model.choice_logits(xn[:, obs_mask.size(1):, :]).squeeze(-1).float().masked_fill(choice_mask, float("-inf"))
    out = torch.full((lg.size(0), WIDTH), float("-inf"), device=lg.device); o = 0
    for k, off in zip(CHOICE_KEYS, CHOICE_OFFSETS):
        out[:, off:off + clens[k]] = lg[:, o:o + clens[k]]; o += clens[k]
    value_xn = model.value_head_norm(xn)
    pooled = value_xn.masked_fill(pos_mask.unsqueeze(-1), 0).sum(dim=1) / (~pos_mask).sum(dim=1, keepdim=True).float()
    global last_pooled
    last_pooled = pooled
    return out, model.value_head(pooled).squeeze(-1).float()

def outputs_of(model, b):
    """(choice logits, value-head logit), fp32."""
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=a.amp and a.device.startswith("cuda")):
        out = packed_forward(model, b) if a.pack else model(b)
    return out[0].float(), out[1].float()

def value_exact(model, b):
    """Value logit in fp32 with TF32 off (counterfactual deltas are ~0.01 logit, below bf16/TF32 resolution)."""
    t32 = torch.backends.cuda.matmul.allow_tf32; torch.backends.cuda.matmul.allow_tf32 = False
    try:
        return (packed_forward(model, b) if a.pack else model(b))[1].float()
    finally:
        torch.backends.cuda.matmul.allow_tf32 = t32

def head(b, n):
    return tree(b, lambda t: t[:n] if hasattr(t, "dim") and t.dim() > 0 else t)

def cf_deltas(b, rule, fixed=False, g=None):
    """(student delta, calibrated teacher delta) of the value logit on the rows the rule applies to."""
    c, sgn = monotone.perturb(b, rule, mono_empty, mono_curses, g, fixed=fixed)
    m = sgn != 0
    with torch.no_grad(): dt = a.cf_slope * (value_exact(teacher, c) - value_exact(teacher, b))
    ds = value_exact(net, c) - value_exact(net, b)
    return ds[m], dt[m]

def cf_loss(b, step):
    ds, dt = cf_deltas(head(b, a.cf_rows), cf_rules[step % len(cf_rules)], g=cf_g)
    return ((ds - dt) ** 2).sum() / (dt ** 2).sum().clamp(min=1e-8)

def cf_report(dl):
    """Per rule, fixed EVAL perturbations: relative squared delta error (1 = flat student), sign agreement with the
    teacher (rows with |teacher delta| > 1e-4 logit), mean deltas (logit), wrong-sign rate of student and teacher."""
    net.eval(); acc = {r: [[], []] for r in cf_rules}
    with torch.no_grad():
        for b, *_ in dl:
            b = to_dev(b)
            for r in cf_rules:
                ds, dt = cf_deltas(b, r, fixed=True); acc[r][0] += ds.tolist(); acc[r][1] += dt.tolist()
    net.train(); out = {}
    for r, (ds, dt) in acc.items():
        sgn = 1 if monotone.EVAL[r] > 0 else -1; big = [(s, t) for s, t in zip(ds, dt) if abs(t) > 1e-4]
        out[r] = {"n": len(ds), "rel_sq_err": round(sum((s - t) ** 2 for s, t in zip(ds, dt)) / max(sum(t * t for t in dt), 1e-12), 4),
                  "sign_agree": round(sum((s > 0) == (t > 0) for s, t in big) / max(len(big), 1), 4),
                  "mean_ds": round(sum(ds) / max(len(ds), 1), 5), "mean_dt": round(sum(dt) / max(len(dt), 1), 5),
                  "student_wrong": round(sum(sgn * s < 0 for s in ds) / max(len(ds), 1), 4),
                  "teacher_wrong": round(sum(sgn * t < 0 for t in dt) / max(len(dt), 1), 4)}
    return out

def mono_report(dl):
    """Per rule, with the fixed EVAL perturbations: rows, violation rate (better state strictly lower value logit;
    and lower probability by more than 0.001) and the median better-minus-worse probability, fp32 without TF32."""
    net.eval(); gaps = collections.defaultdict(list); pg = collections.defaultdict(list)
    with torch.no_grad():
        for b, *_ in dl:
            b = to_dev(b); v = value_exact(net, b)
            for r in mono_rules:
                c, sgn = monotone.perturb(b, r, mono_empty, mono_curses, fixed=True)
                vc = value_exact(net, c)
                gaps[r] += monotone.violations(v, vc, sgn).tolist()
                pg[r] += monotone.violations(torch.sigmoid(v), torch.sigmoid(vc), sgn).tolist()
    net.train()
    return {r: {"n": len(gaps[r]), "viol": round(sum(x < 0 for x in gaps[r]) / max(len(gaps[r]), 1), 4),
                "viol_p001": round(sum(x < -1e-3 for x in pg[r]) / max(len(pg[r]), 1), 4),
                "median_dp": round(sorted(pg[r])[len(pg[r]) // 2], 5) if pg[r] else None} for r in mono_rules}

def kl_rows(logits, mask, tgt):
    lp = F.log_softmax(logits.masked_fill(~mask, -1e9), -1); lt = F.log_softmax(tgt, -1)
    return (lt.exp() * (lt - lp)).masked_fill(~mask, 0).sum(-1)

def argmax(v): return max(range(len(v)), key=lambda i: -1e18 if v[i] is None else v[i])

def auc(y, p):
    pos = sum(y); neg = len(y) - pos
    if not pos or not neg: return None
    order = sorted(range(len(p)), key=p.__getitem__); rank = [0.0] * len(p); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and p[order[j + 1]] == p[order[i]]: j += 1
        for k in range(i, j + 1): rank[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return (sum(r for r, t in zip(rank, y) if t) - pos * (pos + 1) / 2) / (pos * neg)

def losses(b, m, t, full, z):
    """Per-row policy KL (0 without targets), value BCE (0 without z), anchor KL; plus logits and value logits."""
    lg, v = outputs_of(net, b)
    kl = kl_rows(lg, m, t)
    vt = b["value_target"] if "value_target" in b else z
    bce = F.binary_cross_entropy_with_logits(v, vt.clamp(min=0), reduction="none") * (z >= 0)
    anc = torch.zeros_like(kl)
    if ref is not None and (a.anchor_weight or not net.training):
        with torch.no_grad(): rl = outputs_of(ref, b)[0].masked_fill(~full, -1e9)
        anc = kl_rows(lg, full, rl)
    global aux_loss
    aux_loss = None
    if aux is not None and net.training:
        at = b["aux_target"]; ok = at[:, 0] >= 0; o = aux(last_pooled.float())
        if ok.any():
            l_boss = F.binary_cross_entropy_with_logits(o[ok, 0], at[ok, 0]); l_a4 = F.binary_cross_entropy_with_logits(o[ok, 1], at[ok, 1])
            l_fl = F.mse_loss(torch.sigmoid(o[ok, 2]), at[ok, 2]); aux_loss = (l_boss + l_a4 + l_fl) / 3
    return kl, bce, anc, lg, v

def combine(kl, bce, anc, m, z):
    hp, hz = m.any(-1), z >= 0
    loss = kl.sum() / hp.sum().clamp(min=1)
    if a.value_weight: loss = loss + a.value_weight * bce.sum() / hz.sum().clamp(min=1)
    if ref is not None and a.anchor_weight: loss = loss + a.anchor_weight * anc.mean()
    if aux_loss is not None: loss = loss + a.aux_weight * aux_loss
    return loss

def evaluate(val=val, val_dl=val_dl):
    net.eval(); kls, agr, hps, vp, ancs = [], [], [], [], []
    with torch.no_grad():
        for b, m, t, full, z in val_dl:
            b, m, t, full, z = to_dev(b), m.to(a.device), t.to(a.device), full.to(a.device), z.to(a.device)
            kl, _, anc, lg, v = losses(b, m, t, full, z)
            kls += kl.tolist(); agr += (lg.masked_fill(~m, -1e9).argmax(-1) == t.argmax(-1)).tolist()
            hps += m.any(-1).tolist(); vp += torch.sigmoid(v).tolist(); ancs += anc.tolist()
    net.train()
    value = value_metrics(val, vp)
    if ref is not None: value["anchor_kl"] = round(sum(ancs) / len(ancs), 4)
    pol = [(r, k, g) for r, k, g, h in zip(val, kls, agr, hps) if h]
    val_p = [r for r, _, _ in pol]; kls = [k for _, k, _ in pol]; agr = [g for _, _, g in pol]
    if not pol: return (None, None), {}, value
    # per group: n, KL, top1, V4 n, V4 top1, serve n, serve top1
    per = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0, 0, 0])
    for r, k, g in zip(val_p, kls, agr):
        r = unpack(r); s = per[group_of(r)]; s[0] += 1; s[1] += k; s[2] += g
        top = r["token_bits"][argmax(r["logits"])] if r.get("token_bits") else None
        if r.get("v4"):
            vb = r["src_bits"][argmax(r["v4"])]; s[3] += 1; s[4] += (vb == top) or (is_skip(vb) and is_skip(top))
        if r.get("serve"):
            s[5] += 1; s[6] += argmax(r["serve"]) == argmax(r["logits"])
    n = len(val_p)
    tot = (sum(kls) / n, sum(agr) / n)
    rnd = lambda x, d: round(x / d, 4) if d else None
    return tot, {k: {"n": s[0], "kl": rnd(s[1], s[0]), "top1": rnd(s[2], s[0]), "v4_top1": rnd(s[4], s[3]),
                     "serve_top1": rnd(s[6], s[5])} for k, s in sorted(per.items())}, value

def value_metrics(val, vp):
    """Value-head BCE/AUC on validation rows with z, overall and per act."""
    groups = collections.defaultdict(lambda: ([], []))
    for r, p in zip(val, vp):
        r = unpack(r)
        if r.get("z") is None: continue
        for g in ("all", "act%d" % int(r.get("act") or r["record"].get("obs.act", 0) or 0)):
            groups[g][0].append(int(r["z"])); groups[g][1].append(min(max(p, 1e-7), 1 - 1e-7))
    out = {}
    for g, (y, p) in sorted(groups.items()):
        bce = -sum(math.log(q) if t else math.log(1 - q) for t, q in zip(y, p)) / len(y)
        base = sum(y) / len(y)
        const = -(base * math.log(base) + (1 - base) * math.log(1 - base)) if 0 < base < 1 else 0.0
        out[g] = {"n": len(y), "bce": round(bce, 4), "const_bce": round(const, 4), "auc": auc(y, p),
                  "mean_p": round(sum(p) / len(p), 4), "mean_z": round(base, 4)}
    return out

os.makedirs(a.out, exist_ok=True); t0 = time.time(); best = None; hist = []
if a.init and not a.val_at_end:
    (kl, ag), per, value = evaluate()
    print(f"init val KL {kl} top1 {ag}", json.dumps(per), json.dumps(value), flush=True)
    hist.append({"epoch": 0, "val_kl": kl, "val_top1": ag, "per_screen": per, "value": value})
if sr_hold:
    sr0 = sr_report(sr_hold); print("init sibling-rank holdout", json.dumps(sr0), flush=True)
    if hist and hist[-1]["epoch"] == 0: hist[-1]["sr_holdout"] = sr0
    else: hist.append({"epoch": 0, "sr_holdout": sr0})
step = 0
for ep in range(a.epochs):
    tot = n = cf_tot = mono_tot = sr_tot = 0
    if hasattr(train_dl, "set_epoch"): train_dl.set_epoch(ep)
    te = time.time()
    for b, m, t, full, z in train_dl:
        b, m, t, full, z = to_dev(b), m.to(a.device), t.to(a.device), full.to(a.device), z.to(a.device)
        kl, bce, anc, _, v = losses(b, m, t, full, z)
        loss = combine(kl, bce, anc, m, z)
        if a.cf_weight:
            cl = cf_loss(b, step); loss = loss + a.cf_weight * cl; cf_tot += cl.item() * len(m)
        if a.mono_weight:
            c, sgn = monotone.perturb_mixed(b, mono_rules, mono_empty, mono_curses, mono_g)
            pen = monotone.penalty(v, outputs_of(net, c)[1], sgn)
            loss = loss + a.mono_weight * pen; mono_tot += pen.item() * len(m)
        if sr_it is not None:
            sb, gid, tt = next(sr_it)
            sl = sr_loss(outputs_of(net, to_dev(sb))[1], gid.to(a.device), tt.to(a.device))
            loss = loss + a.sr_weight * sl; sr_tot += sl.item() * len(m)
        step += 1
        opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(list(net.parameters()) + (list(aux.parameters()) if aux is not None else []), 1.0)
        opt.step(); sched.step()
        tot += loss.item() * len(m); n += len(m)
    train_sec = time.time() - te
    (kl, ag), per, value = ((None, None), {}, {}) if a.val_at_end else evaluate()
    hist.append({"epoch": ep + 1, "train_loss": tot / n, "val_kl": kl, "val_top1": ag, "value": value,
                 "sec": time.time() - t0, "train_sec": train_sec, "train_rows": n})
    if a.cf_weight: hist[-1]["train_cf_loss"] = cf_tot / n; print(f"   cf loss {cf_tot / n:.5f}", flush=True)
    if a.mono_weight: hist[-1]["train_mono_penalty"] = mono_tot / n; print(f"   mono penalty {mono_tot / n:.5f}", flush=True)
    if sr_it is not None: hist[-1]["train_sr_loss"] = sr_tot / n; print(f"   sibling-rank loss {sr_tot / n:.5f}", flush=True)
    if sr_hold: hist[-1]["sr_holdout"] = sr_report(sr_hold); print(f"   sibling-rank holdout {json.dumps(hist[-1]['sr_holdout'])}", flush=True)
    print(f"ep {ep+1} train loss {tot/n:.4f} val KL {kl} top1 {ag} value {json.dumps(value.get('all'))} "
          f"{time.time()-t0:.0f}s", flush=True)
    score = None if a.val_at_end else kl if kl is not None else value["all"]["bce"]
    if sel_dl is not None:
        (skl, _), _, sval = evaluate(sel, sel_dl)
        score = (skl or 0.0) + (a.value_weight * sval["all"]["bce"] if a.value_weight and "all" in sval else 0.0) \
            + a.anchor_weight * sval.get("anchor_kl", 0.0)
        hist[-1]["select"] = {"kl": skl, "value": sval, "objective": score}
        hist[-1]["epoch_sec"] = time.time() - te
        print(f"   select fold objective {score:.4f} KL {skl} value {json.dumps(sval.get('all'))}", flush=True)
    if a.select == "last" or best is None or score < best[0]:
        best = (score, ag, per, kl, value, ep + 1); torch.save(net.state_dict(), os.path.join(a.out, "student.pt"))
        if aux is not None: torch.save(aux.state_dict(), os.path.join(a.out, "aux.pt"))
    if a.patience and a.select != "last" and ep + 1 - best[5] >= a.patience:
        print(f"early stop: no better selection score for {a.patience} epochs", flush=True); break
    if a.stop_after and ep + 1 >= a.stop_after: break
if a.val_at_end:  # the chosen epoch's weights, scored on the validation fold once
    net.load_state_dict(torch.load(os.path.join(a.out, "student.pt"), map_location=a.device, weights_only=True))
    (kl, ag), per, value = evaluate()
    best = (best[0], ag, per, kl, value, best[5])
    h = next(x for x in hist if x["epoch"] == best[5]); h.update({"val_kl": kl, "val_top1": ag, "value": value, "per_screen": per})
    print(f"chosen epoch {best[5]} val KL {kl} top1 {ag} value {json.dumps(value.get('all'))}", flush=True)
print("best per group:", json.dumps(best[2]), flush=True)
cf, mono = {}, {}
if a.cf_weight or a.cf_report or a.mono_weight or a.mono_report:  # the chosen epoch's weights
    net.load_state_dict(torch.load(os.path.join(a.out, "student.pt"), map_location=a.device, weights_only=True))
if a.cf_weight or a.cf_report:
    cf = {"rules": cf_rules, "eval_deltas": monotone.EVAL, "slope": a.cf_slope,
          **({"select": cf_report(sel_dl)} if sel_dl is not None else {}), "val": cf_report(val_dl)}
    print("counterfactual", json.dumps(cf), flush=True)
if a.mono_weight or a.mono_report:
    mono = {"rules": mono_rules, "eval_deltas": monotone.EVAL, "curses": list(monotone.CURSES),
            **({"select": mono_report(sel_dl)} if sel_dl is not None else {}), "val": mono_report(val_dl)}
    print("monotonicity", json.dumps(mono), flush=True)
sr = {}
if sr_hold:  # the chosen epoch's weights; the first 1,000 training groups show how much of the ranking is memorised
    net.load_state_dict(torch.load(os.path.join(a.out, "student.pt"), map_location=a.device, weights_only=True))
    sr = {"holdout": sr_report(sr_hold), "train_first1000": sr_report(sr_train[:1000])}
if sr: print("sibling-rank", json.dumps(sr), flush=True)
json.dump({"sibling_rank": sr, "counterfactual": cf, "monotone": mono, "args": vars(a), "wing_boots_counter": wing_boots_counter, "params": nparam, "train_rows": n_train, "val_rows": len(val),
           "select_rows": len(sel), "selected_epoch": best[5], "epochs_run": hist[-1]["epoch"], "wall_sec": time.time() - t0,
           "best_val_kl": best[3], "best_val_top1": best[1], "per_screen": best[2], "value": best[4], "history": hist},
          open(os.path.join(a.out, "summary.json"), "w"), indent=1)
