"""PPO training signals from a learner's kept trajectories: per decision type, per encounter, and their history.

Read-only and offline: it reads the parts a `ppo_cloud.py serve` learner keeps on its disk (LOCAL/ARM/parts/
traj-NNNN-pK.jsonl.gz, with LOCAL/ARM/config.json) and never touches the learner, its checkpoint or the store.
No net is evaluated: every number comes from what the actors recorded (behaviour logits, behaviour critic value,
the observation record of each decision, the game line).

    python3 tools/heart1/ppo_signals.py extract --run LOCAL/ARM --out signals.jsonl [--iterations 0-30]
        one JSON line per complete iteration (all config["parts"] parts present); iterations already in --out are
        skipped, so re-running it after each update only reads the new ones.
    python3 tools/heart1/ppo_signals.py report --signals signals.jsonl --ref 0-5 --out report.json [--md report.md]
        compares every iteration (and rolling windows) with the reference iterations.

Per iteration ("extract"):
  outcome     games, stalled games, Heart rate, Act 2/3/4 reached (the outcome's act; a stalled game's line has
              none, so it counts as Act 1), mean final floor.
  screens     per decision type (ScreenState: map = path, rewards = card pick, rest = rest/smith, shop, event,
              card_select, boss_relic, treasure), over decisions with more than one choice:
              n, entropy (nats, of softmax(logits / temp)), entropy_norm (entropy / log n_choices), p_chosen,
              explore (share where the sampled choice is not the argmax), value (behaviour critic), and the
              advantage the learner's GAE gives with the run's --reward/--gamma/--lam but the BEHAVIOUR critic's
              recorded values (the learner uses its own critic at update start, one update later), and --lam
              also for value-only iterations (the learner used --warmup-lam there), so all iterations compare
              on one definition: adv_mean,
              adv_abs (mean |A|), adv_sd, adv_abs_share (the screen's share of sum |A| = its share of the policy
              gradient's weight before normalisation).
  encounters  per encounter (include/constants/MonsterEncounters.h): fights, deaths, and HP loss over the fights
              where it is measurable (hp_n, hp_sum, hp_sq; frac_* = loss / max HP before the fight).
  coverage    fights found vs the game lines' "fights" count.

How a fight is found (the trajectory has no combat lines): between two consecutive decisions of a game,
  - a hallway or elite fight is an encounter that joined obs.v2.fought (the consumed prefix of the act's monster
    and elite queues, a multiset); HP loss = HP at the earlier decision - HP at the later one (the card reward
    after the fight, so Burning Blood's heal is included and potions are not seen);
  - the act's boss is fought when the floor passes 16/33/50 within the act (boss = obs.fixed_observation[4]);
    when the act changes instead (no decision on the boss floor), the boss counts as won without HP loss
    (the act transition heals);
  - the game's last fight: a death at the outcome's death_encounter (loss = HP at the last decision), or the Heart
    when heart_kill (loss = HP at the last decision - the outcome's final HP). An Act 3 boss never has HP loss: a
    win is seen only through the act change, so a death's loss would describe HP at death, not loss per fight;
  - A20's second Act 3 boss (floor 51, right after the first) is pooled as ACT3_SECOND_BOSS, without HP loss;
  - a won game that ends in Act 3 (floor > 51: the victory room without all three keys) won its Act 3 boss(es).
  - Event fights (Mind Bloom, Colosseum, Masked Bandits, Dead Adventurer, ...) are not in the queues: only a lost
    one is seen (its death_encounter), so per-event death rates are not rates. Those with *_EVENT ids stay out of
    the per-act rates; Dead Adventurer (elite ids) and Mind Bloom (Act 1 boss ids, in Act 3) deaths carry queue
    ids and do count there and in that encounter's row (rare). An event followed by a card reward is not a
    reliable sign of a fight (Scrap Ooze also costs HP and gives a reward). coverage.fights_seen <
    fights_reported by about the number of won event fights.
  Several fights between two decisions count, without HP loss. HP loss is net of end-of-combat heals (Burning
  Blood, Meat on the Bone), so a cheap hallway fight can show a negative loss.

Report ("report"): the reference iterations (e.g. a value-only warm-up whose policy is still the start net) give
the baseline; each iteration and each rolling window of --window iterations is compared with it:
  - outcome shares and per-act fight death rates: difference and a two-proportion z;
  - per screen: entropy and explore differences (no z: tens of thousands of decisions make any drift
    "significant"; the size is the signal);
  - per encounter (pooled over the last --window iterations): death-rate and mean-HP-loss differences with z,
    only encounters with >= --min-fights fights on both sides; sorted by |z|.
  - tipping: the first window whose |z| reaches --z for the Heart rate, the Act 4 rate, or a per-act death rate,
    for --persist consecutive windows with the same sign. "direction" says worse (Heart/Act 4 down, a death rate
    up) or better; only a worse one names a rollback candidate, the behaviour net of the iteration before that
    window. Windows overlap and many signals are tested: a flag is a pointer to look, not a verdict.
Conditioning caveat: per-encounter rates are conditional on reaching the encounter; a policy that reaches Act 3
more often brings weaker decks there, so a worse Act 3 death rate can come with a better Heart rate.
"""
import argparse
import collections
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_train  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCREENS = {0: "invalid", 1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure",
           7: "rest", 8: "shop", 9: "battle"}   # include/game/GameContext.h ScreenState
