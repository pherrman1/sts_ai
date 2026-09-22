# Offline OOC MCTS graph viewer

Capture one live advisor OOC decision with `STS_OOC_DEBUG_TREE=1` and render it:

```bash
python3 tools/render_ooc_mcts.py \
  --snapshot ~/.cache/sts-model-inspector/latest.json \
  --output /tmp/ooc-mcts.html
```

Open the generated HTML in a browser. It embeds the capture, D3, and ELK.js;
no network or game process is required. The graph shows actual retained MCTS
state particles and action nodes from the completed search. Action cards name
the StS choice (for example, a map destination or a card reward); state cards
show the floor, room, screen, map position, HP, and gold. The inspector retains
the exact search-local action key and state ID. A dashed gold edge labeled
`CTM` means the action entered combat and the combat transition model sampled
the named encounter and outcome for that successor. Other particle edges sample
noncombat uncertainty. CTM samples inside leaf evaluation can affect a value
without creating a retained graph edge. Q is the action mean backed-up value in `[0,1]`;
unvisited actions have no Q. An edge ending at “capture omitted” exceeded the
capture cap; a state with no outgoing edges can also be an unexpanded frontier.
The capture does not include complete hidden game-state content.
Reports generated from test fixtures are labeled `TEST FIXTURE`. A sampled
terminal loss can retain the state's pre-combat HP field, so a loss card's HP
is not a post-death HP reading.

Native simulator captures use `STS_OOC_MCTS_GRAPH_FILE` and optional
`STS_OOC_MCTS_GRAPH_DECISION_INDEX`; pass the written JSON to the same renderer.

Browser layout libraries are reused from `tools/combat_graph_viewer/vendor/`,
with licenses documented in its README.
