#!/usr/bin/env python3
"""Fail-closed collection and terminal-reference analysis for V4 vs K1/H1."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

KEY = ["sourceSeed", "decisionIdx"]

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(paths: list[Path]) -> pd.DataFrame:
    frame = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    if frame.empty or (frame.valid != 1).any(): raise ValueError("all rows must be valid")
    return frame

def collect(paths: list[Path], manifest: Path, report: Path) -> None:
    frame=load(paths)
    if frame.duplicated([*KEY,"actionIdx"]).any(): raise ValueError("duplicate collection action")
    rows=[]
    for key,g in frame.groupby(KEY):
        if g.v4Chosen.sum()!=1: raise ValueError("decision must have one V4 action")
        if g.legalSiblingCount.nunique()!=1 or len(g)!=g.legalSiblingCount.iloc[0]:
            raise ValueError("incomplete sibling coverage")
        v4=g[g.v4Chosen==1].iloc[0]; best=g.k1Value.max()
        planner=g[g.k1Value==best].sort_values("actionIdx").iloc[0]
        rows.append({"sourceSeed":int(key[0]),"decisionIdx":int(key[1]),
            "act":int(g.act.iloc[0]),"floor":int(g.floor.iloc[0]),"screen":int(g.screen.iloc[0]),
            "actions":len(g),"v4Bits":int(v4.actionBits),"plannerBits":int(planner.actionBits),
            "v4K1Value":float(v4.k1Value),"plannerK1Value":float(planner.k1Value),
            "k1Margin":float(best-g[g.actionBits!=planner.actionBits].k1Value.max()) if len(g)>1 else 0.0,
            "agreement":int(v4.actionBits==planner.actionBits)})
    decisions=pd.DataFrame(rows)
    disagreements=decisions[decisions.agreement==0]
    disagreements.to_csv(manifest,index=False)
    payload={"schema":"ooc_v4_h1_collection_v1","inputs":[{"path":str(p),"sha256":digest(p)} for p in paths],
        "decisions":len(decisions),"actions":len(frame),"agreementRate":float(decisions.agreement.mean()),
        "disagreements":len(disagreements),"screenDistribution":decisions.screen.value_counts().sort_index().to_dict(),
        "disagreementScreenDistribution":disagreements.screen.value_counts().sort_index().to_dict(),
        "k1Margins":{"mean":float(decisions.k1Margin.mean()),"median":float(decisions.k1Margin.median())},
        "manifest":{"path":str(manifest),"sha256":digest(manifest)}}
    report.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")

def bootstrap(rows:pd.DataFrame, cols:list[str], n:int, seed:int)->dict:
    clusters=rows.groupby("sourceSeed")[cols].mean().to_numpy();rng=np.random.default_rng(seed)
    draw=clusters[rng.integers(0,len(clusters),size=(n,len(clusters)))].mean(axis=1)
    return {c:[float(x) for x in np.quantile(draw[:,i],[.025,.975])] for i,c in enumerate(cols)}

def adjudicate(collection_paths:list[Path], reference_paths:list[Path], report:Path,
               boot:int, seed:int)->None:
    c=load(collection_paths);r=load(reference_paths)
    decisions=[]
    for key,g in c.groupby(KEY):
        v4=g[g.v4Chosen==1].iloc[0];planner=g[g.k1Value==g.k1Value.max()].sort_values("actionIdx").iloc[0]
        if v4.actionBits==planner.actionBits: continue
        rr=r[(r.sourceSeed==key[0])&(r.decisionIdx==key[1])]
        if rr.empty or rr.duplicated(["actionIdx","futureIdx"]).any():raise ValueError("bad reference coverage")
        if set(rr.futureIdx)==set(range(100,104)) and not rr.groupby("actionBits").futureIdx.apply(lambda x:set(x)==set(range(100,104))).all():
            raise ValueError("incomplete reference future coverage")
        if set(rr.futureIdx)!=set(range(100,104)) or set(rr.actionBits)!=set(g.actionBits):
            raise ValueError("reference future/action set mismatch")
        truth=rr.groupby("actionBits").terminalWon.mean()
        if int(v4.actionBits) not in truth or int(planner.actionBits) not in truth:raise ValueError("selected action absent")
        best=truth.max();vv=float(truth[int(v4.actionBits)]);pv=float(truth[int(planner.actionBits)])
        decisions.append({"sourceSeed":int(key[0]),"decisionIdx":int(key[1]),"screen":int(g.screen.iloc[0]),
            "v4Win":vv,"plannerWin":pv,"v4Regret":float(best-vv),"plannerRegret":float(best-pv),
            "plannerMinusV4Win":pv-vv,"plannerMinusV4Regret":vv-pv})
    d=pd.DataFrame(decisions);cols=["v4Win","plannerWin","v4Regret","plannerRegret","plannerMinusV4Win","plannerMinusV4Regret"]
    wins=int((d.plannerMinusV4Win>0).sum());losses=int((d.plannerMinusV4Win<0).sum());ties=int((d.plannerMinusV4Win==0).sum())
    verdict="INCONCLUSIVE"
    if d.plannerWin.mean()>d.v4Win.mean() and d.plannerRegret.mean()<d.v4Regret.mean() and wins>=losses:verdict="PROMISING"
    elif d.plannerWin.mean()<d.v4Win.mean() and d.plannerRegret.mean()>d.v4Regret.mean():verdict="REJECT"
    payload={"schema":"ooc_v4_h1_result_v1","inputs":{"collection":[{"path":str(p),"sha256":digest(p)} for p in collection_paths],
        "reference":[{"path":str(p),"sha256":digest(p)} for p in reference_paths]},"disagreements":len(d),
        "winLossTie":{"wins":wins,"losses":losses,"ties":ties},"metrics":{c:float(d[c].mean()) for c in cols},
        "medianRegret":{"V4":float(d.v4Regret.median()),"H1":float(d.plannerRegret.median())},
        "ci95":bootstrap(d,cols,boot,seed),"byScreen":d.groupby("screen")[cols].mean().to_dict(orient="index"),
        "bootstrap":{"clusters":"sourceSeed","replicates":boot,"seed":seed},"verdict":verdict,"rows":d.to_dict(orient="records")}
    report.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")

def self_test()->None:
    x=pd.DataFrame({"sourceSeed":[1,2],"x":[0.,1.]});assert bootstrap(x,["x"],100,1)["x"][0]<=.5

def main()->None:
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="mode",required=True)
    s=sub.add_parser("collect");s.add_argument("csv",nargs="+",type=Path);s.add_argument("--manifest",required=True,type=Path);s.add_argument("--output",required=True,type=Path)
    s=sub.add_parser("adjudicate");s.add_argument("--collection",nargs="+",required=True,type=Path);s.add_argument("--reference",nargs="+",required=True,type=Path);s.add_argument("--output",required=True,type=Path);s.add_argument("--bootstrap",type=int,default=10000);s.add_argument("--seed",type=int,default=20260901)
    sub.add_parser("self-test");a=p.parse_args()
    if a.mode=="self-test":self_test();print("self-test PASS")
    elif a.mode=="collect":collect(a.csv,a.manifest,a.output)
    else:adjudicate(a.collection,a.reference,a.output,a.bootstrap,a.seed)
if __name__=="__main__":main()
