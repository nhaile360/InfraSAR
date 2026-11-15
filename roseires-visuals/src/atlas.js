const map=$("map"), mapBox=$("map-frame"), context=map.getContext("2d");
const mini=$("locator"), miniContext=mini.getContext("2d");
const toolState={view:"swipe",layer:"radar",change:"water",rule:"local",split:56,overview:false,
  focus:"A",points:{A:null,B:null},examples:{A:null,B:null},chosen:null,patch:null,cam:{...inlet,span:4300},
  pairByLayer:{},time:0,events:[],timer:null,ready:false};
const mapNames={radar:"Radar image",water:"Water map",delta:"Radar signal change",agreement:"Agreement"};
const palettes={
  water:{1:[191,184,149],2:[28,90,111],3:[85,210,204],4:[186,139,201],
    5:[66,85,80],6:[239,236,224],7:[92,82,118],8:[211,161,109],9:[138,148,137],10:[211,161,109]},
  agreement:{1:[183,187,160],2:[45,177,157],3:[120,112,194],4:[203,119,77],5:[214,168,71],
    6:[175,76,107],7:[101,156,185],8:[86,99,92],9:[211,161,109]}
};
const patterns={5:"cross",6:"dots",7:"diag",8:"diag",9:"cross",10:"diag"};
const agreementNames={1:"Both stable",2:"Both show water gain",3:"Both show water loss",4:"Radar missed optical change",
  5:"Radar change only",6:"Opposite changes",7:"Radar change · optical unavailable",
  8:"Optical reference unavailable",9:"Radar unclear"};
let rasterCache=new WeakMap(), changeCache=null, baseMask=null, stagedTiffs={}, drawing=0;
let remoteBusy=false;
let terrain=null;
const drawFont = '700 12px "DM Sans","Avenir Next",system-ui,sans-serif';

