"""analyze.py OUT.json SIB.jsonl[.gz]... -- #886 paired-variant monotonicity audit of the active A20 OOC leaf.

Reads STS_OOC_SIBLING_MONO rows (extra.mono) and reports, per estimator (X2-B raw, the M0-calibrated leaf anchor,
the rollout3 leaf on common streams, heart1's value head), signed violations of the same-state dominance pairs:

  hp      current HP lowered (delta < 0) must not raise the value; raised (delta > 0) must not lower it.
  upgrade one upgraded card must not lower the value. Upgrades are classed P (numeric damage/block/magic or cost
          only) or H (draw, innate, exhaust/ethereal removal, choice instead of random, ...: dominance is a
          heuristic expectation, not proven). A zero change on a P upgrade is reported as "blind".

Pairs whose HP dominance is not mechanically guaranteed are flagged and reported separately: act 1 with Hexaghost
(Divider scales with current HP), Red Skull, Meat on the Bone. Rollout differences use the 16 paired streams; a
rollout violation is "material" when the wrong-way mean exceeds 2 paired SE. Ranking impact: each root action's value
is the mean base rollout value of its captured depth-1 leaves (sampled successors); a violation could reorder the
root when its wrong-way change exceeds the gap from its action to the adjacent sibling action in the direction of
the error (i.e. if the same error applied to every successor of that action)."""
import gzip, json, math, sys
from collections import defaultdict

P_UPGRADES = set("""STRIKE_RED DEFEND_RED BASH ANGER CLEAVE CLOTHESLINE IRON_WAVE PERFECTED_STRIKE TWIN_STRIKE WILD_STRIKE
BODY_SLAM CLASH HEADBUTT HEAVY_BLADE SWORD_BOOMERANG THUNDERCLAP UPPERCUT BLOODLETTING CARNAGE DROPKICK HEMOKINESIS
PUMMEL RAMPAGE RECKLESS_CHARGE SEARING_BLOW SEVER_SOUL WHIRLWIND BLUDGEON FEED FIEND_FIRE IMMOLATE REAPER FLAME_BARRIER
GHOSTLY_ARMOR IMPERVIOUS INFLAME METALLICIZE POWER_THROUGH SHRUG_IT_OFF ARMAMENTS FLEX HAVOC SENTINEL SECOND_WIND
SEEING_RED SHOCKWAVE SPOT_WEAKNESS ENTRENCH DISARM INTIMIDATE RAGE DUAL_WIELD INFERNAL_BLADE EXHUME DOUBLE_TAP
JUGGERNAUT BARRICADE BERSERK CORRUPTION DARK_EMBRACE DEMON_FORM EVOLVE FEEL_NO_PAIN FIRE_BREATHING RUPTURE COMBUST
BLOOD_FOR_BLOOD BANDAGE_UP DARK_SHACKLES DRAMATIC_ENTRANCE FINESSE FLASH_OF_STEEL GOOD_INSTINCTS MADNESS PANACEA
PANIC_BUTTON SWIFT_STRIKE APOTHEOSIS HAND_OF_GREED MAGNETISM MAYHEM PANACHE SADISTIC_NATURE THE_BOMB RITUAL_DAGGER
BITE JAX""".split())
EST = ("x2b", "leafAnchor", "rollout", "heart1")
EPS = 1e-9

def rows(paths):
    for p in paths:
        with (gzip.open(p, "rt") if p.endswith(".gz") else open(p)) as f:
            for line in f:
                try: yield json.loads(line)
                except json.JSONDecodeError: pass  # a stopped run's last line

def mean_se(xs):
    n = len(xs)
    if n == 0: return None, None
    m = sum(xs) / n
    if n < 2: return m, None
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)

def rollout_values(v):
    return [r.get("value") for r in v.get("rollouts", [])]

