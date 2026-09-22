const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
for (const file of ['../tools/ooc_graph_viewer/normalize.js',
                    '../tools/combat_graph_viewer/visibility.js'])
  vm.runInThisContext(fs.readFileSync(path.join(__dirname, file), 'utf8'));

// Root edges are all shown; top K applies at the first sampled state.
const tree = {edges:[
  {parentId:0,childId:1,kind:'action',visits:10},
  {parentId:1,childId:2,kind:'particle',visits:10,
   combatModelUsed:true,combatEncounter:'JAW_WORM',combatOutcome:'survived'},
  {parentId:2,childId:3,kind:'action',visits:2},
  {parentId:2,childId:4,kind:'action',visits:8},
]};
const nodes = new Map([0,1,2,3,4].map(id => [String(id), {id:String(id)}]));
const edges = adaptOocEdges(tree,nodes);
assert.deepEqual(edges.map(e=>e.visitCount), [10,10,2,8]);
assert.equal(edges[1].actionLabel,'CTM: Jaw Worm → survived');
const outgoing = new Map();
for (const edge of edges) {
  if (!outgoing.has(edge.parentId)) outgoing.set(edge.parentId, []);
  outgoing.get(edge.parentId).push(edge);
}
const g = {root:'0',nodes,edges,outgoing,validNumber:Number.isFinite};
const options = {budget:300,depth:4,topK:1,minVisits:0,rootFilter:null,
                 focus:null,expanded:new Set()};
let visible = visibleGraph(g,options);
assert.deepEqual(visible.edges.filter(e=>e.parentId==='2').map(e=>e.visitCount),[8]);
options.topK=4;options.minVisits=5;
visible=visibleGraph(g,options);
assert.deepEqual(visible.edges.filter(e=>e.parentId==='2').map(e=>e.visitCount),[8]);
assert(!visible.nodes.some(n=>n.id==='3'));
console.log('ooc graph logic PASS');
