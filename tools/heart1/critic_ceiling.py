"""Offline critic ceiling check (stage 0 of the act-1 critic plan): how much of a run's Heart outcome can a critic
trained offline on many recorded PPO games predict, per act, compared with the online PPO critic the actors logged?

No games are played. Inputs are recorded PPO trajectory parts (traj-NNNN-pXX.jsonl.gz, schema heart1-ppo-traj-v1).

    python3 tools/heart1/critic_ceiling.py fit-net --init net-0399.bin --train 'A/parts/traj-0*.jsonl.gz' \
        --exclude-from 'A/parts/traj-04*.jsonl.gz' --per-game 8 --epochs 3 --out critic.pt
    python3 tools/heart1/critic_ceiling.py fit-gbm --train ... --per-game 8 --out gbm.json
    python3 tools/heart1/critic_ceiling.py evaluate --test 'A/parts/traj-04*.jsonl.gz' --net critic.pt \
        --gbm gbm.json --out report.json

Estimators, each a probability of a Heart kill per net decision (sources heart1_ppo and heart1_ppo_single):
  online  the "value" each decision line carries (the actor net's value head, the critic PPO trained with),
          clipped to [EPS, 1 - EPS] for the log loss.
  online_cal  the same value recalibrated per act (Platt, y ~ a + b v) on the logged values of the --train-seeds-from
          parts: the comparator of the decision rule, since the MSE-trained head is not a calibrated probability
          (values <= 0 in kill games cost 9.2 nats each after clipping; review K F1).
  net     a copy of --init (all of the actor's inputs, ppo_model.featurize) whose value head is refitted as a
          logit with binary cross-entropy on the game's outcome; trunk and head train, the policy is not used.
  gbm     xgboost on flat_features(): every record field enters (bags of ids, per-id counts and counters, map
          aggregates); RECORD_FIELDS lists each field and how it enters, and an unknown field is an error.
Training rows: per game, the first net decision of each act plus --per-game more drawn uniformly (seeded by the game
seed), so long games do not dominate; 5% of the training games (by seed hash) are the early-stopping split.

evaluate scores every net decision of the test games and reports, per act (1-4) and over all decisions: n, AUC,
log loss, Brier, EV = 1 - Var(y - v) / Var(y) against the game's outcome, and the sd of the GAE advantages
(gamma 1, terminal reward 1{Heart}) at lambda --lam and at lambda 1, computed with that estimator's values.
Differences net - online_cal and gbm - online_cal (and, descriptive, against raw online) in act-1 and all-decision
log loss and EV get a game-cluster bootstrap CI.
The decision rule (PREREG critic_ceiling_20261106) is applied in "verdict".

Encounter features (issue #1050 stage 0, PREREG critic_encounters_20261115): `encounters` writes a table of each
seed's pre-generated encounter lists (acts 1-3: normal monsters, elites, boss, second boss) through the slaythespire
module's act_encounter_lists, and `check-encounters` verifies that every recorded obs.v2.fought is the consumed
prefix monsterList[:k] + eliteMonsterList[:j] of that table (and the recorded boss matches); no outcome is read.
fit-gbm --encounters TABLE --enc-scope act|run adds privileged features (enc_*, encounter_features): the remaining
normals and elites of the current act by position and count (scope act, plus the act-3 second boss), and with scope
run also the lists and bosses of the later acts. evaluate --extra-gbm NAME=PATH scores more GBMs on the same
decisions, --contrast B:A bootstraps B - A per act, and --rule encounters applies that PREREG's decision rule.

Bound worth keeping in mind (no code): with a 0/1 outcome, a critic's MSE against the outcome is Var(y) (1 - EV), so an
EV gain of d removes only d * Var(y) of the lambda-1 advantage variance.
"""
import argparse
import functools
import glob
import gzip
import hashlib
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "heart1-ppo-traj-v1"
NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")
EPS = 1e-4
ACTS = (1, 2, 3, 4)
FIXED_ACTION_KEYS = {"action", "gold", "card", "relic", "potion", "info"}
ENC_NORMALS = 8    # remaining normal encounters of the act encoded by position (an act has 15-16; <= 9 are fought)
ENC_ELITES = 4     # remaining elites by position (10 per act; <= 5 are fought)
ENC_SCOPES = ("act", "run")
# Outcome targets (PREREG critic_encounters_20261115 addendum): "heart" = 1{Heart kill} (§761, §801);
# "act1_survive" = 1{the game leaves act 1 alive}, scored on act-1 decisions only (later decisions are dropped).
TARGETS = ("heart", "act1_survive")
ACT1_CLEARED_FLOOR = 17   # = ppo_train.ACT_FLOORS[0]: the first floor after act 1's boss
_TARGET = {"name": "heart"}   # set by the subcommands before any read_part (and before the worker pool forks)


def set_target(name):
    if name not in TARGETS:
        raise ValueError(f"target {name} is not one of {TARGETS}")
    _TARGET["name"] = name


def outcome_y(outcome, target):
    if target == "heart":
        return 1.0 if outcome.get("heart_kill") else 0.0
    if target == "act1_survive":
        if "act" not in outcome:
            # A stalled game's line (ppo_cloud.stalled_game_lines) has only floor/heart_kill/stalled and no
            # decisions: act 1 counts as survived iff the stall floor is past act 1's boss (ppo_train.ACT_FLOORS).
            return 1.0 if int(outcome.get("floor", 0)) >= ACT1_CLEARED_FLOOR else 0.0
        return 1.0 if outcome.get("won") or int(outcome["act"]) >= 2 else 0.0
    raise ValueError(f"target {target}")
BOSS_ENCODING = (18, 20, 19, 39, 37, 38, 54, 55, 53, 57)   # heart1 bossEncoding index -> MonsterEncounter id

