# Offline Silver graph viewer

`tools/render_combat_decision.py --snapshot CAPTURE.json --output report.html`
inlines the browser assets and captured data into one portable HTML file. No
network, server, npm, or game process is needed to open the report. Capture is
still opt-in with `STS_SILVER_DEBUG_TREE=1`; ordinary snapshots retain the
other report sections and display an unavailable explanation.

The canvas shows a bounded retained-search subgraph (default 300 visible
nodes). The sidebar always lists the captured root alternatives. Search and
root filters change only the view, not the saved capture. Q is the stored
evaluation sum divided by node simulation count; it is not a win probability.
No outgoing captured edges means a captured frontier, not necessarily a
terminal state.

Vendored browser dependencies, both inlined at report generation:

- ELK.js 0.11.0, `elk.bundled.js`, from
  https://registry.npmjs.org/elkjs/-/elkjs-0.11.0.tgz;
  license in `vendor/ELK-LICENSE.md`.
- D3 7.9.0, `d3.min.js`, from
  https://registry.npmjs.org/d3/-/d3-7.9.0.tgz;
  license in `vendor/D3-LICENSE`.
