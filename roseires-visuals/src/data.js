"use strict";
const $ = id => document.getElementById(id);
const seed = JSON.parse($("data").textContent);
const grid = seed.grid;
const size = grid.width * grid.height;
const cell = grid.pixel_m;
const crop = {west:grid.west, east:grid.west + grid.width * cell, north:grid.north, south:grid.north - grid.height * cell};
const inlet = {x:659903.152, y:1296948.257};
const dam = {x:651167.115, y:1304597.962};
const town = {x:648088.118, y:1303591.824};
const reservoir = seed.reservoir;
const [lakeWest,lakeSouth,lakeEast,lakeNorth] = reservoir.bounds;
const reservoirBounds = {west:Math.min(town.x,lakeWest)-2500,east:lakeEast+2500,
  south:lakeSouth-2500,north:Math.max(dam.y,lakeNorth)+2500};
const contextBounds = {west:580000,east:740000,south:1200000,north:1360000};
const tiles = ["36PXT", "36PXU"];
const clamp = (n,a,b) => Math.min(b, Math.max(a,n));
const utc = value => Date.parse(value);
const day = value => value.slice(0,10);
const dateFormat = new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
const shortFormat = new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",timeZone:"UTC"});
const formatDate = value => dateFormat.format(utc(value));
const formatShort = value => shortFormat.format(utc(value));
const showTime = value => value?.includes("T") ? value.replace("T"," ").replace(/(?:Z|\+00:00)$/," UTC") : (value || "Unknown date");
const dbText = (number, digits=1) => Number.isFinite(number) ? number.toFixed(digits).replace("-","−") + " dB" : "No reading";
const pointFrom = i => ({x:crop.west + (i % grid.width + .5) * cell, y:crop.north - (Math.floor(i / grid.width) + .5) * cell});
function indexAt({x,y}) {
  const col=Math.floor((x-crop.west)/cell), row=Math.floor((crop.north-y)/cell);
  return col>=0 && col<grid.width && row>=0 && row<grid.height ? row*grid.width+col : -1;
}
const stateNames = {1:"Land",2:"Water",3:"Land in August, water in October",4:"Water in August, land in October",
  5:"No image coverage",6:"Cloud",7:"Cloud shadow",8:"Unclear",9:"No usable image value",10:"Unclear · tiles disagree"};
