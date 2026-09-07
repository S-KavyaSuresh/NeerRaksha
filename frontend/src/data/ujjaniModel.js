export const UJJANI_DAM = { lon:75.120278, lat:18.075 }

export const depthPalette = [
  { id:'shallow', label:'0–1 m', min:0.05, max:1, color:'#22D3EE' },
  { id:'moderate', label:'1–3 m', min:1, max:3, color:'#3B82F6' },
  { id:'deep', label:'3–6 m', min:3, max:6, color:'#6366F1' },
  { id:'very-deep', label:'6+ m', min:6, max:null, color:'#A855F7' }
]

const scenarioModel = {
  partial:{ travelTime:58, maxDepth:4.6, maxVelocity:4.1, baseWidthM:90, finalWidthM:300, peakDischarge:6200 },
  major:{ travelTime:42, maxDepth:8.4, maxVelocity:7.2, baseWidthM:150, finalWidthM:520, peakDischarge:12800 },
  custom:{ travelTime:50, maxDepth:6.2, maxVelocity:5.4, baseWidthM:120, finalWidthM:400, peakDischarge:9000 }
}

const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v))
const dist2=(a,b)=>(a[0]-b[0])**2+(a[1]-b[1])**2

function segmentLengthM(a,b){
  const lat=(a[1]+b[1])*0.5*Math.PI/180
  const x=(b[0]-a[0])*111320*Math.cos(lat)
  const y=(b[1]-a[1])*110540
  return Math.hypot(x,y)
}

function pickDownstreamPath(studyCase) {
  const features=studyCase?.spatial?.real_river?.features || []
  const candidates=features.filter(f=>f?.geometry?.type==='LineString' && Array.isArray(f.geometry.coordinates) && f.geometry.coordinates.length>1)
  if(!candidates.length) return []

  // If the verified downstream OSM way is present, always use it.
  const verified=candidates.find(f=>Number(f?.properties?.osm_id)===41846707)
  if(verified){
    const p=verified.geometry.coordinates
    const dam=[Number(studyCase?.longitude)||UJJANI_DAM.lon, Number(studyCase?.latitude)||UJJANI_DAM.lat]
    return dist2(p[0],dam)<=dist2(p[p.length-1],dam)?p:[...p].reverse()
  }

  const dam=[Number(studyCase?.longitude)||UJJANI_DAM.lon, Number(studyCase?.latitude)||UJJANI_DAM.lat]
  let best=null
  for(const f of candidates){
    const p=f.geometry.coordinates
    const d0=dist2(p[0],dam), d1=dist2(p[p.length-1],dam)
    const oriented=d0<=d1?p:[...p].reverse()
    const near=Math.min(d0,d1)
    const southGain=oriented[0][1]-oriented[oriented.length-1][1]
    const score=near - Math.max(0,southGain)*0.01
    if(!best||score<best.score) best={score,path:oriented}
  }
  return best?.path || []
}

function densifyPath(path, spacingM=80){
  if(path.length<2) return path
  const out=[path[0]]
  for(let i=1;i<path.length;i++){
    const a=path[i-1], b=path[i]
    const len=segmentLengthM(a,b)
    const n=Math.max(1,Math.ceil(len/spacingM))
    for(let j=1;j<=n;j++){
      const t=j/n
      out.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t])
    }
  }
  return out
}

function samplePathByDistance(path, reach) {
  if(path.length<2 || reach<=0) return []
  const dense=densifyPath(path)
  const seg=[]
  let total=0
  for(let i=1;i<dense.length;i++){ const l=segmentLengthM(dense[i-1],dense[i]); seg.push(l); total+=l }
  const target=total*clamp(reach)
  const out=[dense[0]]
  let acc=0
  for(let i=1;i<dense.length;i++){
    const l=seg[i-1]
    if(acc+l<=target){ out.push(dense[i]); acc+=l; continue }
    const remain=target-acc
    if(remain>0 && l>0){ const t=remain/l; const a=dense[i-1], b=dense[i]; out.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]) }
    break
  }
  return out.length>=2?out:[]
}