BOSS_FLOOR = {1: 16, 2: 33, 3: 50}
# apps/one_combat/heart1_policy.cpp bossEncoding: fixed_observation[4] -> encounter name
BOSS_CODE = ["SLIME_BOSS", "HEXAGHOST", "THE_GUARDIAN", "CHAMP", "AUTOMATON", "COLLECTOR", "TIME_EATER",
             "DONU_AND_DECA", "AWAKENED_ONE", "THE_HEART"]
ACT3_BOSSES = {"AWAKENED_ONE", "TIME_EATER", "DONU_AND_DECA"}
ELITES = {"GREMLIN_NOB", "LAGAVULIN", "THREE_SENTRIES", "GREMLIN_LEADER", "SLAVERS", "BOOK_OF_STABBING",
          "GIANT_HEAD", "NEMESIS", "REPTOMANCER", "SHIELD_AND_SPEAR"}
SECOND_BOSS = "ACT3_SECOND_BOSS"   # A20's second Act 3 boss: fought on floor 51 without a decision in between, so
                                   # its identity is seen only when it kills (the outcome's death_encounter)
PART = re.compile(r"traj-(\d{4})-p(\d+)\.jsonl(\.gz)?$")


def encounter_names(header=os.path.join(REPO, "include", "constants", "MonsterEncounters.h")):
    """MonsterEncounter enum order -> names (the integer ids the records carry)."""
    with open(header) as f:
        text = f.read()
    body = text[text.index("enum class MonsterEncounter"):]
    body = body[body.index("{") + 1:body.index("}")]
    body = re.sub(r"//[^\n]*", "", body)
    names = [t.split("=")[0].strip() for t in body.split(",")]
    return [n for n in names if n] + [SECOND_BOSS]


def encounter_kind(name, names):
    if names.index(name) >= names.index("LAGAVULIN_EVENT") and name != SECOND_BOSS:
        return "event"
    if name in BOSS_CODE or name == SECOND_BOSS:
        return "boss"
    return "elite" if name in ELITES else "hallway"


# ---------------------------------------------------------------- per game

def _state(step):
    r = step["record"]
    fo = r["obs.fixed_observation"]
    return {"act": step["act"], "floor": step["floor"], "hp": fo[0], "max_hp": fo[1], "boss": fo[4], "asc": fo[6],
            "fought": collections.Counter(r.get("obs.v2.fought", []))}