function baseImages(){
  const server="https://services.arcgisonline.com/ArcGIS/rest/services/";
  const w=contextBounds.east-contextBounds.west,h=contextBounds.north-contextBounds.south;
  const p=new URLSearchParams({bbox:[contextBounds.west,contextBounds.south,contextBounds.east,contextBounds.north].join(","),
    bboxSR:"32636",imageSR:"32636",size:"1100,"+Math.round(1100*h/w),format:"jpg",f:"image"});
  const image=new Image();
  image.onload=()=>{terrain=image;requestDraw()};
  image.src=server+"World_Shaded_Relief/MapServer/export?"+p;
}
function redrawTo(canvas){
  const ratio=Math.min(devicePixelRatio||1,2);
  const width=canvas.clientWidth,height=canvas.clientHeight;
  if(!width||!height)return null;
  if(canvas.width!==Math.round(width*ratio)||canvas.height!==Math.round(height*ratio)){
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
  }
  const c=canvas.getContext("2d");
  c.setTransform(ratio,0,0,ratio,0,0);
  return {ctx:c,width,height};
}
function transform(cam,width,height){
  const factor=width/cam.span;
  return {width,height,factor, xy:p=>[width/2+(p.x-cam.x)*factor,height/2-(p.y-cam.y)*factor],
    location:(x,y)=>({x:cam.x+(x-width/2)/factor,y:cam.y-(y-height/2)/factor})};
}
function fitSpan(widthMeters,heightMeters,w,h){return Math.max(widthMeters,heightMeters*w/h)}
function resetCamera(reservoir){
  toolState.overview=reservoir;
  if(reservoir){
    toolState.cam={x:653500,y:1300220,span:fitSpan(17900,13200,map.clientWidth,map.clientHeight)};
  }else{
    toolState.cam={...(toolState.patch?.center||inlet),span:fitSpan(3650,2850,map.clientWidth,map.clientHeight)};
  }
  $("extent").textContent=reservoir?"Show inlet":"Show reservoir";
  requestDraw();
}
function rasterImage(data,kind){
  if(!data)return null;
  let styles=rasterCache.get(data);
  if(!styles){styles={};rasterCache.set(data,styles)}
  if(styles[kind])return styles[kind];
  const canvas=document.createElement("canvas");
  canvas.width=grid.width;canvas.height=grid.height;
  const ctx=canvas.getContext("2d"), image=ctx.createImageData(grid.width,grid.height);
  for(let i=0;i<size;i++){
    const value=data[i], factor=i*4, x=i%grid.width, y=Math.floor(i/grid.width);
    let rgb, opacity=255, pattern;
    if(kind==="radar"){
      if(Number.isFinite(value)){
        const level=clamp((value+24)/19,0,1);
        rgb=[Math.round(25+level*213),Math.round(32+level*204),Math.round(32+level*197)];
      }else{rgb=palettes.water[5];pattern="cross"}
    }else if(kind==="delta"){
      if(!Number.isFinite(value)){rgb=palettes.water[5];pattern="cross"}
      else{
        const neutral=[230,225,197], strength=clamp((Math.abs(value)-.7)/11.3,0,1);
        const end=value<0?[37,101,156]:[171,74,34];
        rgb=neutral.map((v,k)=>Math.round(v+(end[k]-v)*strength));
      }
    }else if(kind==="context"){
      if(value!==2){opacity=0;rgb=[0,0,0]}
      else{rgb=[101,154,163];opacity=195}
    }else{
      rgb=palettes[kind][value]||palettes.water[8];
      pattern=kind==="water"?patterns[value]:({7:"diag",8:"cross",9:"dots"})[value];
    }
    const marked=pattern==="dots"?x%4===0&&y%4===0:
      pattern==="diag"?(x+y)%7<2:pattern==="cross"&&((x+y)%9===0||(x-y+900)%9===0);
    const shift=marked?(rgb[0]>150?-48:63):0;
    image.data[factor]=rgb[0]+shift;image.data[factor+1]=rgb[1]+shift;image.data[factor+2]=rgb[2]+shift;
    image.data[factor+3]=opacity;
  }
  ctx.putImageData(image,0,0);styles[kind]=canvas;return canvas;
}
function drawGeo(c,t,image,box,opacity=1){
  if(!image)return;
  const [x,y]=t.xy({x:box.west,y:box.north});
  c.save();c.globalAlpha=opacity;
  c.drawImage(image,x,y,(box.east-box.west)*t.factor,(box.north-box.south)*t.factor);
  c.restore();
}
function mapText(c,text,x,y,{color="#234643",font=drawFont,align="left",background=true}={}){
  c.save();c.font=font;c.textAlign=align;c.textBaseline="middle";
  if(background){
    const w=c.measureText(text).width, start=align==="center"?x-w/2:align==="right"?x-w:x;
    c.fillStyle="#f8f8edec";c.fillRect(start-4,y-8,w+8,16);
  }
  c.fillStyle=color;c.fillText(text,x,y);c.restore();
}
function drawContext(c,t,isMini=false){
  c.fillStyle="#dce2d5";c.fillRect(0,0,t.width,t.height);
  c.imageSmoothingEnabled=true;
  drawGeo(c,t,terrain,contextBounds,.52);
  const water=pilotWater()[1]?.states||loaded.pairs.get("pilot")?.candidates.local;
  c.imageSmoothingEnabled=false;
  drawGeo(c,t,rasterImage(water,"context"),crop);
  c.strokeStyle="#536c5f95";c.setLineDash([4,4]);c.lineWidth=1;
  const [x,y]=t.xy({x:crop.west,y:crop.north});
  if(!isMini)c.strokeRect(x,y,(crop.east-crop.west)*t.factor,(crop.north-crop.south)*t.factor);
  c.setLineDash([]);
}
function drawContextLabels(c,t,isMini=false){
  const [dx,dy]=t.xy(dam), [tx,ty]=t.xy(town);
  const p=toolState.patch?.center||inlet, [ix,iy]=t.xy(p);
  if(Number.isFinite(dx)&&Number.isFinite(dy)){
    c.fillStyle="#b26942";c.strokeStyle="#fffdf0";c.lineWidth=1.5;
    c.fillRect(dx-4,dy-4,8,8);c.strokeRect(dx-4,dy-4,8,8);
    mapText(c,"Roseires Dam",dx+8,dy-8,{font:isMini?'700 10px system-ui':drawFont});
  }
  if(!isMini){
    c.fillStyle="#56726a";c.beginPath();c.arc(tx,ty,3,0,Math.PI*2);c.fill();
    mapText(c,"Ad Damazin",tx-7,ty+9,{align:"right"});
  }
  if(isMini||toolState.overview){
    c.beginPath();c.arc(ix,iy,4,0,Math.PI*2);c.fillStyle="#2a7b70";c.fill();
    c.strokeStyle="#fff";c.stroke();
    mapText(c,"Study inlet",ix-8,iy+9,{align:"right",font:isMini?'700 10px system-ui':drawFont});
    const [wx,wy]=t.xy({x:653900,y:1301800});
    mapText(c,"Blue Nile",wx,wy,{color:"#275e73",font:isMini?'italic 10px system-ui':'italic 12px system-ui'});
  }
}
function patchOutline(c,t){
  const patch=toolState.patch;
  if(!patch||toolState.overview||t.factor<.08)return;
  const n=grid.width;
  c.beginPath();
  for(const i of patch.cells){
    const point=pointFrom(i), [x,y]=t.xy({x:point.x-cell/2,y:point.y+cell/2}), w=cell*t.factor;
    if(!patch.mask[i-n]){c.moveTo(x,y);c.lineTo(x+w,y)}
    if(!patch.mask[i+n]){c.moveTo(x,y+w);c.lineTo(x+w,y+w)}
    if(i%n===0||!patch.mask[i-1]){c.moveTo(x,y);c.lineTo(x,y+w)}
    if(i%n===n-1||!patch.mask[i+1]){c.moveTo(x+w,y);c.lineTo(x+w,y+w)}
  }
  c.strokeStyle="#303229";c.lineWidth=4;c.stroke();c.strokeStyle="#ffcf71";c.lineWidth=2;c.stroke();
}
function selectedPair(kind){
  const saved=toolState.pairByLayer[kind];
  if(saved?.length===2&&saved.every(day=>loaded[kind].has(day)))return saved.map(day=>loaded[kind].get(day));
  return kind==="radar"?pilotRadar():pilotWater();
}
function displayRaster(c,t,row){
  if(row)drawGeo(c,t,rasterImage(row.type==="water"?row.states:row.raw,row.type),crop);
}
function changes(){
  if(changeCache)return changeCache;
  const [a,b]=pilotRadar(), rows=pilotWater();
  const delta=Float32Array.from(b.raw,(value,i)=>value-a.raw[i]), water=rows.length===2?waterChange(...rows):null;
  const {candidates}=loaded.pairs.get("pilot");
  const compare={};
  if(water)for(const rule of ["fixed","local"])if(candidates[rule])compare[rule]=agreement(candidates[rule],water);
  changeCache={delta,water,compare};return changeCache;
}
function changeLayer(){
  const c=changes(), kind=toolState.change;
  if(kind==="water")return c.water;
  if(kind==="delta")return c.delta;
  return c.compare[toolState.rule];
}
function requestDraw(){
  if(!drawing)drawing=requestAnimationFrame(draw);
}
function draw(){
  drawing=0;
  if(!toolState.ready)return;
  const frame=redrawTo(map);
  if(!frame)return;
  const t=transform(toolState.cam,frame.width,frame.height), width=t.width,height=t.height;
  drawContext(context,t);
  if(toolState.view==="swipe"){
    const [a,b]=selectedPair(toolState.layer), split=toolState.split*width/100;
    context.save();context.beginPath();context.rect(0,0,split,height);context.clip();displayRaster(context,t,a);context.restore();
    context.save();context.beginPath();context.rect(split,0,width-split,height);context.clip();displayRaster(context,t,b);context.restore();
    $("divider").style.left=toolState.split+"%";
  }else if(toolState.view==="change"){
    drawGeo(context,t,rasterImage(changeLayer(),toolState.change),crop);
  }else if(toolState.view==="timeline"){
    const current=toolState.events[toolState.time];
    if(current?.record)displayRaster(context,t,current.record);
  }else{
    const rows=pilotWater();
    displayRaster(context,t,toolState.layer==="water"?rows[1]:pilotRadar()[1]);
  }
  drawContextLabels(context,t);
  patchOutline(context,t);
  if(toolState.chosen!==null&&toolState.view!=="points"){
    const [x,y]=t.xy(pointFrom(toolState.chosen));
    context.strokeStyle="#fffdf3";context.lineWidth=2;
    context.beginPath();context.arc(x,y,6,0,Math.PI*2);context.stroke();
  }
  for(const key of ["A","B"]){
    const pin=$("pin-"+key.toLowerCase()), value=toolState.points[key];
    const show=(toolState.view==="points"||toolState.view==="timeline")&&value!==null;
    const xy=show?t.xy(pointFrom(value)):null;
    pin.hidden=!xy||xy[0]<12||xy[0]>width-12||xy[1]<18||xy[1]>height-8;
    if(pin.hidden)continue;
    pin.style.left=xy[0]+"px";pin.style.top=xy[1]+"px";pin.dataset.active=String(toolState.focus===key);
  }
  const meters=[50,100,200,500,1000,2000,5000,10000].filter(x=>x*t.factor<width*.25).at(-1)||50;
  $("scale").textContent=meters>=1000?meters/1000+" km":meters+" m";
  $("scale").style.width=meters*t.factor+"px";
  $("credit").textContent=terrain?"Map context · Esri, USGS, GeoNames, OpenStreetMap":"Map context · GeoNames, OpenStreetMap";
  drawLocator();
}
function drawLocator(){
  const dim=redrawTo(mini);
  if(!dim)return;
  const cam={x:654400,y:1300260,span:fitSpan(16600,12300,dim.width,dim.height)};
  const t=transform(cam,dim.width,dim.height);
  drawContext(miniContext,t,true);
  drawContextLabels(miniContext,t,true);
  if(map.clientWidth){
    const cam=toolState.cam, hz=cam.span/2, vt=hz*map.clientHeight/map.clientWidth;
    const [x,y]=t.xy({x:cam.x-hz,y:cam.y+vt});
    miniContext.strokeStyle="#164b46";miniContext.lineWidth=1.6;
    miniContext.strokeRect(x,y,2*hz*t.factor,2*vt*t.factor);
  }
}

