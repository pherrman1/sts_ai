#!/usr/bin/env python3
"""Issue #401 Stage 1: grouped permutation importance for student_sel (E_d64_sel_xin, cf6bf7fb).

usage:
  audit_student_sel.py parity SILVERBOT STUDENT_PT TOOLS_HEART1 OUT.json VAL_FILES...
  audit_student_sel.py perm   SILVERBOT STUDENT_PT TOOLS_HEART1 OUT_PREFIX N_SUB groups|subs VAL_FILES...

Rows, trim, held-out split, collate and KL/top-1 mirror tools/heart1/distill.py (main) exactly:
held-out = files with seed % 8 == 7; rows without "record" or with < 2 logits dropped; map trimmed
below the current floor (--trim-map); ExtraInputsNN (--extra-inputs). The forward is ExtraInputsNN.forward
with all-padding token columns dropped per batch (set-structured tokens, type embeddings only, key-padding
attention: exact up to float rounding; checked against the stock forward in `parity`).
"""
import collections, gzip, json, math, os, re, sys, time
import numpy as np

cmd, REPO, CKPT, TOOLS = sys.argv[1:5]
sys.path[:0] = [REPO, os.path.join(REPO, "build"), TOOLS]
import torch, torch.nn.functional as F
torch.set_num_threads(1)
from silverbot import network
import student_inputs

SECTIONS = (("cards_offered.cards", 96), ("relics_offered", 3), ("potions_offered", 5), ("fixed_actions", 5), ("paths_offered", 7))
WIDTH = sum(w for _, w in SECTIONS)
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
SELECTS = ["INVALID", "TRANSFORM", "TRANSFORM_UPGRADE", "UPGRADE", "REMOVE", "DUPLICATE", "OBTAIN", "BOTTLE", "BONFIRE_SPIRITS"]


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


def load(paths):
    rows = []
    for p in sorted(paths):
        assert seed_of(p) % 8 == 7, p
        with gzip.open(p, "rt") as f:
            for line in f:
                r = json.loads(line)
                if "record" not in r or len(r["logits"]) < 2: continue
                rec = r["record"]
                rows.append({"record": trim(rec), "logits": r["logits"], "act": r.get("act", 0),
                             "deck_misc": r.get("deck_misc"), "screen": r.get("screen", rec["screen_state"]),
                             "seed": seed_of(p), "old": "kind" not in r, "tvalue": r.get("value")})
    return rows


def positions(rec):
    pos, off = [], 0
    for key, width in SECTIONS:
        pos += list(range(off, off + len(rec[key]))); off += width
    return pos


def collate(rows):
    b = network.collate_fn([{**r["record"], "chosen_idx": 0, "outcome": 0.0} for r in rows])
    b["extra"] = student_inputs.extra_batch(rows)
    mask = torch.zeros(len(rows), WIDTH, dtype=torch.bool); tgt = torch.full((len(rows), WIDTH), -1e9)
    for i, r in enumerate(rows):
        p = positions(r["record"]); mask[i, p] = True; tgt[i, p] = torch.tensor(r["logits"], dtype=torch.float32)
    for k in ("chosen_idx", "outcome", "aux_dest_room"): b.pop(k)
    return b, mask, tgt


def load_net():
    state = torch.load(CKPT, map_location="cpu")
    net = student_inputs.ExtraInputsNN(student_inputs._hp(state))
    missing, unexpected = net.load_state_dict(state, strict=False)
    assert not missing and not unexpected, (missing, unexpected)
    return net.eval()


