#!/usr/bin/env python3
"""Phase-1b posterior-valid particle sensitivity probe analysis.

Reads a `one_combat particle_posterior_probe` CSV (rowType 0 = group summary,
rowType 1 = evaluated compatible world) and reports the pre-registered
Phase-1b prevalence metrics. Analysis only — no model training.

Primary quantity: fraction of ALL sampled source groups with continuation
target range > 5 (groups with <2 evaluated compatible states count as
range = 0; ineligible groups — SOURCE_PARTICLE_FALLBACK /
UNREPLAYABLE_ACTION_PREFIX — also count as non-sensitive in the primary
denominator). The eligible-only measurement (groups with >=2 evaluated
unique compatible states) is reported separately.

Range metrics are subsampled lower-bound estimates whenever any group has
evaluatedWorldCount < uniqueCompatibleStates; this is reported explicitly
and capped/uncapped groups are never mixed silently.

Self-test: python3 tools/analyze_particle_posterior_probe.py --self-test
"""
import argparse
import csv
import io
import json
import math
import random
import sys
from collections import defaultdict

RANGE_THRESHOLDS = (1, 5, 10)


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _num(row, key, default=0.0):
    v = row.get(key, "")
    try:
        return float(v) if v not in ("", None) else default
    except ValueError:
        return default


def build_groups(rows):
    """Group key -> {meta(rowType-0 row), worlds(list of rowType-1 rows)}."""
    groups = {}
    for r in rows:
        key = (r["seed"], r["fightIdx"], r["decIdx"], r["sourceLeafId"])
        if r["rowType"] == "0":
            groups.setdefault(key, {"meta": r, "worlds": []})["meta"] = r
        else:
            groups.setdefault(key, {"meta": None, "worlds": []})["worlds"].append(r)
    return groups


def group_range(worlds, field="target"):
    """max(value)-min(value); 0 when fewer than 2 evaluated worlds."""
    targets = [float(w[field]) for w in worlds if w.get(field) not in ("", None, "nan")]
    if len(targets) < 2:
        return 0.0
    return max(targets) - min(targets)


def group_std(worlds, field="target"):
    targets = [float(w[field]) for w in worlds if w.get(field) not in ("", None, "", "nan")]
    if len(targets) < 2:
        return 0.0
    m = sum(targets) / len(targets)
    return math.sqrt(sum((t - m) ** 2 for t in targets) / len(targets))


def validate_group(meta, worlds):
    """No-fake-padding / structure checks. Returns list of violation strings."""
    v = []
    if meta is None:
        return ["missing_group_summary_row"]
    unique = int(_num(meta, "uniqueCompatibleStates"))
    evaluated = int(_num(meta, "evaluatedWorldCount"))
    if evaluated > unique:
        v.append("evaluated_exceeds_unique")
    if len(worlds) != evaluated:
        v.append("world_row_count_mismatch")
    ordinals = [w.get("dedupOrdinal") for w in worlds]
    if len(set(ordinals)) != len(ordinals):
        v.append("duplicate_dedup_ordinal")
    if int(_num(meta, "groupEligible")) == 1 and int(_num(meta, "sourceParticleReplayOk")) == 1:
        if sum(1 for w in worlds if _num(w, "candidateIsSource") == 1) < 1:
            v.append("source_world_missing_or_duplicated")
    for w in worlds:
        if w.get("invariantOk") == "0":
            v.append("world_invariant_violation")
    return v


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def weighted_mean(pairs):
    tw = sum(w for _, w in pairs)
    return (sum(x * w for x, w in pairs) / tw) if tw > 0 else float("nan")


def seed_bootstrap(seed_values, stat_fn, iters, rng_seed=12345):
    """seed_values: {seed: [per-group values]}. stat_fn flattens and reduces."""
    seeds = sorted(seed_values)
    stats = []
    rng = random.Random(rng_seed)
    for _ in range(iters):
        sample = [rng.choice(seeds) for _ in seeds]
        flat = [v for s in sample for v in seed_values[s]]
        stats.append(stat_fn(flat))
    stats.sort()
    lo = stats[int(0.025 * len(stats))]
    hi = stats[min(len(stats) - 1, int(0.975 * len(stats)))]
    return lo, hi