function node(tag,text,klass){
  const elem=document.createElement(tag);
  if(text!=null)elem.textContent=text;
  if(klass)elem.className=klass;
  return elem;
}
function link(label,href){
  const a=node("a",label);a.href=href;a.target="_blank";a.rel="noopener";return a;
}
function legendChip(label,swatch,pattern){
  const item=node("span",null,"legend-item"), square=node("i");
  square.setAttribute("aria-hidden","true");
  const color=Array.isArray(swatch)?"rgb("+swatch.join(",")+")":swatch;
  square.style.background=pattern==="dots" ? "radial-gradient(#49544a 19%,transparent 23%) 0 0/5px 5px,"+color :
    pattern==="diag" ? "repeating-linear-gradient(135deg,#304d4a64 0 2px,transparent 2px 5px),"+color :
    pattern==="cross" ? "repeating-linear-gradient(135deg,#fff5 0 1px,transparent 1px 5px),repeating-linear-gradient(45deg,#fff5 0 1px,transparent 1px 5px),"+color : color;
  item.append(square,node("span",label));return item;
}
function updateLegend(){
  const legend=$("legend"), isChange=toolState.view==="change";
  const current=toolState.events[toolState.time];
  const kind=isChange?toolState.change:toolState.view==="timeline"?current?.record?.type:toolState.layer;
  const note=text=>node("span",text,"line-note");
  legend.replaceChildren();
  if(kind==="radar"||kind==="delta"){
    const ramp=node("span",null,"ramp");
    if(kind==="radar"){
      ramp.style.background="linear-gradient(90deg,#192020,#ececde)";
      legend.append(node("strong","Radar image"),node("span","Weaker return · −24 dB"),ramp,node("span","Stronger return · −5 dB"),
        note("Radar return is how much of the signal bounced back to the satellite."));
    }else{
      ramp.style.background="linear-gradient(90deg,#25659c,#e6e1c5,#ab4a22)";
      legend.append(node("strong","Radar signal change"),node("span","Weaker · −12 dB"),ramp,node("span","Stronger · +12 dB"),
        note("Little change near 0 dB. October minus August radar return."));
    }
  }else if(kind==="agreement"){
    legend.append(node("strong","Radar candidates vs. the water map"),...([2,3,4,5,6,7,8,9,1].map(i=>
      legendChip(agreementNames[i],palettes.agreement[i],({7:"diag",8:"cross",9:"dots"})[i]))),
    note(toolState.rule==="local"?"Radar rule uses a cutoff estimated from local reference areas.":"Radar rule marks returns at or below −17 dB as candidate water."));
  }else if(kind==="water"){
    const keys=isChange?[3,4,2,1,6,7,8,5,9]:[1,2,6,7,8,5,9];
    const label=i=>i===1&&isChange?"Land both dates":i===2&&isChange?"Water both dates":stateNames[i];
    legend.append(node("strong",isChange?"Water map change":"Water map"),...keys.map(i=>legendChip(label(i),palettes.water[i],patterns[i])));
  }else{
    legend.append(node("strong","Map context"),note("There is a reservoir height reading on this date. The map shows location only."));
  }
  if(toolState.patch)legend.append(legendChip("Outlined inlet patch","#ffcf71"));
  if((isChange&&kind!=="delta")||toolState.view==="points") {
    if(pilotWater().length===2)legend.append(note(currentCoverage()));
  }
  if(pilotWater().length<2 && (toolState.view==="swipe"||isChange||toolState.view==="points")){
    const button=node("button","Load water maps","outline");
    button.type="button";button.addEventListener("click",openData);
    legend.append(button);
  }
}
function currentCoverage(){
  const rows=pilotWater();
  if(rows.length!==2)return "Water maps are awaiting data.";
  const share=totalCoverage(rows);
  const all=rows.every(r=>tiles.every(t=>r.sources.some(s=>s.tile===t)&&r.tileRaw[t]));
  return (share*100).toFixed(1)+"% of the study crop has a usable water or land class on both dates. "+(all?
    "Tiles 36PXT and 36PXU are loaded for both dates.":"Coverage reflects the tiles currently loaded.");
}
function makeLayerButtons(){
  const parent=$("layers"), available=pilotWater().length===2;
  parent.replaceChildren();
  const candidates=loaded.pairs.get("pilot").candidates;
  let buttons=[];
  if(toolState.view==="swipe"||toolState.view==="points"){
    buttons=[["radar",mapNames.radar,true],["water",mapNames.water,available]];
  }else if(toolState.view==="change"){
    buttons=[["water","Water map change",available],["delta",mapNames.delta,true]];
    if(available&&(candidates.local||candidates.fixed))buttons.push(["agreement",mapNames.agreement,true]);
  }
  if(toolState.view==="timeline"){
    parent.append(node("span","Map follows the selected date","note"));return;
  }
  for(const [key,label,enabled] of buttons){
    const button=node("button",label);
    button.type="button";button.disabled=!enabled;
    button.setAttribute("aria-pressed",String(key===(toolState.view==="change"?toolState.change:toolState.layer)));
    button.addEventListener("click",()=>{
      if(toolState.view==="change")toolState.change=key;else toolState.layer=key;
      refreshControls();requestDraw();
    });
    parent.append(button);
  }
  if(toolState.view==="change"&&toolState.change==="agreement"&&candidates.local&&candidates.fixed){
    const button=node("button",toolState.rule==="local"?"Rule: local":"Rule: fixed");
    button.type="button";button.title="Switch the radar classification rule";
    button.addEventListener("click",()=>{toolState.rule=toolState.rule==="local"?"fixed":"local";refreshControls();requestDraw()});
    parent.append(button);
  }
}
function updateDates(){
  const a=$("before"), b=$("after");
  if(toolState.view==="swipe"){
    const [before,after]=selectedPair(toolState.layer);
    a.textContent=before?formatDate(before.time):"";
    b.textContent=after?formatDate(after.time):"";
  }else if(toolState.view==="timeline"){
    const current=toolState.events[toolState.time];
    a.textContent=current?formatDate(current.date):"";
    b.textContent=current?.record?(current.record.type==="water"?"Sentinel‑2":"NISAR"):"DAHITI";
  }else{
    a.textContent=toolState.view==="points"?"October · "+mapNames[toolState.layer]:"August → October 2026";
    b.textContent="";
  }
}
function coordinateReadout(index){
  const p=pointFrom(index);
  return "UTM 36N · "+p.x.toFixed(1)+" m E, "+p.y.toFixed(1)+" m N · cell "+(index%grid.width+1)+", "+(Math.floor(index/grid.width)+1);
}
function pointCompare(){
  const parent=$("points"), radar=pilotRadar(), water=pilotWater();
  parent.replaceChildren();
  for(const key of ["A","B"]){
    const i=toolState.points[key], same=i===toolState.examples[key];
    const section=node("section",null,"point-card"), title=node("h3","Point "+key,key.toLowerCase()+"-label");
    if(i!==null&&same&&key==="A"&&toolState.patch)title.append(" · Inlet");
    if(i!==null&&same&&key==="B")title.append(" · Stayed dry");
    section.append(title);
    if(i===null){
      section.append(node("p","Choose Point "+key+" and tap the map."));parent.append(section);continue;
    }
    const matrix=node("div",null,"point-values");
    for(const k of [0,1]){
      const card=node("div"), r=radar[k], w=water[k];
      card.append(node("strong",k?"October":"August"),node("span",w?stateNames[stateAt(w,i)]:"Water map unavailable"),
        node("small",w?"Sentinel‑2 · "+formatShort(w.time):"Sentinel‑2"),
        node("span",dbText(r.raw[i],2)),node("small","NISAR · "+formatShort(r.time)));
      matrix.append(card);
    }
    section.append(matrix);parent.append(section);
  }
}
function details(){
  const parent=$("methods"), pair=loaded.pairs.get("pilot");
  parent.replaceChildren(node("p",currentCoverage()),
    node("p","20 m cells on WGS 84 / UTM zone 36N. Sentinel‑2 scene classes were aligned with nearest-neighbor resampling. Only mapped vegetation or bare land count as land. Water is class 6."));
  const list=node("ul");
  for(const r of ordered("radar"))list.append(node("li","NISAR · "+showTime(r.time)+" · "+r.id));
  for(const w of ordered("water"))for(const r of w.sources)list.append(node("li","Sentinel‑2 · "+showTime(r.datetime||r.date)+" · "+r.id));
  const sources=node("p");
  sources.append(link("NISAR GCOV guide","https://hyp3-docs.asf.alaska.edu/nisar-docs/gcov/"),
    " · ",link("Sentinel‑2 processing and scene classes","https://sentiwiki.copernicus.eu/web/s2-processing"));
  parent.append(list,sources);
  if(pair.candidates.local||pair.candidates.fixed){
    parent.append(node("p","Radar candidates were generated from NISAR HH alone. The fixed rule uses −17 dB. The local rule uses a 3×3 median and compares reference water and land, with a 0.75 dB uncertainty band."));
  }
  const height=document.createElement("p");
  const estimates=pilotRadar().map(r=>estimateHeight(r.time));
  height.append(link("DAHITI station 216","https://dahiti.dgfi.tum.de/en/216/"),
    " · Radar-date estimates "+estimates.map(v=>v===null?"unavailable":v.toFixed(2)+" m").join(" and ")+
    ". Each is linearly interpolated between neighboring DAHITI observations. Heights describe the reservoir as a whole.");
  parent.append(height);
  for(const [name,idx] of [["Point A",toolState.points.A],["Point B",toolState.points.B],["Selected cell",toolState.chosen]]){
    if(idx===null)continue;
    const block=node("p",null);
    block.append(node("strong",name+" · "),coordinateReadout(idx));
    const values=node("ul");
    for(const r of ordered("radar")){
      const value=r.raw[idx], power=Number.isFinite(value)?(10**(value/10)).toPrecision(7):"missing";
      values.append(node("li",showTime(r.time)+" · HH "+dbText(value,4)+" · power "+power));
    }
    for(const w of ordered("water")){
      const v=w.raw[idx];
      const tileText=Object.entries(w.tileRaw).map(([tile,data])=>tile+" "+data[idx]).join(", ");
      values.append(node("li",showTime(w.time)+" · SCL "+v+" ("+(sclNames[v]||stateNames[stateAt(w,idx)])+")"+(tileText?" · "+tileText:"")));
    }
    parent.append(block,values);
  }
}
function updateEvidence(){
  const patch=toolState.patch, rows=pilotWater(), available=rows.length===2;
  $("patch-db").textContent=patch?dbText(patch.median):"−4.3 dB";
  $("patch-count").textContent=patch?"· "+patch.cells.length+" cells":"· 108 cells in the study";
  const agrees=patch&&available&&patch.cells.every(i=>rows[0].states[i]===1&&rows[1].states[i]===2);
  $("evidence-water").textContent=agrees
    ?"Sentinel‑2 mapped this patch as land in August and water in October."
    : patch&&available
      ?"The original Sentinel‑2 classification mapped this patch as land in August and water in October. The current mosaic adds observations from the neighboring tile."
      :"The pilot’s Sentinel‑2 classification mapped the outlined study patch as land in August and water in October.";
  $("follow-up").disabled=toolState.examples.B===null;
  if(toolState.examples.B===null)$("follow-up").title="Load Sentinel‑2 water maps to verify a dry comparison point.";
  else $("follow-up").removeAttribute("title");
}
function showSelected(){
  const section=$("selection"), i=toolState.chosen;
  section.hidden=i===null||toolState.view==="points"||toolState.view==="timeline";
  if(section.hidden)return;
  const rows=pilotWater(), [a,b]=pilotRadar();
  const water=rows.length===2?stateNames[rows[0].states[i]]+" → "+stateNames[rows[1].states[i]]:"Water map unavailable";
  const change=b.raw[i]-a.raw[i];
  section.replaceChildren(node("h3","Selected cell"),node("p","Water map · "+water),
    node("p","Radar signal change · "+dbText(change,2)),node("p",coordinateReadout(i)));
}
function refreshControls(){
  const view=toolState.view;
  for(const b of document.querySelectorAll("[data-view]"))b.setAttribute("aria-pressed",String(b.dataset.view===view));
  $("divider").hidden=view!=="swipe";
  $("timeline").hidden=view!=="timeline";
  $("point-section").hidden=view!=="points";
  $("evidence").hidden=view==="points";
  $("map").dataset.pick=String(view==="points"||view==="timeline");
  for(const b of document.querySelectorAll("[data-point]"))b.setAttribute("aria-pressed",String(b.dataset.point===toolState.focus));
  makeLayerButtons();updateDates();updateLegend();showSelected();
  if(view==="points")pointCompare();
  if(view==="timeline")updateTimeline();
}
function setView(view){
  if(!toolState.ready)return;
  if(toolState.view==="timeline"&&view!=="timeline")pause();
  toolState.view=view;
  if(view==="change"){
    if(!pilotWater().length&&toolState.change==="water")toolState.change="delta";
    if(toolState.change==="agreement"&&!changes().compare[toolState.rule])toolState.change=pilotWater().length?"water":"delta";
  }
  refreshControls();requestDraw();
}
function openData(){
  $("data-details").open=true;
  $("add-data").focus();
}
function setPoint(which,i){
  if(i<0||i>=size)return;
  toolState.focus=which;toolState.points[which]=i;
  for(const b of document.querySelectorAll("[data-point]"))b.setAttribute("aria-pressed",String(b.dataset.point===which));
  if(toolState.view==="points")pointCompare();
  if(toolState.view==="timeline")updateTimeline();
  if($("data-details").open)details();
  requestDraw();
}