def fast_forward(net, batch):
    """ExtraInputsNN.forward with columns that are padding in every row dropped before the transformer."""
    D, R = student_inputs.DECK, student_inputs.RELICS
    ex = batch["extra"]
    obs_embed, obs_mask = net.obs_embed(batch)
    choice_embed, choice_mask = net.choice_embed(batch["choices"])
    obs_embed = obs_embed.clone()
    obs_embed[:, :D] = obs_embed[:, :D] + net.x_deck_misc(ex["deck_misc"])
    obs_embed[:, D:D + R] = obs_embed[:, D:D + R] + net.x_relic_counter(ex["relic_counter"])
    obs_embed[:, student_inputs.FIXED_TOKEN] = obs_embed[:, student_inputs.FIXED_TOKEN] + net.x_act(ex["act"])
    x = torch.cat([obs_embed, choice_embed], 1); pm = torch.cat([obs_mask, choice_mask], 1)
    keep = ~pm.all(0); nobs = obs_mask.size(1)
    x, pm2 = x[:, keep], pm[:, keep]
    for l in net.layers: x = l(x, pm2)
    xn = net.norm(x)
    ckeep = keep[nobs:]; nko = int(keep[:nobs].sum())
    lg = net.choice_logits(xn[:, nko:]).squeeze(-1).float()
    full = torch.full((x.size(0), choice_mask.size(1)), float("-inf"))
    full[:, ckeep] = lg
    full = full.masked_fill(choice_mask, float("-inf"))
    vx = net.value_head_norm(xn)
    pooled = vx.masked_fill(pm2.unsqueeze(-1), 0).sum(1) / (~pm2).sum(1, keepdim=True).float()
    return full, net.value_head(pooled).squeeze(-1).float()


def kl_rows(logits, mask, tgt):
    lp = F.log_softmax(logits.masked_fill(~mask, -1e9), -1); lt = F.log_softmax(tgt, -1)
    return (lt.exp() * (lt - lp)).masked_fill(~mask, 0).sum(-1)


def metrics(lg, m, t):
    return kl_rows(lg, m, t), (lg.masked_fill(~m, -1e9).argmax(-1) == t.argmax(-1)).float()


# ---------------------------------------------------------------- flat tensor dataset helpers
def flatten(d, pre=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flatten(v, pre + k + "."))
        else: out[pre + k] = v
    return out


def unflatten(flat):
    out = {}
    for k, v in flat.items():
        cur = out; parts = k.split(".")
        for p in parts[:-1]: cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out


def cmd_parity(out_path, files):
    rows = load(files); net = load_net()
    print(f"val rows {len(rows)} from {len(files)} files", flush=True)
    kls, agr, vals = [], [], []
    t0 = time.time(); maxdiff = 0.0
    with torch.no_grad():
        for s in range(0, len(rows), 256):
            b, m, t = collate(rows[s:s + 256])
            lg, v = fast_forward(net, b)
            if s < 256 * 4:  # stock forward check on the first 4 batches
                lg0, v0 = net(b)
                fin = torch.isfinite(lg0)
                assert torch.equal(fin, torch.isfinite(lg))
                maxdiff = max(maxdiff, float((lg0[fin] - lg[fin]).abs().max()), float((v0 - v).abs().max()))
            k, a = metrics(lg, m, t); kls += k.tolist(); agr += a.tolist(); vals += v.tolist()
            if s % 25600 == 0: print(s, f"{time.time()-t0:.0f}s", flush=True)
    per = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for r, k, g in zip(rows, kls, agr):
        s = per[group_of(r)]; s[0] += 1; s[1] += k; s[2] += g
    tv = np.array([r["tvalue"] if r["tvalue"] is not None else np.nan for r in rows]); sv = np.array(vals)
    ok = np.isfinite(tv)
    old = np.array([r["old"] for r in rows])
    res = {"n": len(rows), "kl": float(np.mean(kls)), "top1": float(np.mean(agr)), "fast_vs_stock_maxdiff": maxdiff,
           "old": {"n": int(old.sum()), "top1": float(np.mean(np.array(agr)[old]))},
           "new": {"n": int((~old).sum()), "top1": float(np.mean(np.array(agr)[~old]))},
           "per_screen": {k: {"n": s[0], "kl": round(s[1] / s[0], 4), "top1": round(s[2] / s[0], 4)} for k, s in sorted(per.items())},
           "value_head": {"n": int(ok.sum()), "pearson_vs_teacher_value": float(np.corrcoef(sv[ok], tv[ok])[0, 1]),
                          "mse_vs_teacher_value": float(np.mean((sv[ok] - tv[ok]) ** 2)),
                          "student_mean": float(sv.mean()), "student_sd": float(sv.std()),
                          "teacher_mean": float(tv[ok].mean()), "teacher_sd": float(tv[ok].std())},
           "sec": time.time() - t0}
    json.dump(res, open(out_path, "w"), indent=1); print(json.dumps({k: v for k, v in res.items() if k != "per_screen"}))


