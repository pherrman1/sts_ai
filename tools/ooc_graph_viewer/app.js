(function () {
  const payload = window.__OOC_GRAPH__, tree = payload.tree, evaluator = payload.evaluator;
  const $ = id => document.getElementById(id);
  const root = String(tree.rootId);
  const nodes = new Map(tree.nodes.map(n => [String(n.id), {
    ...n, id:String(n.id), isChanceNode:n.kind === 'chance'}]));
  const edges = tree.edges.map((e,i) => ({...e, id:'e'+i,
    parentId:String(e.parentId), childId:e.childId == null ? null : String(e.childId),
    childCaptured:e.childId != null, actionLabel:e.kind === 'particle' ? 'sample' :
      (nodes.get(String(e.childId))?.label || 'action')}));
  const outgoing = new Map(), incoming = new Map();
  for (const e of edges) {
    if (!outgoing.has(e.parentId)) outgoing.set(e.parentId, []);
    outgoing.get(e.parentId).push(e);
    if (e.childCaptured) {
      if (!incoming.has(e.childId)) incoming.set(e.childId, []);
      incoming.get(e.childId).push(e);
    }
  }
  const g = {root,nodes,edges,outgoing,incoming,validNumber:x=>typeof x==='number' && Number.isFinite(x)};
  const rootRows = outgoing.get(root) || [];
  const selected = evaluator.selectedSemanticKey;
  const controls = {budget:300,depth:4,topK:4,minVisits:0,rootFilter:null,focus:null,
    direction:'RIGHT',expanded:new Set()};
  let rendered = null, transform = d3.zoomIdentity, revision=0, selectedItem=null, history=[];
  const canvas=$('graph'), zoom=d3.zoom().scaleExtent([.1,4]).on('zoom',event=>{
    transform=event.transform;if(rendered)rendered.setAttribute('transform',transform);
  });
  d3.select(canvas).call(zoom).on('dblclick.zoom',null);
  $('identity').textContent=payload.identity.session+' · #'+payload.identity.sequence;
  $('capture').textContent=tree.truncated?'Capture truncated':'Capture complete';
  function label(n){return n.label || (n.kind==='chance'?'Action #'+n.actionId:
    'Particle state '+n.stateId);}
  function inspect(item){
    selectedItem=item;const pane=$('inspector-content');pane.replaceChildren();
    if (!item) {pane.textContent='Select an action, particle, or edge.';return;}
    const data=item.kind==='edge'?edges.find(e=>e.id===item.id):nodes.get(item.id);
    if(!data)return;
    const title=document.createElement('h3');title.textContent=item.kind==='edge'?
      (data.kind==='particle'?'Sampled outcome':'Action edge'):label(data);pane.append(title);
    const rows=item.kind==='edge'?{
      'From':data.parentId,'To':data.childId??'capture omitted','Kind':data.kind,
      'Visits':data.visits}:{
      'Node ID':data.id,'Kind':data.kind,'State ID':data.stateId,
      'Depth':data.depth,'Visits':data.visits,'Prior':data.prior,'Q':data.q};
    for(const [name,value] of Object.entries(rows)){
      const line=document.createElement('div');line.className='fact';
      const a=document.createElement('span'),b=document.createElement('strong');
      a.textContent=name;b.textContent=value==null?'unavailable':String(value);
      line.append(a,b);pane.append(line);
    }
    if(item.kind==='node')for(const e of outgoing.get(item.id)||[]){
      const button=document.createElement('button');button.className='inspector-row';
      button.textContent=e.actionLabel+' · n='+e.visits;
      button.onclick=()=>inspect({kind:'edge',id:e.id});pane.append(button);
    }
    const raw=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent='Raw captured JSON';const pre=document.createElement('pre');
    pre.textContent=JSON.stringify(data,null,2);raw.append(summary,pre);pane.append(raw);
    drawSelection();
  }
  function drawSelection(){
    canvas.querySelectorAll('.inspected').forEach(el=>el.classList.remove('inspected'));
    if(selectedItem)canvas.querySelector('[data-'+selectedItem.kind+'="'+selectedItem.id+'"]')?.classList.add('inspected');
  }
  function fit(layout){
    const box=canvas.getBoundingClientRect();const k=Math.min(1.2,Math.max(.1,
      Math.min((box.width-50)/layout.width,(box.height-50)/layout.height)));
    d3.select(canvas).call(zoom.transform,d3.zoomIdentity.translate(
      (box.width-layout.width*k)/2,(box.height-layout.height*k)/2).scale(k));
  }
  async function refresh(){
    const current=++revision,visible=visibleGraph(g,controls);
    $('visible-count').textContent=visible.nodes.length+' / '+nodes.size+' captured nodes · '+
      visible.edges.length+' / '+edges.length+' edges · '+visible.hidden+' hidden by view';
    $('layout-status').textContent='Laying out '+visible.nodes.length+' nodes…';
    try {
      const layout=await layoutVisible(visible,controls.direction);
      if(current!==revision)return;
      canvas.replaceChildren();const svgNS='http://www.w3.org/2000/svg';
      const make=(tag,attrs={})=>{const element=document.createElementNS(svgNS,tag);
        for(const [key,value] of Object.entries(attrs))element.setAttribute(key,String(value));
        return element;};
      const defs=make('defs'),marker=make('marker',{id:'ooc-arrow',markerWidth:9,markerHeight:9,
        refX:8,refY:4.5,orient:'auto'});
      marker.append(make('path',{d:'M0 0 L9 4.5 L0 9 z',fill:'#8293a5'}));defs.append(marker);canvas.append(defs);
      const layer=make('g');canvas.append(layer);rendered=layer;
      const positions=new Map((layout.children||[]).map(n=>[n.id.slice(2),n]));
      const routes=new Map((layout.edges||[]).map(e=>[e.id,e]));
      for(const e of visible.edges){
        const route=routes.get(e.id)?.sections?.[0],source=positions.get(e.parentId);
        if(!source)continue;
        const group=make('g',{class:'link '+(e.kind==='particle'?'chance':'')});
        group.setAttribute('data-edge',e.id);
        if(route){const points=[route.startPoint,...(route.bendPoints||[]),route.endPoint];
          group.append(make('path',{d:points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' '),
            'marker-end':'url(#ooc-arrow)','stroke-width':1.5+Math.min(3,Math.sqrt(e.visits||0)/8)}));
        }else if(!e.childCaptured){const text=make('text',{x:source.x+source.width+12,
            y:source.y+source.height/2,class:'omitted'});
          text.textContent='capture omitted';group.append(text);}
        const tip=make('title');tip.textContent=e.actionLabel+' · visits '+e.visits;group.append(tip);
        group.onclick=()=>inspect({kind:'edge',id:e.id});layer.append(group);
      }
      for(const n of visible.nodes){const pos=positions.get(n.id);if(!pos)continue;
        const group=make('g',{class:'node '+(n.isChanceNode?'chance':'decision'),
          transform:'translate('+pos.x+','+pos.y+')'});group.setAttribute('data-node',n.id);
        group.append(make('rect',{width:pos.width,height:pos.height,rx:9}));
        const title=make('text',{x:10,y:n.isChanceNode?17:23,class:'node-title'});
        title.textContent=n.isChanceNode?'ACTION #'+n.actionId:'STATE #'+n.id;
        const count=make('text',{x:10,y:n.isChanceNode?37:48,class:'node-count'});count.textContent='n '+n.visits;
        const detail=make('text',{x:10,y:n.isChanceNode?54:74,class:'node-secondary'});
        detail.textContent=n.isChanceNode?'Q '+(n.q==null?'—':n.q.toFixed(3))+
          ' · P '+n.prior.toFixed(3):label(n).slice(0,29);
        group.append(title,count,detail);const tip=make('title');tip.textContent=label(n);group.append(tip);
        group.onclick=()=>inspect({kind:'node',id:n.id});layer.append(group);
      }
      layer.setAttribute('transform',transform);drawSelection();
      $('layout-status').textContent='';fit(layout);
    }catch(error){if(current===revision)$('layout-status').textContent='Layout failed: '+error.message;}
  }
  const pane=$('root-actions');
  for(const e of rootRows){const n=nodes.get(e.childId),button=document.createElement('button');
    button.className='action-row'+(n?.label===selected?' silver-choice':'');
    const name=document.createElement('span'),stats=document.createElement('span');
    name.className='action-title';stats.className='action-stats';
    name.textContent=n?.label||'Action #'+n?.actionId;
    stats.textContent='n '+e.visits+' · Q '+(n?.q==null?'—':n.q.toFixed(3))+
      ' · prior '+(n?.prior==null?'—':n.prior.toFixed(3));
    button.append(name,stats);button.onclick=()=>inspect({kind:'node',id:e.childId});pane.append(button);
    const option=document.createElement('option');option.value=e.id;option.textContent=name.textContent;
    $('root-filter').append(option);
  }
  $('root-filter').onchange=event=>{controls.rootFilter=event.target.value||null;refresh();};
  for(const [id,key] of [['depth','depth'],['top-k','topK'],['min-visits','minVisits']])
    $(id).onchange=event=>{controls[key]=Math.max(key==='minVisits'?0:1,Number(event.target.value)||0);refresh();};
  $('direction').onchange=event=>{controls.direction=event.target.value;refresh();};
  $('root').onclick=()=>{history=[];controls.focus=null;refresh();};
  $('back').onclick=()=>{controls.focus=history.pop()||null;refresh();};
  $('fit').onclick=()=>refresh();
  $('zoom-in').onclick=()=>d3.select(canvas).call(zoom.scaleBy,1.3);
  $('zoom-out').onclick=()=>d3.select(canvas).call(zoom.scaleBy,1/1.3);
  $('fullscreen').onclick=()=>document.body.classList.toggle('graph-fullscreen');
  $('search').oninput=event=>{const query=event.target.value.toLowerCase(),results=$('search-results');
    results.replaceChildren();if(!query)return;
    for(const n of [...nodes.values()].filter(n=>n.id===query||label(n).toLowerCase().includes(query)).slice(0,12)){
      const b=document.createElement('button');b.textContent=label(n)+' · #'+n.id;
      b.onclick=()=>{history.push(controls.focus);controls.focus=n.id;controls.expanded.add(n.id);
        inspect({kind:'node',id:n.id});refresh();results.replaceChildren();};results.append(b);}
  };
  inspect(null);refresh();
})();