function pathCorridor(path, widthM) {
  if(path.length<2 || widthM<=0) return []
  const left=[], right=[]
  for(let i=0;i<path.length;i++){
    const prev=path[Math.max(0,i-1)], next=path[Math.min(path.length-1,i+1)]
    const lat=path[i][1]
    const lonScale=111320*Math.max(0.25,Math.cos(lat*Math.PI/180))
    const latScale=110540
    const dxM=(next[0]-prev[0])*lonScale
    const dyM=(next[1]-prev[1])*latScale
    const len=Math.hypot(dxM,dyM)||1
    const nx=-dyM/len, ny=dxM/len
    const progress=i/Math.max(1,path.length-1)
    const body=0.82+0.18*Math.sin(Math.PI*progress)
    const head=Math.min(1,0.28+i/5)
    const tail=i===path.length-1?0.42:1
    const half=widthM*0.5*body*head*tail
    left.push([path[i][0]+nx*half/lonScale,path[i][1]+ny*half/latScale])
    right.push([path[i][0]-nx*half/lonScale,path[i][1]-ny*half/latScale])
  }
  const ring=[...left,...right.reverse()]
  if(ring.length) ring.push([...ring[0]])
  return ring
}

export function ujjaniFrame(studyCase, minute, scenario) {
  const t=clamp(Number(minute)||0,0,60)
  const preset=scenario?.preset in scenarioModel ? scenario.preset : (scenario?.breach_type==='partial'?'partial':'major')
  const m=scenarioModel[preset] || scenarioModel.major
  if(t<=0) return { minute:0, depth:0, velocity:0, area:0, risk:'Advisory', bands:[], ring:[], unavailable:false }

  const path=pickDownstreamPath(studyCase)
  // Critical safety rule: never invent a straight fallback flood path.
  // If verified/real river geometry is unavailable, render no inundation.
  if(path.length<2) return { minute:t, depth:0, velocity:0, area:0, risk:'Advisory', bands:[], ring:[], unavailable:true }

  const formation=Math.max(1,Number(scenario?.breach_time_minutes)|| (preset==='partial'?45:20))
  const widthRatio=clamp((Number(scenario?.breach_width_m)|| (preset==='partial'?80:250))/250,0.25,2)
  const rise=1-Math.exp(-t/Math.max(4,formation*0.38))
  const reach=clamp((t+1.5)/m.travelTime,0.015,1)
  const depth=m.maxDepth*rise*(0.82+0.18*widthRatio)
  const velocity=m.maxVelocity*Math.sqrt(clamp(depth/Math.max(0.1,m.maxDepth),0,1))
  const width=(m.baseWidthM+(m.finalWidthM-m.baseWidthM)*clamp(t/60))*Math.sqrt(widthRatio)
  const activePath=samplePathByDistance(path,reach)

  const bandDefs=[
    {...depthPalette[0], factor:1},
    {...depthPalette[1], factor:0.72},
    {...depthPalette[2], factor:0.48},
    {...depthPalette[3], factor:0.29}
  ]
  const bands=[]
  for(const def of bandDefs){
    if(depth < def.min) continue
    const ring=pathCorridor(activePath,width*def.factor)
    if(ring.length>=4) bands.push({...def,ring})
  }
  const outer=bands[0]?.ring || []
  const approxLengthKm=Math.max(0,activePath.reduce((sum,p,i)=>i?sum+segmentLengthM(activePath[i-1],p)/1000:0,0))
  const area=Math.max(0,approxLengthKm*(width/1000)*0.78)
  const risk=depth>=6?'Critical':depth>=3?'Severe':depth>=1?'Warning':'Advisory'
  return {minute:t,depth,velocity,area,risk,bands,ring:outer,preset,unavailable:false}
}

export function ujjaniScenarioSummary(preset) {
  const m=scenarioModel[preset]||scenarioModel.major
  const scenario={preset,breach_type:preset==='partial'?'partial':'major',breach_width_m:preset==='partial'?80:250,breach_time_minutes:preset==='partial'?45:20}
  const depth=m.maxDepth*(0.98)*(0.82+0.18*(scenario.breach_width_m/250))
  const area=(preset==='partial'?6.8:14.4)
  return {name:preset==='partial'?'Partial Breach':'Major Breach',area,depth,velocity:m.maxVelocity,peak:m.peakDischarge,arrival:preset==='partial'?18:10}
}
