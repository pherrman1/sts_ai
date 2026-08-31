#!/usr/bin/env python3
"""Create the immutable pre-execution specification for the K-budget experiment."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--manifest",type=Path,required=True);p.add_argument("--executable",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--model",action="append",default=[],metavar="ROLE=PATH")
    p.add_argument("--stage-a-futures",default="0,1,2,3");p.add_argument("--stage-b-futures",default="10,11,12,13")
    p.add_argument("--b-futures",default="100,101,102,103");a=p.parse_args()
    models=[]
    for item in a.model:
        role,path=item.split("=",1);q=Path(path);models.append({"role":role,"path":path,"sha256":sha(q)})
    if {m["role"] for m in models}!={"floor","win"} or len(models)!=2 or len({m["path"] for m in models})!=2:
        raise ValueError("exactly one distinct floor and win OOC model are required")
    source=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    spec={"schema":"ooc_k_budget_experiment_v1","sourceSha":source,"executable":{"path":str(a.executable),"sha256":sha(a.executable)},
      "manifest":{"path":str(a.manifest),"sha256":sha(a.manifest)},"oocModels":models,
      "A":{"stageA":{"futureIdentities":[int(x) for x in a.stage_a_futures.split(",")],"schedules":[[10000,10000,10000]]},
           "stageB":{"futureIdentities":[int(x) for x in a.stage_b_futures.split(",")],"schedules":[[10000],[5000,5000],[3333,3333,3334],[150,100,50]]}},
      "B":{"futureIdentities":[int(x) for x in a.b_futures.split(",")],"schedule":[10000]},
      "stageB":{"authorizedOnlyByStageARule":True,"schedules":[[10000],[5000,5000],[3333,3333,3334],[150,100,50]]},
      "silver":{"backend":"silver_uct","rngRegime":"project_fair","exploration":25.0,"chanceExploration":25.0,
        "reuseCapMode":"allocated","reuseCap":32768,"sequentialHalving":False,"pruning":False,"learnedPriorPuct":False,"learnedLeaf":False,"adaptive":False},
      "analysis":{"path":"tools/analyze_ooc_k_budget.py","sha256":sha(Path("tools/analyze_ooc_k_budget.py")),
        "bootstrapClusters":"sourceSeed","replicates":10000,"seed":20260831},
      "decisionRule":{"minimumPracticalDelta":0.01,"longerRequiresLowerRegret":True,"noSelectedWinDeterioration":True,
        "uncertaintyVerdict":"HORIZON_INCONCLUSIVE","automaticReplicateIncrease":False}}
    identity_sets=[set(spec["A"][stage]["futureIdentities"]) for stage in ("stageA","stageB")]+[set(spec["B"]["futureIdentities"])]
    if any(len(s)!=4 for s in identity_sets) or any(identity_sets[i]&identity_sets[j] for i in range(3) for j in range(i+1,3)):
        raise ValueError("Stage-A A, Stage-B A, and B must contain four mutually disjoint identities")
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(spec,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(sha(a.output),a.output)
if __name__=="__main__":main()