# Every record field and how flat_features() uses it (an unlisted field raises: the GBM must see all inputs).
RECORD_FIELDS = {
    "obs.fixed_observation": "each entry (hp, max hp, gold, floor, boss, toSelect, ascension, 3 keys) + hp/max hp",
    "obs.act": "value",
    "obs.deck.cards": "count per card id, deck size",
    "obs.deck.upgrades": "upgraded count per card id, upgraded total",
    "obs.deck.misc": "sum and max per card id (searing blow / genetic algorithm style counters), total",
    "obs.relics.relics": "one indicator per relic id, relic count",
    "obs.relics.relic_counters": "counter per relic id",
    "obs.potions": "count per potion id (0 invalid, 1 empty slot), filled slots",
    "obs.v2.run_counters": "each entry",
    "obs.v2.fought": "count per encounter id, number fought",
    "obs.map.xs": "map aggregates (map_dag_features) with ys, roomTypes, pathXs, mapX, mapY",
    "obs.map.ys": "map aggregates",
    "obs.map.roomTypes": "count per room type among reachable nodes; elite min/max and rest distance ahead",
    "obs.map.pathXs": "map aggregates (edges)",
    "obs.mapX": "value + map aggregates",
    "obs.mapY": "value + map aggregates",
    "obs.map.burningEliteX": "burning elite reachable indicator",
    "obs.map.burningEliteY": "burning elite reachable indicator",
    "screen_state": "one indicator per value",
    "select_screen_type": "one indicator per value",
    "cards_offered.cards": "count per offered card id, number offered",
    "cards_offered.upgrades": "upgraded offered count per card id",
    "relics_offered": "indicator per offered relic id",
    "potions_offered": "count per offered potion id",
    "offer_prices": "min, max, sum of prices >= 0, number priced",
    "fixed_actions": "count per action id; gold sum; card/relic/potion/info ids per action (FIXED_ACTION_KEYS)",
    "paths_offered": "count; per offered path destination room type count; burning elite reach count",
}


# ---------------------------------------------------------------- reading trajectories

def _unit(seed, salt):
    h = hashlib.sha256(f"{salt}:{seed}".encode()).digest()
    return int.from_bytes(h[:8], "little") / 2.0 ** 64


def read_part(path):
    """Games of one part: [{"seed", "y", "outcome", "steps": [decision rows in idx order]}] (net decisions only).
    A decision without its game line (a part cut mid-game) is dropped; a game line with another schema raises.
    y follows _TARGET; with "act1_survive" only act-1 decisions are kept."""
    pending, games = {}, []
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["type"] == "decision":
                if row.get("source") in NET_SOURCES:
                    row.pop("logits", None)
                    pending.setdefault(row["seed"], []).append(row)
            elif row["type"] == "game":
                if row.get("schema") != SCHEMA:
                    raise ValueError(f"{path}: schema {row.get('schema')} is not {SCHEMA}")
                steps = sorted(pending.pop(row["seed"], []), key=lambda r: r["idx"])
                if _TARGET["name"] == "act1_survive":
                    steps = [st for st in steps if act_of(st) == 1]
                y = outcome_y(row["outcome"], _TARGET["name"])
                games.append({"seed": str(row["seed"]), "y": y, "outcome": row["outcome"], "steps": steps})
    return games


def act_of(step):
    a = step.get("act")
    if a is None:
        a = step["record"].get("obs.act", 0)
    return int(min(max(int(a), 1), 4))


def select_steps(game, per_game):
    """First net decision of each act plus per_game more drawn uniformly (seeded by the game seed)."""
    steps = game["steps"]
    keep, seen = set(), set()
    for i, s in enumerate(steps):
        a = act_of(s)
        if a not in seen:
            seen.add(a); keep.add(i)
    rest = [i for i in range(len(steps)) if i not in keep]
    rng = random.Random(int(hashlib.sha256(game["seed"].encode()).hexdigest()[:16], 16))
    keep.update(rng.sample(rest, min(per_game, len(rest))))
    return sorted(keep)


def expand(patterns):
    out = []
    for p in patterns:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        if not hits:
            raise ValueError(f"no files match {p}")
        out.extend(hits)
    return sorted(set(out))


def _train_part(path, per_game, want_feat, trim_map, exclude, game_frac=1.0):
    import ppo_model
    rows = []
    for g in read_part(path):
        if g["seed"] in exclude or _unit(g["seed"], "frac") >= game_frac:
            continue
        for i in select_steps(g, per_game):
            s = g["steps"][i]
            rec = s["record"]
            rows.append({"seed": g["seed"], "y": g["y"], "act": act_of(s),
                         "feat": ppo_model.featurize(rec, trim_map) if want_feat else None,
                         "flat": None if want_feat else flat_with_encounters(rec, g["seed"], _ENC or None)})
    return rows


def load_training(patterns, exclude_patterns, per_game, want_feat, trim_map=False, workers=None, game_frac=1.0):
    files = expand(patterns)
    exclude = set()
    if exclude_patterns:
        for p in expand(exclude_patterns):
            exclude.update(g["seed"] for g in read_part(p))
        files = [f for f in files if f not in set(expand(exclude_patterns))]
    fn = functools.partial(_train_part, per_game=per_game, want_feat=want_feat, trim_map=trim_map, exclude=exclude,
                           game_frac=game_frac)
    rows = []
    workers = workers or min(4, os.cpu_count() or 1)
    if workers > 1 and len(files) > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(workers) as pool:
            for part in pool.imap(fn, files, chunksize=4):
                rows.extend(part)
    else:
        for f in files:
            rows.extend(fn(f))
    rows.sort(key=lambda r: (r["seed"],))
    return rows, files, exclude


# ---------------------------------------------------------------- privileged encounter lists (issue #1050)

def load_encounters(path):
    """{seed (str): [{act, monsters, elites, boss, second_boss} for acts 1-3]} and the file's sha256."""
    with open(path, "rb") as f:
        raw = f.read()
    tab = json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)
    if tab.get("schema") != "critic-encounters-v1":
        raise ValueError(f"{path}: schema {tab.get('schema')} is not critic-encounters-v1")
    return tab["seeds"], hashlib.sha256(raw).hexdigest()


def consumed_prefix(rec, acts):
    """(k, j) with obs.v2.fought == monsters[:k] + elites[:j] of the record's act; ValueError when it is not."""
    act = int(rec["obs.act"])
    L = acts[act - 1]
    f = list(rec.get("obs.v2.fought") or [])
    m, e = L["monsters"], L["elites"]
    k = 0
    while k < len(f) and k < len(m) and f[k] == m[k]:
        k += 1
    j = len(f) - k
    if f[k:] != e[:j]:
        raise ValueError(f"fought {f} is not a prefix of the act-{act} lists {m} / {e}")
    return k, j


