'use strict';
const handbook = JSON.parse(document.getElementById('handbook-data').textContent);
const byId = id => document.getElementById(id);
const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => Number.isFinite(value) ? new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(value/100) : 'Not recorded';
const flowKeys = Object.keys(handbook.flows);
let selectedNode = 'F04';
let currentFlow = 'F04';
let journeyIndex = 0;
let stepIndex = 0;
const NS = 'http://www.w3.org/2000/svg';

function element(name, attrs = {}, text = '') {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text) node.textContent = text;
  return node;
}
function statusText(counts) {
  return ['W','M','P','?'].map(code => `${code}: ${counts?.[code] ?? 0}`).join(' · ');
}
function activitiesFor(flow) {
  return handbook.activities.filter(a => a.id.split('.')[0] === flow);
}
function processDetail(flow) {
  const p = handbook.processes[flow];
  const activities = activitiesFor(flow);
  const evidence = ['V','D','U'].map(code => `${code}: ${activities.filter(a=>a.ev===code).length}`).join(' · ');
  byId('node-detail').innerHTML = `<p class="eyebrow">${safe(flow)} · Repository synthesis</p><h3>${safe(handbook.flows[flow].name)}</h3>
    <dl><dt>Trigger</dt><dd>${safe(p.trigger)}</dd><dt>Handoffs</dt><dd>${safe(p.path)}</dd><dt>Business record</dt><dd>${safe(p.record)}</dd><dt>Control</dt><dd>${safe(p.control)}</dd></dl>
    <p>${activities.length} activity definitions · ${safe(evidence)} · ${activities.filter(a=>a.fut).length} future activities.</p>
    <p class="source-note">Activity evidence labels are source-research labels, not test passes. Reference keys: ${p.sources.map(k=>`<a href="#source-${safe(k)}">${safe(k)}</a>`).join(' · ')}.</p>
    <button id="show-role-map">Inspect role handoffs</button><p><a href="#process-${flow}">Read the field note →</a>${flow==='F04'?'<br><a href="#replays">See recorded claim journeys →</a>':''}</p>`;
  byId('show-role-map').addEventListener('click', () => {byId('map-view').value='roles'; selectedNode=''; renderMap();});
}
function roleDetail(role) {
  const record = handbook.inventory.stakeholders[role];
  const activities = activitiesFor(currentFlow).filter(a=>a.actor===role);
  byId('node-detail').innerHTML = `<p class="eyebrow">${safe(role)}</p><h3>${safe(record.name)}</h3><p>${safe(record.group)}</p>
    <h4>Endpoint inventory snapshot</h4><p>${safe(statusText(record.endpoints))}</p><p class="source-note">W working POC · M mock · P planned · ? unclear. Counts are for the role across the generated inventory, not only this process, and do not establish passing tests.</p>
    <h4>${safe(currentFlow)} activities</h4><ul>${activities.map(a=>`<li><strong>${safe(a.id)}</strong><br>${safe(a.does)}<br><small>Evidence ${safe(a.ev||'?')} · Reference ${safe(Array.isArray(a.src)?a.src.join(', '):a.src||'unspecified')}${a.fut?' · FUTURE / PLANNED':''}</small>${a.next?.length?`<br><small>Next reference(s): ${safe(a.next.join(', '))}</small>`:''}</li>`).join('')}</ul>
    <p class="source-note">Multiple next references may be alternatives. Some handoffs cross process families and are listed here even when they lie outside the current graph.</p>`;
}
function serviceDetail(service) {
  const flows = flowKeys.filter(flow=>handbook.processes[flow].services.includes(service));
  byId('node-detail').innerHTML = `<p class="eyebrow">POC service ownership synthesis</p><h3>${safe(service)}</h3><p>The handbook associates this service with the following process families:</p><ul>${flows.map(f=>`<li><a href="#process-${f}">${f} · ${safe(handbook.flows[f].name)}</a></li>`).join('')}</ul><p class="source-note">This view is a curated ownership map, not a trace of every endpoint, event consumer or running production service. Inspect service code and contracts for exact implementation.</p>`;
}
function nodesAndEdges() {
  const view = byId('map-view').value;
  if (view === 'landscape') {
    return {nodes: flowKeys.map(key=>({id:key,label:handbook.processes[key].short,kicker:key,sub:'Process family',kind:'process',search:handbook.flows[key].name+' '+handbook.processes[key].path})),
      edges: [['F01','F02'],['F02','F03'],['F03','F04'],['F04','F05'],['F04','F08'],['F06','F07'],['F09','F03'],['F10','F02'],['F11','F04'],['F12','F13'],['F14','F13']].map(([from,to])=>({from,to,inferred:false})),
      note:'Conceptual process connections; not a transaction sequence or recorded execution.'};
  }
  if (view === 'services') {
    const services = handbook.processes[currentFlow].services;
    return {nodes:[{id:currentFlow,label:handbook.processes[currentFlow].short,kicker:currentFlow,sub:'Selected process',kind:'process'},...services.map(id=>({id,label:id.replace('-service',''),kicker:'SERVICE',sub:id,kind:'service'}))],
      edges:services.map(to=>({from:currentFlow,to,inferred:false})),note:'Curated POC ownership associations. No runtime dependency or production completeness is asserted.'};
  }
  const activities = activitiesFor(currentFlow);
  const actorIds = [...new Set(activities.map(a=>a.actor))];
  const activityLookup = new Map(handbook.activities.map(a=>[a.id,a]));
  const edges = new Map();
  for (const a of activities) for (const next of (a.next || [])) {
    const b = activityLookup.get(next);
    if (!b || b.id.split('.')[0] !== currentFlow || b.actor === a.actor) continue;
    const key = a.actor+'|'+b.actor;
    const inferred = a.ev==='U' || b.ev==='U';
    if (!edges.has(key)) edges.set(key,{from:a.actor,to:b.actor,inferred});
    else if (inferred) edges.get(key).inferred=true;
  }
  return {nodes:actorIds.map(id=>({id,label:handbook.inventory.stakeholders[id].name,kicker:id,sub:`${activities.filter(a=>a.actor===id).length} activity definitions`,kind:'role',search:activities.filter(a=>a.actor===id).map(a=>a.does).join(' ')})),
    edges:[...edges.values()],note:'Grouped actors from activity definitions. Arrows combine documented next references; alternative branches are not necessarily executed together. Cross-family references are in node details.'};
}
function wrapLabel(label, max=26) {
  const words = label.split(/\s+/);
  const lines = [''];
  for (const word of words) {
    if ((lines[lines.length-1]+' '+word).trim().length>max && lines[lines.length-1]) lines.push(word);
    else lines[lines.length-1]=(lines[lines.length-1]+' '+word).trim();
  }
  return lines.slice(0,2).map((line,i)=>i===1 && lines.length>2 ? line.slice(0,max-1)+'…' : line.length>max?line.slice(0,max-1)+'…':line);
}
function renderMap() {
  currentFlow=byId('map-flow').value;
  const view=byId('map-view').value;
  if (view==='landscape') selectedNode=currentFlow;
  const graph=nodesAndEdges();
  const needle=byId('map-search').value.trim().toLowerCase();
  const matches=graph.nodes.filter(n=>`${n.id} ${n.label} ${n.search||''}`.toLowerCase().includes(needle));
  const matchIds=new Set(matches.map(n=>n.id));
  const svg=byId('map');
  svg.replaceChildren();
  const columns=3, width=900, nodeWidth=260, nodeHeight=105, gapY=45, offset=25;
  const rows=Math.ceil(graph.nodes.length/columns);
  svg.setAttribute('viewBox',`0 0 ${width} ${Math.max(260,rows*(nodeHeight+gapY)+25)}`);
  const defs=element('defs');
  const marker=element('marker',{id:'arrowhead',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
  marker.append(element('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#8399aa'}));defs.append(marker);svg.append(defs);
  const positions=new Map(graph.nodes.map((n,i)=>[n.id,{x:offset+(i%columns)*300,y:offset+Math.floor(i/columns)*(nodeHeight+gapY)}]));
  for(const edge of graph.edges){
    const a=positions.get(edge.from),b=positions.get(edge.to);
    if(!a||!b)continue;
    const startX=a.x+nodeWidth/2,startY=a.y+nodeHeight,endX=b.x+nodeWidth/2,endY=b.y;
    const bend=(startY+endY)/2;
    const path=element('path',{d:`M${startX},${startY} C${startX},${bend} ${endX},${bend} ${endX},${endY}`,class:'graph-edge'+(edge.inferred?' inferred':''),'marker-end':'url(#arrowhead)'});
    if(needle && (!matchIds.has(edge.from)||!matchIds.has(edge.to)))path.setAttribute('opacity','.15');
    path.append(element('title',{},`${edge.from} → ${edge.to}${edge.inferred?' · includes inferred activity':''}`));svg.append(path);
  }
  for(const node of graph.nodes){
    const {x,y}=positions.get(node.id);
    const group=element('g',{class:'map-node'+(selectedNode===node.id?' selected':'')+(!matchIds.has(node.id)?' dimmed':''),transform:`translate(${x} ${y})`,tabindex:0,role:'button','aria-label':`${node.id}: ${node.label}; inspect details`,'aria-pressed':selectedNode===node.id?'true':'false','data-node':node.id});
    group.append(element('rect',{width:nodeWidth,height:nodeHeight,rx:3}));
    group.append(element('text',{x:14,y:23,class:'node-kicker'},node.kicker.length>31?node.kicker.slice(0,30)+'…':node.kicker));
    const lines=wrapLabel(node.label);
    lines.forEach((line,i)=>group.append(element('text',{x:14,y:49+i*19,class:'node-title'},line)));
    group.append(element('text',{x:14,y:90,class:'node-sub'},node.sub));
    group.append(element('title',{},`${node.id} · ${node.label}`));
    const choose=()=>{
      selectedNode=node.id;
      if(node.kind==='process'){currentFlow=node.id;byId('map-flow').value=node.id;}
      renderMap();
      if(node.kind==='role')roleDetail(node.id);else if(node.kind==='service')serviceDetail(node.id);else processDetail(node.id);
      // Re-rendered SVG nodes retain keyboard focus for a coherent tab order.
      svg.querySelector(`[data-node="${CSS.escape(node.id)}"]`)?.focus({preventScroll:true});
    };
    group.addEventListener('click',choose);
    group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose();}});
    svg.append(group);
  }
  byId('map-status').textContent=`${matches.length} / ${graph.nodes.length} nodes match · ${graph.edges.length} connections. ${graph.note}`;
  if(view==='landscape'||!graph.nodes.some(n=>n.id===selectedNode)){selectedNode=currentFlow;processDetail(currentFlow);}
  else {const n=graph.nodes.find(n=>n.id===selectedNode);if(n.kind==='role')roleDetail(n.id);else if(n.kind==='service')serviceDetail(n.id);else processDetail(n.id);}
}