# ---------------------------------------------------------------- permutation
# Each group: list of (flat key, column index or None).  "state" groups permute whole rows across all roots;
# "strat" groups permute among roots with the same token count in the stratifying section (mask key).
FO = "fixed_obs.fixed_observation"  # scalar cols: 0 curHp, 1 maxHp, 2 gold, 3 floorNum, 4 toSelectCount
MAPK = ["map_nodes.value.room", "map_nodes.value.is_current", "map_nodes.value.pos", "map_nodes.value.path_xs",
        "map_nodes.value.rel", "map_nodes.value.reachable", "map_nodes.value.agg", "map_nodes.value.burning", "map_nodes.mask"]
FIXK = ["choices.fixed.value.action", "choices.fixed.value.gold", "choices.fixed.value.card",
        "choices.fixed.value.relic", "choices.fixed.value.info", "choices.fixed.mask"]
PATHK = ["choices.paths.value.x", "choices.paths.value.room", "choices.paths.value.cone",
         "choices.paths.value.reaches_burn", "choices.paths.mask"]
GROUPS = {
    # state-level groups
    "hp": ("state", None, [(FO, 0), (FO, 1)]),
    "gold": ("state", None, [(FO, 2)]),
    "progress (floor, act)": ("state", None, [(FO, 3), ("extra.act", None)]),
    "boss": ("state", None, [("fixed_obs.boss", None)]),
    "ascension": ("state", None, [("fixed_obs.ascension", None)]),
    "keys": ("state", None, [("fixed_obs.key_ruby", None), ("fixed_obs.key_emerald", None), ("fixed_obs.key_sapphire", None)]),
    "screen/select context": ("state", None, [("fixed_obs.screen_state", None), ("SEL", None), (FO, 4)]),
    "deck": ("state", None, [("deck.value", None), ("deck.mask", None), ("extra.deck_misc", None)]),
    "relics": ("state", None, [("relics.value", None), ("relics.mask", None), ("extra.relic_counter", None)]),
    "potions (held)": ("state", None, [("potions.value", None), ("potions.mask", None)]),
    "map": ("state", None, [(k, None) for k in MAPK]),
    # per-candidate groups: candidate block of another root with the same count in that section
    "cand: cards offered": ("strat", "choices.cards.mask", [("CARDS01", None)]),
    "cand: relics offered": ("strat", "choices.relics.mask", [("choices.relics.value", None)]),
    "cand: potions offered": ("strat", "choices.potions.mask", [("choices.potions.value", None)]),
    "cand: fixed actions": ("strat", "choices.fixed.mask", [(k, None) for k in FIXK if not k.endswith("mask")]),
    "cand: path options": ("strat", "choices.paths.mask", [(k, None) for k in PATHK if not k.endswith("mask")]),
}
SUBFEATURES = {
    "hp": {"curHp": ("state", None, [(FO, 0)]), "maxHp": ("state", None, [(FO, 1)])},
    "progress (floor, act)": {"floor": ("state", None, [(FO, 3)]), "act": ("state", None, [("extra.act", None)])},
    "screen/select context": {"screen_state": ("state", None, [("fixed_obs.screen_state", None)]),
                              "select_screen_type": ("state", None, [("SEL", None)]),
                              "toSelectCount": ("state", None, [(FO, 4)])},
    "deck": {"deck card ids": ("strat", "deck.mask", [("DECK0", None)]),
             "deck upgrades": ("strat", "deck.mask", [("DECK1", None)]),
             "deck misc": ("strat", "deck.mask", [("extra.deck_misc", None)])},
    "relics": {"relic ids": ("strat", "relics.mask", [("relics.value", None)]),
               "relic counters": ("strat", "relics.mask", [("extra.relic_counter", None)])},
    "map": {"map room types": ("strat", "map_nodes.mask", [("map_nodes.value.room", None)]),
            "map ego/position (is_current, rel, reachable, agg)": ("strat", "map_nodes.mask",
                [(k, None) for k in ("map_nodes.value.is_current", "map_nodes.value.rel", "map_nodes.value.reachable", "map_nodes.value.agg")]),
            "map burning elite": ("strat", "map_nodes.mask", [("map_nodes.value.burning", None)])},
    "cand: fixed actions": {"fixed action enum": ("strat", "choices.fixed.mask", [("choices.fixed.value.action", None)]),
                            "fixed gold": ("strat", "choices.fixed.mask", [("choices.fixed.value.gold", None)]),
                            "fixed card/relic/info": ("strat", "choices.fixed.mask", [(k, None) for k in ("choices.fixed.value.card", "choices.fixed.value.relic", "choices.fixed.value.info")])},
    "cand: path options": {"path x": ("strat", "choices.paths.mask", [("choices.paths.value.x", None)]),
                           "path dest room": ("strat", "choices.paths.mask", [("choices.paths.value.room", None)]),
                           "path cone+reaches_burn": ("strat", "choices.paths.mask", [("choices.paths.value.cone", None), ("choices.paths.value.reaches_burn", None)])},
    "cand: cards offered": {"offered card ids": ("strat", "choices.cards.mask", [("CARDS0", None)]),
                            "offered card upgrades": ("strat", "choices.cards.mask", [("CARDS1", None)])},
}
ALIAS = {"CARDS01": ("choices.cards.value", [0, 1]), "CARDS0": ("choices.cards.value", [0]), "CARDS1": ("choices.cards.value", [1]),
         "DECK0": ("deck.value", [0]), "DECK1": ("deck.value", [1])}