def paired_bootstrap(seed_values, iters, rng_seed=12345):
    """Bootstrap paired per-seed values; seed_values maps seed -> (early, late)."""
    seeds = sorted(seed_values)
    rng = random.Random(rng_seed)
    means = []
    fracs = []
    for _ in range(iters):
        sample = [rng.choice(seeds) for _ in seeds]
        deltas = [seed_values[s][1][0] - seed_values[s][0][0] for s in sample]
        frac_deltas = [seed_values[s][1][1] - seed_values[s][0][1] for s in sample]
        means.append(mean(deltas))
        fracs.append(mean(frac_deltas))
    means.sort(); fracs.sort()
    lo = int(0.025 * len(means)); hi = min(len(means) - 1, int(0.975 * len(means)))
    return {"delta_mean_range": (mean(means), (means[lo], means[hi])),
            "delta_frac_gt5": (mean(fracs), (fracs[lo], fracs[hi])),
            "paired_seeds": len(seeds), "iters": iters}


def analyze(rows, bootstrap_iters=10000):
    groups = build_groups(rows)
    all_groups = []          # (seed, meta, worlds) for every sampled group
    for key, g in groups.items():
        all_groups.append((key[0], g["meta"], g["worlds"]))

    failures = defaultdict(int)
    for _, meta, _ in all_groups:
        if meta is not None and meta.get("replayFailure") not in ("", "-", None):
            failures[meta["replayFailure"]] += 1

    violations = defaultdict(int)
    for _, meta, worlds in all_groups:
        for v in validate_group(meta, worlds):
            violations[v] += 1

    eligible = [(s, m, w) for s, m, w in all_groups
                if m is not None and int(_num(m, "groupEligible")) == 1]
    aborted = [(s, m, w) for s, m, w in all_groups
               if m is not None and int(_num(m, "invariantOk")) == 0]
    ineligible = [(s, m, w) for s, m, w in all_groups
                  if m is not None and int(_num(m, "groupEligible")) == 0]
    multi = [(s, m, w) for s, m, w in eligible
             if int(_num(m, "evaluatedWorldCount")) >= 2]

    def prevalences(subset, field="target"):
        ranges = [group_range(w, field) for _, _, w in subset]
        n = len(ranges)
        out = {"groups": n,
               "frac_range_eq0": (sum(1 for r in ranges if r == 0) / n) if n else float("nan")}
        for t in RANGE_THRESHOLDS:
            out[f"frac_range_gt{t}"] = (sum(1 for r in ranges if r > t) / n) if n else float("nan")
        out["mean_range"] = mean(ranges)
        out["median_range"] = median(ranges)
        return out

    def mass_stats(subset, field="target"):
        range_pairs = [(group_range(w, field), _num(m, "compatibleMass")) for _, m, w in subset]
        std_pairs = [(group_std(w, field), _num(m, "compatibleMass")) for _, m, w in subset]
        return {
            "mass_weighted_mean_range": weighted_mean(range_pairs),
            "mass_weighted_mean_std": weighted_mean(std_pairs),
            "median_range": median([p[0] for p in range_pairs]),
            "median_std": median([p[0] for p in std_pairs]),
            "mean_compatible_mass": mean([p[1] for p in range_pairs]),
            "mean_evaluated_mass": mean([_num(m, "evaluatedMass") for _, m, _ in subset]),
        }

    capped = sum(1 for _, m, _ in eligible
                 if m is not None
                 and int(_num(m, "invariantOk")) == 1
                 and int(_num(m, "evaluatedWorldCount")) < int(_num(m, "uniqueCompatibleStates")))

    seed_ranges = defaultdict(list)
    controlled_seed_ranges = defaultdict(list)
    for s, m, w in all_groups:
        seed_ranges[s].append(group_range(w))
        controlled_seed_ranges[s].append(group_range(w, "controlledTarget"))

    frac_gt5_ci = seed_bootstrap(
        seed_ranges,
        lambda rs: (sum(1 for r in rs if r > 5) / len(rs)) if rs else float("nan"),
        bootstrap_iters)
    mean_range_ci = seed_bootstrap(seed_ranges, lambda rs: mean(rs), bootstrap_iters)
    controlled_frac_gt5_ci = seed_bootstrap(
        controlled_seed_ranges,
        lambda rs: (sum(1 for r in rs if r > 5) / len(rs)) if rs else float("nan"),
        bootstrap_iters)
    controlled_mean_range_ci = seed_bootstrap(
        controlled_seed_ranges, lambda rs: mean(rs), bootstrap_iters)

    per_seed = {}
    for s in sorted(seed_ranges):
        rs = seed_ranges[s]
        per_seed[s] = {"groups": len(rs),
                       "frac_range_gt5": sum(1 for r in rs if r > 5) / len(rs),
                       "mean_range": mean(rs),
                       "controlled_frac_range_gt5": sum(1 for r in controlled_seed_ranges[s] if r > 5) / len(rs),
                       "controlled_mean_range": mean(controlled_seed_ranges[s])}

    def stratify(field, subset, key_fn):
        buckets = defaultdict(list)
        for _, m, w in subset:
            if m is None:
                continue
            try:
                buckets[key_fn(m.get(field, ""))].append(group_range(w))
            except (ValueError, TypeError):
                continue
        return {str(k): {"groups": len(v), "mean_range": mean(v),
                         "frac_range_gt5": sum(1 for r in v if r > 5) / len(v)}
                for k, v in sorted(buckets.items(), key=lambda kv: str(kv[0]))}

    def draw_bin(n):
        n = int(n)
        return "0" if n == 0 else ("1-5" if n <= 5 else ("6-10" if n <= 10 else ("11-15" if n <= 15 else "16+")))

    def depth_bin(n):
        n = int(n)
        return "0-5" if n <= 5 else ("6-10" if n <= 10 else ("11-20" if n <= 20 else "21+"))

    def stratum_summary(subset):
        ranges = prevalences(subset, "controlledTarget")
        ranges["mass_stats"] = mass_stats(subset, "controlledTarget")
        if not subset:
            ranges["seed_bootstrap"] = {"frac_range_gt5_ci95": (float("nan"), float("nan")),
                                         "mean_range_ci95": (float("nan"), float("nan")),
                                         "iters": bootstrap_iters}
            return ranges
        seed_values = defaultdict(list)
        for s, _, worlds in subset:
            seed_values[s].append(group_range(worlds, "controlledTarget"))
        ranges["seed_bootstrap"] = {
            "frac_range_gt5_ci95": seed_bootstrap(
                seed_values, lambda xs: (sum(x > 5 for x in xs) / len(xs)) if xs else float("nan"), bootstrap_iters),
            "mean_range_ci95": seed_bootstrap(seed_values, mean, bootstrap_iters),
            "iters": bootstrap_iters,
        }
        return ranges

    def composition(subset):
        metas_local = [m for _, m, _ in subset if m is not None]
        def vals(name): return [_num(m, name) for m in metas_local]
        draw = vals("drawPileSize")
        compat = vals("uniqueCompatibleStates")
        return {
            "treeDepth": {"mean": mean(vals("treeDepth")), "median": median(vals("treeDepth"))},
            "turn": {"mean": mean(vals("turn")), "median": median(vals("turn"))},
            "drawPileSize": {"mean": mean(draw), "median": median(draw),
                              "distribution": {str(int(k)): draw.count(k) for k in sorted(set(draw))}},
            "compatibleParticles": {"mean": mean(vals("replayCompatibleParticles")),
                                     "median": median(vals("replayCompatibleParticles"))},
            "fraction_groups_ge2": sum(x >= 2 for x in compat) / len(compat) if compat else float("nan"),
            "fraction_groups_ge4": sum(x >= 4 for x in compat) / len(compat) if compat else float("nan"),
            "fraction_groups_ge8": sum(x >= 8 for x in compat) / len(compat) if compat else float("nan"),
            "mean_compatible_mass": mean(vals("compatibleMass")),
        }

    strata = {}
    for name in ("EARLY", "LATE"):
        subset = [(s, m, w) for s, m, w in all_groups
                  if m is not None and m.get("ageStratum") == name]
        strata[name] = {"controlledTarget": stratum_summary(subset),
                        "fullParticleTarget": prevalences(subset, "target"),
                        "composition": composition(subset),
                        "groups": len(subset)}

    paired = {}
    early = {s: [] for s, _, _ in all_groups}
    late = {s: [] for s, _, _ in all_groups}
    for s, m, w in all_groups:
        if m is None: continue
        target = early if m.get("ageStratum") == "EARLY" else late if m.get("ageStratum") == "LATE" else None
        if target is not None: target[s].append(group_range(w, "controlledTarget"))
    paired_values = {}
    for s in sorted(set(early) & set(late)):
        if early[s] and late[s]:
            e = (mean(early[s]), sum(x > 5 for x in early[s]) / len(early[s]))
            l = (mean(late[s]), sum(x > 5 for x in late[s]) / len(late[s]))
            paired_values[s] = (e, l)
    if paired_values:
        paired = paired_bootstrap(paired_values, bootstrap_iters, rng_seed=67890)
        paired["per_seed"] = {s: {"early_mean_range": v[0][0], "late_mean_range": v[1][0],
                                  "early_frac_gt5": v[0][1], "late_frac_gt5": v[1][1],
                                  "delta_mean_range": v[1][0] - v[0][0],
                                  "delta_frac_gt5": v[1][1] - v[0][1]}
                               for s, v in paired_values.items()}

    expected_bins = set(range(16))
    coverage = {}
    for name in ("EARLY", "LATE"):
        by_seed = defaultdict(list)
        for s, m, _ in all_groups:
            if m is not None and m.get("ageStratum") == name:
                by_seed[s].append(int(_num(m, "ageBin")))
        duplicates = sum(len(bins) - len(set(bins)) for bins in by_seed.values())
        missing = {s: sorted(expected_bins - set(bins)) for s, bins in by_seed.items() if set(bins) != expected_bins}
        ages = [_num(m, "searchSimulation") for _, m, _ in all_groups
                if m is not None and m.get("ageStratum") == name]
        coverage[name] = {"groups": len(ages), "bins_per_seed": {s: len(v) for s, v in by_seed.items()},
                          "missing_bins": missing, "duplicate_bins": duplicates,
                          "min_searchSimulation": min(ages) if ages else None,
                          "max_searchSimulation": max(ages) if ages else None}

    metas = [m for _, m, _ in all_groups if m is not None]
    n_all = len(all_groups)
    return {
        "all_groups": prevalences(all_groups),
        "primary_controlled_draw_order": prevalences(all_groups, "controlledTarget"),
        "secondary_full_particle": prevalences(all_groups, "target"),
        "eligible_groups": prevalences(eligible),
        "multi_state_groups": prevalences(multi),
        "mass_stats_all": mass_stats(all_groups),
        "mass_stats_multi": mass_stats(multi),
        "controlled_mass_stats_all": mass_stats(all_groups, "controlledTarget"),
        "source_replay_failures": sum(1 for m in metas if _num(m, "sourceParticleReplayOk") == 0),
        "invariant_failures": sum(1 for m in metas if _num(m, "invariantOk") == 0),
        "replay_failure_categories": dict(failures),
        "structure_violations": dict(violations),
        "unique_compatible_state_distribution": {
            "mean": mean([_num(m, "uniqueCompatibleStates") for m in metas]),
            "median": median([_num(m, "uniqueCompatibleStates") for m in metas]),
            "frac_groups_ge2_states": (sum(1 for m in metas if _num(m, "uniqueCompatibleStates") >= 2) / n_all) if n_all else float("nan"),
            "frac_groups_ge4_states": (sum(1 for m in metas if _num(m, "uniqueCompatibleStates") >= 4) / n_all) if n_all else float("nan"),
            "frac_groups_ge8_states": (sum(1 for m in metas if _num(m, "uniqueCompatibleStates") >= 8) / n_all) if n_all else float("nan"),
        },
        "compatible_particle_distribution": {
            "mean": mean([_num(m, "replayCompatibleParticles") for m in metas]),
            "median": median([_num(m, "replayCompatibleParticles") for m in metas]),
        },
        "groups_with_capped_evaluation": capped,
        "groups_aborted_by_invariant": len(aborted),
        "groups_ineligible": len(ineligible),
        "range_metrics_are_subsampled": capped > 0,
        "seed_bootstrap": {"frac_range_gt5_ci95": frac_gt5_ci,
                           "mean_range_ci95": mean_range_ci,
                           "controlled_frac_range_gt5_ci95": controlled_frac_gt5_ci,
                           "controlled_mean_range_ci95": controlled_mean_range_ci,
                           "iters": bootstrap_iters},
        "per_seed": per_seed,
        "strata_descriptive": {
            "by_turn": stratify("turn", all_groups, int),
            "by_draw_pile_bin": stratify("drawPileSize", all_groups, draw_bin),
            "by_depth_bin": stratify("treeDepth", all_groups, depth_bin),
            "by_encounter": stratify("encounterName", all_groups, str),
        },
        "age_strata": strata,
        "paired_search_age": paired,
        "coverage": coverage,
        "validity": {
            "source_replay_failures": sum(1 for m in metas if _num(m, "sourceParticleReplayOk") == 0),
            "invariant_failures": sum(1 for m in metas if _num(m, "invariantOk") == 0),
            "replay_explosions": sum(_num(m, "replayExplosion") for m in metas),
            "mass_violations": 0,
            "structure_violations": dict(violations),
            "complete_age_coverage": all(not x["missing_bins"] and x["duplicate_bins"] == 0 for x in coverage.values()) if coverage else False,
            "first_fight_decision_only": all(_num(m, "fightIdx") == 0 and _num(m, "decIdx") == 0 for m in metas),
        },
        "late_practical_gate": {
            "fraction_gt5": strata.get("LATE", {}).get("controlledTarget", {}).get("frac_range_gt5"),
            "fraction_gt5_seed_bootstrap_lower95": (strata.get("LATE", {}).get("controlledTarget", {})
                                                     .get("seed_bootstrap", {}).get("frac_range_gt5_ci95", (float("nan"), float("nan")))[0]),
            "equal_group_mean_range": strata.get("LATE", {}).get("controlledTarget", {}).get("mean_range"),
            "pass": bool(strata.get("LATE", {}).get("controlledTarget", {}).get("frac_range_gt5", 0) >= 0.10
                         and strata.get("LATE", {}).get("controlledTarget", {}).get("seed_bootstrap", {})
                             .get("frac_range_gt5_ci95", (0, 0))[0] > 0.05
                         and strata.get("LATE", {}).get("controlledTarget", {}).get("mean_range", 0) >= 3),
        },
        "seeds": len({s for s, _, _ in all_groups}),
        "groups_total": n_all,
    }