for(const key of flowKeys){const option=document.createElement('option');option.value=key;option.textContent=`${key} · ${handbook.processes[key].short}`;byId('map-flow').append(option);}
byId('map-flow').value=currentFlow;
for(const id of ['map-view','map-flow'])byId(id).addEventListener('change',()=>{selectedNode='';renderMap();});
byId('map-search').addEventListener('input',renderMap);
byId('map-clear').addEventListener('click',()=>{byId('map-search').value='';renderMap();});
document.querySelectorAll('[data-flow]').forEach(link=>link.addEventListener('click',()=>{byId('map-flow').value=link.dataset.flow;byId('map-view').value='roles';byId('map-search').value='';selectedNode='';renderMap();}));

function renderRoles(){
  const needle=byId('role-search').value.toLowerCase();
  const roles=Object.entries(handbook.inventory.stakeholders).filter(([id,r])=>`${id} ${r.name} ${r.group}`.toLowerCase().includes(needle));
  byId('role-rows').innerHTML=roles.map(([id,r])=>`<tr><th scope="row"><code>${safe(id)}</code><br>${safe(r.name)}</th><td>${safe(r.group)}</td><td>${safe(statusText(r.endpoints))}</td></tr>`).join('');
  byId('role-status').textContent=`${roles.length} / ${Object.keys(handbook.inventory.stakeholders).length} catalogue entries`;
}
byId('role-search').addEventListener('input',renderRoles);

