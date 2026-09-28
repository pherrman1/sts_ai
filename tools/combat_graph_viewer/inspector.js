function inspect(g, selection, onNavigate, onExpand, expanded) {
  const pane=document.getElementById("inspector-content");
  pane.replaceChildren();
  const element=(tag,value,klass)=>{const e=document.createElement(tag);if(value!=null)e.textContent=String(value);
    if(klass)e.className=klass;return e;};
  const field=(name,value)=>{const row=element("div",null,"fact");row.append(element("span",name),element("strong",value??"unavailable"));pane.append(row);};
  const raw=(object,title="Raw captured JSON")=>{const details=element("details"),summary=element("summary",title);
    const pre=element("pre");details.append(summary,pre);
    details.addEventListener("toggle",()=>{if(details.open&&!pre.textContent)
      pre.textContent=JSON.stringify(object,null,2);});pane.append(details);};
  const button=(name,action)=>{const b=element("button",name);b.type="button";b.onclick=action;pane.append(b);};
  const copy=(identity)=>button("Copy identity",()=>{
    const input=element("input");input.value=identity;pane.append(input);input.select();
    document.execCommand("copy");input.remove();
  });
  if(!selection){pane.append(element("p","Choose a node or edge to inspect its exact captured values."));return;}
  if(selection.kind==="edge"){
    const e=g.edges.find(x=>x.id===selection.id);if(!e)return;
    pane.append(element("h3",g.label(e)));field("Identity",e.id);field("From → to",e.parentId+" → "+
      (e.childCaptured?e.childId:"capture omitted"));
    field("Edge visits",e.visitCount);field("Fingerprint",e.actionFingerprint);
    field("Continuation fingerprint",e.continuationFingerprint||null);
    field("Chance outcome",e.chanceOutcome?"yes":"no");field("RNG advance steps",e.rngAdvanceSteps);
    if(e.parentId===g.root){const summary=g.rootRows.find(r=>r.edge.id===e.id)?.summary;
      field("Root selection Q",summary?.selectionQValid?summary.selectionQ:null);
      field("Silver root prior P(a|state)",summary?.prior);
      field("Silver prior logit",summary?.priorLogit);}
    const child=g.nodes.get(e.childId);field("Child visits",child?.simulationCount);
    field("Child mean Q",g.mean(child));
    const before=g.nodes.get(e.parentId);
    if(before?.hasState && child?.hasState && !before.isChanceNode && !child.isChanceNode){
      const pairs=[
        ["HP",before.state?.player?.curHp,child.state?.player?.curHp],
        ["Block",before.state?.player?.block,child.state?.player?.block],
        ["Energy",before.state?.player?.energy,child.state?.player?.energy],
        ["Turn",before.state?.turn,child.state?.turn]];
      pane.append(element("h4","Captured before → after (selected edge)"));
      for(const [name,left,right] of pairs)if(left!=null&&right!=null)
        field(name,String(left)+" → "+String(right));
    } else pane.append(element("p","Endpoint states unavailable or chance boundary; no state change inferred.","muted"));
    if(child)button("Inspect child #"+child.id,()=>onNavigate({kind:"node",id:child.id}));
    copy(e.id);
    raw(e);return;
  }
  const n=g.nodes.get(selection.id);if(!n)return;
  pane.append(element("h3",(n.isChanceNode?"Chance":"State")+" #"+n.id));
  field("Stored depth",n.depth);field("State hash",n.stateHash);field("Node N",n.simulationCount);
  field("Evaluation sum",n.evaluationSum);field("Mean Q",g.mean(n));
  field("Victories",n.victoryCount);field("Captured state",n.hasState?"yes":"no");
  copy(n.id);
  const s=n.state||{},p=s.player||{};
  if(n.hasState){field("Turn",s.turn);field("HP",p.curHp==null?null:p.curHp+(p.maxHp==null?"":"/"+p.maxHp));
    field("Energy",p.energy);field("Block",p.block);
    if(Array.isArray(s.monsters))field("Enemies",s.monsters.slice(0,s.monsterCount??s.monsters.length)
      .map(m=>(m.id??"Enemy")+" "+(m.curHp??"?")+(m.maxHp==null?"":"/"+m.maxHp)).join(", "));
    if(Array.isArray(s.hand))field("Hand",s.hand.map(c=>c.id??c.name??"?").join(", "));
    for(const [name,key] of [["Draw pile","drawPile"],["Discard pile","discardPile"],
      ["Exhaust pile","exhaustPile"]]){const pile=s[key];if(pile)
        field(name,"known top "+(pile.knownTop?.length??"?")+" · unknown "+
          (pile.unknown?.length??"?")+" · known bottom "+(pile.knownBottom?.length??"?"));}
    if(p.statusMap!=null)field("Status map",JSON.stringify(p.statusMap));
    if(p.statusBits0!=null||p.statusBits1!=null)
      field("Status bits",String(p.statusBits0??"?")+" / "+String(p.statusBits1??"?"));}
  const incoming=g.incoming.get(n.id)||[],outgoing=g.outgoing.get(n.id)||[];
  for(const [title,edges] of [["Incoming references",incoming],["Outgoing actions",outgoing]]){
    pane.append(element("h4",title+" ("+edges.length+")"));
    for(const e of edges){const b=element("button",g.label(e)+" · edge n="+(e.visitCount??"—")+
      (title==="Outgoing actions"?" · child n="+(g.nodes.get(e.childId)?.simulationCount??"—"):""),"inspector-row");
      b.onclick=()=>onNavigate({kind:"edge",id:e.id});pane.append(b);}
  }
  if(outgoing.length)button(expanded.has(n.id)?"Use top-K children":"Show all captured children",
    ()=>onExpand(n.id));
  if(n.hasState)raw(s,"BattleStateWire state");
  raw(n);
}