function rebuildEvents(){
  const sensors=[...ordered("radar"),...ordered("water")];
  const first=Math.min(...sensors.map(r=>utc(r.time))),last=Math.max(...sensors.map(r=>utc(r.time)));
  const pad=6*86400000;
  const estimates=ordered("radar").map(r=>({datetime:r.time,meters:estimateHeight(r.time),estimated:true})).filter(h=>h.meters!==null);
  const observed=seed.heights.filter(h=>utc(h.datetime)>=first-pad&&utc(h.datetime)<=last+pad);
  const byTime=new Map();
  for(const h of [...observed,...estimates])byTime.set(utc(h.datetime),{date:h.datetime,height:h});
  for(const r of sensors)byTime.set(utc(r.time),{...(byTime.get(utc(r.time))||{}),date:r.time,record:r});
  const prior=toolState.events[toolState.time]?.date;
  toolState.events=[...byTime.values()].sort((a,b)=>utc(a.date)-utc(b.date));
  const desired=toolState.events.findIndex(e=>e.date===(prior||pilotRadar()[0].time));
  toolState.time=Math.max(0,desired);
  $("scrubber").max=toolState.events.length-1;
  setDateOptions();
}
function setDateOptions(){
  const kind=$("date-layer").value, records=ordered(kind);
  for(const [i,id] of ["date-start","date-end"].entries()){
    const selector=$(id);selector.replaceChildren();
    for(const r of records){
      const opt=node("option",formatDate(r.time));opt.value=r.time;selector.append(opt);
    }
    const preferred=selectedPair(kind)[i];
    if(preferred)selector.value=preferred.time;
  }
  $("open-swipe").disabled=records.length<2;
}
function createCharts(){
  const definitions=[
    ["radar-chart","Radar returns · dB","Each dot is one radar reading. The space between dots is a gap in observations."],
    ["water-chart","Sentinel‑2 water classes","Square = land, circle = water, × = unclear or missing. The rows are Point A and Point B."],
    ["height-chart","Reservoir height · m","Dots are DAHITI observations. Hollow diamonds are estimated heights on radar dates."]
  ];
  for(const [id,title,note] of definitions){
    const wrapper=node("section",null,id==="water-chart"?"chart waterchart":"chart");
    const h=node("h3",title), c=node("canvas");
    c.id=id;c.setAttribute("role","img");c.setAttribute("aria-label",title+" "+note);
    c.addEventListener("click",event=>{
      const box=c.getBoundingClientRect();
      const {first,last}=timeDomain();
      const target=first+clamp((event.clientX-box.left-49)/(box.width-64),0,1)*(last-first);
      const i=toolState.events.reduce((idx,row,j)=>Math.abs(utc(row.date)-target)<Math.abs(utc(toolState.events[idx].date)-target)?j:idx,0);
      goToTime(i);
    });
    wrapper.append(h,c,node("p",note));$("charts").append(wrapper);
  }
}
function timeDomain(){
  return {first:utc(toolState.events[0].date),last:utc(toolState.events.at(-1).date)};
}
function chartFrame(id,labels,unitRange,ticksTime=true){
  const frame=redrawTo($(id));
  if(!frame)return null;
  const {ctx:c,width:w,height:h}=frame;
  c.clearRect(0,0,w,h);
  const {first,last}=timeDomain();
  const x0=49,x1=w-15,y0=13,y1=h-25;
  const X=time=>x0+(utc(time)-first)/(last-first)*(x1-x0);
  const Y=v=>y1-(v-unitRange[0])/(unitRange[1]-unitRange[0])*(y1-y0);
  c.lineWidth=1;c.strokeStyle="#d5dfd2";c.fillStyle="#45645c";c.font="11px system-ui";
  c.textBaseline="middle";
  for(const [value,label] of labels){
    const y=Y(value);c.beginPath();c.moveTo(x0,y);c.lineTo(x1,y);c.stroke();
    c.textAlign="right";c.fillText(label,x0-5,y);
  }
  if(ticksTime){
    const count=w<400?3:5;
    for(let i=0;i<count;i++){
      const t=first+(last-first)*i/(count-1),x=x0+(x1-x0)*i/(count-1);
      c.textAlign=i===0?"left":i===count-1?"right":"center";
      c.fillText(shortFormat.format(t),x,h-10);
    }
  }
  const marker=X(toolState.events[toolState.time].date);
  c.setLineDash([4,3]);c.strokeStyle="#4f7067";c.beginPath();c.moveTo(marker,7);c.lineTo(marker,y1+4);c.stroke();c.setLineDash([]);
  return {c,X,Y,x0,x1,y0,y1};
}
function dot(c,x,y,r,color,selected=false){
  c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fillStyle=color;c.fill();
  c.strokeStyle=selected?"#22392f":"white";c.lineWidth=selected?2:1;c.stroke();
}
function drawCharts(){
  if(toolState.view!=="timeline"||!toolState.events.length)return;
  const palette={A:"#a65b21",B:"#286bc1"}, selected=toolState.events[toolState.time].date;
  let radarValues=[];
  for(const r of ordered("radar"))for(const i of Object.values(toolState.points))
    if(i!==null&&Number.isFinite(r.raw[i]))radarValues.push(r.raw[i]);
  const bottom=Math.min(-24,Math.floor(Math.min(...radarValues)/5)*5);
  const top=Math.max(-5,Math.ceil(Math.max(...radarValues)/5)*5);
  let table=chartFrame("radar-chart",[[bottom,bottom.toString()],[(bottom+top)/2,((bottom+top)/2).toFixed(1)],[top,top.toString()]],[bottom,top]);
  if(!table)return;
  const radarTexts=[];
  for(const r of ordered("radar"))for(const [key,i] of Object.entries(toolState.points)){
    if(i===null||!Number.isFinite(r.raw[i]))continue;
    dot(table.c,table.X(r.time),table.Y(r.raw[i]),key==="A"?5:4,palette[key],r.time===selected);
    radarTexts.push(formatDate(r.time)+" point "+key+" "+dbText(r.raw[i],2));
  }
  $("radar-chart").setAttribute("aria-label","Radar returns. "+radarTexts.join(". "));
  table=chartFrame("water-chart",[[0,"B"],[1,"A"]],[-.35,1.35]);
  if(!table)return;
  const waterTexts=[];
  for(const r of ordered("water"))for(const [key,i] of Object.entries(toolState.points)){
    if(i===null)continue;
    const code=r.states[i], x=table.X(r.time), y=table.Y(key==="A"?1:0), c=table.c;
    const k=r.time===selected?6:4.5;
    if(code===2)dot(c,x,y,k,palette[key],r.time===selected);
    else if(code===1){c.fillStyle=palette[key];c.fillRect(x-k,y-k,2*k,2*k)}
    else{
      c.strokeStyle=palette[key];c.lineWidth=2;
      c.beginPath();c.moveTo(x-k,y-k);c.lineTo(x+k,y+k);c.moveTo(x+k,y-k);c.lineTo(x-k,y+k);c.stroke();
    }
    waterTexts.push(formatDate(r.time)+" point "+key+" "+stateNames[code]);
  }
  $("water-chart").setAttribute("aria-label","Water class observations. "+(waterTexts.join(". ")||"No Sentinel-2 water maps loaded."));
  const hdata=toolState.events.filter(e=>e.height).map(e=>e.height);
  const heights=hdata.map(h=>h.meters);
  const a=Math.floor(Math.min(...heights)*2)/2,b=Math.max(a+.5,Math.ceil(Math.max(...heights)*2)/2);
  table=chartFrame("height-chart",[[a,a.toFixed(1)],[(a+b)/2,((a+b)/2).toFixed(1)],[b,b.toFixed(1)]],[a,b]);
  if(!table)return;
  for(const obs of hdata){
    const x=table.X(obs.datetime),y=table.Y(obs.meters),c=table.c;
    if(obs.estimated){
      c.beginPath();c.moveTo(x,y-5);c.lineTo(x+5,y);c.lineTo(x,y+5);c.lineTo(x-5,y);c.closePath();
      c.fillStyle="#f9fcf4";c.strokeStyle="#35685f";c.lineWidth=2;c.fill();c.stroke();
    }else{
      const bar=table.Y(obs.meters-obs.uncertainty)-y;
      c.strokeStyle="#689f9170";c.lineWidth=1;
      c.beginPath();c.moveTo(x,y-bar);c.lineTo(x,y+bar);c.stroke();
      dot(c,x,y,3.8,"#39766c",obs.datetime===selected);
    }
  }
  $("height-chart").setAttribute("aria-label","DAHITI reservoir height. "+hdata.map(o=>formatDate(o.datetime)+" "+o.meters.toFixed(2)+" meters"+(o.estimated?" estimated":"")).join(". "));
}
function updateTimeline(){
  const e=toolState.events[toolState.time];
  if(!e)return;
  $("scrubber").value=toolState.time;
  $("scrubber").setAttribute("aria-valuetext",formatDate(e.date));
  $("scrub-date").textContent=formatDate(e.date);
  const radarCount=loaded.radar.size, waterCount=loaded.water.size;
  $("time-count").textContent=radarCount+" radar passes · "+waterCount+" water maps";
  const messages=[];
  if(e.record?.type==="radar"){
    for(const [key,i] of Object.entries(toolState.points))
      if(i!==null)messages.push("Point "+key+" "+dbText(e.record.raw[i],2));
  }
  if(e.record?.type==="water"){
    for(const [key,i] of Object.entries(toolState.points))
      if(i!==null)messages.push("Point "+key+" "+stateNames[e.record.states[i]].toLowerCase());
  }
  if(!e.record)messages.push("No radar or water map at this observation time");
  if(e.height)messages.push("DAHITI "+e.height.meters.toFixed(2)+" m"+(e.height.estimated?" estimated":""));
  $("time-status").textContent=messages.join(" · ");
  drawCharts();
}
function goToTime(index){
  if(!toolState.events.length)return;
  toolState.time=clamp(index,0,toolState.events.length-1);
  updateTimeline();updateDates();updateLegend();requestDraw();
}
function pause(){
  clearInterval(toolState.timer);toolState.timer=null;
  $("play").disabled=false;$("pause").disabled=true;
}
function play(){
  if(toolState.timer||!toolState.events.length)return;
  if(toolState.time===toolState.events.length-1)goToTime(0);
  $("play").disabled=true;$("pause").disabled=false;
  toolState.timer=setInterval(()=>{
    goToTime(toolState.time+1);
    if(toolState.time===toolState.events.length-1)pause();
  },1050);
}

