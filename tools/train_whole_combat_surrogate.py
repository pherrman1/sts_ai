#!/usr/bin/env python3
"""Train survival and conditional ending-HP XGBoost models from one-row/fight data."""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd

META = {"sourceSeed", "fightIdx", "decisionIdx", "act", "floor", "encounter", "roomClass",
        "teacherId", "won", "endHp", "startHp", "startMaxHp", "endMaxHp", "endHpFrac",
        "startPotionIds", "endPotionIds", "startPotionCount", "endPotionCount", "goldDelta",
        "smokeBombUsed", "changedRelicCounters", "ritualDaggerChanges", "deckStructureChanged",
        "persistentMutationSummary"}

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def split_seeds(values, split_seed=20260831):
    seeds = np.array(sorted(set(values))); rng = np.random.default_rng(split_seed); rng.shuffle(seeds)
    ntest=max(1, round(len(seeds)*.15)); nval=max(1, round(len(seeds)*.15))
    if len(seeds) < 4: raise ValueError("need at least four source seeds for grouped train/validation/test split")
    return set(seeds[ntest+nval:]), set(seeds[ntest:ntest+nval]), set(seeds[:ntest])
def metrics_binary(y,p):
    from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
    out={"logloss":float(log_loss(y,p,labels=[0,1])),"brier":float(brier_score_loss(y,p))}
    out["roc_auc"] = float(roc_auc_score(y,p)) if len(set(y)) == 2 else None
    return out
def calibration(y,p,bins=10):
    out=[]
    for lo in np.linspace(0,1,bins,endpoint=False):
        hi=lo+1/bins; mask=(p>=lo)&((p<hi) if hi<1 else (p<=hi))
        if mask.any(): out.append({"lo":lo,"hi":hi,"n":int(mask.sum()),"pred":float(p[mask].mean()),"observed":float(y[mask].mean())})
    return out
def regression(y,p):
    e=np.asarray(p)-np.asarray(y); return {"mae":float(np.abs(e).mean()),"rmse":float(np.sqrt((e*e).mean()))}
def slice_reports(test, ps, hp, features, minimum):
    import xgboost as xgb
    survival=[]; conditional=[]
    dimensions=[c for c in ("act","roomClass","encounter") if c in test]
    for column in dimensions:
        for value, group in test.groupby(column):
            if len(group) >= minimum:
                idx=test.index.get_indexer(group.index)
                survival.append({"dimension":column,"value":str(value),"n":len(group),**metrics_binary(group.won.to_numpy(),ps[idx])})
            winners=group[group.won.eq(1)]
            if len(winners) >= minimum:
                pred=hp.predict(xgb.DMatrix(winners[features])); m=regression(winners.endHpFrac.to_numpy(),pred)
                m["absolute_hp_mae"]=float(np.abs((pred-winners.endHpFrac.to_numpy())*winners.startMaxHp.to_numpy()).mean())
                conditional.append({"dimension":column,"value":str(value),"n":len(winners),**m})
    return {"minimum_population":minimum,"survival":survival,"conditional_hp":conditional}

def train(args):
    import xgboost as xgb
    from ooc_pipeline_contract import validate_manifest
    manifest=json.loads(Path(args.data_manifest).read_text()); validate_manifest(manifest)
    df=pd.read_csv(manifest["csv"]["path"])
    required={"sourceSeed","won","endHp","startMaxHp","endHpFrac","teacherId"}
    if missing:=sorted(required-set(df.columns)): raise ValueError("corpus missing required columns: "+", ".join(missing))
    if set(df.teacherId) != {manifest["combat_teacher"]["teacher_id"]}: raise ValueError("row teacherId disagrees with manifest")
    features=[c for c in df.columns if c not in META and pd.api.types.is_numeric_dtype(df[c])]
    train_s,val_s,test_s=split_seeds(df.sourceSeed,args.split_seed)
    sets={"train":df.sourceSeed.isin(train_s),"validation":df.sourceSeed.isin(val_s),"test":df.sourceSeed.isin(test_s)}
    variance=df.loc[sets["train"],features].var(); features=[c for c in features if variance[c]>1e-12]
    if not features: raise ValueError("no nonconstant numeric features in TRAIN")
    params={"max_depth":args.max_depth,"eta":args.eta,"subsample":.8,"colsample_bytree":.8,"seed":args.split_seed,"nthread":args.threads}
    surv=xgb.train({**params,"objective":"binary:logistic","eval_metric":"logloss"},xgb.DMatrix(df.loc[sets["train"],features],label=df.loc[sets["train"],"won"]),num_boost_round=args.rounds)
    win_train=sets["train"]&(df.won==1)
    hp=xgb.train({**params,"objective":"reg:squarederror","eval_metric":"rmse"},xgb.DMatrix(df.loc[win_train,features],label=df.loc[win_train,"endHpFrac"]),num_boost_round=args.rounds)
    test=df.loc[sets["test"]]; y=test.won.to_numpy(); ps=surv.predict(xgb.DMatrix(test[features])); base=np.full(len(y),df.loc[sets["train"],"won"].mean())
    wt=test.won.eq(1); hp_y=test.loc[wt,"endHpFrac"].to_numpy(); hp_p=hp.predict(xgb.DMatrix(test.loc[wt,features])); hp_base=np.full(len(hp_y),df.loc[win_train,"endHpFrac"].mean())
    start=time.perf_counter()
    for _ in range(args.timing_repeats): surv.predict(xgb.DMatrix(test.iloc[:1][features]))
    batch1_ms=(time.perf_counter()-start)*1000/args.timing_repeats
    report={"counts":{"fights":len(df),"wins":int(df.won.sum()),"losses":int((1-df.won).sum()),"base_rate":float(df.won.mean())},
      "split":{"key":"sourceSeed","seed":args.split_seed,"train_seeds":sorted(map(int,train_s)),"validation_seeds":sorted(map(int,val_s)),"test_seeds":sorted(map(int,test_s))},
      "survival":{"model":metrics_binary(y,ps),"constant_baseline":metrics_binary(y,base),"calibration":calibration(y,ps)},
      "conditional_hp":{"model":regression(hp_y,hp_p),"conditional_mean_baseline":regression(hp_y,hp_base),"absolute_hp_mae":float(np.abs((hp_p-hp_y)*test.loc[wt,"startMaxHp"].to_numpy()).mean())},
      "slices":slice_reports(test,ps,hp,features,args.minimum_slice),
      "batch1_inference_ms":batch1_ms,"feature_contract":{"source":"canonical battle-start rich combat features","count":len(features),"names":features,"variance_filter":"fit on TRAIN only"},
      "training_parameters":params|{"rounds":args.rounds},"data_sha256":digest(manifest["csv"]["path"]),"teacher_id":manifest["combat_teacher"]["teacher_id"]}
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True); surv.save_model(out/"survival.json"); hp.save_model(out/"conditional_hp.json")
    (out/"manifest.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2))

def main():
    p=argparse.ArgumentParser(); p.add_argument("data_manifest"); p.add_argument("output"); p.add_argument("--split-seed",type=int,default=20260831)
    p.add_argument("--rounds",type=int,default=300); p.add_argument("--max-depth",type=int,default=6); p.add_argument("--eta",type=float,default=.05); p.add_argument("--threads",type=int,default=1); p.add_argument("--timing-repeats",type=int,default=100)
    p.add_argument("--minimum-slice",type=int,default=20)
    train(p.parse_args())
if __name__=="__main__": main()
