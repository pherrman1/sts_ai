const viewerElk = new ELK();
async function layoutVisible(visible, direction) {
  const nodeSet = new Set(visible.nodes.map(n => n.id));
  const children = visible.nodes.map(n => ({
    id:"n:" + n.id, width:n.graphWidth || (n.isChanceNode ? 142 : 230),
    height:n.graphHeight || (n.isChanceNode ? 60 : 104),
    layoutOptions:{"elk.portConstraints":"FIXED_SIDE"},
    ports:[{id:"in:" + n.id, width:1,height:1, properties:{"port.side":direction==="RIGHT"?"WEST":"NORTH"}},
      {id:"out:" + n.id,width:1,height:1,properties:{"port.side":direction==="RIGHT"?"EAST":"SOUTH"}}]}));
  const edges = visible.edges.filter(e => e.childCaptured && nodeSet.has(e.childId))
    .map(e => ({id:e.id, sources:["out:" + e.parentId],targets:["in:" + e.childId],
      labels:[{text:e.combatModelUsed ? "CTM" : "",
        width:Math.min(210,Math.max(60,(e.actionLabel||"").length*7)),height:22}]}));
  const graph={id:"silver-graph", children, edges,
    layoutOptions:{"elk.algorithm":"layered","elk.direction":direction,
      "elk.edgeRouting":"ORTHOGONAL","elk.spacing.nodeNode":"36",
      "elk.layered.spacing.nodeNodeBetweenLayers":"140",
      "elk.layered.considerModelOrder.strategy":"NODES_AND_EDGES"}};
  return viewerElk.layout(graph);
}