function refreshData({recenter=false}={}){
  changeCache=null;
  const rows=pilotWater();
  const previous=toolState.examples;
  toolState.patch=patchStats(baseMask)||derivePatch(rows);
  toolState.examples=examplePoints(toolState.patch,rows);
  for(const key of ["A","B"]){
    if(toolState.points[key]===null||toolState.points[key]===previous[key])toolState.points[key]=toolState.examples[key];
  }
  if(rows.length!==2&&toolState.layer==="water")toolState.layer="radar";
  rebuildEvents();updateEvidence();details();refreshControls();
  if(recenter)resetCamera(false);
  requestDraw();
}
function mapPosition(e){
  const rect=map.getBoundingClientRect();
  return {x:e.clientX-rect.left,y:e.clientY-rect.top};
}
function mapWorld(e){
  const p=mapPosition(e);
  return transform(toolState.cam,map.clientWidth,map.clientHeight).location(p.x,p.y);
}
function boundedCamera(){
  const c=toolState.cam;
  c.x=clamp(c.x,contextBounds.west,contextBounds.east);
  c.y=clamp(c.y,contextBounds.south,contextBounds.north);
}
function zoom(amount,at){
  const t=transform(toolState.cam,map.clientWidth,map.clientHeight), c=toolState.cam;
  const origin=at?t.location(at.x,at.y):{x:c.x,y:c.y};
  const factor=clamp(c.span*amount,520,35000)/c.span;
  c.span*=factor;
  c.x=origin.x+(c.x-origin.x)*factor;
  c.y=origin.y+(c.y-origin.y)*factor;
  boundedCamera();requestDraw();
}
function selectCell(where){
  const i=indexAt(where);
  if(toolState.view==="points"||toolState.view==="timeline"){
    if(i>=0)setPoint(toolState.focus,i);
    else flash("Choose a spot inside the outlined study area.");
    return;
  }
  toolState.chosen=i>=0?i:null;
  if(i>=0&&toolState.patch?.mask[i]===1){
    $("evidence").dataset.highlight="true";
    flash("Outlined inlet patch");
  }else{
    delete $("evidence").dataset.highlight;
  }
  showSelected();
  if($("data-details").open)details();
  requestDraw();
}
let flashTimer;
function flash(text){
  const tip=$("tip");
  tip.textContent=text;tip.hidden=false;
  clearTimeout(flashTimer);flashTimer=setTimeout(()=>tip.hidden=true,2500);
}
function arrows(key){
  return ({ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]})[key];
}
function activateMap(){
  let drag=null;
  map.addEventListener("pointerdown",e=>{
    if(!toolState.ready||e.button>0||drag)return;
    const p=mapPosition(e);
    drag={id:e.pointerId,p,x:toolState.cam.x,y:toolState.cam.y,moved:false};
    map.setPointerCapture(e.pointerId);
  });
  map.addEventListener("pointermove",e=>{
    if(drag?.id!==e.pointerId)return;
    const p=mapPosition(e), dx=p.x-drag.p.x,dy=p.y-drag.p.y;
    if(!drag.moved&&Math.hypot(dx,dy)<6)return;
    drag.moved=true;
    const t=toolState.cam.span/map.clientWidth;
    toolState.cam.x=drag.x-dx*t;toolState.cam.y=drag.y+dy*t;
    boundedCamera();requestDraw();
  });
  map.addEventListener("pointerup",e=>{
    if(drag?.id!==e.pointerId)return;
    if(!drag.moved)selectCell(mapWorld(e));
    drag=null;
  });
  map.addEventListener("pointercancel",()=>drag=null);
  map.addEventListener("wheel",e=>{
    if(!toolState.ready||!(e.ctrlKey||e.metaKey))return;
    e.preventDefault();zoom(e.deltaY>0?1.22:.82,mapPosition(e));
  },{passive:false});
  map.addEventListener("keydown",e=>{
    if(!toolState.ready)return;
    const p=arrows(e.key);
    if(p){
      const turn=toolState.cam.span*.12;
      toolState.cam.x+=p[0]*turn;toolState.cam.y-=p[1]*turn;
      boundedCamera();requestDraw();
    }else if(e.key==="+"||e.key==="=")zoom(.72);
    else if(e.key==="-")zoom(1.4);
    else if(e.key==="Enter")selectCell(toolState.cam);
    else return;
    e.preventDefault();
  });
  for(const key of ["A","B"]){
    const pin=$("pin-"+key.toLowerCase());
    let active=null;
    pin.addEventListener("pointerdown",e=>{
      active=e.pointerId;pin.setPointerCapture(e.pointerId);
      toolState.focus=key;requestDraw();
    });
    pin.addEventListener("pointermove",e=>{if(e.pointerId===active)setPoint(key,indexAt(mapWorld(e)))});
    pin.addEventListener("pointerup",()=>active=null);
    pin.addEventListener("pointercancel",()=>active=null);
    pin.addEventListener("click",()=>setPoint(key,toolState.points[key]));
    pin.addEventListener("keydown",e=>{
      const p=arrows(e.key), i=toolState.points[key];
      if(!p||i===null)return;
      e.preventDefault();
      const where=pointFrom(i), amount=e.shiftKey?5:1;
      setPoint(key,indexAt({x:where.x+p[0]*amount*cell,y:where.y-p[1]*amount*cell}));
    });
  }
  const handle=$("drag");
  function moveSplit(value){
    toolState.split=clamp(value,7,93);
    handle.setAttribute("aria-valuenow",Math.round(toolState.split));
    handle.setAttribute("aria-valuetext",Math.round(toolState.split)+"% left image");
    requestDraw();
  }
  let dividerPointer=null;
  handle.addEventListener("pointerdown",e=>{
    dividerPointer=e.pointerId;handle.setPointerCapture(e.pointerId);
    e.preventDefault();handle.focus();
  });
  handle.addEventListener("pointermove",e=>{if(e.pointerId===dividerPointer)moveSplit(mapPosition(e).x/map.clientWidth*100)});
  handle.addEventListener("pointerup",()=>dividerPointer=null);
  handle.addEventListener("pointercancel",()=>dividerPointer=null);
  handle.addEventListener("keydown",e=>{
    if(e.key==="ArrowLeft")moveSplit(toolState.split-3);
    else if(e.key==="ArrowRight")moveSplit(toolState.split+3);
    else if(e.key==="Home")moveSplit(7);
    else if(e.key==="End")moveSplit(93);
    else return;
    e.preventDefault();
  });
  $("extent").addEventListener("click",()=>resetCamera(!toolState.overview));
  $("loc-inlet").addEventListener("click",()=>{
    resetCamera(false);
    if(toolState.patch)selectCell(pointFrom(toolState.examples.A));
  });
  $("loc-dam").addEventListener("click",()=>resetCamera(true));
  $("zoom-in").addEventListener("click",()=>zoom(.72));
  $("zoom-out").addEventListener("click",()=>zoom(1.4));
  new ResizeObserver(()=>{requestDraw();drawCharts()}).observe(mapBox);
}

