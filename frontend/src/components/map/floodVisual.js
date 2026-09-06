const channel = [[83.87,21.535],[83.881,21.509],[83.908,21.484],[83.939,21.469],[83.962,21.445],[83.982,21.418],[84.022,21.396],[84.068,21.374],[84.102,21.348]]
const keys = [
  {minute:0,reach:0,width:0,depth:0},
  {minute:15,reach:.18,width:.004,depth:2.1},
  {minute:30,reach:.5,width:.011,depth:5.3},
  {minute:60,reach:1,width:.023,depth:8.4}
]

export const depthBands = [
  {id:'shallow',minimum:0,label:'0–1 m',color:'#30d6e5'},
  {id:'moderate',minimum:1,label:'1–3 m',color:'#3787ee'},
  {id:'deep',minimum:3,label:'3–6 m',color:'#7164f4'},
  {id:'very-deep',minimum:6,label:'6–9+ m',color:'#be94fc'}
]

function corridor(reach,width) {
  const end=Math.max(.001,Math.min(1,reach))*(channel.length-1)
  const sections=Array.from({length:25},(_,index)=>{
    const along=end*index/24
    const segment=Math.min(channel.length-2,Math.floor(along))
    const fraction=along-segment
    const [lon,lat]=channel[segment]
    const next=channel[segment+1]
    const halfWidth=width*(.65+.35*Math.sin(index/24*Math.PI))*(index===24?.1:1)
    return {lon:lon+(next[0]-lon)*fraction,lat:lat+(next[1]-lat)*fraction,width:halfWidth}
  })
  const ring=[...sections.map(point=>[point.lon-point.width,point.lat]),...sections.toReversed().map(point=>[point.lon+point.width,point.lat])]
  return [...ring,ring[0]]
}

export function getFloodVisual(value) {
  const minute=Number.isFinite(Number(value))?Math.max(0,Math.min(60,Number(value))):0
  if(minute===0) return {minute,depth:0,ring:[],bands:[],risk:'Advisory'}
  const upper=keys.find(key=>key.minute>=minute)||keys.at(-1)
  const lower=keys[Math.max(0,keys.indexOf(upper)-1)]
  const fraction=(minute-lower.minute)/(upper.minute-lower.minute)
  const interpolate=key=>lower[key]+(upper[key]-lower[key])*fraction
  const reach=interpolate('reach'),width=interpolate('width'),depth=interpolate('depth')
  const bands=depthBands.filter(band=>depth>band.minimum).map((band,index)=>{
    const ratio=band.minimum/depth
    return {...band,ring:corridor(reach*(1-ratio*.45),width*(index===0?1:Math.sqrt(1-ratio)*.72)),zIndex:index+1}
  })
  return {minute,depth,ring:bands[0].ring,bands,risk:depth>=3?'Critical':'Warning'}
}

export function validFloodBounds(ring) {
  if(!Array.isArray(ring)||ring.length<4||ring.some(point=>!Array.isArray(point)||point.length<2||!Number.isFinite(point[0])||!Number.isFinite(point[1])||Math.abs(point[0])>180||Math.abs(point[1])>90)) return null
  const lons=ring.map(point=>point[0]),lats=ring.map(point=>point[1])
  const west=Math.max(-180,Math.min(...lons)-.025),east=Math.min(180,Math.max(...lons)+.025)
  const south=Math.max(-89.9,Math.min(...lats)-.025),north=Math.min(89.9,Math.max(...lats)+.025)
  return [west,south,east,north].every(Number.isFinite)&&west<east&&south<north?{west,south,east,north}:null
}