const sclNames = ["No data","Saturated or defective","Dark area","Cloud shadow","Vegetation","Bare land","Water","Unclassified","Medium cloud probability","High cloud probability","Cirrus","Snow or ice"];
function sclState(code) {
  if (code===4 || code===5) return 1;
  if (code===6) return 2;
  if (code===255) return 5;
  if (code===254) return 10;
  if (code===3) return 7;
  if (code>=8 && code<=10) return 6;
  if (code===0) return 9;
  return 8;
}
const stateAt = (row,i) => i < 0 || !row ? 5 : row.states[i];
const isClear = code => code===1 || code===2;
function waterChange(before,after) {
  let data=new Uint8Array(size);
  const precedence=[5,9,10,6,7,8];
  for(let i=0;i<size;i++){
    const a=before.states[i], b=after.states[i];
    data[i]=isClear(a)&&isClear(b) ? (a===b?a:b===2?3:4) : (precedence.find(k=>a===k||b===k)||8);
  }
  return data;
}
function agreement(radar,water) {
  const data=new Uint8Array(size);
  for(let i=0;i<size;i++){
    const r=radar[i], o=water[i], rc=r===3||r===4, oc=o===3||o===4;
    data[i]=o>=5 ? (rc?7:8) : r===o && oc ? (r===3?2:3) : rc&&oc ? 6 : oc ? 4 : rc ? 5 : r>=5 ? 9 : 1;
  }
  return data;
}
function radarCandidateChange(radar, before, after) {
  return radar?.map((value,i)=>Number.isFinite(before.raw[i])&&Number.isFinite(after.raw[i])?value:0);
}
async function inflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function unpack(encoded) {
  if (!encoded || !["float32","uint8"].includes(encoded.type) || typeof encoded.payload!=="string" || encoded.payload.length>size*8) throw new Error("Invalid raster payload.");
  const bytes = await inflate(Uint8Array.from(atob(encoded.payload), c => c.charCodeAt(0)));
  if (encoded.type === "float32" && bytes.length === size*4) return new Float32Array(bytes.buffer);
  if (encoded.type === "uint8" && bytes.length === size) return bytes;
  throw new Error("Raster size differs from the 20 m study grid.");
}
function validGrid(value) {
  return value?.width===grid.width && value.height===grid.height && value.epsg===32636 && value.pixel_m===cell
    && Math.abs(value.west-grid.west)<1e-5 && Math.abs(value.north-grid.north)<1e-5;
}
const loaded = {radar:new Map(), water:new Map(), pairs:new Map()};
function radarRecord(record, raw, optical) {
  const parts = record.id.split("_");
  const release = record.release || record.id.match(/_(P\d{5})_/)?.[1];
  const maturity = record.maturity || (parts[2] === "PR" ? "PROVISIONAL" : "Unknown maturity");
  return {type:"radar",time:record.datetime,id:record.id,raw,maturity,optical,
    version:record.version || (release === "P05023" ? "1.0.11" : null),
    release, mode:record.mode || parts[9],
    geometry:parts.slice(5,9).join(":"),cells:record.valid_cells};
}
function comparable(a, b) {
  return Boolean(a && b && a.type === b.type && (a.type !== "radar" ||
    (a.version && ["maturity","version","release","mode","geometry"].every(field => a[field] === b[field]))));
}
async function addRadarObservation(record) {
  if (!validGrid(record.grid) || !/^NISAR_L2_PR_GCOV_[A-Z0-9_]+$/.test(record.id)
      || !Number.isFinite(utc(record.datetime)) || !record.version || !record.release || !record.mode) {
    throw new Error("Choose a verified single NISAR observation on the 20 m Roseires grid.");
  }
  const raw = await unpack(record.hh_db);
  if (!(raw instanceof Float32Array) || !raw.some(Number.isFinite)) throw new Error("No usable radar readings.");
  if ([...loaded.radar.values()].some(row => utc(row.time) === utc(record.datetime) || row.id === record.id))
    throw new Error("This radar acquisition is already available.");
  loaded.radar.set(record.datetime, radarRecord(record, raw, []));
}
async function addBundle(bundle) {
  if (!validGrid(bundle.grid) || !["pilot","holdout"].includes(bundle.pair)) throw new Error("Choose a scored Roseires pilot or holdout comparator on the same grid.");
  const records=bundle.radar?.radar;
  if (records?.length!==2 || records.some(r=>typeof r.id!=="string" || !Number.isFinite(utc(r.datetime)))) throw new Error("Missing radar acquisition metadata.");
  const pair={name:bundle.pair, radar:[],water:[],candidates:{},policy:bundle.radar.policy||{}};
  const processed=Object.fromEntries(await Promise.all(Object.entries(bundle.arrays).filter(([key])=>
    /^(?:hh_before|hh_after|scl_before|scl_after|opt_before|opt_after|fixed|local|tile_[01]_36PX[TU])$/.test(key))
    .map(async ([key,value])=>[key,await unpack(value)])));
  const radarRows=[], waterRows=[];
  for(const [i,record] of records.entries()){
    const phase=i?"after":"before";
    const raw=processed["hh_"+phase];
    if (!(raw instanceof Float32Array)) throw new Error("The processed file is missing radar readings.");
    const optical=bundle.optical_sources?.[day(record.datetime)], scl=processed["scl_"+phase];
    radarRows.push(radarRecord(record,raw,optical&&scl instanceof Uint8Array ? Object.values(optical) : []));
    if (optical && scl instanceof Uint8Array) {
      const sources=Object.values(optical);
      const time=sources[0]?.datetime||sources[0]?.date;
      if (!Number.isFinite(utc(time))) throw new Error("The water map is missing its acquisition date.");
      waterRows.push({type:"water",time,id:sources[0].id,raw:scl,states:processed["opt_"+phase]||scl.map(sclState),
        sources,tileRaw:Object.fromEntries(tiles.filter(tile=>processed["tile_"+i+"_"+tile]).map(tile=>[tile,processed["tile_"+i+"_"+tile]]))});
    }
  }
  for(const name of ["fixed","local"]) if(processed[name] instanceof Uint8Array) pair.candidates[name]=processed[name];
  for(const row of radarRows){
    if (bundle.pair === "pilot" || !loaded.radar.has(row.time)) loaded.radar.set(row.time,row);
    pair.radar.push(row);
  }
  for(const row of waterRows){loaded.water.set(row.time,row);pair.water.push(row)}
  loaded.pairs.set(pair.name,pair);
  return pair;
}
function addWater(rows) {
  const pilot = loaded.pairs.get("pilot");
  for (const old of pilot.water) loaded.water.delete(old.time);
  pilot.water=rows;
  for (const [i,row] of rows.entries()) {
    loaded.water.set(row.time,row);
    if (pilot.radar[i]) pilot.radar[i].optical = row.sources;
  }
}
function ordered(kind){return [...loaded[kind].values()].sort((a,b)=>utc(a.time)-utc(b.time))}
function pilotWater(){return loaded.pairs.get("pilot").water}
function pilotRadar(){return loaded.pairs.get("pilot").radar}
function totalCoverage(rows) {
  if(rows.length!==2) return null;
  let usable=0;
  for(let i=0;i<size;i++) if(isClear(rows[0].states[i])&&isClear(rows[1].states[i])) usable++;
  return usable/size;
}
function mergeTiles(sources, rasters) {
  const [a,b]=rasters;
  const raw=a.slice();
  for(let i=0;i<size;i++){
    const ca=a[i], cb=b[i], validA=[4,5,6].includes(ca), validB=[4,5,6].includes(cb);
    if(ca===255 || (validB&&!validA) || (ca===0&&cb!==255)) raw[i]=cb;
    if(validA&&validB&&((ca===6)!==(cb===6))) raw[i]=254;
  }
  return {type:"water",time:sources[0].datetime||sources[0].date,id:sources[0].id,raw,states:raw.map(sclState),
    tileRaw:Object.fromEntries(tiles.map((tile,i)=>[tile,rasters[i]])),sources};
}
function median(values) {
  const arr=values.slice().sort((a,b)=>a-b), i=arr.length>>1;
  return arr.length%2?arr[i]:(arr[i-1]+arr[i])/2;
}
function patchStats(mask) {
  if(!mask) return null;
  const [before,after]=pilotRadar(), cells=[], deltas=[];
  let x=0,y=0;
  for(let i=0;i<size;i++) if(mask[i]===1){
    const p=pointFrom(i), delta=after.raw[i]-before.raw[i];
    if(!Number.isFinite(delta)) return null;
    x+=p.x;y+=p.y;cells.push(i);deltas.push(delta);
  }
  if(cells.length!==108) return null;
  const mid=median(deltas);
  if(Math.abs(mid+4.32)>.04) return null;
  return {mask,cells,median:mid,center:{x:x/cells.length,y:y/cells.length}};
}
function derivePatch(rows) {
  if(rows.length!==2) return null;
  // Re-create the original 136 × 136 study window and require its measured signature.
  const left=Math.round((658545.1044029767-grid.west)/cell);
  const top=Math.round((grid.north-1298318.0249756854)/cell);
  const extent=136;
  const gains=new Uint8Array(extent*extent);
  for(let y=0;y<extent;y++)for(let x=0;x<extent;x++){
    const i=(y+top)*grid.width+x+left;
    gains[y*extent+x]=rows[0].states[i]===1 && rows[1].states[i]===2?1:0;
  }
  for(const diagonal of [false,true]){
    const remaining=gains.slice();
    for(let i=0;i<remaining.length;i++)if(remaining[i]){
      const group=[i];remaining[i]=0;
      for(let j=0;j<group.length;j++){
        const x=group[j]%extent,y=Math.floor(group[j]/extent);
        for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
          if(!diagonal&&dx&&dy)continue;
          const xx=x+dx,yy=y+dy,nextIndex=yy*extent+xx;
          if(xx>=0&&xx<extent&&yy>=0&&yy<extent&&remaining[nextIndex]){
            remaining[nextIndex]=0;group.push(nextIndex);
          }
        }
      }
      if(group.length!==108)continue;
      const mask=new Uint8Array(size);
      for(const j of group) mask[(Math.floor(j/extent)+top)*grid.width+j%extent+left]=1;
      const stats=patchStats(mask);
      if(stats)return stats;
    }
  }
  return null;
}
function examplePoints(patch,rows) {
  const [before,after]=pilotRadar();
  let a=patch ? patch.cells.reduce((best,i)=>{
    const score=j=>Math.hypot(pointFrom(j).x-patch.center.x,pointFrom(j).y-patch.center.y)/120
      + Math.abs(after.raw[j]-before.raw[j]-patch.median);
    return score(i)<score(best)?i:best;
  }) : indexAt(inlet);
  if(rows.length!==2) return {A:a,B:null};
  if(!patch){
    let distance=Infinity;
    for(let i=0;i<size;i++){
      if(rows[0].states[i]!==1||rows[1].states[i]!==2||!Number.isFinite(before.raw[i]+after.raw[i]))continue;
      const p=pointFrom(i), d=Math.hypot(p.x-inlet.x,p.y-inlet.y);
      if(d<700&&d<distance){a=i;distance=d}
    }
  }
  const p=pointFrom(a);
  let bestB=null,bestScore=Infinity;
  const radius=70, row=Math.floor(a/grid.width),col=a%grid.width;
  for(let y=Math.max(1,row-radius);y<Math.min(grid.height-1,row+radius);y++)for(let x=Math.max(1,col-radius);x<Math.min(grid.width-1,col+radius);x++){
    const i=y*grid.width+x, delta=after.raw[i]-before.raw[i];
    if(rows.some(r=>r.states[i]!==1) || !(delta<-2))continue;
    let count=0;
    for(let yy=-1;yy<=1;yy++)for(let xx=-1;xx<=1;xx++) if(rows.every(r=>r.states[i+yy*grid.width+xx]===1))count++;
    if(count<8)continue;
    const where=pointFrom(i), distance=Math.hypot(where.x-p.x,where.y-p.y);
    if(distance<130||distance>1400)continue;
    const score=Math.abs(delta+4.32)+distance/600;
    if(score<bestScore){bestScore=score;bestB=i}
  }
  // Fall back to a nearby, clear, darkening land cell when no 3×3 control exists.
  if(bestB===null) for(let i=0;i<size;i++){
    if(rows.some(r=>r.states[i]!==1) || !(after.raw[i]-before.raw[i]<-2))continue;
    const q=pointFrom(i),dist=Math.hypot(q.x-p.x,q.y-p.y);
    if(dist>=100&&dist<=1600&&dist<bestScore){bestScore=dist;bestB=i}
  }
  return {A:a,B:bestB};
}
function estimateHeight(time) {
  const heights=seed.heights;
  const after=heights.findIndex(v=>utc(v.datetime)>=utc(time));
  if(after<0) return null;
  if(utc(heights[after].datetime)===utc(time))return heights[after].meters;
  if(after===0)return null;
  const a=heights[after-1],b=heights[after];
  return a.meters+(b.meters-a.meters)*(utc(time)-utc(a.datetime))/(utc(b.datetime)-utc(a.datetime));
}
