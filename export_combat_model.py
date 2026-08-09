#!/usr/bin/env python3
"""Export the trained V_combat XGBoost model to a compact flat text format that
the C++ CombatValueNet evaluator reads, plus a validation CSV (canonical feature
vectors + this model's predictions) so the C++ eval can be checked to match.

Usage: export_combat_model.py [model.json] [out_trees.txt] [train.csv] [val.csv]
       export_combat_model.py --per-encounter <dir>   # convert <dir>/<NAME>.json -> <NAME>.txt
"""
import sys, json, numpy as np, pandas as pd, xgboost as xgb

# MonsterEncounter enum names accepted by the C++ loader (must match
# monsterEncounterEnumNames in include/constants/MonsterEncounters.h). Only
# files whose base name is in this list are exported by --per-encounter.
_ENUM_NAMES = {"INVALID","CULTIST","JAW_WORM","TWO_LOUSE","SMALL_SLIMES",
"BLUE_SLAVER","GREMLIN_GANG","LOOTER","LARGE_SLIME","LOTS_OF_SLIMES",
"EXORDIUM_THUGS","EXORDIUM_WILDLIFE","RED_SLAVER","THREE_LOUSE",
"TWO_FUNGI_BEASTS","GREMLIN_NOB","LAGAVULIN","THREE_SENTRIES","SLIME_BOSS",
"THE_GUARDIAN","HEXAGHOST","SPHERIC_GUARDIAN","CHOSEN","SHELL_PARASITE",
"THREE_BYRDS","TWO_THIEVES","CHOSEN_AND_BYRDS","SENTRY_AND_SPHERE",
"SNAKE_PLANT","SNECKO","CENTURION_AND_HEALER","CULTIST_AND_CHOSEN",
"THREE_CULTIST","SHELLED_PARASITE_AND_FUNGI","GREMLIN_LEADER","SLAVERS",
"BOOK_OF_STABBING","AUTOMATON","COLLECTOR","CHAMP","THREE_DARKLINGS",
"ORB_WALKER","THREE_SHAPES","SPIRE_GROWTH","TRANSIENT","FOUR_SHAPES","MAW",
"SPHERE_AND_TWO_SHAPES","JAW_WORM_HORDE","WRITHING_MASS","GIANT_HEAD",
"NEMESIS","REPTOMANCER","AWAKENED_ONE","TIME_EATER","DONU_AND_DECA",
"SHIELD_AND_SPEAR","THE_HEART","LAGAVULIN_EVENT","COLOSSEUM_EVENT_SLAVERS",
"COLOSSEUM_EVENT_NOBS","MASKED_BANDITS_EVENT","MUSHROOMS_EVENT",
"MYSTERIOUS_SPHERE_EVENT"}

def flatten(tree):
    """xgboost json tree -> (nodes list in compact index order, root_index=0).
    node = ('S', featIdx, thresh, yes_ci, no_ci) or ('L', value)."""
    byid = {}
    def walk(nd):
        byid[nd["nodeid"]] = nd
        for c in nd.get("children", []): walk(c)
    walk(tree)
    ids = sorted(byid)                      # nodeid 0 (root) sorts first
    ci = {nid: i for i, nid in enumerate(ids)}
    out = []
    for nid in ids:
        nd = byid[nid]
        if "leaf" in nd:
            out.append(("L", float(nd["leaf"])))
        else:
            out.append(("S", fidx[nd["split"]], float(nd["split_condition"]),
                        ci[nd["yes"]], ci[nd["no"]]))
    return out


def export_trees(model_path, out_path, max_trees=0):
    """Write the compact-tree text for an XGBoost model. max_trees<=0 keeps
    every tree; otherwise the first N (boosting is additive). Returns the
    loaded booster so callers can reuse it for the validation sample."""
    bst = xgb.Booster(); bst.load_model(model_path)
    feats = list(bst.feature_names)
    global fidx
    fidx = {n: i for i, n in enumerate(feats)}
    cfg = json.loads(bst.save_config())
    base_score = float(cfg["learner"]["learner_model_param"]["base_score"].strip("[] "))
    dumps = bst.get_dump(dump_format="json")
    NTREE = len(dumps) if max_trees <= 0 else min(max_trees, len(dumps))
    dumps = dumps[:NTREE]
    print(f"model: {len(feats)} features, keeping {NTREE} trees, base_score={base_score}")

    with open(out_path, "w") as f:
        f.write(f"nfeat {len(feats)}\n")
        for n in feats: f.write(f"feat {n}\n")
        f.write(f"base_score {base_score}\n")
        f.write(f"ntrees {len(dumps)}\n")
        for t, d in enumerate(dumps):
            nodes = flatten(json.loads(d))
            f.write(f"tree {t} {len(nodes)}\n")
            for nd in nodes:
                if nd[0] == "L":
                    f.write(f"L {nd[1]:.7g}\n")
                else:
                    f.write(f"S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n")
    print(f"wrote {out_path}")
    return bst, feats, NTREE, base_score


def write_validation(csv_path, out_val_path, bst, feats, ntrees, nrows=200):
    """Sample nrows rows from the combat CSV and write canonical features +
    pyPred so the C++ evaluator can be checked against Python."""
    _hdr = pd.read_csv(csv_path, nrows=0).columns
    _dt = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
    df = pd.read_csv(csv_path, dtype=_dt, nrows=nrows)
    canon = [c for c in df.columns if c not in ("seed", "fightIdx", "won", "endHp")]
    samp = df.sample(frac=1, random_state=1).reset_index(drop=True)
    Xmodel = samp[feats].to_numpy(np.float32)          # model-ordered features
    pred = bst.predict(xgb.DMatrix(Xmodel, feature_names=feats), iteration_range=(0, ntrees))
    out = samp[canon].copy()
    out["pyPred"] = pred
    out.to_csv(out_val_path, index=False)
    print(f"wrote {out_val_path}: {len(out)} rows, {len(canon)} canonical features "
          f"(pred mean {pred.mean():.2f})")
    print("canonical feature order matches C++ combatFeatureNames():")
    print("  " + ",".join(canon))


def per_encounter_export(directory):
    """Convert <dir>/<ENUM_NAME>.json -> <dir>/<ENUM_NAME>.txt for every JSON
    whose base name is a MonsterEncounter enum name (the C++ loader convention).
    Non-enum files (e.g. _pooled.json) are skipped with a note."""
    import glob, os
    written = 0
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name not in _ENUM_NAMES:
            print(f"skip {os.path.basename(path)} (not a MonsterEncounter enum name)")
            continue
        export_trees(path, os.path.join(directory, name + ".txt"))
        written += 1
    print(f"--per-encounter: wrote {written} compact-tree file(s) in {directory}")
    return written


def main(argv):
    if "--per-encounter" in argv:
        try:
            directory = argv[argv.index("--per-encounter") + 1]
        except IndexError:
            print("--per-encounter requires a directory argument")
            return 2
        return 0 if per_encounter_export(directory) else 1

    MODEL = argv[0] if len(argv) > 0 else "build/v_combat.json"
    OUT   = argv[1] if len(argv) > 1 else "build/v_combat_trees.txt"
    CSV   = argv[2] if len(argv) > 2 else "build/vcombat.csv"
    VAL   = argv[3] if len(argv) > 3 else "build/v_combat_val.csv"
    MAXTREES = int(argv[4]) if len(argv) > 4 else 0   # 0 = all; else keep first N (boosting is additive)
    bst, feats, NTREE, _ = export_trees(MODEL, OUT, MAXTREES)
    write_validation(CSV, VAL, bst, feats, NTREE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
