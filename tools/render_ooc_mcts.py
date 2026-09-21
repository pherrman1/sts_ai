#!/usr/bin/env python3
"""Render an opt-in live OOC MCTS search capture as portable HTML."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ASSETS = Path(__file__).parent / "combat_graph_viewer"
SCRIPT = Path(__file__).parent / "ooc_graph_viewer" / "app.js"


def render(snapshot: dict) -> str:
    observation = snapshot.get("observation") or {}
    response = snapshot.get("response") or {}
    if observation.get("boundary") == "combat":
        raise ValueError("snapshot is a combat observation")
    identity = {key: snapshot.get(key) for key in ("session", "sequence", "observationHash")}
    advisor = response.get("advisor") or {}
    if (response.get("ready") is not True
            or not isinstance(identity["session"], str) or not identity["session"]
            or type(identity["sequence"]) is not int or identity["sequence"] < 0
            or not isinstance(identity["observationHash"], str) or not identity["observationHash"]
            or any(response.get(key) != value for key, value in identity.items())
            or any(key in advisor and advisor[key] != value for key, value in identity.items())):
        raise ValueError("snapshot response is not ready or does not match its observation")
    evaluators = [e for e in advisor.get("evaluators", [])
                  if e.get("id") == "live_ooc_decision_v1"]
    if len(evaluators) != 1:
        raise ValueError("snapshot has no unique live OOC evaluator")
    evaluator = evaluators[0]
    tree = evaluator.get("tree") or {}
    if not tree.get("accepted"):
        raise ValueError("OOC graph was not captured; enable STS_OOC_DEBUG_TREE=1 in the advisor")
    if not tree.get("nodes") or tree.get("rootId") is None:
        raise ValueError("OOC tree has no captured root")
    # JSON.parse cannot preserve all uint64 IDs. Keep state identities as text.
    payload = {"tree": tree, "fixture": observation.get("fixture"),
               "provenance": snapshot.get("captureProvenance"),
               "evaluator": {key: evaluator.get(key) for key in
               ("candidateSummaries", "selectedSemanticKey", "model", "status")},
               "identity": identity}
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    scripts = "".join(f"<script>{(ASSETS / name).read_text(encoding='utf-8').replace('</script', '<\\/script')}</script>"
                      for name in ("vendor/elk.bundled.js", "vendor/d3.min.js", "visibility.js", "layout.js"))
    scripts += f"<script>window.__OOC_GRAPH__={data};</script>"
    scripts += "<script>" + (SCRIPT.parent / "normalize.js").read_text(encoding="utf-8") + "</script>"
    scripts += "<script>" + SCRIPT.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    css += "\n" + (SCRIPT.parent / "style.css").read_text(encoding="utf-8")
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><title>OOC MCTS graph</title>"
            f"<style>{css}</style></head><body>"
            '<header><strong>OOC MCTS search</strong><span id="provenance"></span>'
            '<span id="identity"></span>'
            '<span id="capture"></span><span class="spacer"></span>'
            '<button id="fullscreen">Graph only</button></header>'
            '<div class="workspace"><aside class="sidebar"><h2>Root actions</h2><div id="root-actions"></div>'
            '<label>Root filter<select id="root-filter"><option value="">All actions</option></select></label>'
            '<label>Search action or node ID<input id="search" type="search"></label>'
            '<div id="search-results" class="search-results"></div></aside>'
            '<div class="graph-column"><div class="graph-tools">'
            '<button id="back">Back</button><button id="root">Root</button>'
            '<button id="zoom-out">−</button><button id="zoom-in">+</button><button id="fit">Fit</button>'
            '<label>Depth<input id="depth" type="number" min="1" value="4"></label>'
            '<label>Top K<input id="top-k" type="number" min="1" value="4"></label>'
            '<label>Min visits<input id="min-visits" type="number" min="0" value="0"></label>'
            '<label>Direction<select id="direction"><option value="RIGHT">Right</option>'
            '<option value="DOWN">Down</option></select></label></div>'
            '<div class="graph-stage"><svg id="graph" aria-label="OOC MCTS search graph"></svg>'
            '<span id="layout-status" class="layout-status"></span></div>'
            '<div class="graph-footer" id="visible-count"></div></div>'
            '<aside class="inspector"><h2>Inspector</h2><div id="inspector-content"></div></aside>'
            '</div>' + scripts + "</body></html>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = render(json.loads(args.snapshot.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.write_text(document, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
