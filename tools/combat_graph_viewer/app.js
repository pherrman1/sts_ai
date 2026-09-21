(function() {
  const payload=window.__COMBAT_VIEWER__, tree=payload.evaluator.tree;
  const $=id=>document.getElementById(id);
  const status=$("layout-status");
  if(!tree || !tree.accepted || !Array.isArray(tree.nodes)) {
    status.textContent=tree?.failureReason || "Retained graph not captured. Enable the existing opt-in Silver debug capture.";
    $("graph-area").hidden=true;return;
  }
  const g=normalizeCapture(tree,payload.evaluator.rootActionSummaries,
    payload.evaluator.selectedAction);
  const controls={budget:300,depth:3,topK:4,minVisits:0,rootFilter:null,focus:null,
    direction:"RIGHT",expanded:new Set()};
  const state={selected:null,visible:null,layout:null,rendered:null,revision:0,
    history:[],trail:[g.root],transform:d3.zoomIdentity,initialFit:true};
  const graph=$("graph"),mini=$("minimap"),zoom=d3.zoom().scaleExtent([.15,3])
    .on("zoom",event=>{state.transform=event.transform;
      if(state.rendered)state.rendered.layer.setAttribute("transform",event.transform);
      graph.classList.toggle("overview",event.transform.k<.55);
      updateMini();});
  d3.select(graph).call(zoom).on("dblclick.zoom",null);
  function updateMini(){
    if(!state.layout)return;const r=graph.getBoundingClientRect(),t=state.transform;
    const box=$("mini-viewport");if(!box)return;
    box.setAttribute("x",Math.max(0,-t.x/t.k));box.setAttribute("y",Math.max(0,-t.y/t.k));
    box.setAttribute("width",r.width/t.k);box.setAttribute("height",r.height/t.k);
  }
  function fit(immediate=false){
    if(!state.layout)return;const r=graph.getBoundingClientRect();
    const k=Math.min(1.2,Math.max(.15,Math.min((r.width-60)/state.layout.width,
      (r.height-60)/state.layout.height)));
    const target=d3.zoomIdentity.translate((r.width-state.layout.width*k)/2,
      (r.height-state.layout.height*k)/2).scale(k);
    if(immediate)d3.select(graph).call(zoom.transform,target);
    else d3.select(graph).transition().duration(260).call(zoom.transform,target);
  }
  function center(id,immediate=false,left=false){
    const n=state.layout?.children?.find(x=>x.id==="n:"+id);if(!n)return;
    const r=graph.getBoundingClientRect(),k=Math.max(.65,state.transform.k);
    const target=d3.zoomIdentity.translate((left?150:r.width/2)-(n.x+n.width/2)*k,
      r.height/2-(n.y+n.height/2)*k).scale(k);
    if(immediate)d3.select(graph).call(zoom.transform,target);
    else d3.select(graph).transition().duration(230).call(zoom.transform,target);
  }
  function select(item, move=false) {
    state.selected=item;
    renderRanking();
    inspect(g,item,select,id=>{controls.expanded.has(id)?controls.expanded.delete(id):
      controls.expanded.add(id);refresh();},controls.expanded);
    if(state.layout && state.visible) {
      state.rendered=drawGraph(g,state.visible,state.layout,state.selected,
        g.selectedFingerprint,{selectNode:id=>select({kind:"node",id}),
          selectEdge:id=>select({kind:"edge",id})});
      state.rendered.layer.setAttribute("transform",state.transform);
      updateMini();
      if(move)center(item.kind==="node"?item.id:
        g.edges.find(e=>e.id===item.id)?.childId);
    }
  }
  async function refresh(anchor) {
    const rev=++state.revision;
    const anchorId=anchor || (state.selected?.kind==="node"?state.selected.id:g.root);
    const oldNode=state.layout?.children?.find(n=>n.id==="n:"+anchorId);
    const oldScreen=oldNode?{x:state.transform.x+(oldNode.x+oldNode.width/2)*state.transform.k,
      y:state.transform.y+(oldNode.y+oldNode.height/2)*state.transform.k}:null;
    state.visible=visibleGraph(g,controls);
    $("visible-count").textContent=state.visible.nodes.length+" / "+g.nodes.size+" retained nodes · "+
      state.visible.edges.length+" / "+g.edges.length+" retained edges · "+
      state.visible.hidden+" UI-hidden · "+(tree.truncated?"capture truncated":"capture complete");
    status.textContent="Laying out "+state.visible.nodes.length+" nodes…";
    await new Promise(resolve=>setTimeout(resolve,0));
    try {
      const layout=await layoutVisible(state.visible,controls.direction);
      if(rev!==state.revision)return;
      state.layout=layout;
      state.rendered=drawGraph(g,state.visible,layout,state.selected,g.selectedFingerprint,
        {selectNode:id=>select({kind:"node",id}),selectEdge:id=>select({kind:"edge",id})});
      status.textContent="";
      if(state.initialFit){state.initialFit=false;
        if(state.visible.nodes.length<=6)fit(true);else center(g.root,true,true);}
      else {
        const nextNode=layout.children?.find(n=>n.id==="n:"+anchorId);
        if(oldScreen && nextNode){
          const k=state.transform.k;
          d3.select(graph).call(zoom.transform,d3.zoomIdentity.translate(
            oldScreen.x-(nextNode.x+nextNode.width/2)*k,
            oldScreen.y-(nextNode.y+nextNode.height/2)*k).scale(k));
        } else if(anchor)center(anchor);
        else {state.rendered.layer.setAttribute("transform",state.transform);updateMini();}
      }
    } catch(err){if(rev===state.revision)status.textContent="Layout failed: "+err.message;}
  }
  function renderRanking(){
    const pane=$("root-actions");pane.replaceChildren();
    for(const row of g.rootRows){
      const e=row.edge,s=row.summary||{},button=document.createElement("button");
      button.type="button";button.className="action-row";
      if(row.chosen)button.classList.add("silver-choice");
      if(state.selected?.id===e.id)button.classList.add("inspected");
      const line=document.createElement("span");line.className="action-title";
      line.textContent=(s.label||g.label(e))+(row.chosen?" · Silver choice":"");
      const stats=document.createElement("span");stats.className="action-stats";
      stats.textContent="n "+(e.visitCount??"—")+" · share "+
        (g.validNumber(s.visitShare)?s.visitShare.toFixed(3):"—")+
        " · selection Q "+(s.selectionQValid&&g.validNumber(s.selectionQ)?s.selectionQ.toFixed(2):"—");
      const bar=document.createElement("i");bar.className="visit-bar";
      const max=Math.max(1,...g.rootRows.map(r=>g.validNumber(r.edge.visitCount)?
        r.edge.visitCount:0));bar.style.width=(g.validNumber(e.visitCount)?
          Math.max(0,Math.min(100,e.visitCount/max*100)):0)+"%";
      button.append(line,stats,bar);button.onclick=()=>{select({kind:"edge",id:e.id},true);
        renderRanking();};pane.append(button);
    }
  }
  function reveal(id){
    const goal=String(id),queue=[[g.root]],seen=new Set();
    while(queue.length){
      const path=queue.shift(),here=path.at(-1);
      if(here===goal){controls.rootFilter=null;controls.focus=null;
        $("root-filter").value="";
        controls.minVisits=0;$("min-visits").value="0";
        controls.depth=Math.max(controls.depth,path.length+1);path.forEach(p=>controls.expanded.add(p));
        $("depth").value=controls.depth;
        refresh(goal);return true;}
      if(seen.has(here))continue;seen.add(here);
      for(const e of g.outgoing.get(here)||[])if(e.childCaptured&&g.nodes.has(e.childId))
        queue.push([...path,e.childId]);
    }
    status.textContent="Node #"+goal+" is not reachable from this captured root.";return false;
  }
  $("search").addEventListener("input",event=>{
    const query=event.target.value.trim().toLowerCase(),results=$("search-results");
    results.replaceChildren();if(!query)return;
    for(const n of [...g.nodes.values()].filter(n=>n.id===query ||
      n.stateHash===query).slice(0,12)){
      const b=document.createElement("button");b.textContent="State #"+n.id+" · hash "+n.stateHash;
      b.onclick=()=>{reveal(n.id);select({kind:"node",id:n.id});results.replaceChildren();};
      results.append(b);
    }
    for(const e of g.edges.filter(e=>g.label(e).toLowerCase().includes(query) ||
      String(e.actionFingerprint||"").toLowerCase().includes(query)).slice(0,12)){
      const b=document.createElement("button");b.textContent=g.label(e)+" · "+e.id;
      b.onclick=()=>{reveal(e.parentId);select({kind:"edge",id:e.id});results.replaceChildren();};
      results.append(b);
    }
  });
  $("root-filter").append(...g.rootRows.map(row=>{
    const opt=document.createElement("option");opt.value=row.edge.id;
    opt.textContent=row.summary?.label||g.label(row.edge);
    return opt;
  }));
  $("root-filter").onchange=e=>{controls.rootFilter=e.target.value||null;refresh();};
  $("min-visits").onchange=e=>{controls.minVisits=Math.max(0,Number(e.target.value)||0);refresh();};
  $("depth").onchange=e=>{controls.depth=Math.max(1,Number(e.target.value)||1);refresh();};
  $("top-k").onchange=e=>{controls.topK=Math.max(1,Number(e.target.value)||1);refresh();};
  $("direction").onchange=e=>{controls.direction=e.target.value;refresh();};
  $("fit").onclick=()=>fit();$("root").onclick=()=>{controls.focus=null;state.history=[];
    state.trail=[g.root];$("breadcrumb").textContent="Root";refresh(g.root);};
  $("zoom-in").onclick=()=>d3.select(graph).transition().call(zoom.scaleBy,1.3);
  $("zoom-out").onclick=()=>d3.select(graph).transition().call(zoom.scaleBy,1/1.3);
  $("fullscreen").onclick=()=>document.body.classList.toggle("graph-fullscreen");
  $("focus").onclick=()=>{if(!state.selected)return;
    state.history.push(controls.focus);controls.focus=state.selected.kind==="node"?
      state.selected.id:g.edges.find(e=>e.id===state.selected.id)?.childId;
    if(!g.nodes.has(controls.focus)){controls.focus=state.history.pop();
      status.textContent="No captured child state to focus on.";return;}
    state.trail.push(controls.focus);
    $("breadcrumb").textContent=state.trail.map((id,i)=>i?"State #"+id:"Root").join(" / ");
    refresh(controls.focus);};
  $("back").onclick=()=>{if(state.history.length){controls.focus=state.history.pop();
    state.trail.pop();$("breadcrumb").textContent=state.trail.map((id,i)=>i?"State #"+id:"Root").join(" / ");
    refresh(controls.focus||g.root);}};
  mini.addEventListener("click",event=>{
    const point=mini.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
    const p=point.matrixTransform(mini.getScreenCTM().inverse()),r=graph.getBoundingClientRect();
    d3.select(graph).call(zoom.transform,d3.zoomIdentity.translate(r.width/2-p.x*state.transform.k,
      r.height/2-p.y*state.transform.k).scale(state.transform.k));
  });
  $("encounter").textContent=(payload.observation?.silverRoot?.encounter||
    payload.observation?.encounter||"Combat")+" · turn "+
    (payload.observation?.combat?.turn??payload.observation?.turn??"—");
  $("simulations").textContent="Simulations "+(payload.evaluator.totalSimulations??"—");
  $("choice").textContent="Silver choice: "+(payload.evaluator.selectedLabel||"unavailable");
  $("capture").textContent=tree.truncated?"Truncated capture":"Captured graph";
  for(const tab of document.querySelectorAll("[data-tab]"))tab.onclick=()=>{
    document.querySelectorAll("[data-panel]").forEach(p=>p.hidden=p.dataset.panel!==tab.dataset.tab);
    document.querySelectorAll("[data-tab]").forEach(t=>t.classList.toggle("active",t===tab));
  };
  for(const details of document.querySelectorAll("[data-raw]"))details.addEventListener("toggle",()=>{
    if(!details.open || details.dataset.loaded)return;
    const value=details.dataset.raw==="observation"?payload.observation:
      details.dataset.raw==="evaluator"?payload.evaluator:window.__RAW_RECORD__;
    details.querySelector("pre").textContent=JSON.stringify(value,null,2);
    details.dataset.loaded="1";
  });
  renderRanking();inspect(g,null,select,id=>{controls.expanded.add(id);refresh();},controls.expanded);
  refresh();
})();
