const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, value) {
  const el = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key,val]) => el.setAttribute(key, String(val)));
  if (value != null) el.textContent = String(value);
  return el;
}
function stateSummary(n) {
  if (!n.hasState || !n.state) return ["State not captured", ""];
  const s = n.state, p = s.player || {}, enemies = (s.monsters || []).slice(0,s.monsterCount??undefined);
  const turn = s.turn == null ? "" : "Turn " + s.turn;
  const hp = p.curHp == null ? "" : "HP " + p.curHp + (p.maxHp == null ? "" : "/" + p.maxHp);
  const energy = p.energy == null ? "" : "Energy " + p.energy;
  const enemy = enemies.slice(0,2).map(m => (m.id ?? "Enemy") +
    (m.curHp == null ? "" : " " + m.curHp + (m.maxHp == null ? "" : "/" + m.maxHp))).join(" · ");
  return [[turn,hp,energy].filter(Boolean).join(" · ") || "State captured", enemy];
}
function drawGraph(g, visible, laid, selected, choice, callbacks) {
  const canvas = document.getElementById("graph"), map = document.getElementById("minimap");
  canvas.replaceChildren(); map.replaceChildren();
  const defs=svg("defs"), arrow=svg("marker",{id:"arrowhead",markerWidth:9,markerHeight:9,
    refX:8,refY:4.5,orient:"auto",markerUnits:"userSpaceOnUse"});
  arrow.append(svg("path",{d:"M 0 0 L 9 4.5 L 0 9 z",fill:"currentColor"}));defs.append(arrow);canvas.append(defs);
  const layer=svg("g",{id:"graph-layer"});canvas.append(layer);
  const positions=new Map((laid.children||[]).map(n=>[n.id.slice(2),n]));
  const route=new Map((laid.edges||[]).map(e=>[e.id,e]));
  const outgoingMax=new Map();
  const occupied=[];
  const nodeBoxes=[...positions.values()].map(n=>({x:n.x-5,y:n.y-5,w:n.width+10,h:n.height+10}));
  const collides=box=>[...nodeBoxes,...occupied].some(other=>
    box.x<other.x+other.w && box.x+box.w>other.x &&
    box.y<other.y+other.h && box.y+box.h>other.y);
  for(const e of visible.edges) if(g.validNumber(e.visitCount))
    outgoingMax.set(e.parentId,Math.max(outgoingMax.get(e.parentId)||0,e.visitCount));
  for(const e of visible.edges) {
    const source=positions.get(e.parentId), target=positions.get(e.childId);
    if(!source)continue;
    const isChoice=e.parentId===g.root && e.actionFingerprint===choice;
    const isSelected=selected?.kind==="edge" && selected.id===e.id;
    const klass=["link",e.chanceOutcome?"chance":"",
      e.parentId===e.childId||(g.incoming.get(e.childId)||[]).length>1?"reference":"",
      isChoice?"choice":"",isSelected?"inspected":""].join(" ");
    const group=svg("g",{class:klass,"data-edge":e.id});
    const routed=route.get(e.id), section=routed?.sections?.[0];
    if(section) {
      const points=[section.startPoint,...(section.bendPoints||[]),section.endPoint];
      group.append(svg("path",{d:points.map((p,i)=>(i?"L":"M")+p.x+" "+p.y).join(" "),
        "marker-end":"url(#arrowhead)",
        "stroke-width":g.validNumber(e.visitCount)&&outgoingMax.get(e.parentId)
          ? (1.5+2.4*Math.sqrt(Math.max(0,e.visitCount)/outgoingMax.get(e.parentId))).toFixed(2):1.5}));
      // ELK returns edge-label coordinates relative to its own label box in some
      // configurations. Anchor visible text to the routed section instead.
      const label=g.label(e)+(g.validNumber(e.visitCount)?" · n="+e.visitCount:" · n=—");
      const shown=label.length>28?label.slice(0,27)+"…":label;
      const segments=points.slice(0,-1).map((first,i)=>({first,last:points[i+1]}))
        .sort((a,b)=>(Math.abs(b.last.x-b.first.x)*1.2+Math.abs(b.last.y-b.first.y))-
          (Math.abs(a.last.x-a.first.x)*1.2+Math.abs(a.last.y-a.first.y)));
      let placed=false;
      for(const {first,last} of segments) {
        for(const fraction of [.5,.28,.72]){
          for(const offset of [-7,20,-24]){
            const x=first.x+(last.x-first.x)*fraction,
              y=first.y+(last.y-first.y)*fraction+offset;
            const box={x:x-shown.length*3.5,y:y-12,w:shown.length*7,h:18};
            if(collides(box))continue;
            occupied.push(box);
            group.append(svg("text",{x,y,class:"edge-label","text-anchor":"middle"},shown));
            placed=true;break;
          }
          if(placed)break;
        }
        if(placed)break;
      }
      // Never force a label over a state card. The complete label remains
      // available through the edge tooltip and inspector when space is tight.
    } else if(!e.childCaptured) {
      group.append(svg("text",{x:source.x+source.width+18,y:source.y+source.height/2,class:"omitted"},
        "capture omitted · "+g.label(e)));
    }
    group.append(svg("title",{},g.label(e)+" · edge visits "+(e.visitCount??"unavailable")));
    group.addEventListener("click",event=>{event.stopPropagation();callbacks.selectEdge(e.id);});
    layer.append(group);
  }
  for(const n of visible.nodes) {
    const pos=positions.get(n.id);if(!pos)continue;
    const mean=g.mean(n), summary=stateSummary(n), incoming=g.incoming.get(n.id)||[];
    const klass=["node",n.isChanceNode?"chance":"decision",incoming.length>1?"shared":"",
      selected?.kind==="node"&&selected.id===n.id?"inspected":""].join(" ");
    const group=svg("g",{class:klass,transform:"translate("+pos.x+" "+pos.y+")","data-node":n.id});
    group.append(svg("rect",{width:pos.width,height:pos.height,rx:9}));
    group.append(svg("text",{x:12,y:24,class:"node-title"},(n.isChanceNode?"CHANCE":"STATE")+" #"+n.id));
    if(incoming.length>1)group.append(svg("text",{x:pos.width-12,y:24,"text-anchor":"end",class:"shared-label"},"shared"));
    group.append(svg("text",{x:12,y:50,class:"node-q"},"Q "+(mean==null?"—":mean.toFixed(2))));
    group.append(svg("text",{x:pos.width-12,y:50,"text-anchor":"end",class:"node-count"},
      "N "+(n.simulationCount??"—")));
    if(!n.isChanceNode) {
      group.append(svg("text",{x:12,y:73,class:"node-secondary"},summary[0].slice(0,35)));
      group.append(svg("text",{x:12,y:92,class:"node-secondary"},summary[1].slice(0,35)));
    }
    if(visible.frontier.has(n.id))group.append(svg("text",{x:pos.width-12,y:pos.height-8,
      "text-anchor":"end",class:"more-label"},"+"+visible.frontier.get(n.id)+" more"));
    group.append(svg("title",{},"node #"+n.id+" · "+summary.join(" · ")));
    group.addEventListener("click",event=>{event.stopPropagation();callbacks.selectNode(n.id);});
    layer.append(group);
  }
  const bounds={width:Math.max(laid.width||0,360),height:Math.max(laid.height||0,240)};
  map.setAttribute("viewBox","0 0 "+bounds.width+" "+bounds.height);
  for(const n of laid.children||[])map.append(svg("rect",{x:n.x,y:n.y,width:n.width,height:n.height,
    rx:5,class:"mini-node"}));
  map.append(svg("rect",{id:"mini-viewport",x:0,y:0,width:1,height:1,class:"mini-viewport"}));
  return {layer,bounds};
}