function renderReplay(){
  const journey=handbook.replays[journeyIndex], step=journey.steps[stepIndex], lc=journey.lifecycle;
  byId('replay-summary').className='replay-summary';
  byId('replay-summary').innerHTML=`<p class="eyebrow">Verified synthetic capture · ${safe(journey.finished_at)}</p><h3>${safe(journey.title)}</h3><p>${safe(journey.lesson)}</p><div class="replay-facts"><span>${safe(lc.claim_id)}</span><span>Final outcome: ${safe(lc.outcome)}</span><span>${journey.steps.length} business captures / ${journey.original_step_count} original steps</span></div><p class="source-note">Cases: ${safe(lc.case_ids.join(', '))}. Data partition: ${safe(lc.data)}.</p>`;
  byId('replay-position').textContent=`Capture ${stepIndex+1} / ${journey.steps.length} · Original step ${step.number}`;
  byId('replay-prev').disabled=stepIndex===0;
  byId('replay-next').disabled=stepIndex===journey.steps.length-1;
  byId('replay-timeline').replaceChildren();
  for(let i=0;i<journey.steps.length;i++){
    const recorded=journey.steps[i],li=document.createElement('li'),button=document.createElement('button');
    button.textContent=String(recorded.number);button.title=`Original step ${recorded.number}: ${recorded.role} · ${recorded.title}`;
    button.setAttribute('aria-label',button.title);if(i===stepIndex)button.setAttribute('aria-current','step');
    button.addEventListener('click',()=>{stepIndex=i;renderReplay();byId('replay-timeline').querySelector('[aria-current]')?.focus({preventScroll:true});});
    li.append(button);byId('replay-timeline').append(li);
  }
  byId('replay-caption').innerHTML=`<p class="eyebrow">Original step ${step.number} · ${safe(step.role)}</p><h4>${safe(step.title)}</h4><p>${safe(step.instruction)}</p><p><strong>Recorded expected result:</strong> ${safe(step.expected)}</p>${step.observations.length?`<div class="observed"><strong>Asserted observations at this step</strong>${step.observations.map(o=>`<p>${safe(o.stage)}: ${safe(o.value)}</p>`).join('')}</div>`:'<p class="source-note">This capture provides screen context. No separate lifecycle observation was recorded at this exact step.</p>'}`;
  byId('replay-image').src=step.image;
  byId('replay-image').alt=`${journey.title} — original step ${step.number}, ${step.role}: ${step.title}`;
  byId('replay-evidence').innerHTML=`<p>Outcome: <strong>${safe(lc.outcome)}</strong>. Opening PF balance: ${money(lc.opening_balance_paise)}; closing observed PF balance: ${money(lc.closing_balance_paise)}.</p><p>Recorded amount: ${money(lc.amount_paise)}. Gross: ${money(lc.gross_paise)}; simulated TDS: ${money(lc.tds_paise)}; net: ${money(lc.net_paise)}.</p><p>Balances belong to each case’s point in a sequential synthetic run. They are not a newly seeded balance for every replay.</p><p class="source-note">Original manifest: ${safe(journey.manifest)}<br>Captured: ${safe(step.captured_at)}<br>Original PNG SHA-256: ${safe(step.sha256)}<br>Manifest SHA-256: ${safe(journey.manifest_sha256)}</p><h4>Manifest limitations</h4><ul>${journey.limitations.map(l=>`<li>${safe(l)}</li>`).join('')}</ul>`;
}
handbook.replays.forEach((journey,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`${index+1}. ${journey.title}`;byId('replay-select').append(option);});
byId('replay-select').addEventListener('change',()=>{journeyIndex=Number(byId('replay-select').value);stepIndex=0;renderReplay();});
byId('replay-prev').addEventListener('click',()=>{if(stepIndex>0){stepIndex--;renderReplay();}});
byId('replay-next').addEventListener('click',()=>{if(stepIndex<handbook.replays[journeyIndex].steps.length-1){stepIndex++;renderReplay();}});
byId('replay-open').href='#screenshot-dialog';
byId('replay-open').addEventListener('click',event=>{event.preventDefault();byId('screenshot-full').src=byId('replay-image').src;byId('screenshot-full').alt=byId('replay-image').alt;byId('screenshot-dialog').showModal();});
byId('screenshot-close').addEventListener('click',()=>byId('screenshot-dialog').close());