function bundleFromHtml(html){
  if(html.length>30_000_000)throw new Error("Choose a Roseires pipeline comparator smaller than 30 MB.");
  const match=html.match(/<script\s+type=["']application\/json["']\s+id=["']data["']\s*>([\s\S]*?)<\/script>/i);
  if(!match)throw new Error("This HTML is missing the processed Roseires data.");
  return JSON.parse(match[1]);
}
async function importLocal(files){
  const status=$("import-status");
  status.textContent="Reading selected files…";
  let touched=false;
  for(const file of files){
    try{
      if(/\.html$/i.test(file.name)){
        await addBundle(bundleFromHtml(await file.text()));
        touched=true;
      }else if(/\.tiff?$/i.test(file.name)){
        const raw=await readClassTiff(await file.arrayBuffer());
        const date=opticalDays.find(d=>file.name.includes(d));
        if(/mask|patch/i.test(file.name)){
          if(!patchStats(raw))throw new Error("This is not the verified 108-cell inlet mask.");
          baseMask=raw;touched=true;
        }else if(date){
          stagedTiffs[date]=sourceTileRecord(date,raw);
          if(opticalDays.every(d=>stagedTiffs[d])){
            const full=pilotWater().length===2&&pilotWater().every(r=>r.tileRaw["36PXU"]);
            if(!full)addWater(opticalDays.map(d=>stagedTiffs[d]));
            touched=true;
          }
        }else{throw new Error("Use the Aug 26 or Oct 15 Sentinel‑2 SCL GeoTIFF, or the outlined patch mask.")}
      }else{throw new Error("Choose a scored comparator HTML or an aligned GeoTIFF.")}
    }catch(error){
      status.textContent=file.name+" · "+error.message;
      if(touched)refreshData();
      return;
    }
  }
  if(touched)refreshData();
  status.textContent=touched?currentCoverage():"Choose both dated Sentinel‑2 classifications to compare water.";
}
async function loadSentinel(){
  if(remoteBusy)return;
  if(pilotWater().length===2&&pilotWater().every(r=>tiles.every(t=>r.tileRaw[t]))){
    $("import-status").textContent=currentCoverage();return;
  }
  remoteBusy=true;
  const button=$("load-sentinel"), status=$("import-status");
  button.disabled=true;status.textContent="Loading the four public Sentinel‑2 scenes…";
  try{
    const results=await Promise.all(opticalDays.map(async date=>{
      const observed=await Promise.allSettled(tiles.map(t=>fetchScene(t,date)));
      if(observed[0].status==="rejected")throw observed[0].reason;
      const a=observed[0].value;
      if(observed[1].status==="fulfilled"){
        const b=observed[1].value;
        return mergeTiles([a.scene,b.scene],[a.raw,b.raw]);
      }
      return {...sourceTileRecord(date,a.raw),time:a.scene.datetime||date,sources:[a.scene]};
    }));
    if (!pilotWater().every(r=>r.tileRaw["36PXU"]) || !pilotWater().length){
      addWater(results);refreshData();
    }
    status.textContent=currentCoverage();
    if(pilotWater().length===2&&toolState.view==="swipe"&&document.activeElement===button){toolState.layer="water";refreshControls()}
  }catch{
    status.textContent="Public Sentinel‑2 scenes could not be loaded. Choose the scored comparator HTML from the pipeline to use your processed observations.";
  }finally{
    button.disabled=false;remoteBusy=false;
  }
}
async function init(){
  for(const bundle of seed.bundles)await addBundle(bundle);
  if(seed.patch)baseMask=await unpack(seed.patch);
  createCharts();
  activateMap();
  for(const button of document.querySelectorAll("[data-view]"))button.addEventListener("click",()=>setView(button.dataset.view));
  for(const button of document.querySelectorAll("[data-point]"))button.addEventListener("click",()=>{
    toolState.focus=button.dataset.point;
    for(const b of document.querySelectorAll("[data-point]"))b.setAttribute("aria-pressed",String(b===button));
    requestDraw();
  });
  $("reset-points").addEventListener("click",()=>{
    toolState.points={...toolState.examples};toolState.focus="A";pointCompare();resetCamera(false);refreshControls();details();
  });
  $("follow-up").addEventListener("click",()=>{
    toolState.points={...toolState.examples};toolState.layer="water";
    resetCamera(false);setView("points");document.querySelector('[data-point="A"]').focus();
  });
  $("data-details").addEventListener("toggle",()=>{if($("data-details").open)details()});
  $("add-data").addEventListener("change",async e=>{
    const list=[...e.target.files];e.target.value="";
    if(list.length)await importLocal(list);
  });
  $("load-sentinel").addEventListener("click",loadSentinel);
  $("scrubber").addEventListener("input",e=>{pause();goToTime(Number(e.target.value))});
  $("play").addEventListener("click",play);
  $("pause").addEventListener("click",pause);
  $("date-layer").addEventListener("change",()=>{$("pair-message").textContent="";setDateOptions()});
  $("open-swipe").addEventListener("click",()=>{
    const start=$("date-start").value,end=$("date-end").value,kind=$("date-layer").value;
    if(!start||!end||utc(start)>=utc(end)){$("pair-message").textContent="Choose an earlier left date and a later right date.";return}
    $("pair-message").textContent="";
    toolState.pairByLayer[kind]=[start,end];toolState.layer=kind;setView("swipe");
  });
  toolState.ready=true;
  refreshData({recenter:true});
  baseImages();
  if(pilotWater().length<2)loadSentinel();
}
init().catch(error=>{
  const alert=node("p","InfraSAR could not open the data. "+error.message,"line-note");
  alert.setAttribute("role","alert");$("legend").replaceChildren(alert);
});
