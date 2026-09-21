/* Retained Silver graph normalization. IDs are strings to avoid JS precision loss. */
function normalizeCapture(tree, summaries, selectedFingerprint) {
  const rawNodes = Array.isArray(tree.nodes) ? tree.nodes : [];
  const rawEdges = Array.isArray(tree.edges) ? tree.edges : [];
  const nodes = new Map(rawNodes.map(n => [String(n.id), {...n, id: String(n.id),
    stateHash: n.stateHash == null ? null : String(n.stateHash)}]));
  const edges = rawEdges.map((e, index) => ({...e, id: String(e.id ?? "edge:" + index),
    parentId: String(e.parentId), childId: e.childId == null ? null : String(e.childId)}));
  const outgoing = new Map(), incoming = new Map();
  for (const edge of edges) {
    if (!outgoing.has(edge.parentId)) outgoing.set(edge.parentId, []);
    outgoing.get(edge.parentId).push(edge);
    if (edge.childCaptured && nodes.has(edge.childId)) {
      if (!incoming.has(edge.childId)) incoming.set(edge.childId, []);
      incoming.get(edge.childId).push(edge);
    }
  }
  const validNumber = x => typeof x === "number" && Number.isFinite(x);
  const mean = n => n && validNumber(n.evaluationSum) &&
    validNumber(n.simulationCount) && n.simulationCount > 0
    ? n.evaluationSum / n.simulationCount : null;
  const root = String(tree.rootId);
  const rootEdges = outgoing.get(root) || [];
  const summaryByFingerprint = new Map((summaries || []).map(s => [s.fingerprint, s]));
  const rootRows = rootEdges.map(e => ({edge:e,
    summary:summaryByFingerprint.get(e.actionFingerprint) || null,
    chosen:e.actionFingerprint === selectedFingerprint}));
  const label = e => [(e.parentId===root?summaryByFingerprint.get(e.actionFingerprint)?.label:null) ||
      e.actionLabel || (e.chanceOutcome ? "Chance outcome" : "Action"),
    e.continuationLabel ? "→ " + e.continuationLabel : ""].filter(Boolean).join(" ");
  return {tree, nodes, edges, outgoing, incoming, root, rootRows, mean, label,
    selectedFingerprint, validNumber};
}