def game_fights(game, names):
    """[(encounter id, died, hp_loss or None, max_hp before or None, act)] of one game, in order (see the docstring)."""
    out = []
    steps = game["steps"]
    o = game["outcome"]
    if o.get("stalled") or not steps:
        return out
    ids = {n: i for i, n in enumerate(names)}
    boss_done = set()
    prev = _state(steps[0])
    for step in steps[1:]:
        cur = _state(step)
        if cur["act"] == prev["act"]:
            new = list((cur["fought"] - prev["fought"]).elements())
            bf = BOSS_FLOOR.get(prev["act"])
            boss = bf is not None and prev["floor"] < bf <= cur["floor"]
            if boss:
                new.append(ids[BOSS_CODE[prev["boss"]]])
                boss_done.add(prev["act"])
            single = len(new) == 1
            for e in new:
                out.append((e, False, prev["hp"] - cur["hp"] if single else None, prev["max_hp"] if single else None,
                            prev["act"]))
        else:
            if prev["act"] not in boss_done and prev["act"] in BOSS_FLOOR:
                out.append((ids[BOSS_CODE[prev["boss"]]], False, None, None, prev["act"]))
                if prev["act"] == 3 and prev["asc"] >= 20:
                    out.append((ids[SECOND_BOSS], False, None, None, 3))
                boss_done.add(prev["act"])
            for e in cur["fought"].elements():   # fights of the new act before its first decision (none expected)
                out.append((e, False, None, None, cur["act"]))
        prev = cur
    if o.get("heart_kill"):
        out.append((ids["THE_HEART"], False, prev["hp"] - int(o.get("hp", 0)), prev["max_hp"], prev["act"]))
    elif int(o.get("death_encounter", 0) or 0) > 0:
        e = int(o["death_encounter"])
        if (prev["act"] == 3 and prev["asc"] >= 20 and int(o.get("floor", 0)) > BOSS_FLOOR[3]
                and names[e] in BOSS_CODE and 3 not in boss_done):
            out.append((ids[BOSS_CODE[prev["boss"]]], False, None, None, 3))   # the first boss was won
            out.append((ids[SECOND_BOSS], True, None, None, 3))
        else:
            act3_boss = prev["act"] == 3 and names[e] in ACT3_BOSSES
            out.append((e, True, None if act3_boss else prev["hp"], None if act3_boss else prev["max_hp"],
                        prev["act"]))
    elif (prev["act"] == 3 and int(o.get("act", 0) or 0) == 3 and int(o.get("floor", 0)) > BOSS_FLOOR[3] + 1
          and 3 not in boss_done):   # won in the Act 3 victory room (no keys): its boss(es) were won
        out.append((ids[BOSS_CODE[prev["boss"]]], False, None, None, 3))
        if prev["asc"] >= 20:
            out.append((ids[SECOND_BOSS], False, None, None, 3))
    return out


def softmax_stats(logits, temp, chosen):
    t = temp if temp > 0 else 1.0
    z = [x / t for x in logits]
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    p = [x / s for x in e]
    ent = -sum(q * math.log(q) for q in p if q > 0)
    return ent, p[chosen], int(chosen != max(range(len(z)), key=z.__getitem__))


# ---------------------------------------------------------------- extract

