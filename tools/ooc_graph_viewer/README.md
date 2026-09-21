# Offline OOC MCTS graph viewer

Capture one live advisor OOC decision with `STS_OOC_DEBUG_TREE=1` and render it:

```bash
python3 tools/render_ooc_mcts.py \
  --snapshot ~/.cache/sts-model-inspector/latest.json \
  --output /tmp/ooc-mcts.html
```

Open the generated HTML in a browser. It embeds the capture, D3, and ELK.js;
no network or game process is required. The graph shows actual retained MCTS
state particles and action nodes from the completed search. Root actions have
semantic labels; state cards show floor, HP, and screen summaries. Child action
IDs and state IDs are search-local identities,
not observed game state. Q is the action mean backed-up value in `[0,1]`;
unvisited actions have no Q. An edge ending at “capture omitted” exceeded the
capture cap; a state with no outgoing edges can also be an unexpanded frontier.
The capture does not include hidden game-state content.

Browser layout libraries are reused from `tools/combat_graph_viewer/vendor/`,
with licenses documented in its README.