def make_perm(kind, strat_key, T, gen):
    N = T["deck.mask"].shape[0]
    if kind == "state":
        return torch.randperm(N, generator=gen)
    cnt = (~T[strat_key]).sum(1)
    perm = torch.arange(N)
    for c in cnt.unique().tolist():
        if c == 0: continue
        idx = (cnt == c).nonzero().squeeze(1)
        perm[idx] = idx[torch.randperm(len(idx), generator=gen)]
    return perm


def apply(T, spec, gen):
    kind, strat_key, items = spec
    perm = make_perm(kind, strat_key, T, gen)
    P = dict(T)
    for key, col in items:
        if key == "SEL":
            P["SEL"] = T["SEL"][perm]; continue
        if key in ALIAS:
            k, cols = ALIAS[key]; v = P[k].clone(); v[..., cols] = T[k][perm][..., cols]; P[k] = v; continue
        if col is None: P[key] = T[key][perm]
        else: v = P[key].clone(); v[:, col] = T[key][perm, col]; P[key] = v
    return P


def eval_T(net, T, M, TG, bs=256):
    N = M.shape[0]
    ntok = sum((~T[k]).sum(1) for k in T if k.endswith("mask"))
    order = torch.argsort(ntok)
    kl = torch.empty(N); top = torch.empty(N); val = torch.empty(N)
    sel = T["SEL"]
    with torch.no_grad():
        for s in range(0, N, bs):
            idx = order[s:s + bs]
            flat = {k: v[idx] for k, v in T.items() if k != "SEL"}
            cv = flat["choices.cards.value"].clone(); cv[..., 2] = sel[idx].unsqueeze(1); flat["choices.cards.value"] = cv
            b = unflatten(flat)
            lg, v = fast_forward(net, b)
            k, a = metrics(lg, M[idx], TG[idx]); kl[idx] = k; top[idx] = a; val[idx] = v
    return kl.numpy(), top.numpy(), val.numpy()