def main(out_path, paths):
    checks = defaultdict(int)
    pairs, leaves = [], []
    siblings = defaultdict(lambda: defaultdict(list))   # (seed, decision) -> action -> [base rollout means]
    for r in rows(paths):
        e = r.get("extra", {})
        m = e.get("mono")
        checks["rows"] += 1
        if not m: checks["rows_without_mono"] += 1; continue
        if m.get("restoreError"): checks["restore_errors"] += 1
        vs = m["variants"]
        base = vs[0]
        assert base["kind"] == "base"
        if base["featureDiff"]: checks["base_feature_diff"] += 1
        bro = rollout_values(base)
        if None in bro: checks["base_rollout_errors"] += 1; continue
        # The base rollouts reuse the repeats' streams: they must reproduce them exactly.
        rep = [x.get("value") for x in e.get("repeats", [])]
        k = min(len(rep), len(bro))
        checks["base_vs_repeats_compared"] += 1
        if rep[:k] != bro[:k]: checks["base_vs_repeats_mismatch"] += 1
        key = (r["seed"], r["decision"])
        bmean = sum(bro) / len(bro)
        siblings[key][r["action"]].append(bmean)
        hpflag = []
        if m.get("act") == 1 and m.get("boss") == "HEXAGHOST": hpflag.append("hexaghost")
        if m.get("redSkull"): hpflag.append("red_skull")
        if m.get("meatOnTheBone"): hpflag.append("meat_on_the_bone")
        leaves.append({"seed": r["seed"], "decision": r["decision"], "leaf": r["leaf"], "act": r["act"],
                       "floor": r["floor"], "screen": r["screen"], "parentScreen": r["parentScreen"],
                       "actionKey": r["actionKey"], "hp": r["hp"], "maxHp": r["maxHp"], "boss": m.get("boss"),
                       "hpFlags": hpflag, "base": {"x2b": base.get("x2b"), "leafAnchor": base.get("leafAnchor"),
                       "heart1": base.get("heart1"), "rolloutMean": bmean}})
        for v in vs[1:]:
            kind = v["kind"]
            fd = v["featureDiff"]
            if kind == "hp":
                ok = len(fd) == 1 and fd[0][0] == "curHp" and fd[0][2] - fd[0][1] == v["delta"]
                sign = 1 if v["delta"] > 0 else -1
                cls = "flagged" if hpflag else "proven"
                label = f"hp{v['delta']:+d}"
            else:
                expected = f"u{v['cardId']}"
                ok = (fd == [] and v.get("wasUpgraded")) or (len(fd) == 1 and fd[0][0] == expected
                                                            and fd[0][2] - fd[0][1] == 1)
                blind_feature = fd == []
                sign = 1
                cls = "P" if v["card"] in P_UPGRADES and not v.get("wasUpgraded") else "H"
                label = v["card"]
            if not ok: checks["feature_diff_unexpected"] += 1
            ro = rollout_values(v)
            if None in ro or len(ro) != len(bro): checks["variant_rollout_errors"] += 1; ro = None
            d = {}
            for est in ("x2b", "leafAnchor", "heart1"):
                if v.get(est) is not None and base.get(est) is not None: d[est] = v[est] - base[est]
            se = None
            if ro is not None:
                diffs = [a - b for a, b in zip(ro, bro)]
                d["rollout"], se = mean_se(diffs)
            p = {"seed": r["seed"], "decision": r["decision"], "leaf": r["leaf"], "action": r["action"],
                 "act": r["act"], "kind": kind,
                 "label": label, "class": cls, "sign": sign, "featureOk": ok, "delta": d, "rolloutSe": se,
                 "hpFlags": hpflag, "featureDiff": fd}
            if kind == "upgrade": p["modelBlind"] = blind_feature
            pairs.append(p)
    # Violations and ranking impact.
    order = {k: sorted(((a, sum(v) / len(v)) for a, v in acts.items()), key=lambda x: x[1])
             for k, acts in siblings.items()}
    def gap_to_neighbour(p):
        sib = order[(p["seed"], p["decision"])]
        if len(sib) < 2: return None
        idx = [i for i, (action, _) in enumerate(sib) if action == p["action"]][0]
        return sib, idx, sib[idx][1]
    summary = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    examples = []
    for p in pairs:
        group = f"{p['kind']}:{p['class']}"
        for est, dv in p["delta"].items():
            if dv is None: continue
            s = summary[group][est]
            s["n"] += 1
            signed = dv * p["sign"]          # > 0: the expected direction
            if abs(dv) <= EPS: s["tie"] += 1
            elif signed < 0:
                s["wrong"] += 1
                s["wrong_mag_sum"] += -signed
                s["wrong_mag_max"] = max(s["wrong_mag_max"], -signed)
                if -signed >= 0.005: s["wrong_ge_0.5pp"] += 1
                if est == "rollout" and p["rolloutSe"] and -signed > 2 * p["rolloutSe"]: s["wrong_material_2se"] += 1
            else:
                s["right"] += 1
            if est in ("leafAnchor", "rollout") and signed < -EPS:
                res = gap_to_neighbour(p)
                if res:
                    sib, idx, val = res
                    newval = val + dv
                    # Flip: the leaf crosses an adjacent sibling.
                    flips = (idx > 0 and newval < sib[idx - 1][1]) or (idx + 1 < len(sib) and newval > sib[idx + 1][1])
                    if flips: s["wrong_flips_sibling_order"] += 1
                    if est == "rollout" and flips and p["rolloutSe"] and -signed > 2 * p["rolloutSe"]:
                        examples.append(p)
        if p["kind"] == "upgrade" and p.get("modelBlind"): summary[group]["x2b"]["model_blind"] += 1
    by_upgrade = defaultdict(lambda: defaultdict(float))
    for p in pairs:
        if p["kind"] != "upgrade": continue
        b = by_upgrade[p["label"]]
        b["n"] += 1
        for est in ("leafAnchor", "rollout"):
            dv = p["delta"].get(est)
            if dv is None: continue
            b[est + "_sum"] += dv
            if dv < -EPS: b[est + "_wrong"] += 1
            if abs(dv) <= EPS: b[est + "_tie"] += 1
    for b in by_upgrade.values():
        for est in ("leafAnchor", "rollout"):
            if b["n"]: b[est + "_mean"] = b.pop(est + "_sum", 0.0) / b["n"]
    hp_curve = defaultdict(lambda: defaultdict(list))
    for p in pairs:
        if p["kind"] == "hp":
            for est, dv in p["delta"].items():
                if dv is not None: hp_curve[p["label"]][est].append(dv)
    hp_mean = {k: {est: sum(v) / len(v) for est, v in d.items()} for k, d in hp_curve.items()}
    out = {"checks": dict(checks), "leaves": len(leaves), "pairs": len(pairs), "roots": len(siblings),
           "summary": {g: {e: dict(v) for e, v in d.items()} for g, d in summary.items()},
           "hpMeanDelta": hp_mean, "byUpgrade": {k: dict(v) for k, v in sorted(by_upgrade.items())},
           "materialFlipExamples": examples[:40]}
    with open(out_path, "w") as f: json.dump(out, f, indent=1, sort_keys=True)
    with open(out_path.replace(".json", "") + ".pairs.jsonl", "w") as f:
        for p in pairs: f.write(json.dumps(p) + "\n")
    with open(out_path.replace(".json", "") + ".leaves.jsonl", "w") as f:
        for l in leaves: f.write(json.dumps(l) + "\n")
    print(json.dumps({"checks": out["checks"], "leaves": out["leaves"], "pairs": out["pairs"],
                      "roots": out["roots"]}))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