def run_config(run):
    for name in ("config.json", "config"):
        path = os.path.join(run, name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    sys.exit(f"{run}: no config.json")


def complete_iterations(run, n_parts, partial=False):
    parts = collections.defaultdict(dict)
    for path in glob.glob(os.path.join(run, "parts", "traj-*")):
        m = PART.search(os.path.basename(path))
        if m:
            parts[int(m.group(1))][int(m.group(2))] = path
    if partial:
        return {it: [ps[k] for k in sorted(ps)] for it, ps in parts.items()}
    return {it: [ps[k] for k in range(n_parts)] for it, ps in parts.items() if set(ps) == set(range(n_parts))}


def iteration_signals(it, files, hp, names, pipeline=1):
    games = ppo_train.load_games(files)
    scr = collections.defaultdict(lambda: collections.defaultdict(float))
    enc = collections.defaultdict(lambda: collections.defaultdict(float))
    acts = collections.defaultdict(lambda: [0, 0])   # act -> [fights, deaths]
    outc = collections.Counter()
    floors, fights_seen, fights_reported = [], 0, 0
    for g in games:
        o = g["outcome"]
        outc["games"] += 1
        if o.get("stalled"):
            outc["stalled"] += 1
        outc["heart"] += int(bool(o.get("heart_kill")))
        fl = int(o.get("floor", 0))
        floors.append(fl)
        for k in (2, 3, 4):   # the outcome's act, not ppo_train.ACT_FLOORS: floor 51 is A20's second Act 3 boss
            outc[f"act{k}"] += int(int(o.get("act", 0) or 0) >= k)
        steps = g["steps"]
        if steps:
            r = ppo_train.step_rewards(g, hp.reward, hp.gamma, hp.act_bonus, hp.key_bonus)
            adv, _ = ppo_train.gae(r, [float(s["value"]) for s in steps], hp.gamma, hp.lam)
            for s, a in zip(steps, adv):
                if s["n"] <= 1:
                    continue
                d = scr[SCREENS.get(s["screen"], str(s["screen"]))]
                ent, pc, ex = softmax_stats(s["logits"], float(s["temp"]), int(s["chosen"]))
                d["n"] += 1
                d["entropy"] += ent
                d["entropy_norm"] += ent / math.log(s["n"])
                d["p_chosen"] += pc
                d["explore"] += ex
                d["value"] += float(s["value"])
                d["adv"] += a
                d["adv_abs"] += abs(a)
                d["adv_sq"] += a * a
        fights_reported += int(o.get("fights", 0) or 0)
        for e, died, loss, mx, act in game_fights(g, names):
            fights_seen += 1
            x = enc[e]
            x["fights"] += 1
            x["deaths"] += died
            if loss is not None and mx:
                x["hp_n"] += 1
                x["hp_sum"] += loss
                x["hp_sq"] += loss * loss
                x["frac_sum"] += loss / mx
                x["frac_sq"] += (loss / mx) ** 2
            if encounter_kind(names[e], names) != "event":
                acts[act][0] += 1
                acts[act][1] += died
    total_abs = sum(d["adv_abs"] for d in scr.values()) or 1.0
    screens = {}
    for name, d in sorted(scr.items()):
        n = d["n"]
        sd = math.sqrt(max(d["adv_sq"] / n - (d["adv"] / n) ** 2, 0.0))
        screens[name] = {"n": int(n), **{k: round(d[k] / n, 6) for k in
                                         ("entropy", "entropy_norm", "p_chosen", "explore", "value")},
                         "adv_mean": round(d["adv"] / n, 6), "adv_abs": round(d["adv_abs"] / n, 6),
                         "adv_sd": round(sd, 6), "adv_abs_share": round(d["adv_abs"] / total_abs, 6)}
    fields = ("fights", "deaths", "hp_n", "hp_sum", "hp_sq", "frac_sum", "frac_sq")
    encounters = {names[e]: {"id": e, "kind": encounter_kind(names[e], names),
                             **{k: round(x[k], 6) for k in fields}}
                  for e, x in sorted(enc.items())}
    n = outc["games"]
    return {"iteration": it, "behaviour_net": f"net-{max(it - 1, 0) if pipeline else it:04d}",
            "value_only": None, "games": n, "stalled": outc["stalled"],
            "outcome": {k: outc[k] for k in ("heart", "act2", "act3", "act4")},
            "heart_rate": round(outc["heart"] / n, 6) if n else None,
            "mean_floor": round(sum(floors) / n, 3) if n else None,
            "screens": screens, "encounters": encounters,
            "act_fights": {str(a): {"fights": v[0], "deaths": v[1]} for a, v in sorted(acts.items())},
            "coverage": {"fights_seen": fights_seen, "fights_reported": fights_reported}}


def cmd_extract(argv):
    ap = argparse.ArgumentParser(prog="ppo_signals.py extract")
    ap.add_argument("--run", required=True, help="the learner's arm directory (config.json, parts/)")
    ap.add_argument("--out", required=True, help="signals JSONL, appended (iterations already in it are skipped)")
    ap.add_argument("--iterations", default="", help="A-B (inclusive); default every complete iteration")
    ap.add_argument("--partial", action="store_true",
                    help="also iterations with missing parts (a store snapshot); the line records its part count")
    a = ap.parse_args(argv)
    cfg = run_config(a.run)
    hp = argparse.ArgumentParser(add_help=False)
    ppo_train.add_hparams(hp)
    hp = hp.parse_args(cfg.get("learner_argv", []))
    if hp.reward in ("heart_pbrs", "heart_phi"):
        sys.exit(f"--reward {hp.reward}: the shaped rewards need the potentials; not supported here")
    names = encounter_names()
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            done = {json.loads(line)["iteration"] for line in f if line.strip()}
    its = complete_iterations(a.run, int(cfg["parts"]), a.partial)
    lo, hi = (int(x) for x in a.iterations.split("-")) if a.iterations else (0, 10 ** 9)
    todo = sorted(i for i in its if lo <= i <= hi and i not in done)
    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    for it in todo:
        sig = iteration_signals(it, its[it], hp, names, int(cfg.get("pipeline", 0)))
        sig["value_only"] = it < int(cfg.get("value_warmup", 0))
        sig["parts"] = len(its[it])
        with open(a.out, "a") as f:
            f.write(json.dumps(sig, separators=(",", ":")) + "\n")
        print(f"iteration {it}: {sig['games']} games, heart {sig['heart_rate']:.3f}, "
              f"fights {sig['coverage']['fights_seen']}/{sig['coverage']['fights_reported']}", flush=True)
    if not todo:
        print("nothing new")


# ---------------------------------------------------------------- report

def _z2(k1, n1, k0, n0):
    """Two-proportion z of k1/n1 - k0/n0 (pooled variance); None without data."""
    if not n1 or not n0:
        return None
    p = (k1 + k0) / (n1 + n0)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n0))
    return round((k1 / n1 - k0 / n0) / se, 3) if se > 0 else 0.0


