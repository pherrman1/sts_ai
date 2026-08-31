#!/usr/bin/env python3
"""Evaluate the frozen Phase-1 combat surrogate on OOC counterfactual siblings."""
import argparse, hashlib, json, math
from pathlib import Path

import numpy as np
import pandas as pd

SURVIVAL_SHA="3a20e1f1df1821f0ff950a85c1d5d87a39cdcf7513cfaa4243b00a4069e5f361"
HP_SHA="a13b11f1b493033db77da5ee68f74e854cd1752cab2c5bc55c1f5f6c7dbca5f0"
MANIFEST_SHA="5c545721d8f36b0062b91b60a83cd1405231f22e66f3b10726bcc5d5a95bafa9"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()

def scores(y,p):
    from sklearn.metrics import log_loss, roc_auc_score
    p=np.clip(np.asarray(p,dtype=float),1e-7,1-1e-7); y=np.asarray(y,dtype=int)
    base=float(y.mean()) if len(y) else math.nan
    result={"n":len(y),"wins":int(y.sum()),"losses":int(len(y)-y.sum()),"base_rate":base,
            "logloss":float(log_loss(y,p,labels=[0,1])),"brier":float(np.mean((p-y)**2)),
            "constant_logloss":float(log_loss(y,np.full(len(y),base),labels=[0,1])) if len(y) else None,
            "constant_brier":float(np.mean((base-y)**2)) if len(y) else None,
            "roc_auc":float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None}
    result["calibration"]=[]
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<(lo+.1) if lo<.9 else p<=1)
        if mask.any(): result["calibration"].append({"lo":float(lo),"hi":float(lo+.1),"n":int(mask.sum()),"pred":float(p[mask].mean()),"observed":float(y[mask].mean())})
    return result

def hp_scores(df,p):
    wins=df.won.astype(bool).to_numpy(); y=df.loc[wins,"endHpFrac"].to_numpy(float); pred=np.asarray(p)[wins]
    maxhp=df.loc[wins,"startMaxHp"].to_numpy(float); mean=float(y.mean()) if len(y) else math.nan
    return {"n":len(y),"mae":float(np.mean(np.abs(pred-y))) if len(y) else None,
            "rmse":float(np.sqrt(np.mean((pred-y)**2))) if len(y) else None,
            "absolute_hp_mae":float(np.mean(np.abs(pred-y)*maxhp)) if len(y) else None,
            "conditional_mean":mean,"baseline_mae":float(np.mean(np.abs(mean-y))) if len(y) else None,
            "baseline_rmse":float(np.sqrt(np.mean((mean-y)**2))) if len(y) else None}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("csv");ap.add_argument("survival_model");ap.add_argument("hp_model");ap.add_argument("training_manifest");ap.add_argument("output");ap.add_argument("--teacher-id",required=True);a=ap.parse_args()
    for path,expected in [(a.survival_model,SURVIVAL_SHA),(a.hp_model,HP_SHA),(a.training_manifest,MANIFEST_SHA)]:
        actual=sha256(path)
        if actual!=expected: raise SystemExit(f"frozen artifact hash mismatch: {path}: {actual}")
    from tools.verify.vnettest_selftest import canonical_names
    raw_header=Path(a.csv).read_text(encoding="utf-8").splitlines()[0].split(",")
    prefix=["sourceSeed","decisionIdx","actionIdx","actionBits","action","chosen","screen","decisionAct","decisionFloor","battleAct","battleFloor","battleEncounter","roomClass","teacherId","valid","quarantineReason"]
    suffix=["won","endHp","startHp","startMaxHp","endMaxHp","endHpFrac"]
    if raw_header[:len(prefix)]!=prefix or raw_header[len(prefix):-len(suffix)]!=canonical_names() or raw_header[-len(suffix):]!=suffix:
        raise SystemExit("counterfactual audit schema/canonical feature mismatch")
    df=pd.read_csv(a.csv); valid=df[df.valid==1].copy()
    if set(valid.teacherId)!={a.teacher_id}: raise SystemExit("teacher mismatch")
    if valid[["sourceSeed","decisionIdx","actionIdx"]].duplicated().any(): raise SystemExit("duplicate branch key")
    grouped=valid.groupby(["sourceSeed","decisionIdx"])
    if not all(g.chosen.sum()==1 for _,g in grouped): raise SystemExit("each valid decision must have exactly one chosen sibling")
    features=canonical_names()
    if not np.isfinite(valid[features].to_numpy(float)).all(): raise SystemExit("non-finite canonical feature")
    import xgboost as xgb
    tm=json.loads(Path(a.training_manifest).read_text()); retained=tm["feature_contract"]["names"]
    feature_source={name:("encounter" if name=="encounter.1" else name) for name in retained}
    if not set(feature_source.values()).issubset(features): raise SystemExit("frozen model feature contract absent from audit")
    survival=xgb.Booster();survival.load_model(a.survival_model);hp=xgb.Booster();hp.load_model(a.hp_model)
    model_input=pd.DataFrame({name:valid[source].to_numpy() for name,source in feature_source.items()})
    matrix=xgb.DMatrix(model_input,feature_names=retained); ps=survival.predict(matrix); ph=hp.predict(matrix)
    valid["predSurvival"]=ps;valid["predEndHpFracGivenWin"]=ph
    report={"artifact_hashes":{"csv":sha256(a.csv),"survival":SURVIVAL_SHA,"conditional_hp":HP_SHA,"training_manifest":MANIFEST_SHA},
            "sources":int(valid.sourceSeed.nunique()),"decisions":int(grouped.ngroups),"valid_branches":len(valid),"quarantined_branches":int((df.valid!=1).sum()),"slices":{}}
    for name,part in [("all",valid),("chosen",valid[valid.chosen==1]),("unchosen",valid[valid.chosen==0])]:
        idx=part.index; report["slices"][name]={"survival":scores(part.won,part.predSurvival),"conditional_hp":hp_scores(part,part.predEndHpFracGivenWin),"branches":len(part)}
    report["composition"]={"screens":valid.groupby(["screen","decisionAct"]).size().rename("branches").reset_index().to_dict("records"),"battle_acts":valid.battleAct.value_counts().sort_index().to_dict(),"rooms":valid.roomClass.value_counts().to_dict()}
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); valid.to_csv(Path(a.output).with_suffix(".predictions.csv"),index=False);print(json.dumps(report,indent=2))
if __name__=="__main__": main()
