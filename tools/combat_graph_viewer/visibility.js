/* Traverse from the root over permitted edges; no unique-parent assumptions. */
function visibleGraph(g, options) {
  const root = options.focus || g.root, selected = new Set([root]), shownEdges = [];
  const queue = [{id:root, depth:0}], visited = new Set();
  const budget = options.budget || 300, frontier = new Map();
  const edgeOrder=new Map(g.edges.map((e,i)=>[e.id,i]));
  while (queue.length) {
    const {id, depth} = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    const all = (g.outgoing.get(id) || []).filter(e =>
      (id !== g.root || !options.rootFilter || e.id === options.rootFilter) &&
      (!g.validNumber(e.visitCount) || e.visitCount >= options.minVisits))
      .sort((a,b)=>(b.visitCount??-1)-(a.visitCount??-1) ||
        edgeOrder.get(a.id)-edgeOrder.get(b.id));
    const limit = id === g.root || options.expanded.has(id) ? Infinity : options.topK;
    const allowed = all.slice(0, limit);
    let omitted = Math.max(0, all.length - allowed.length);
    for (const e of allowed) {
      if (depth >= options.depth) {omitted++; continue;}
      if (e.childCaptured && g.nodes.has(e.childId) && !selected.has(e.childId) && selected.size >= budget) {
        omitted++; continue;
      }
      shownEdges.push(e);
      if (e.childCaptured && g.nodes.has(e.childId) && !selected.has(e.childId)) {
        selected.add(e.childId);
        queue.push({id:e.childId, depth:depth+1});
      }
    }
    if (omitted) frontier.set(id, omitted);
  }
  return {nodes:[...selected].map(id => g.nodes.get(id)).filter(Boolean),
    edges:shownEdges, frontier, hidden:g.nodes.size-selected.size};
}
