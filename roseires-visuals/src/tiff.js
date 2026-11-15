// The source SCL tiles and exported masks are single-band GeoTIFFs on UTM 36N.
function lzw(bytes,expected) {
  const table=new Array(4096), out=new Uint8Array(expected);
  let bit=0,length=0,width=9,size=258,previous=null;
  function reset(){
    for(let i=0;i<256;i++)table[i]=[i];
    width=9;size=258;previous=null;
  }
  reset();
  while(bit+width<=bytes.length*8 && length<expected){
    let code=0;
    for(let i=0;i<width;i++,bit++)code=(code<<1)|((bytes[bit>>3]>>(7-bit%8))&1);
    if(code===256){reset();continue}
    if(code===257)break;
    const value=code<size ? table[code] : code===size&&previous ? [...previous,previous[0]] : null;
    if(!value)throw new Error("Invalid LZW block.");
    if(previous&&size<4096){
      table[size++]=[...previous,value[0]];
      if(size===(1<<width)-1 && width<12)width++;
    }
    if(length+value.length>expected)throw new Error("Invalid TIFF block length.");
    out.set(value,length);length+=value.length;previous=value;
  }
  if(length!==expected)throw new Error("Incomplete LZW raster block.");
  return out;
}
async function readClassTiff(bytes) {
  const view=new DataView(bytes), little=view.getUint16(0)===0x4949;
  const u16=o=>view.getUint16(o,little), u32=o=>view.getUint32(o,little);
  if(u16(2)!==42)throw new Error("Choose a standard single-band Roseires GeoTIFF.");
  const first=u32(4), count=u16(first), entries=new Map();
  const widths={1:1,2:1,3:2,4:4,12:8};
  for(let i=0;i<count;i++){
    const entry=first+2+i*12, type=u16(entry+2), n=u32(entry+4), length=widths[type]*n;
    if(!length)continue;
    const at=length<=4?entry+8:u32(entry+8);
    entries.set(u16(entry),{type,n,at});
  }
  function tag(id){
    const entry=entries.get(id);
    if(!entry)return [];
    const {type,n,at}=entry, step=widths[type];
    return Array.from({length:n},(_,i)=>{
      const x=at+i*step;
      return type===12?view.getFloat64(x,little):type===4?u32(x):type===3?u16(x):view.getUint8(x);
    });
  }
  const width=tag(256)[0], height=tag(257)[0], bits=tag(258)[0]||8, compression=tag(259)[0]||1;
  const samples=tag(277)[0]||1, predictor=tag(317)[0]||1;
  const pixel=tag(33550), tie=tag(33922), keys=tag(34735);
  const proj=keys.findIndex((k,i)=>i>=4&&i%4===0&&k===3072&&keys[i+1]===0);
  if(samples!==1||![1,8].includes(bits)||![1,5,8,32946].includes(compression)
     || ![1,2].includes(predictor) || !width || !height || !pixel[0] || !pixel[1]
     || tie.length<6 || proj<0 || keys[proj+3]!==32636)
    throw new Error("This GeoTIFF needs to be a byte classification or mask in UTM zone 36N.");
  const west=tie[3]-tie[0]*pixel[0], north=tie[4]+tie[1]*pixel[1];
  const tiled=entries.has(324);
  const blockWidth=tiled?tag(322)[0]:width, blockHeight=tiled?tag(323)[0]:(tag(278)[0]||height);
  const offsets=tag(tiled?324:273), lengths=tag(tiled?325:279);
  const nAcross=Math.ceil(width/blockWidth);
  if (!blockWidth||!blockHeight||offsets.length!==lengths.length)throw new Error("Invalid GeoTIFF layout.");
  const targets=new Map(), result=new Uint8Array(size);
  result.fill(255);
  for(let row=0;row<grid.height;row++){
    const sy=Math.floor((north-(grid.north-(row+.5)*cell))/pixel[1]+1e-8);
    if(sy<0||sy>=height)continue;
    for(let col=0;col<grid.width;col++){
      const sx=Math.floor((grid.west+(col+.5)*cell-west)/pixel[0]+1e-8);
      if(sx<0||sx>=width)continue;
      const block=Math.floor(sy/blockHeight)*nAcross+Math.floor(sx/blockWidth);
      if(!targets.has(block))targets.set(block,[]);
      targets.get(block).push(row*grid.width+col,sy%blockHeight,sx%blockWidth);
    }
  }
  if(!targets.size)throw new Error("That raster does not overlap the Roseires study area.");
  const rowBytes=Math.ceil(blockWidth*bits/8);
  for(const [b,lookups] of targets){
    const offset=offsets[b], length=lengths[b];
    if(offset===0&&!length)continue;
    if(!length||offset+length>bytes.byteLength)throw new Error("Missing GeoTIFF block.");
    const packed=new Uint8Array(bytes,offset,length);
    const rows=tiled?blockHeight:Math.min(blockHeight,height-b*blockHeight);
    const data=compression===1 ? packed.slice() : compression===5 ? lzw(packed,rows*rowBytes) : await inflate(packed);
    if(data.length<rows*rowBytes)throw new Error("Incomplete GeoTIFF block.");
    if(predictor===2&&bits===8) for(let y=0;y<rows;y++)for(let x=1;x<rowBytes;x++)data[y*rowBytes+x]+=data[y*rowBytes+x-1];
    for(let i=0;i<lookups.length;i+=3){
      const [index,y,x]=[lookups[i],lookups[i+1],lookups[i+2]];
      result[index]=bits===8 ? data[y*rowBytes+x] : ((data[y*rowBytes+(x>>3)]>>(7-x%8))&1);
    }
  }
  return result;
}
const opticalDays=["2026-08-26","2026-10-15"];
const searchRoot="https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/";
const cogRoot="https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/36/P/";
const fetchOptions=()=>({signal:AbortSignal.timeout(18000)});
function sceneFor(tile,date){
  return {id:"S2C_"+tile+"_"+date.replaceAll("-","")+"_0_L2A",tile,date};
}
async function fetchScene(tile,date) {
  const scene=sceneFor(tile,date);
  const fallback=cogRoot+tile.slice(-2)+"/2026/"+Number(date.slice(5,7))+"/"+scene.id+"/SCL.tif";
  let url=fallback;
  try {
    const r=await fetch(searchRoot+scene.id,fetchOptions());
    if(r.ok){
      const asset=await r.json();
      if(asset.id===scene.id){
        if(Number.isFinite(utc(asset.properties?.datetime)))scene.datetime=asset.properties.datetime;
        if(asset.assets?.scl?.href?.startsWith("https://"))url=asset.assets.scl.href;
      }
    }
  } catch {} // The known public asset still works when the catalog cannot be reached.
  const response=await fetch(url,fetchOptions());
  if(!response.ok)throw new Error("Source image unavailable ("+response.status+").");
  const raw=await readClassTiff(await response.arrayBuffer());
  return {scene:{...scene,scl:url},raw};
}
function sourceTileRecord(date,raw){
  const source=sceneFor(tiles[0],date);
  return {type:"water",time:date,id:source.id,raw,states:raw.map(sclState),tileRaw:{[tiles[0]]:raw},sources:[source]};
}