def encounter_features(rec, acts, scope):
    """Privileged features of one decision (the policy never sees them): the current act's remaining normal
    encounters (first ENC_NORMALS by position, and their counts) and elites (first ENC_ELITES, and counts), the act-3
    second boss (A20); scope "run" adds the lists and bosses of the later acts from their start. Act 4: none."""
    if scope not in ENC_SCOPES:
        raise ValueError(f"encounter scope {scope}")
    act = int(rec["obs.act"])
    x = {}
    if act > 3:
        return x

    def add(k, v=1.0):
        x[k] = x.get(k, 0.0) + float(v)

    def lists(prefix, L, k, j):
        for i, enc in enumerate(L["monsters"][k:k + ENC_NORMALS]):
            add(f"{prefix}n{i}_{enc}"); add(f"{prefix}ncnt_{enc}")
        for i, enc in enumerate(L["elites"][j:j + ENC_ELITES]):
            add(f"{prefix}e{i}_{enc}"); add(f"{prefix}ecnt_{enc}")
        if L["second_boss"]:
            add(f"{prefix}boss2_{L['second_boss']}")

    k, j = consumed_prefix(rec, acts)
    lists("enc_", acts[act - 1], k, j)
    if scope == "run":
        for later in range(act + 1, 4):
            L = acts[later - 1]
            lists(f"enc_a{later}_", L, 0, 0)
            add(f"enc_a{later}_boss_{L['boss']}")
    return x