GROUP_FIELDS = ("rowType,seed,fightIdx,decIdx,sourceLeafId,obsHash,treeDepth,encounterName,turn,"
                "curHp,maxHp,drawPileSize,rootParticleCount,positiveParticleCount,replayAttempted,"
                "replayCompatibleParticles,uniqueCompatibleStates,compatibleMass,evaluatedWorldCount,"
                "evaluatedMass,sourceParticleIndex,sourceParticleReplayOk,sourceParticleFallback,"
                "groupEligible,invariantOk,replayFailure,semanticReplayFailures,actionIllegalFailures,"
                "intermediateObservationMismatches,intermediateOutcomeMismatches,finalObservationMismatches,"
                "drawPileMismatches,rootCarried,reuseGeneration,reuseSearchCount,searchSimulation,ageStratum,ageBin,candidateParticleIndex,"
                "candidateWeight,candidateIsSource,dedupOrdinal,semanticBranchesCreated,extraSemanticBranches,maxSurvivingBranches,"
                "branchesCollapsed,replayExplosion,rngSignature,drawOrder,terminal,target,"
                "fullTarget,controlledTarget,controlledTargetStd,rolloutSteps")


def _to_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=GROUP_FIELDS.split(","), restval="0")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return list(csv.DictReader(io.StringIO(out.getvalue())))


