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
--mono-weight M adds M * relu(sign * (v - v')) on value logits, v' the value of a copy of the row with one variable
changed by a monotonicity rule of monotone.py (--mono-rules; one random rule and delta per row); --mono-report (implied
by --mono-weight) scores the chosen epoch's violation rates per rule on the selection and validation folds.
--select last keeps the last epoch instead of the best validation epoch (keeps the validation split clean for a gate);
--select fold holds out the files with seed % --val-mod == --select-mod (default --val-mod - 2) from training and keeps
the epoch with the lowest training objective (policy KL + weighted value BCE + weighted anchor KL) on them.
Validation = held-out seeds: files whose seed (from "-<seed>.capture" in the name) has seed % --val-mod ==
--val-mod - 1. Loss: KL(teacher softmax || student softmax) over the row's choice tokens (temperature 1).
Reports val KL and top-1 agreement with the teacher per screen and card-select type, and the agreement of
V4 / the serving net where rows carry them. SILVERBOT_REPO is daniel-ziegler/sts_lightspeed built at 84ab3ea
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
ap.add_argument("--select", choices=("best", "last", "fold"), default="best")
ap.add_argument("--select-mod", type=int, help="--select fold: seed %% --val-mod of the selection files")
ap.add_argument("--extra-inputs", action="store_true",
                help="student_inputs.ExtraInputsNN: zero-initialised relic counter, act and card misc inputs")
ap.add_argument("--mono-weight", type=float, default=0.0, help="weight of the value monotonicity hinge (monotone.py)")
ap.add_argument("--mono-rules", default=",".join(("hp", "mhp", "gold", "potion", "curse")))
ap.add_argument("--mono-report", action="store_true", help="report monotonicity violations of the chosen epoch")
a = ap.parse_args()
if a.anchor_weight and not a.init: sys.exit("--anchor-weight needs --init")
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

def load(paths, compact=False):
    """compact: keep each training row as its zlib-compressed JSON (unpacked in collate), so 3M+ rows fit in RAM."""
    rows = []
    for p in paths:
        op = gzip.open if p.endswith(".gz") else open
        with op(p, "rt") as f:
            for line in f:
                r = json.loads(line)
                if "record" not in r: continue
                lg, z = r.get("logits"), r.get("z")
                if lg is not None and sum(x is not None for x in lg) < 2: lg = None
                if lg is None and z is None: continue
                rec = r["record"]
                wing_boots_counters.add(row_wing_boots_counter(r))
                row = {"record": trim(rec) if a.trim_map else rec, "logits": lg, "z": z,
                       "token_bits": r.get("token_bits"), "v4": r.get("v4"), "src_bits": r.get("src_bits"),
                       "serve": r.get("serve"), "screen": r.get("screen", rec["screen_state"]),
                       "act": r.get("act", 0), "deck_misc": r.get("deck_misc"), "seed": seed_of(p)}
                if compact:
                    row = (row["screen"], zlib.compress(json.dumps(
                        {k: row[k] for k in ("record", "logits", "z", "act", "deck_misc")}).encode(), 1))
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
train, val, sel = load(train_files, compact=a.compact), load(val_files), load(sel_files)
if a.max_train: random.shuffle(train); train = train[:a.max_train]
if a.select_repeat > 1: train += [r for r in train if screen_of(r) == 4] * (a.select_repeat - 1)
wing_boots_counter = single_wing_boots_counter(wing_boots_counters)
print(f"train {len(train)} rows / {len(train_files)} files, val {len(val)} rows / {len(val_files)} files, "
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
    return b, mask, tgt, full, z

def to_dev(x):
    if isinstance(x, dict): return {k: to_dev(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return type(x)(to_dev(v) for v in x)
    return x.to(a.device, non_blocking=True) if hasattr(x, "to") else x

def loader(rows, shuffle):
    return torch.utils.data.DataLoader(rows, batch_size=a.bs, shuffle=shuffle, collate_fn=collate,
                                       num_workers=a.workers, persistent_workers=a.workers > 0, pin_memory=a.device != "cpu")

H = network.ModelHP(dim=a.dim, n_layers=a.layers, mlp_dim_mult=a.mult, n_heads=a.heads, use_value_head=True)
if a.extra_inputs:
    import student_inputs
net = (student_inputs.ExtraInputsNN(H) if a.extra_inputs else network.NN(H)).to(a.device)
if a.init:
    # A plain student loads into ExtraInputsNN with only the zero-initialised x_* inputs missing.
    missing, unexpected = net.load_state_dict(torch.load(a.init, map_location=a.device), strict=False)
    if unexpected or any(not k.startswith("x_") for k in missing): sys.exit(f"--init mismatch: {missing} {unexpected}")
ref = None
if a.anchor_weight:
    import copy
    ref = copy.deepcopy(net).eval()
    for p in ref.parameters(): p.requires_grad_(False)
nparam = sum(p.numel() for p in net.parameters()); print("student params", nparam, flush=True)
mono_rules = [r for r in a.mono_rules.split(",") if r]
if a.mono_weight or a.mono_report:
    import monotone
    if any(r not in monotone.RULES for r in mono_rules): sys.exit(f"--mono-rules: one of {monotone.RULES}")
    mono_empty, mono_curses = monotone.ids(network.sts)
    mono_g = torch.Generator(device=a.device).manual_seed(a.seed * 100019 + 7)  # off the training RNG

def mono_report(dl):
    """Per rule, with the fixed EVAL perturbations: rows, violation rate (better state strictly lower value logit;
    and lower probability by more than 0.001) and the median better-minus-worse probability, fp32."""
    net.eval(); gaps = collections.defaultdict(list); pg = collections.defaultdict(list)
    with torch.no_grad():
        for b, *_ in dl:
            b = to_dev(b); v = outputs_of(net, b, amp=False)[1]
            for r in mono_rules:
                c, sgn = monotone.perturb(b, r, mono_empty, mono_curses, fixed=True)
                vc = outputs_of(net, c, amp=False)[1]
                gaps[r] += monotone.violations(v, vc, sgn).tolist()
                pg[r] += monotone.violations(torch.sigmoid(v), torch.sigmoid(vc), sgn).tolist()
    net.train()
    return {r: {"n": len(gaps[r]), "viol": round(sum(x < 0 for x in gaps[r]) / max(len(gaps[r]), 1), 4),
                "viol_p001": round(sum(x < -1e-3 for x in pg[r]) / max(len(pg[r]), 1), 4),
                "median_dp": round(sorted(pg[r])[len(pg[r]) // 2], 5) if pg[r] else None} for r in mono_rules}

opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
train_dl, val_dl = loader(train, True), loader(val, False)
sel_dl = loader(sel, False) if sel else None
sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * len(train_dl), pct_start=0.05)

def outputs_of(model, b, amp=True):
    """(choice logits, value-head logit), fp32."""
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp and a.amp and a.device.startswith("cuda")):
        out = model(b)
    return out[0].float(), out[1].float()

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
    bce = F.binary_cross_entropy_with_logits(v, z.clamp(min=0), reduction="none") * (z >= 0)
    anc = torch.zeros_like(kl)
    if ref is not None:
        with torch.no_grad(): rl = outputs_of(ref, b)[0].masked_fill(~full, -1e9)
        anc = kl_rows(lg, full, rl)
    return kl, bce, anc, lg, v

def combine(kl, bce, anc, m, z):
    hp, hz = m.any(-1), z >= 0
    loss = kl.sum() / hp.sum().clamp(min=1)
    if a.value_weight: loss = loss + a.value_weight * bce.sum() / hz.sum().clamp(min=1)
    if ref is not None: loss = loss + a.anchor_weight * anc.mean()
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
if a.init:
    (kl, ag), per, value = evaluate()
    print(f"init val KL {kl} top1 {ag}", json.dumps(per), json.dumps(value), flush=True)
    hist.append({"epoch": 0, "val_kl": kl, "val_top1": ag, "per_screen": per, "value": value})
for ep in range(a.epochs):
    tot = n = mono_tot = 0
    for b, m, t, full, z in train_dl:
        b, m, t, full, z = to_dev(b), m.to(a.device), t.to(a.device), full.to(a.device), z.to(a.device)
        kl, bce, anc, _, v = losses(b, m, t, full, z)
        loss = combine(kl, bce, anc, m, z)
        if a.mono_weight:
            c, sgn = monotone.perturb_mixed(b, mono_rules, mono_empty, mono_curses, mono_g)
            pen = monotone.penalty(v, outputs_of(net, c)[1], sgn)
            loss = loss + a.mono_weight * pen; mono_tot += pen.item() * len(m)
        opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); sched.step()
        tot += loss.item() * len(m); n += len(m)
    (kl, ag), per, value = evaluate()
    hist.append({"epoch": ep + 1, "train_loss": tot / n, "val_kl": kl, "val_top1": ag, "value": value,
                 "sec": time.time() - t0})
    if a.mono_weight: hist[-1]["train_mono_penalty"] = mono_tot / n; print(f"   mono penalty {mono_tot / n:.5f}", flush=True)
    print(f"ep {ep+1} train loss {tot/n:.4f} val KL {kl} top1 {ag} value {json.dumps(value.get('all'))} "
          f"{time.time()-t0:.0f}s", flush=True)
    score = kl if kl is not None else value["all"]["bce"]
    if sel_dl is not None:
        (skl, _), _, sval = evaluate(sel, sel_dl)
        score = (skl or 0.0) + (a.value_weight * sval["all"]["bce"] if a.value_weight and "all" in sval else 0.0) \
            + a.anchor_weight * sval.get("anchor_kl", 0.0)
        hist[-1]["select"] = {"kl": skl, "value": sval, "objective": score}
        print(f"   select fold objective {score:.4f} KL {skl} value {json.dumps(sval.get('all'))}", flush=True)
    if a.select == "last" or best is None or score < best[0]:
        best = (score, ag, per, kl, value, ep + 1); torch.save(net.state_dict(), os.path.join(a.out, "student.pt"))
print("best per group:", json.dumps(best[2]), flush=True)
mono = {}
if a.mono_weight or a.mono_report:  # the chosen epoch's weights
    net.load_state_dict(torch.load(os.path.join(a.out, "student.pt"), map_location=a.device, weights_only=True))
    mono = {"rules": mono_rules, "eval_deltas": monotone.EVAL, "curses": list(monotone.CURSES),
            **({"select": mono_report(sel_dl)} if sel_dl is not None else {}), "val": mono_report(val_dl)}
    print("monotonicity", json.dumps(mono), flush=True)
json.dump({"monotone": mono, "args": vars(a), "wing_boots_counter": wing_boots_counter, "params": nparam, "train_rows": len(train), "val_rows": len(val),
           "select_rows": len(sel), "selected_epoch": best[5],
           "best_val_kl": best[3], "best_val_top1": best[1], "per_screen": best[2], "value": best[4], "history": hist},
          open(os.path.join(a.out, "summary.json"), "w"), indent=1)