def _pool(rows):
    """Sum the additive fields of several iterations' signal lines."""
    out = {"games": 0, "outcome": collections.Counter(), "act_fights": collections.defaultdict(collections.Counter),
           "encounters": collections.defaultdict(collections.Counter), "screens": {}}
    scr = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        out["games"] += r["games"]
        out["outcome"].update(r["outcome"])
        for a, v in r["act_fights"].items():
            out["act_fights"][a].update(v)
        for name, v in r["encounters"].items():
            out["encounters"][name].update({k: x for k, x in v.items() if k not in ("id", "kind")})
            out["encounters"][name]["_kind"] = v["kind"]
        for name, v in r["screens"].items():
            for k in ("entropy", "entropy_norm", "explore", "p_chosen", "adv_abs", "adv_mean"):
                scr[name][k] += v[k] * v["n"]
            scr[name]["n"] += v["n"]
            scr[name]["adv_abs_share"] += v["adv_abs_share"]
    for name, d in scr.items():
        n = d["n"] or 1
        out["screens"][name] = {k: d[k] / n for k in ("entropy", "entropy_norm", "explore", "p_chosen", "adv_abs",
                                                      "adv_mean")}
        out["screens"][name]["n"] = int(d["n"])
        out["screens"][name]["adv_abs_share"] = d["adv_abs_share"] / max(len(rows), 1)
    return out


def _mean_sd(s, sq, n):
    m = s / n
    return m, math.sqrt(max(sq / n - m * m, 0.0))


