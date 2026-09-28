const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
for(const name of ["normalize.js","visibility.js"]){
  vm.runInThisContext(fs.readFileSync(path.join(__dirname,"../tools/combat_graph_viewer",name),"utf8"));
}
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,"fixtures/silver_mcts_graph_fixture.json")));
const evaluator=fixture.response.advisor.evaluators[0];
const capture=evaluator.tree;
let g=normalizeCapture(capture,evaluator.rootActionSummaries,evaluator.selectedAction);
assert.equal(g.nodes.size,5);
assert.equal(g.edges.length,6);
assert.equal(g.mean(g.nodes.get("1")),0.6845);
assert.equal(g.nodes.get("2").stateHash,g.nodes.get("5").stateHash);
assert.notEqual(g.nodes.get("2"),g.nodes.get("5"));
assert.equal(g.incoming.get("2").length,3);
const options={budget:300,depth:10,topK:4,minVisits:0,rootFilter:null,focus:null,
  expanded:new Set()};
let visible=visibleGraph(g,options);
assert.equal(visible.nodes.length,5);
assert.equal(visible.edges.length,6);
options.rootFilter=g.rootRows[2].edge.id;
visible=visibleGraph(g,options);
assert.equal(visible.edges.filter(e=>e.parentId===g.root).length,1);
options.rootFilter=null;
options.expanded=new Set(["4"]);
visible=visibleGraph(g,options);
assert(visible.nodes.some(n=>n.id==="2"));
const extended=structuredClone(capture);
extended.nodes.push({id:"9007199254740993",stateHash:"9007199254740995",
  simulationCount:0,evaluationSum:1,hasState:false});
extended.edges.push({parentId:1,childId:"9007199254740993",childCaptured:true,
  actionLabel:"Bash",actionFingerprint:"different-Bash",visitCount:0});
extended.edges.push({parentId:1,childId:2,childCaptured:true,
  actionLabel:"Bash",actionFingerprint:"parallel-Bash",visitCount:1,
  continuationLabel:"End turn"});
g=normalizeCapture(extended,evaluator.rootActionSummaries,evaluator.selectedAction);
assert.equal(g.mean(g.nodes.get("9007199254740993")),null);
assert.equal(g.nodes.get("9007199254740993").stateHash,"9007199254740995");
assert.notEqual(g.edges.at(-1).id,g.edges.at(-2).id);
assert.match(g.label(g.edges.at(-1)),/End turn/);
// Valid Q is an unconstrained evaluation score, not a probability.
extended.nodes.find(n=>n.id===2).evaluationSum=-1220;
extended.nodes.find(n=>n.id===5).evaluationSum=160;
extended.nodes.find(n=>n.id===3).evaluationSum=null;
extended.edges.push({parentId:2,childId:"9007199254740993",childCaptured:false,
  visitCount:null,actionLabel:"</script><img src=x onerror=alert(1)>"});
g=normalizeCapture(extended,evaluator.rootActionSummaries,evaluator.selectedAction);
assert.equal(g.mean(g.nodes.get("2")),-2);
assert.equal(g.mean(g.nodes.get("5")),2);
assert.equal(g.mean(g.nodes.get("3")),null);
assert.match(g.label(g.edges.at(-1)),/onerror/);
assert.equal(g.edges.at(-1).visitCount,null);
options.rootFilter=null;options.expanded=new Set();options.depth=10;
visible=visibleGraph(g,options);
assert(visible.edges.some(e=>!e.childCaptured));
options.topK=1;
visible=visibleGraph(g,options);
assert(visible.frontier.size>0);
// A shared node stays visible through another allowed incoming route.
options.topK=4;options.rootFilter="edge:2";
visible=visibleGraph(g,options);
assert(visible.nodes.some(n=>n.id==="2"));
assert(!visible.edges.some(e=>e.parentId===g.root && e.id!=="edge:2"));
options.topK=1;
options.expanded=new Set(["4"]);
visible=visibleGraph(g,options);
assert(visible.nodes.some(n=>n.id==="2"));
console.log("combat graph logic PASS");