function filterGlossary(){let count=0;const needle=byId('glossary-search').value.toLowerCase();for(const row of document.querySelectorAll('#glossary-table tbody tr')){row.hidden=!row.textContent.toLowerCase().includes(needle);if(!row.hidden)count++;}byId('glossary-status').textContent=`${count} / ${handbook.glossary.length} terms`;}
byId('glossary-search').addEventListener('input',filterGlossary);
window.preparePrint=()=>{
  document.querySelector('.map-alternative').open=true;
  for(const row of document.querySelectorAll('#glossary-table tbody tr'))row.hidden=false;
  for(const image of document.querySelectorAll('.print-frame img')){
    const journey=handbook.replays.find(r=>r.scenario===image.dataset.replay);
    image.src=journey.steps.find(s=>s.number===Number(image.dataset.step)).image;
  }
};
window.addEventListener('beforeprint',window.preparePrint);
window.addEventListener('afterprint',filterGlossary);
byId('print').addEventListener('click',async()=>{window.preparePrint();await Promise.all([...document.querySelectorAll('.print-frame img')].map(i=>i.decode()));window.print();});
const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+entry.target.id));}},{rootMargin:'-100px 0px -65% 0px'});
document.querySelectorAll('main>section[id]').forEach(section=>observer.observe(section));
renderMap();
// Freeze a landscape for printing, independent of later filters / selections.
const printMap=byId('map').cloneNode(true);printMap.id='print-map';
printMap.querySelector('#arrowhead').id='print-arrowhead';
printMap.querySelectorAll('[marker-end]').forEach(path=>path.setAttribute('marker-end','url(#print-arrowhead)'));
printMap.querySelectorAll('[tabindex]').forEach(node=>{node.removeAttribute('tabindex');node.removeAttribute('role');node.removeAttribute('aria-pressed');node.classList.remove('selected');});
byId('print-landscape').append(printMap);
renderRoles();renderReplay();filterGlossary();
