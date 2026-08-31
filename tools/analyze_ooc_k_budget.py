#!/usr/bin/env python3
"""Fail-closed K/search-budget ranking analysis with source-cluster bootstrap."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

KEY=["sourceSeed","decisionIdx","actionIdx"]
def _normalize_schedule(f:pd.DataFrame)->pd.DataFrame:
    f["schedule"]=f.schedule.astype(str)
    return f
def _load(paths:list[Path])->pd.DataFrame:
    f=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True)
    # A multi-fight schedule contains semicolons and is inferred as text, while
    # a single-fight schedule such as 10000 may be inferred as an integer when
    # its shard is read independently.  Normalize before identity checks.
    f=_normalize_schedule(f)
    if f.empty or (f.valid!=1).any(): raise ValueError("all evaluator rows must be valid")
    if f.duplicated(["sourceSeed","decisionIdx","actionIdx","side","futureIdentity","prefixFight","rowKind","schedule"]).any():
        raise ValueError("duplicate evaluator identity")
    return f
def _scores(f:pd.DataFrame,schedule:str,k:int)->pd.Series:
    x=f[(f.side=="A")&(f.rowKind=="prefix")&(f.schedule==schedule)&(f.prefixFight==k)]
    if x.empty: raise ValueError(f"missing A prefix K={k} schedule={schedule}")
    return x.groupby(KEY).qProduct.mean()
def _truth(f:pd.DataFrame)->pd.Series:
    x=f[(f.side=="B")&(f.rowKind=="terminal")]
    if x.empty: raise ValueError("missing independent B terminal reference")
    return x.groupby(KEY).terminalWon.mean()
def metric_rows(scores:pd.Series,truth:pd.Series)->pd.DataFrame:
    joined=pd.concat([scores.rename("score"),truth.rename("truth")],axis=1,join="inner").reset_index()
    if len(joined)!=len(scores) or len(joined)!=len(truth): raise ValueError("A/B action coverage differs")
    rows=[]
    for key,g in joined.groupby(["sourceSeed","decisionIdx"]):
        maxs=g.score.max(); selected=g[g.score==maxs]; chosen_truth=selected.truth.mean(); best=g.truth.max()
        bbest=set(g.loc[g.truth==best,"actionIdx"]); sbest=set(selected.actionIdx)
        concord=[]
        vals=g.to_dict("records")
        for i in range(len(vals)):
            for j in range(i+1,len(vals)):
                ds=np.sign(vals[i]["score"]-vals[j]["score"]);dt=np.sign(vals[i]["truth"]-vals[j]["truth"])
                if ds and dt: concord.append(float(ds==dt))
        rows.append({"sourceSeed":key[0],"decisionIdx":key[1],"selectedTerminalWin":chosen_truth,
            "terminalRegret":best-chosen_truth,"topAgreement":float(bool(sbest&bbest)),
            "pairwiseConcordance":np.mean(concord) if concord else np.nan,
            "scoreTie":float(len(selected)>1),"truthTie":float(len(bbest)>1)})
    return pd.DataFrame(rows)
def summarize(rows:pd.DataFrame)->dict:
    return {c:float(rows[c].mean()) for c in rows.columns if c not in {"sourceSeed","decisionIdx"}}
def intervals(rows:pd.DataFrame,n:int,seed:int)->dict:
    clusters=rows.groupby("sourceSeed")[[c for c in rows.columns if c not in {"sourceSeed","decisionIdx"}]].mean()
    rng=np.random.default_rng(seed);idx=np.arange(len(clusters));draw=[]
    for _ in range(n):draw.append(clusters.iloc[rng.choice(idx,len(idx),replace=True)].mean().to_numpy())
    arr=np.asarray(draw)
    return {c:[float(x) for x in np.quantile(arr[:,i],[.025,.975])] for i,c in enumerate(clusters.columns)}
def contrast(left:pd.DataFrame,right:pd.DataFrame,n:int,seed:int)->dict:
    l=left.groupby("sourceSeed")[["selectedTerminalWin","terminalRegret"]].mean()
    r=right.groupby("sourceSeed")[["selectedTerminalWin","terminalRegret"]].mean()
    if not l.index.equals(r.index): raise ValueError("contrast cluster coverage differs")
    delta=l-r;rng=np.random.default_rng(seed);idx=np.arange(len(delta));draw=[]
    for _ in range(n): draw.append(delta.iloc[rng.choice(idx,len(idx),replace=True)].mean().to_numpy())
    arr=np.asarray(draw)
    return {c:{"estimate":float(delta[c].mean()),"ci95":[float(x) for x in np.quantile(arr[:,i],[.025,.975])]}
            for i,c in enumerate(delta.columns)}
def _sha(path:Path)->str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
def analyze(paths:list[Path],spec_path:Path,boot:int,seed:int)->dict:
    f=_load(paths); b=f[(f.side=="B")&(f.rowKind=="terminal")]
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema")!="ooc_k_budget_experiment_v1":raise ValueError("frozen experiment spec mismatch")
    manifest_path=Path(spec["manifest"]["path"])
    if _sha(manifest_path)!=spec["manifest"]["sha256"] or _sha(Path(spec["analysis"]["path"]))!=spec["analysis"]["sha256"]:
        raise ValueError("frozen manifest/analysis hash mismatch")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema")!="ooc_k_budget_manifest_v1" or len(manifest.get("decisions",[]))!=32:
        raise ValueError("analysis requires the exact 32-decision frozen manifest")
    if sorted(d["sourceSeed"] for d in manifest["decisions"])!=list(range(982100,982132)):
        raise ValueError("frozen source-seed cohort mismatch")
    expected_rows={(d["sourceSeed"],d["decisionIdx"],d["act"],d["floor"],d["screen"],i,a["actionBits"],int(a["chosen"]))
                   for d in manifest["decisions"] for i,a in enumerate(d["actions"])}
    expected_keys={(r[0],r[1],r[5]) for r in expected_rows}
    if len(expected_keys)!=157: raise ValueError("frozen manifest must contain exactly 157 actions")
    actual_keys=set(map(tuple,f[KEY].drop_duplicates().itertuples(index=False,name=None)))
    if actual_keys!=expected_keys: raise ValueError("CSV action coverage differs from frozen manifest")
    metadata=["sourceSeed","decisionIdx","act","floor","screen","actionIdx","actionBits","chosen"]
    actual_rows=set(map(tuple,f[metadata].drop_duplicates().itertuples(index=False,name=None)))
    if actual_rows!=expected_rows:raise ValueError("CSV action metadata differs from frozen manifest")
    expected_b=spec["B"]["futureIdentities"]
    if set(map(int,b.futureIdentity.unique()))!=set(expected_b):raise ValueError("B future identities differ from frozen plan")
    if set(b.schedule.unique())!={"10000"}:raise ValueError("B terminal reference must use frozen ordinary Silver 10k")
    if not b.groupby(KEY).futureIdentity.apply(lambda s:set(map(int,s))==set(expected_b)).all():raise ValueError("incomplete B H=4 coverage")
    truth=_truth(f); results={}; frames={}; costs={}
    present=set(f.loc[(f.side=="A")&(f.rowKind=="prefix"),"schedule"].unique())
    stage_a={";".join(map(str,s)) for s in spec["A"]["stageA"]["schedules"]};stage_b={";".join(map(str,s)) for s in spec["A"]["stageB"]["schedules"]}
    if not stage_a.issubset(present) or not present.issubset(stage_a|stage_b):raise ValueError("missing Stage-A or unknown A schedule")
    if present&stage_b and not stage_b.issubset(present):raise ValueError("Stage-B schedule set is incomplete")
    for schedule in sorted(present):
        expected_a=spec["A"]["stageA" if schedule in stage_a else "stageB"]["futureIdentities"]
        ks=sorted(f.loc[(f.side=="A")&(f.rowKind=="prefix")&(f.schedule==schedule),"prefixFight"].unique())
        if ks!=list(range(1,len(schedule.split(";"))+1)):raise ValueError(f"prefix set differs from schedule {schedule}")
        for k in ks:
            coverage=f[(f.side=="A")&(f.rowKind=="prefix")&(f.schedule==schedule)&(f.prefixFight==k)]
            if set(map(tuple,coverage[KEY].drop_duplicates().itertuples(index=False,name=None)))!=expected_keys:
                raise ValueError(f"incomplete A action coverage for {schedule}:K{k}")
            if not coverage.groupby(KEY).futureIdentity.apply(lambda s:set(map(int,s))==set(expected_a)).all():
                raise ValueError(f"incomplete A H=4 coverage for {schedule}:K{k}")
            name=f"{schedule}:K{k}";frames[name]=metric_rows(_scores(f,schedule,int(k)),truth)
            results[name]=summarize(frames[name]);results[name]["ci95"]=intervals(frames[name],boot,seed+int(k))
            c=f[(f.side=="A")&(f.rowKind=="prefix")&(f.schedule==schedule)&(f.prefixFight==k)]
            costs[name]={"silverSimulations":int(c.silverSimulations.sum()),"combatDecisions":int(c.combatDecisions.sum()),
                         "cpuSeconds":float(c.cpuMs.sum()/1000),"wallSeconds":float(c.wallMs.sum()/1000)}
    high=["10000;10000;10000:K1","10000;10000;10000:K2","10000;10000;10000:K3"]
    contrasts={}
    if not all(k in frames for k in high):raise ValueError("mandatory Stage-A K1/K2/K3 rows are missing")
    contrasts["K2-K1"]=contrast(frames[high[1]],frames[high[0]],boot,seed)
    contrasts["K3-K2"]=contrast(frames[high[2]],frames[high[1]],boot,seed+1)
    costs["B-terminal-reference"]={"silverSimulations":int(b.silverSimulations.sum()),
        "combatDecisions":int(b.combatDecisions.sum()),"cpuSeconds":float(b.cpuMs.sum()/1000),
        "wallSeconds":float(b.wallMs.sum()/1000)}
    return {"rows":len(f),"A_future_identities":sorted(map(int,f.loc[f.side=="A","futureIdentity"].unique())),
            "B_future_identities":sorted(map(int,b.futureIdentity.unique())),"metrics":results,
            "costs":costs,"contrasts":contrasts,
            "stage_a_rule":{"minimum_absolute_practical_delta":0.01,
                "longer_requires":["lower terminal-regret point estimate","no lower selected-terminal-win point estimate","selected-win gain >=0.01 or regret reduction >=0.01"],
                "uncertainty_blocker_verdict":"HORIZON_INCONCLUSIVE","automatic_replicate_increase":False}}
def self_test()->None:
    # Pairwise/tie behavior and source-cluster contrast smoke.
    idx=pd.MultiIndex.from_tuples([(1,0,0),(1,0,1),(2,0,0),(2,0,1)],names=KEY)
    a=pd.Series([.8,.2,.1,.9],index=idx);b=pd.Series([1.,0.,1.,0.],index=idx)
    r=metric_rows(a,b);assert r.selectedTerminalWin.tolist()==[1.,0.]
    assert abs(summarize(r)["terminalRegret"]-.5)<1e-12
    raw=_normalize_schedule(pd.DataFrame({"schedule":[10000,"10000;10000;10000"]}))
    assert raw.schedule.tolist()==["10000","10000;10000;10000"]
def main()->None:
    p=argparse.ArgumentParser();p.add_argument("csv",nargs="*",type=Path);p.add_argument("--output",type=Path)
    p.add_argument("--spec",type=Path)
    p.add_argument("--bootstrap",type=int);p.add_argument("--seed",type=int);p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:self_test();print("self-test PASS");return
    if not a.csv or not a.output or not a.spec:
        p.error("CSV inputs, --output, and --spec are required")
    spec=json.loads(a.spec.read_text(encoding="utf-8"));frozen_n=spec["analysis"]["replicates"];frozen_seed=spec["analysis"]["seed"]
    if (a.bootstrap is not None and a.bootstrap!=frozen_n) or (a.seed is not None and a.seed!=frozen_seed):
        p.error("bootstrap count/seed differ from frozen spec")
    report=analyze(a.csv,a.spec,frozen_n,frozen_seed)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__=="__main__":main()
