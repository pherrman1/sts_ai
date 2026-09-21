// Preserve search visits under the field consumed by the shared visibility helper.
function adaptOocEdges(tree, nodes) {
  return tree.edges.map((e,i) => ({...e, id:'e'+i, visitCount:e.visits,
    parentId:String(e.parentId), childId:e.childId == null ? null : String(e.childId),
    childCaptured:e.childId != null, actionLabel:e.kind === 'particle' ? 'sample' :
      (nodes.get(String(e.childId))?.label || 'action')}));
}