def _g(seed, lid, uniq, comp_mass, evald, failure="-", eligible=1, replay_ok=1):
    return dict(rowType="0", seed=str(seed), sourceLeafId=str(lid),
                uniqueCompatibleStates=str(uniq), compatibleMass=str(comp_mass),
                evaluatedWorldCount=str(evald), evaluatedMass=str(comp_mass),
                groupEligible=str(eligible), invariantOk="1", replayFailure=failure,
                sourceParticleReplayOk=str(replay_ok), turn="3", treeDepth="6",
                drawPileSize="9", encounterName="JAW_WORM", replayCompatibleParticles="2")


def _w(seed, lid, target, is_src, ordinal, weight, controlled=None):
    if controlled is None:
        controlled = target
    return dict(rowType="1", seed=str(seed), sourceLeafId=str(lid),
                target=str(target), candidateIsSource=str(is_src), dedupOrdinal=str(ordinal),
                candidateWeight=str(weight), invariantOk="1", groupEligible="1",
                sourceParticleReplayOk="1", uniqueCompatibleStates="2",
                evaluatedWorldCount="2", compatibleMass="1.0",
                fullTarget=str(target), controlledTarget=str(controlled),
                controlledTargetStd="0.0")


def _self_test():
    # seed 0: two worlds, full range 8 but controlled range 0. seed 1: single-state group
    # (range 0) + one fallback-ineligible group (non-sensitive in primary).
    rows = [
        _g(0, 1, 2, 0.6, 2), _w(0, 1, 0.5, 1, 0, 0.3, controlled=1.0), _w(0, 1, 8.5, 0, 1, 0.3, controlled=1.0),
        _g(1, 1, 1, 0.2, 1), _w(1, 1, 0.5, 1, 0, 0.2),
        _g(1, 2, 0, 0.0, 0, failure="SOURCE_PARTICLE_FALLBACK", eligible=0, replay_ok=-1),
    ]
    res = analyze(_to_csv(rows), bootstrap_iters=200)

    # Primary all-group prevalence: 3 groups, 1 with range > 5 -> 1/3.
    assert res["all_groups"]["groups"] == 3
    assert abs(res["all_groups"]["frac_range_gt5"] - 1 / 3) < 1e-9
    assert res["secondary_full_particle"]["frac_range_gt5"] == 1 / 3
    assert res["primary_controlled_draw_order"]["frac_range_gt5"] == 0.0
    assert res["primary_controlled_draw_order"]["mean_range"] == 0.0
    # <2-state and ineligible groups count as range 0 in the primary fraction.
    assert abs(res["all_groups"]["frac_range_eq0"] - 2 / 3) < 1e-9
    # Multi-state-only measurement restricts to >= 2 evaluated states.
    assert res["multi_state_groups"]["groups"] == 1
    assert abs(res["multi_state_groups"]["frac_range_gt5"] - 1.0) < 1e-9
    # Mass metrics use the GROUP-level compatibleMass (0.6/0.2/0.0), not the
    # sum of surviving world weights — duplicate particle mass is aggregated.
    expected = (8.0 * 0.6 + 0.0 * 0.2 + 0.0 * 0.0) / 0.8
    assert abs(res["mass_stats_all"]["mass_weighted_mean_range"] - expected) < 1e-9
    # Fallback groups land in their failure category, NOT replay failures.
    assert res["replay_failure_categories"].get("SOURCE_PARTICLE_FALLBACK") == 1
    assert res["source_replay_failures"] == 0
    # Structure validation: no padding, source world present exactly once.
    assert res["structure_violations"] == {}, res["structure_violations"]
    assert res["groups_with_capped_evaluation"] == 0
    assert res["groups_aborted_by_invariant"] == 0
    assert res["groups_ineligible"] == 1
    assert res["range_metrics_are_subsampled"] is False
    # Seed bootstrap grouping: seeds present and CI well-formed.
    assert set(res["per_seed"]) == {"0", "1"}
    lo, hi = res["seed_bootstrap"]["frac_range_gt5_ci95"]
    assert 0.0 <= lo <= hi <= 1.0

    # Capped group: unique=4 evaluated=2 -> flagged subsampled lower bound.
    rows2 = [_g(0, 1, 4, 1.0, 2), _w(0, 1, 0.5, 1, 0, 0.6), _w(0, 1, 0.7, 0, 1, 0.4)]
    res2 = analyze(_to_csv(rows2), bootstrap_iters=50)
    assert res2["groups_with_capped_evaluation"] == 1
    assert res2["range_metrics_are_subsampled"] is True

    # An invariant-aborted group with positive support is not K-capped.
    aborted = _g(0, 2, 4, 1.0, 0, replay_ok=0)
    aborted["invariantOk"] = "0"
    aborted["replayFailure"] = "SOURCE_PARTICLE_REPLAY_FAILED"
    res_aborted = analyze(_to_csv([aborted]), bootstrap_iters=50)
    assert res_aborted["groups_with_capped_evaluation"] == 0
    assert res_aborted["groups_aborted_by_invariant"] == 1

    # Fake padding is caught (duplicate dedupOrdinal + row-count mismatch).
    rows3 = [_g(0, 1, 2, 1.0, 2), _w(0, 1, 0.5, 1, 0, 0.5), _w(0, 1, 0.6, 0, 1, 0.5),
             _w(0, 1, 0.7, 0, 1, 0.5)]
    res3 = analyze(_to_csv(rows3), bootstrap_iters=50)
    assert res3["structure_violations"], "fake padding not detected"

    print("analyze_particle_posterior_probe self-test: PASS")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?", help="particle_posterior_probe CSV")
    ap.add_argument("--json", action="store_true", help="emit JSON (default)")
    ap.add_argument("--bootstrap-iters", type=int, default=10000)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if not args.csv:
        ap.error("csv path required (or --self-test)")
    print(json.dumps(analyze(load_rows(args.csv), bootstrap_iters=args.bootstrap_iters),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
