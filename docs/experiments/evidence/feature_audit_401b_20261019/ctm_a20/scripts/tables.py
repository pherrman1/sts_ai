#!/usr/bin/env python3
"""#401b ctm_a20: print markdown tables from perm.json (for REPORT.md)."""
import json, sys
r = json.load(open(sys.argv[1])); b = r["baseline"]
def f(x, nd): return f"{x:+.{nd}f}"
def row(name, v):
    s, h, m, mh, p = v["surv"], v["hp"], v["hp_mae"], v["maxhp"], v["potion"]
    sp = min(s["repeat_means"]), max(s["repeat_means"])
    acts = " / ".join(f(s["by_act"][a]["delta"], 3) for a in ("1", "2", "3"))
    return (f"| {name} | {f(s['delta'],4)} [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] | {sp[0]:+.4f}..{sp[1]:+.4f} | {acts} | "
            f"{f(h['delta'],3)} | {f(m['delta'],2)} | {f(mh['delta'],4)} | {f(p['delta'],4)} |")
hdr = "| group | Δ survival BCE [95% CI] | repeat range | Δ by act 1/2/3 | Δ HP CE | Δ HP MAE (HP) | Δ maxHP CE | Δ potion CE |\n|---|---|---|---|---|---|---|---|"
for sec in ("groups", "singles", "token_fields"):
    print(f"\n### {sec}\n" + hdr)
    for k, v in sorted(r["results"][sec].items(), key=lambda kv: -kv[1]["surv"]["delta"]): print(row(k, v))