def compare(cur, ref, min_fights):
    """Window cur vs reference ref (both _pool outputs)."""
    res = {"games": cur["games"], "outcome": {}, "act_death": {}, "screens": {}, "encounters": []}
    for k in ("heart", "act2", "act3", "act4"):
        p1 = cur["outcome"][k] / cur["games"] if cur["games"] else None
        p0 = ref["outcome"][k] / ref["games"] if ref["games"] else None
        res["outcome"][k] = {"rate": _r(p1), "ref": _r(p0), "diff": _r(p1 - p0 if None not in (p1, p0) else None),
                             "z": _z2(cur["outcome"][k], cur["games"], ref["outcome"][k], ref["games"])}
    for a in sorted(set(cur["act_fights"]) | set(ref["act_fights"])):
        c, r = cur["act_fights"].get(a, {}), ref["act_fights"].get(a, {})
        cf, cd, rf, rd = c.get("fights", 0), c.get("deaths", 0), r.get("fights", 0), r.get("deaths", 0)
        res["act_death"][a] = {"rate": _r(cd / cf if cf else None), "ref": _r(rd / rf if rf else None),
                               "fights": cf, "ref_fights": rf, "z": _z2(cd, cf, rd, rf)}
    for name in sorted(set(cur["screens"]) | set(ref["screens"])):
        c, r = cur["screens"].get(name), ref["screens"].get(name)
        if not c or not r:
            continue
        res["screens"][name] = {"n": c["n"], **{k: _r(c[k]) for k in ("entropy", "entropy_norm", "explore",
                                                                       "adv_abs", "adv_abs_share")},
                                "d_entropy": _r(c["entropy"] - r["entropy"]),
                                "d_entropy_norm": _r(c["entropy_norm"] - r["entropy_norm"]),
                                "d_explore": _r(c["explore"] - r["explore"]),
                                "d_adv_abs_share": _r(c["adv_abs_share"] - r["adv_abs_share"])}
    for name in sorted(set(cur["encounters"]) & set(ref["encounters"])):
        c, r = cur["encounters"][name], ref["encounters"][name]
        if c["fights"] < min_fights or r["fights"] < min_fights:
            continue
        row = {"encounter": name, "kind": c["_kind"], "fights": int(c["fights"]), "ref_fights": int(r["fights"]),
               "death": _r(c["deaths"] / c["fights"]), "ref_death": _r(r["deaths"] / r["fights"]),
               "z_death": _z2(c["deaths"], c["fights"], r["deaths"], r["fights"])}
        if c["hp_n"] >= 2 and r["hp_n"] >= 2:
            m1, s1 = _mean_sd(c["hp_sum"], c["hp_sq"], c["hp_n"])
            m0, s0 = _mean_sd(r["hp_sum"], r["hp_sq"], r["hp_n"])
            se = math.sqrt(s1 * s1 / c["hp_n"] + s0 * s0 / r["hp_n"])
            row.update({"hp_loss": _r(m1, 3), "ref_hp_loss": _r(m0, 3), "d_hp_loss": _r(m1 - m0, 3),
                        "z_hp": _r((m1 - m0) / se, 3) if se > 0 else 0.0})
        res["encounters"].append(row)
    res["encounters"].sort(key=lambda x: -max(abs(x["z_death"] or 0), abs(x.get("z_hp") or 0)))
    return res


def _r(x, nd=6):
    return None if x is None else round(x, nd)


def parse_range(s):
    out = set()
    for part in s.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


TIP_SIGNALS = ("heart", "act4")


def tipping(windows, z, persist):
    """Per signal, the first window whose |z| >= z for persist consecutive windows of the same sign.

    direction: "worse" (Heart or Act 4 rate down, a per-act death rate up) or "better"; only a worse one names a
    rollback net."""
    out = {}
    names = list(TIP_SIGNALS) + sorted({f"death_act{a}" for w in windows for a in w["cmp"]["act_death"]})
    for sig in names:
        run, sign = 0, 0
        for k, w in enumerate(windows):
            if sig.startswith("death_act"):
                v = w["cmp"]["act_death"].get(sig[len("death_act"):], {}).get("z")
            else:
                v = w["cmp"]["outcome"][sig]["z"]
            s = 0 if v is None or abs(v) < z else (1 if v > 0 else -1)
            run, sign = (run + 1, s) if s and s == sign else ((1, s) if s else (0, 0))
            if run >= persist:
                first = windows[k - persist + 1]
                worse = (sign > 0) == sig.startswith("death_act")
                out[sig] = {"window_first": first["first"], "window_last": first["last"],
                            "z": first["cmp"]["outcome"][sig]["z"] if sig in TIP_SIGNALS else
                            first["cmp"]["act_death"][sig[len("death_act"):]]["z"],
                            "direction": "worse" if worse else "better",
                            "rollback_net": first["rollback_net"] if worse else None}
                break
    return out