def cmd_encounters(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py encounters")
    ap.add_argument("--seed-range", nargs=2, type=int, required=True, metavar=("FIRST", "LAST"), help="inclusive")
    ap.add_argument("--ascension", type=int, default=20)
    ap.add_argument("--module-dir", default="", help="directory holding the built slaythespire module")
    ap.add_argument("--out", required=True, help=".json.gz")
    a = ap.parse_args(argv)
    if a.module_dir:
        sys.path.insert(0, a.module_dir)
    import slaythespire
    seeds = {str(sd): slaythespire.act_encounter_lists(sd, a.ascension) for sd in range(a.seed_range[0],
                                                                                         a.seed_range[1] + 1)}
    tab = {"schema": "critic-encounters-v1", "ascension": a.ascension, "seed_range": a.seed_range, "seeds": seeds}
    # No file name and mtime 0 in the gzip header: the file (and its sha256) depends on the content only.
    with open(a.out, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as f:
        f.write(json.dumps(tab, sort_keys=True, separators=(",", ":")).encode())
    print(f"{len(seeds)} seeds, sha256 {hashlib.sha256(open(a.out, 'rb').read()).hexdigest()}")


def _check_part(path, seeds):
    out = {"decisions": 0, "act4": 0, "checked": 0, "games": 0, "max_normals": [0, 0, 0], "max_elites": [0, 0, 0]}
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["type"] == "game":
                out["games"] += 1
            if row["type"] != "decision" or row.get("source") not in NET_SOURCES:
                continue
            out["decisions"] += 1
            rec = row["record"]
            act = int(rec["obs.act"])
            if act > 3:
                out["act4"] += 1
                continue
            acts = seeds.get(str(row["seed"]))
            if acts is None:
                raise ValueError(f"{path}: seed {row['seed']} is not in the encounter table")
            k, j = consumed_prefix(rec, acts)   # raises on a mismatch
            boss = BOSS_ENCODING[rec["obs.fixed_observation"][4]]
            if boss != acts[act - 1]["boss"]:
                raise ValueError(f"{path}: seed {row['seed']} act {act} boss {boss} vs table {acts[act - 1]['boss']}")
            if k >= len(acts[act - 1]["monsters"]):
                raise ValueError(f"{path}: seed {row['seed']} act {act} used up its normal list (regeneration)")
            out["checked"] += 1
            out["max_normals"][act - 1] = max(out["max_normals"][act - 1], k)
            out["max_elites"][act - 1] = max(out["max_elites"][act - 1], j)
    return out


def cmd_importance(argv):
    """Total-gain importance of a fitted GBM: the enc_* features' share and the top features (no data read)."""
    ap = argparse.ArgumentParser(prog="critic_ceiling.py importance")
    ap.add_argument("--gbm", nargs="+", required=True)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    import xgboost as xgb
    out = {}
    for path in a.gbm:
        meta = json.load(open(path))
        bst = xgb.Booster()
        bst.load_model(os.path.join(os.path.dirname(os.path.abspath(path)), meta["model"]))
        # keyed by the path as given: two directories may hold models with the same file name
        out[path] = importance_summary(bst.get_score(importance_type="total_gain"), meta["vocab"], a.top)
    json.dump(out, open(a.out, "w"), indent=1)
    for name, d in out.items():
        print(name, f"enc share {d['enc_gain_share']:.4f}, enc features used {d['enc_features_used']}"
                    f"/{d['enc_features']}, top enc {d['top_enc'][:5]}")


def importance_summary(score, vocab, top):
    """score: xgboost get_score (f<index> -> total gain); vocab: feature names in index order."""
    gain = {vocab[int(k[1:])]: float(v) for k, v in score.items()}
    tot = sum(gain.values()) or 1.0
    enc = {k: v for k, v in gain.items() if k.startswith("enc_")}
    rank = sorted(gain.items(), key=lambda kv: -kv[1])
    return {"total_gain": tot, "enc_gain_share": sum(enc.values()) / tot,
            "enc_features": sum(1 for k in vocab if k.startswith("enc_")), "enc_features_used": len(enc),
            "top": [[k, v / tot] for k, v in rank[:top]],
            "top_enc": [[k, v / tot] for k, v in sorted(enc.items(), key=lambda kv: -kv[1])[:top]],
            "enc_rank_of_best": next((i + 1 for i, (k, _) in enumerate(rank) if k.startswith("enc_")), None)}


def cmd_check_encounters(argv):
    """Every net decision of acts 1-3: fought == consumed prefix of the table's lists, recorded boss == table boss.
    Reads no outcome. Exits non-zero on the first mismatch."""
    ap = argparse.ArgumentParser(prog="critic_ceiling.py check-encounters")
    ap.add_argument("--parts", nargs="+", required=True)
    ap.add_argument("--encounters", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    seeds, sha = load_encounters(a.encounters)
    tot = {"decisions": 0, "act4": 0, "checked": 0, "games": 0, "max_normals": [0, 0, 0], "max_elites": [0, 0, 0]}
    files = expand(a.parts)
    for p in files:
        o = _check_part(p, seeds)
        for key in ("decisions", "act4", "checked", "games"):
            tot[key] += o[key]
        for key in ("max_normals", "max_elites"):
            tot[key] = [max(x, y) for x, y in zip(tot[key], o[key])]
    tot.update(files=len(files), encounters_sha256=sha, ok=True)
    print(json.dumps(tot))
    if a.out:
        json.dump(tot, open(a.out, "w"), indent=1)


_ENC = {}   # loaded once before the worker pool forks: {"seeds": ..., "sha256": ..., "scope": ...}


def flat_with_encounters(rec, seed, enc=None):
    """flat_features plus, when enc (see _ENC) is given, encounter_features for that seed."""
    x = flat_features(rec)
    if enc:
        acts = enc["seeds"].get(str(seed))
        if acts is None:
            raise ValueError(f"seed {seed} is not in the encounter table")
        x.update(encounter_features(rec, acts, enc["scope"]))
    return x


# ---------------------------------------------------------------- flat features for the GBM

def flat_features(rec):
    """Every record field as named numeric features (sparse dict); see RECORD_FIELDS."""
    unknown = set(rec) - set(RECORD_FIELDS)
    if unknown:
        raise ValueError(f"record fields without a flat encoding: {sorted(unknown)}")
    import ppo_model
    x = {}

    def add(k, v=1.0):
        x[k] = x.get(k, 0.0) + float(v)

    fo = rec["obs.fixed_observation"]
    for i, v in enumerate(fo):
        add(f"fo{i}", v)
    add("hp_frac", fo[0] / max(fo[1], 1))
    add("act", rec.get("obs.act", 0))
    cards, ups = rec["obs.deck.cards"], rec["obs.deck.upgrades"]
    misc = rec.get("obs.deck.misc") or []
    for i, c in enumerate(cards):
        add(f"card{c}")
        if i < len(ups) and ups[i]:
            add(f"card_up{c}"); add("deck_up")
        m = misc[i] if i < len(misc) else 0
        if m:
            add(f"card_misc{c}", m); add("deck_misc", m)
            x[f"card_miscmax{c}"] = max(x.get(f"card_miscmax{c}", -1e9), float(m))
    add("deck_n", len(cards))
    for j, v in enumerate(ppo_model.deck_aggregates(rec)):
        add(f"x3_{j}", v)
    counters = rec.get("obs.relics.relic_counters") or []
    for i, r in enumerate(rec["obs.relics.relics"]):
        add(f"relic{r}")
        add(f"relic_ctr{r}", counters[i] if i < len(counters) else 0)
    add("relic_n", len(rec["obs.relics.relics"]))
    for p in rec["obs.potions"]:
        add(f"potion{p}")
        if p > 1:
            add("potion_n")
    for i, v in enumerate(rec.get("obs.v2.run_counters") or []):
        add(f"run{i}", v)
    for e in rec.get("obs.v2.fought") or []:
        add(f"fought{e}"); add("fought_n")
    add("mapX", rec["obs.mapX"]); add("mapY", rec["obs.mapY"])
    add(f"screen{rec['screen_state']}"); add(f"select{rec['select_screen_type']}")
    if rec["obs.map.xs"]:
        minE, maxE, dR, reach, dest, cone, burn = ppo_model.map_dag_features(rec)
        for j, ok in enumerate(reach):
            if ok:
                add(f"reach_room{rec['obs.map.roomTypes'][j]}"); add("reach_n")
        front = [c for c in cone] or [(0, 0, ppo_model.MAP_AGG_CAP)]
        add("path_minE", min(c[0] for c in front)); add("path_maxE", max(c[1] for c in front))
        add("path_dR", min(c[2] for c in front))
        for d in dest:
            add(f"path_room{d}")
        add("path_burn", sum(burn))
    add("paths_n", len(rec["paths_offered"]))
    oups = rec["cards_offered.upgrades"]
    for i, c in enumerate(rec["cards_offered.cards"]):
        add(f"offer_card{c}"); add("offer_cards_n")
        if i < len(oups) and oups[i]:
            add(f"offer_card_up{c}")
    for r in rec["relics_offered"]:
        add(f"offer_relic{r}")
    for p in rec["potions_offered"]:
        add(f"offer_potion{p}")
    prices = [p for p in (rec.get("offer_prices") or []) if p >= 0]
    if prices:
        add("price_min", min(prices)); add("price_max", max(prices)); add("price_sum", sum(prices))
    add("price_n", len(prices))
    for fa in rec["fixed_actions"]:
        if set(fa) - FIXED_ACTION_KEYS:
            raise ValueError(f"fixed_actions keys without a flat encoding: {sorted(set(fa) - FIXED_ACTION_KEYS)}")
        add(f"fa{fa['action']}"); add("fa_gold", fa.get("gold", 0))
        if fa.get("info", 0):
            add(f"fa{fa['action']}_info{fa['info']}")
        for k in ("card", "relic", "potion"):
            if k in fa and fa[k] is not None and fa[k] >= 0:
                add(f"fa_{k}{fa[k]}")
    return x


def to_csr(flats, vocab):
    from scipy.sparse import csr_matrix
    data, ind, ptr = [], [], [0]
    for f in flats:
        for k, v in f.items():
            j = vocab.get(k)
            if j is not None:
                ind.append(j); data.append(v)
        ptr.append(len(ind))
    return csr_matrix((np.array(data, np.float32), np.array(ind, np.int64), np.array(ptr, np.int64)),
                      shape=(len(flats), len(vocab)))


# ---------------------------------------------------------------- fits

def split_val(rows, frac=0.05):
    tr = [r for r in rows if _unit(r["seed"], "val") >= frac]
    va = [r for r in rows if _unit(r["seed"], "val") < frac]
    return tr, va


def cmd_fit_gbm(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py fit-gbm")
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--exclude-from", nargs="*", default=[])
    ap.add_argument("--per-game", type=int, default=8)
    ap.add_argument("--game-frac", type=float, default=1.0, help="keep this share of training games (seed hash)")
    ap.add_argument("--rounds", type=int, default=3000)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--eta", type=float, default=0.05)
    ap.add_argument("--min-count", type=int, default=20, help="drop flat features seen in fewer training rows")
    ap.add_argument("--threads", type=int, default=4, help="xgboost threads (keep the PC usable while LONG_C trains)")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--encounters", default="", help="encounter table (`encounters`): add privileged enc_* features")
    ap.add_argument("--enc-scope", default="act", choices=ENC_SCOPES)
    ap.add_argument("--target", default="heart", choices=TARGETS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    import xgboost as xgb
    set_target(a.target)
    _ENC.clear()
    if a.encounters:
        seeds, sha = load_encounters(a.encounters)
        _ENC.update(seeds=seeds, sha256=sha, scope=a.enc_scope)
    rows, files, excl = load_training(a.train, a.exclude_from, a.per_game, want_feat=False, workers=a.workers,
                                      game_frac=a.game_frac)
    tr, va = split_val(rows)
    counts = {}
    for r in tr:
        for k in r["flat"]:
            counts[k] = counts.get(k, 0) + 1
    vocab = {k: i for i, k in enumerate(sorted(k for k, c in counts.items() if c >= a.min_count))}
    dtr = xgb.DMatrix(to_csr([r["flat"] for r in tr], vocab), label=[r["y"] for r in tr])
    dva = xgb.DMatrix(to_csr([r["flat"] for r in va], vocab), label=[r["y"] for r in va])
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": a.depth, "eta": a.eta,
              "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 20, "tree_method": "hist", "seed": 0,
              "nthread": a.threads}
    bst = xgb.train(params, dtr, a.rounds, evals=[(dva, "val")], early_stopping_rounds=100, verbose_eval=200)
    model_path = a.out + ".ubj"
    bst.save_model(model_path)
    meta = {"kind": "critic_ceiling_gbm", "model": os.path.basename(model_path), "vocab": sorted(vocab, key=vocab.get),
            "best_iteration": int(bst.best_iteration), "train_rows": len(tr), "val_rows": len(va),
            "train_files": len(files), "excluded_seeds": len(excl), "per_game": a.per_game,
            "params": params, "rounds": a.rounds, "game_frac": a.game_frac,
            "encounters": {"sha256": _ENC["sha256"], "scope": _ENC["scope"]} if _ENC else None, "target": a.target}
    json.dump(meta, open(a.out, "w"), indent=1)
    print(f"gbm: {len(tr)} train / {len(va)} val rows, {len(vocab)} features, best iteration {bst.best_iteration}")


class Gbm:
    def __init__(self, path, encounters=None):
        """encounters: (seeds, sha256) of the table; required when the model was fitted with one (same sha)."""
        import xgboost as xgb
        self.meta = json.load(open(path))
        self.vocab = {k: i for i, k in enumerate(self.meta["vocab"])}
        self.bst = xgb.Booster()
        self.bst.load_model(os.path.join(os.path.dirname(os.path.abspath(path)), self.meta["model"]))
        self.xgb = xgb
        self.enc = None
        want = self.meta.get("encounters")
        if want:
            if encounters is None or encounters[1] != want["sha256"]:
                raise ValueError(f"{path} was fitted with encounter table {want['sha256'][:12]}; pass the same "
                                 "table to evaluate --encounters")
            self.enc = {"seeds": encounters[0], "sha256": want["sha256"], "scope": want["scope"]}

    def predict(self, recs, seed=None, flats=None):
        """flats: flat_features of recs computed once by the caller (encounter features are added per model)."""
        flats = flats if flats is not None else [flat_features(r) for r in recs]
        if self.enc:
            acts = self.enc["seeds"].get(str(seed))
            if acts is None:
                raise ValueError(f"seed {seed} is not in the encounter table")
            flats = [dict(f, **encounter_features(r, acts, self.enc["scope"])) for f, r in zip(flats, recs)]
        m = self.xgb.DMatrix(to_csr(flats, self.vocab))
        return self.bst.predict(m, iteration_range=(0, self.meta["best_iteration"] + 1)).astype(np.float64)


def _net_logits(net, store, idx, device, amp):
    import torch
    import ppo_model
    b = ppo_model.batch_to(store.batch(idx), device)
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp and device.type == "cuda"):
        _, value, _ = net.heads_out(net.trunk(b), b)
    return value.float()


def cmd_fit_net(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py fit-net")
    ap.add_argument("--init", required=True, help="actor net .bin whose trunk starts the critic")
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--exclude-from", nargs="*", default=[])
    ap.add_argument("--per-game", type=int, default=8)
    ap.add_argument("--game-frac", type=float, default=1.0, help="keep this share of training games (seed hash)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--head-lr", type=float, default=1e-3)
    ap.add_argument("--minibatch", type=int, default=256)
    ap.add_argument("--amp", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--device", default="cuda" if _cuda() else "cpu")
    ap.add_argument("--threads", type=int, default=4, help="torch CPU threads")
    ap.add_argument("--target", default="heart", choices=TARGETS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    set_target(a.target)
    import torch
    import torch.nn.functional as F
    import ppo_model
    torch.set_num_threads(a.threads)
    torch.manual_seed(a.seed)
    device = torch.device(a.device)
    net = ppo_model.PolicyNet.from_bin(a.init).to(device)
    rows, files, excl = load_training(a.train, a.exclude_from, a.per_game, want_feat=True,
                                      trim_map=net.trim_map, workers=a.workers, game_frac=a.game_frac)
    tr, va = split_val(rows)
    ybar = sum(r["y"] for r in tr) / max(len(tr), 1)
    with torch.no_grad():   # the value head becomes a logit head starting at the base rate
        net.value_head.weight.zero_()
        net.value_head.bias.fill_(math.log(max(ybar, EPS) / max(1 - ybar, EPS)))
    head = list(net.value_head.parameters()) + list(net.value_head_norm.parameters())
    hid = {id(p) for p in head}
    opt = torch.optim.Adam([{"params": [p for p in net.parameters() if id(p) not in hid], "lr": a.lr},
                            {"params": head, "lr": a.head_lr}])
    st_tr, st_va = ppo_model.FeatureStore([r["feat"] for r in tr]), ppo_model.FeatureStore([r["feat"] for r in va])
    y_tr = torch.tensor([r["y"] for r in tr], device=device)
    y_va = torch.tensor([r["y"] for r in va], device=device)

    def val_loss():
        net.eval()
        tot = 0.0
        with torch.no_grad():
            for i in range(0, len(va), 1024):
                idx = list(range(i, min(i + 1024, len(va))))
                z = _net_logits(net, st_va, idx, device, bool(a.amp))
                tot += float(F.binary_cross_entropy_with_logits(z, y_va[idx], reduction="sum"))
        return tot / max(len(va), 1)

    best, best_state, log = val_loss(), None, []
    print(f"net: {len(tr)} train / {len(va)} val rows from {len(files)} files; epoch 0 val logloss {best:.5f}")
    rng = random.Random(a.seed)
    for ep in range(1, a.epochs + 1):
        net.train()
        order = list(range(len(tr)))
        rng.shuffle(order)
        for i in range(0, len(order), a.minibatch):
            idx = order[i:i + a.minibatch]
            z = _net_logits(net, st_tr, idx, device, bool(a.amp))
            loss = F.binary_cross_entropy_with_logits(z, y_tr[idx])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        vl = val_loss()
        log.append({"epoch": ep, "val_logloss": vl})
        print(f"epoch {ep} val logloss {vl:.5f}")
        if vl < best:
            best, best_state = vl, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    torch.save({"kind": "critic_ceiling_net", "init": os.path.abspath(a.init),
                "init_sha256": hashlib.sha256(open(a.init, "rb").read()).hexdigest(), "state": best_state,
                "val_logloss": best, "log": log, "train_rows": len(tr), "val_rows": len(va), "per_game": a.per_game,
                "excluded_seeds": len(excl), "args": vars(a)}, a.out)


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


class Net:
    def __init__(self, path, device=None):
        import torch
        import ppo_model
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.device = torch.device(device or ("cuda" if _cuda() else "cpu"))
        self.net = ppo_model.PolicyNet.from_bin(ck["init"])
        self.net.load_state_dict(ck["state"])
        self.net.to(self.device).eval()
        self.meta = {k: v for k, v in ck.items() if k != "state"}

    def predict(self, recs):
        import torch
        import ppo_model
        out = []
        with torch.no_grad():
            for i in range(0, len(recs), 512):
                feats = [ppo_model.featurize(r, self.net.trim_map) for r in recs[i:i + 512]]
                st = ppo_model.FeatureStore(feats)
                z = _net_logits(self.net, st, list(range(len(feats))), self.device, False)
                out.append(torch.sigmoid(z).cpu().numpy().astype(np.float64))
        return np.concatenate(out) if out else np.zeros(0)


# ---------------------------------------------------------------- metrics

def gae_adv(y, v, lam):
    """GAE advantages of one game: gamma 1, reward 0 except y at the last step, value 0 after the last step."""
    n = len(v)
    adv = np.zeros(n)
    last = 0.0
    for t in range(n - 1, -1, -1):
        nxt = v[t + 1] if t + 1 < n else 0.0
        r = y if t == n - 1 else 0.0
        last = r + nxt - v[t] + lam * last
        adv[t] = last
    return adv


def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    if pos == 0 or neg == 0:
        return None
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    ps = p[order]   # average ranks over ties
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def logloss(y, p):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def ev(y, v):
    vy = np.var(y)
    return float(1 - np.var(y - v) / vy) if vy > 0 else None


def summarize(y, v, adv_l, adv_1):
    return {"n": int(len(y)), "heart": float(np.mean(y)) if len(y) else None, "auc": auc(y, v),
            "logloss": float(np.mean(logloss(y, v))) if len(y) else None,
            "brier": float(np.mean((y - v) ** 2)) if len(y) else None, "ev": ev(y, v) if len(y) else None,
            "sd_adv_lam": float(np.std(adv_l)) if len(y) else None, "sd_adv_1": float(np.std(adv_1)) if len(y) else None}


def game_sums(gid, y, v, G):
    """Per-game sums for the cluster bootstrap of log loss and EV: n, sum e, sum e^2, sum y, sum y^2, sum ll."""
    e = y - v
    out = np.zeros((G, 6))
    for col, w in enumerate((np.ones_like(y), e, e * e, y, y * y, logloss(y, v))):
        np.add.at(out[:, col], gid, w)
    return out


def stats_from_sums(S):
    """S (..., G, 6) weighted sums -> (log loss, EV) over the last-but-one axis."""
    n, se, se2, sy, sy2, sll = (S[..., k] for k in range(6))
    var_e = se2 / n - (se / n) ** 2
    var_y = sy2 / n - (sy / n) ** 2
    return sll / n, 1 - var_e / var_y


def bootstrap_diff(gid, y, va, vb, G, B, seed):
    """Point and percentile CI (2.5/97.5 and 1.25/98.75) of (b - a) in log loss and EV, resampling games."""
    Sa, Sb = game_sums(gid, y, va, G), game_sums(gid, y, vb, G)
    keep = Sa[:, 0] > 0
    Sa, Sb = Sa[keep], Sb[keep]
    la, ea = stats_from_sums(Sa.sum(0)); lb, eb = stats_from_sums(Sb.sum(0))
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(Sa), np.full(len(Sa), 1.0 / len(Sa)), size=B).astype(np.float64)   # (B, G')
    la_b, ea_b = stats_from_sums(np.einsum("bg,gk->bk", W, Sa))
    lb_b, eb_b = stats_from_sums(np.einsum("bg,gk->bk", W, Sb))
    dl, de = lb_b - la_b, eb_b - ea_b

    def ci(d, q):
        return [float(np.percentile(d, q)), float(np.percentile(d, 100 - q))]
    return {"games": int(len(Sa)), "logloss_diff": float(lb - la), "logloss_ci95": ci(dl, 2.5),
            "logloss_ci9875": ci(dl, 0.625), "ev_diff": float(eb - ea), "ev_ci95": ci(de, 2.5),
            "ev_ci9875": ci(de, 0.625)}


def verdict(boot, ev_margin):
    """PREREG rule (amended after review K F1/F2): against online_cal (the online critic recalibrated per act on the
    training parts), an offline estimator is BETTER on a scope when its log-loss difference has a 98.75% CI entirely
    below 0, its EV-gain 98.75% CI entirely above 0, and its EV gain is at least ev_margin (point estimate); 98.75% =
    Bonferroni over 2 estimators x 2 scopes. GO for stage 1 when some estimator is BETTER on act 1 or on all
    decisions; otherwise NO_GO."""
    out = {}
    for name, scopes in boot.items():
        out[name] = {sc: ("BETTER" if b["logloss_ci9875"][1] < 0 and b["ev_ci9875"][0] > 0 and b["ev_diff"] >= ev_margin
                          else "NOT_BETTER") for sc, b in scopes.items()}
    go = any(v == "BETTER" for d in out.values() for v in d.values())
    return {"by_estimator": out, "ev_margin": ev_margin, "decision": "GO" if go else "NO_GO"}


CONTRAST_SCOPES = ("first_decision", "act1", "act2", "act3", "act4", "all")


def _scorable(y):
    """A scope gets a contrast only with decisions of both outcomes (act1_survive leaves acts 2-4 empty)."""
    return len(y) > 0 and 0 < float(np.mean(y)) < 1


def verdict_encounters(contrasts, ev_margin):
    """PREREG critic_encounters_20261115 (issue #1050 stage 0): GO for step 1 (a privileged critic in PPO) when, on
    act-1 decisions, gbm_enc gains at least ev_margin EV over gbm (same rows, settings and public features) with its
    95% CI above 0, and gbm_enc's EV gain over online_cal (the critic PPO has) also has its 95% CI above 0. Otherwise
    NO_GO. Log loss and the other scopes are descriptive."""
    a, b = contrasts.get("gbm_enc-gbm"), contrasts.get("gbm_enc-online_cal")
    if a is None or b is None:
        raise ValueError("--rule encounters needs --contrast gbm_enc:gbm and --contrast gbm_enc:online_cal")
    a1, b1 = a["act1"], b["act1"]
    checks = {"gain_over_gbm_at_margin": a1["ev_diff"] >= ev_margin, "gain_over_gbm_ci95_above_0": a1["ev_ci95"][0] > 0,
              "gain_over_online_cal_ci95_above_0": b1["ev_ci95"][0] > 0}
    return {"rule": "encounters", "ev_margin": ev_margin, "checks": checks,
            "decision": "GO" if all(checks.values()) else "NO_GO"}


def fit_platt(acts, v, y, iters=50, ridge=1e-6):
    """Per act (1-4): logistic regression y ~ a + b v on the raw logged online value (Newton steps)."""
    acts, v, y = np.asarray(acts), np.asarray(v, dtype=np.float64), np.asarray(y, dtype=np.float64)
    out = {}
    for act in ACTS:
        m = acts == act
        if m.sum() < 2 or y[m].min() == y[m].max():
            yb = float(np.clip(y[m].mean() if m.any() else y.mean(), EPS, 1 - EPS))
            out[act] = (math.log(yb / (1 - yb)), 0.0)
            continue
        X = np.stack([np.ones(int(m.sum())), v[m]], 1)
        w = np.zeros(2)
        for _ in range(iters):
            p = 1 / (1 + np.exp(-(X @ w)))
            g = X.T @ (p - y[m])
            H = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(2)
            step = np.linalg.solve(H, g)
            w -= step
            if np.abs(step).max() < 1e-10:
                break
        out[act] = (float(w[0]), float(w[1]))
    return out


def apply_platt(cal, acts, v):
    z = np.array([cal[int(a)][0] + cal[int(a)][1] * x for a, x in zip(acts, v)])
    return 1 / (1 + np.exp(-z))


def cmd_evaluate(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py evaluate")
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--net", default="")
    ap.add_argument("--gbm", default="")
    ap.add_argument("--extra-gbm", action="append", default=[], metavar="NAME=PATH",
                    help="more GBMs scored on the same decisions (e.g. gbm_enc=gbm_enc.json)")
    ap.add_argument("--encounters", default="", help="encounter table for GBMs fitted with one")
    ap.add_argument("--contrast", action="append", default=[], metavar="B:A",
                    help="bootstrap B - A on act 1-4, first decision and all (95%% CIs)")
    ap.add_argument("--rule", default="critic_ceiling", choices=("critic_ceiling", "encounters"))
    ap.add_argument("--enc-ev-margin", type=float, default=0.03)
    ap.add_argument("--target", default="heart", choices=TARGETS,
                    help="outcome scored; every GBM/net must have been fitted on the same target")
    ap.add_argument("--lam", type=float, default=0.97)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--boot-seed", type=int, default=20261106)
    ap.add_argument("--ev-margin", type=float, default=0.02)
    ap.add_argument("--train-seeds-from", nargs="*", default=[],
                    help="parts used in training: test must not share seeds; their logged values fit online_cal")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    set_target(a.target)
    files = expand(a.test)
    train_seeds, ca, cv, cy = set(), [], [], []
    for p in (expand(a.train_seeds_from) if a.train_seeds_from else []):
        for g in read_part(p):
            train_seeds.add(g["seed"])
            for s in g["steps"]:
                ca.append(act_of(s)); cv.append(float(s["value"])); cy.append(g["y"])
    cal = fit_platt(ca, cv, cy) if cv else None
    ests = {"online": None}
    if cal is not None:
        ests["online_cal"] = None
    if a.net:
        ests["net"] = Net(a.net)
    enc_tab = load_encounters(a.encounters) if a.encounters else None
    if a.gbm:
        ests["gbm"] = Gbm(a.gbm, enc_tab)
    for spec in a.extra_gbm:
        name, _, path = spec.partition("=")
        if not name or not path or name in ests or name == "net":
            raise ValueError(f"--extra-gbm {spec}: need a new NAME=PATH")
        ests[name] = Gbm(path, enc_tab)
    for k, m in ests.items():
        if m is not None:
            fitted = (m.meta.get("target") or (m.meta.get("args") or {}).get("target") or "heart")
            if fitted != a.target:
                raise ValueError(f"{k} was fitted on target {fitted}, evaluate scores {a.target}")
    contrasts = []
    for spec in a.contrast:
        b, _, base = spec.partition(":")
        if b not in ests or base not in ests:
            raise ValueError(f"--contrast {spec}: both estimators must be scored")
        contrasts.append((b, base))
    cols = {k: [] for k in ("gid", "y", "act", "first") + tuple(ests)}
    advs = {k: {"lam": [], "one": []} for k in ests}
    seeds, gid = set(), 0
    for path in files:
        for g in read_part(path):
            if g["seed"] in seeds:
                raise ValueError(f"seed {g['seed']} twice in the test parts")
            if g["seed"] in train_seeds:
                raise ValueError(f"test seed {g['seed']} is in the training parts")
            seeds.add(g["seed"])
            if not g["steps"]:
                continue
            recs = [s["record"] for s in g["steps"]]
            raw = np.array([float(s["value"]) for s in g["steps"]])
            vals = {"online": np.clip(raw, EPS, 1 - EPS)}
            if cal is not None:
                vals["online_cal"] = np.clip(apply_platt(cal, [act_of(s) for s in g["steps"]], raw), EPS, 1 - EPS)
            flats = [flat_features(r) for r in recs] if any(isinstance(m, Gbm) for m in ests.values()) else None
            for k, m in ests.items():
                if isinstance(m, Gbm):
                    vals[k] = np.clip(m.predict(recs, g["seed"], flats), EPS, 1 - EPS)
                elif m is not None:
                    vals[k] = np.clip(m.predict(recs), EPS, 1 - EPS)
            n = len(recs)
            cols["gid"].extend([gid] * n); cols["y"].extend([g["y"]] * n)
            cols["act"].extend(act_of(s) for s in g["steps"]); cols["first"].extend([1] + [0] * (n - 1))
            for k in ests:
                cols[k].extend(vals[k].tolist())
                advs[k]["lam"].extend(gae_adv(g["y"], vals[k], a.lam).tolist())
                advs[k]["one"].extend(gae_adv(g["y"], vals[k], 1.0).tolist())
            gid += 1
    C = {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}
    gids = C["gid"].astype(np.int64)
    scopes = {"all": np.ones(len(C["y"]), bool), "first_decision": C["first"] == 1}
    for act in ACTS:
        scopes[f"act{act}"] = C["act"] == act
    report = {"schema": "critic-ceiling-report-v1", "test_files": len(files), "games": gid, "lam": a.lam,
              "target": a.target,
              "estimators": {}, "bootstrap": {}, "bootstrap_vs_raw_online": {},
              "meta": {"online_cal": {"platt_by_act": cal, "rows": len(cv)}} if cal is not None else {}}
    for k in ests:
        A_l, A_1 = np.asarray(advs[k]["lam"]), np.asarray(advs[k]["one"])
        report["estimators"][k] = {sc: summarize(C["y"][m], C[k][m], A_l[m], A_1[m]) for sc, m in scopes.items()}
        if ests[k] is not None:
            report["meta"][k] = ests[k].meta if isinstance(ests[k], Gbm) else \
                {x: y for x, y in ests[k].meta.items() if x != "log"}
    for k in ests:
        if k in ("online", "online_cal"):
            continue
        both = {}
        for base in ("online_cal", "online"):
            if base in C:
                both[base] = {sc: bootstrap_diff(gids[m], C["y"][m], C[base][m], C[k][m], gid, a.boot, a.boot_seed)
                              for sc in ("act1", "all") for m in [scopes[sc]]}
        if "online_cal" in both:
            report["bootstrap"][k] = both["online_cal"]
        report["bootstrap_vs_raw_online"][k] = both["online"]
    report["contrasts"] = {f"{b}-{base}": {sc: bootstrap_diff(gids[scopes[sc]], C["y"][scopes[sc]], C[base][scopes[sc]],
                                                            C[b][scopes[sc]], gid, a.boot, a.boot_seed)
                                         for sc in CONTRAST_SCOPES if _scorable(C["y"][scopes[sc]])}
                           for b, base in contrasts}
    # The rule needs the recalibrated comparator; without --train-seeds-from there is no verdict.
    if a.rule == "encounters":
        report["verdict"] = verdict_encounters(report["contrasts"], a.enc_ev_margin)
    else:
        report["verdict"] = verdict(report["bootstrap"], a.ev_margin) if report["bootstrap"] else None
    json.dump(report, open(a.out, "w"), indent=1, default=str)
    for k, d in report["estimators"].items():
        print(k, " ".join(f"{sc}: auc {d[sc]['auc'] and round(d[sc]['auc'], 3)} ev {d[sc]['ev'] and round(d[sc]['ev'], 3)}"
                          for sc in ("act1", "act2", "act3", "act4", "all")))
    for name, d in report["contrasts"].items():
        print(name, " ".join(f"{sc}: dEV {d[sc]['ev_diff']:+.4f} [{d[sc]['ev_ci95'][0]:+.4f}, {d[sc]['ev_ci95'][1]:+.4f}]"
                             for sc in CONTRAST_SCOPES if sc in d))
    if report["verdict"]:
        print("verdict", report["verdict"]["decision"],
              report["verdict"].get("by_estimator", report["verdict"].get("checks")))


def main():
    cmds = {"fit-net": cmd_fit_net, "fit-gbm": cmd_fit_gbm, "evaluate": cmd_evaluate, "encounters": cmd_encounters,
            "check-encounters": cmd_check_encounters, "importance": cmd_importance}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(f"usage: critic_ceiling.py {{{','.join(cmds)}}} ...")
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
