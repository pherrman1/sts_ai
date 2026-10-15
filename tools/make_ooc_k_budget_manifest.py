#!/usr/bin/env python3
"""Freeze the exact PR-100 counterfactual cohort into an evaluator manifest."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

SCHEMA = "ooc_k_budget_manifest_v1"
EXPECTED = list(range(982100, 982132))

def build(source: Path) -> dict:
    with source.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    required = {"sourceSeed","decisionIdx","actionIdx","actionBits","action","chosen",
                "screen","decisionAct","decisionFloor","valid"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("audit CSV schema mismatch")
    if any(r["valid"] not in {"1","true","True"} for r in rows):
        raise ValueError("audit contains invalid branches")
    grouped: dict[tuple[int,int], list[dict]] = {}
    for r in rows:
        key=(int(r["sourceSeed"]),int(r["decisionIdx"]))
        grouped.setdefault(key,[]).append(r)
    seeds=sorted(k[0] for k in grouped)
    if seeds != EXPECTED or len(grouped) != 32:
        raise ValueError("audit must contain exactly one decision for every frozen source seed")
    decisions=[]
    for (seed,dec_idx), group in sorted(grouped.items()):
        group.sort(key=lambda r:int(r["actionIdx"]))
        if [int(r["actionIdx"]) for r in group] != list(range(len(group))) or len(group)<2:
            raise ValueError(f"incomplete action set for {seed}")
        fixed={(int(r["decisionAct"]),int(r["decisionFloor"]),int(r["screen"])) for r in group}
        identities={(int(r["actionBits"]),r["action"]) for r in group}
        if len(fixed)!=1 or len(identities)!=len(group) or sum(r["chosen"] in {"1","true","True"} for r in group)!=1:
            raise ValueError(f"ambiguous decision/action identity for {seed}")
        act,floor,screen=fixed.pop()
        decisions.append({"sourceSeed":seed,"decisionIdx":dec_idx,"act":act,"floor":floor,"screen":screen,
            "actions":[{"actionBits":int(r["actionBits"]),"semantic":r["action"],
                        "chosen":r["chosen"] in {"1","true","True"}} for r in group]})
    return {"schema":SCHEMA,"sourceAuditSha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "sourceSeeds":{"first":EXPECTED[0],"last":EXPECTED[-1],"count":32},"decisions":decisions}

def main() -> None:
    p=argparse.ArgumentParser();p.add_argument("audit_csv",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--smoke-source",type=int,choices=EXPECTED);a=p.parse_args()
    manifest=build(a.audit_csv)
    if a.smoke_source is not None:
        manifest["decisions"]=[d for d in manifest["decisions"] if d["sourceSeed"]==a.smoke_source]
        manifest["smokeSubsetOfFrozenCohort"]=True
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(hashlib.sha256(a.output.read_bytes()).hexdigest(),a.output)
if __name__=="__main__": main()