def cmd_report(argv):
    ap = argparse.ArgumentParser(prog="ppo_signals.py report")
    ap.add_argument("--signals", required=True)
    ap.add_argument("--ref", required=True, help="reference iterations, e.g. 0-5 (ranges and commas)")
    ap.add_argument("--window", type=int, default=5, help="iterations per rolling window")
    ap.add_argument("--min-fights", type=int, default=30, help="per encounter, on both sides")
    ap.add_argument("--z", type=float, default=3.0, help="tipping threshold on |z|")
    ap.add_argument("--persist", type=int, default=2, help="consecutive windows beyond --z")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", help="also write a short Markdown summary")
    a = ap.parse_args(argv)
    rows = {}
    with open(a.signals) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows[r["iteration"]] = r
    its = sorted(rows)
    ref_its = sorted(parse_range(a.ref) & set(its))
    if not ref_its:
        sys.exit("no reference iteration in the signals")
    ref = _pool([rows[i] for i in ref_its])
    per_it = [{"iteration": i, "behaviour_net": rows[i]["behaviour_net"], "value_only": rows[i]["value_only"],
               "heart_rate": rows[i]["heart_rate"], "mean_floor": rows[i]["mean_floor"],
               "cmp": compare(_pool([rows[i]]), ref, a.min_fights)} for i in its]
    for p in per_it:
        p["cmp"].pop("encounters")   # per encounter only per window: one iteration is too few fights
    after = [i for i in its if i > max(ref_its)]
    windows = []
    for k in range(len(after) - a.window + 1):
        w = after[k:k + a.window]
        prev = [i for i in its if i < w[0]]
        windows.append({"first": w[0], "last": w[-1], "rollback_net": rows[prev[-1]]["behaviour_net"] if prev
                        else None, "cmp": compare(_pool([rows[i] for i in w]), ref, a.min_fights)})
    report = {"signals": os.path.abspath(a.signals), "ref_iterations": ref_its, "ref_games": ref["games"],
              "window": a.window, "min_fights": a.min_fights, "z": a.z, "persist": a.persist,
              "iterations": per_it, "windows": windows, "tipping": tipping(windows, a.z, a.persist),
              "latest": windows[-1] if windows else None}
    for path in (a.out, a.md):
        if path and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1)
    if a.md:
        with open(a.md, "w") as f:
            f.write(markdown(report))
    print(markdown(report))


def _pp(x):
    return "n/a" if x is None else f"{100 * x:+.1f} pp"


def markdown(rep):
    L = [f"# PPO signals vs reference iterations {rep['ref_iterations'][0]}-{rep['ref_iterations'][-1]} "
         f"({rep['ref_games']} games)", ""]
    w = rep["latest"]
    if not w:
        return "\n".join(L + ["No iteration after the reference yet.", ""])
    c = w["cmp"]
    L += [f"Latest window: iterations {w['first']}-{w['last']} ({c['games']} games).", "",
          "| signal | window | reference | diff | z |", "|---|---|---|---|---|"]
    for k, v in c["outcome"].items():
        L.append(f"| {k} | {100 * v['rate']:.1f}% | {100 * v['ref']:.1f}% | {_pp(v['diff'])} | {v['z']} |")
    for a, v in c["act_death"].items():
        if v["rate"] is not None and v["ref"] is not None:
            L.append(f"| death rate per fight, act {a} | {100 * v['rate']:.2f}% | {100 * v['ref']:.2f}% | "
                     f"{_pp(v['rate'] - v['ref'])} | {v['z']} |")
    L += ["", "| decision type | n | entropy | Δ entropy | explore | Δ explore | share of sum abs(A) |",
          "|---|---|---|---|---|---|---|"]
    for name, v in sorted(c["screens"].items(), key=lambda kv: -kv[1]["n"]):
        L.append(f"| {name} | {v['n']} | {v['entropy']:.3f} | {v['d_entropy']:+.3f} | {100 * v['explore']:.1f}% | "
                 f"{_pp(v['d_explore'])} | {100 * v['adv_abs_share']:.1f}% |")
    L += ["", "Encounters with the largest |z| (death rate or HP loss):", "",
          "| encounter | kind | fights | death | ref | z | HP loss | ref | z |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in c["encounters"][:12]:
        L.append(f"| {e['encounter']} | {e['kind']} | {e['fights']} | {100 * e['death']:.1f}% | "
                 f"{100 * e['ref_death']:.1f}% | {e['z_death']} | {e.get('hp_loss', '')} | {e.get('ref_hp_loss', '')} "
                 f"| {e.get('z_hp', '')} |")
    L += ["", f"Tipping (|z| >= {rep['z']} in {rep['persist']} consecutive windows of {rep['window']}):"]
    if rep["tipping"]:
        for sig, t in rep["tipping"].items():
            L.append(f"- {sig}: {t['direction']} from window {t['window_first']}-{t['window_last']} (z {t['z']})"
                     + (f"; rollback candidate {t['rollback_net']}" if t["rollback_net"] else ""))
    else:
        L.append("- none")
    return "\n".join(L) + "\n"


def main():
    cmds = {"extract": cmd_extract, "report": cmd_report}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