def cluster_boot(delta, clusters, B=1000, seed=0):
    rng = np.random.default_rng(seed)
    ids = np.unique(clusters); sums = np.array([delta[clusters == c].sum() for c in ids]); ns = np.array([(clusters == c).sum() for c in ids])
    bs = []
    for _ in range(B):
        pick = rng.integers(0, len(ids), len(ids)); bs.append(sums[pick].sum() / ns[pick].sum())
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def cmd_perm(prefix, nsub, mode, files, repeats=5, sub_repeats=3):
    rows = load(files); net = load_net()
    rng = np.random.default_rng(401)
    pick = np.sort(rng.choice(len(rows), size=min(nsub, len(rows)), replace=False))
    rows = [rows[i] for i in pick]
    clusters = np.array([r["seed"] for r in rows]); old = np.array([r["old"] for r in rows])
    isel = np.array([r["screen"] == 4 for r in rows]); scr = np.array([group_of(r) for r in rows])
    tv = np.array([r["tvalue"] if r["tvalue"] is not None else np.nan for r in rows])
    t0 = time.time(); parts = collections.defaultdict(list); Ms, TGs = [], []
    for s in range(0, len(rows), 512):
        b, m, t = collate(rows[s:s + 512])
        for k, v in flatten(b).items(): parts[k].append(v)
        Ms.append(m); TGs.append(t)
    T = {k: torch.cat(v) for k, v in parts.items()}; M = torch.cat(Ms); TG = torch.cat(TGs)
    T["SEL"] = torch.tensor([r["record"]["select_screen_type"] for r in rows], dtype=torch.int32)
    # sanity: SEL rebuild must equal the collated column on offered cards
    cm = ~T["choices.cards.mask"]
    assert torch.equal(T["choices.cards.value"][..., 2][cm], T["SEL"].unsqueeze(1).expand_as(cm)[cm])
    del rows
    print(f"collated {len(pick)} rows {time.time()-t0:.0f}s", flush=True)
    kl0, top0, v0 = eval_T(net, T, M, TG)
    print(f"baseline KL {kl0.mean():.5f} top1 {top0.mean():.5f} {time.time()-t0:.0f}s", flush=True)
    okv = np.isfinite(tv)
    vmse0 = (v0 - tv) ** 2
    res = {"n": int(len(pick)), "n_clusters": int(len(np.unique(clusters))), "baseline": {
        "kl": float(kl0.mean()), "top1": float(top0.mean()), "kl_ci": cluster_boot(kl0, clusters),
        "value_mse": float(np.nanmean(vmse0))}, "groups": {}, "subfeatures": {}}
    if os.path.exists(prefix + ".json"):  # resume: keep finished entries (per-entry seeds are deterministic)
        prev = json.load(open(prefix + ".json"))
        assert prev["n"] == res["n"] and abs(prev["baseline"]["kl"] - res["baseline"]["kl"]) < 1e-9, "resume mismatch"
        res["groups"], res["subfeatures"] = prev["groups"], prev["subfeatures"]

    def run(name, spec, reps, seed):
        dk, dt, dv, per_rep = 0, 0, 0, []
        for r in range(reps):
            gen = torch.Generator().manual_seed(seed * 100 + r)
            kl, top, v = eval_T(net, apply(T, spec, gen), M, TG)
            dk = dk + (kl - kl0) / reps; dt = dt + (top - top0) / reps; dv = dv + ((v - tv) ** 2 - vmse0) / reps
            per_rep.append([float((kl - kl0).mean()), float((top - top0).mean())])
        out = {"d_kl": float(dk.mean()), "d_kl_ci": cluster_boot(dk, clusters),
               "d_top1": float(dt.mean()), "d_top1_ci": cluster_boot(dt, clusters),
               "rep_d_kl": [p[0] for p in per_rep], "rep_d_top1": [p[1] for p in per_rep],
               "d_value_mse": float(np.nanmean(np.where(okv, dv, np.nan))),
               "d_kl_old": float(dk[old].mean()), "d_kl_new": float(dk[~old].mean()),
               "d_kl_select_rows": float(dk[isel].mean()), "d_kl_node_rows": float(dk[~isel].mean()),
               "d_kl_by_screen": {s: round(float(dk[scr == s].mean()), 4) for s in sorted(set(scr))}}
        print(f"{name:55s} dKL {out['d_kl']:+.4f} {out['d_kl_ci']} dTop1 {out['d_top1']:+.4f} reps {np.round(out['rep_d_kl'], 4).tolist()} {time.time()-t0:.0f}s", flush=True)
        return out

    for gi, (name, spec) in enumerate(GROUPS.items() if mode == "groups" else []):
        if name in res["groups"]: continue
        res["groups"][name] = run(name, spec, repeats, gi + 1)
        json.dump(res, open(prefix + ".json", "w"), indent=1)
    for gi, (gname, subs) in enumerate(SUBFEATURES.items() if mode == "subs" else []):
        for si, (name, spec) in enumerate(subs.items()):
            if spec is None or f"{gname} / {name}" in res["subfeatures"]: continue
            res["subfeatures"][f"{gname} / {name}"] = run(f"  {gname} / {name}", spec, sub_repeats, 1000 + gi * 10 + si)
            json.dump(res, open(prefix + ".json", "w"), indent=1)
    res["sec"] = time.time() - t0
    json.dump(res, open(prefix + ".json", "w"), indent=1)


if cmd == "parity":
    cmd_parity(sys.argv[5], sys.argv[6:])
elif cmd == "perm":
    cmd_perm(sys.argv[5], int(sys.argv[6]), sys.argv[7], sys.argv[8:])
