const channel = [[83.87,21.545],[83.88,21.515],[83.908,21.485],[83.945,21.46],[83.982,21.42],[84.03,21.392],[84.07,21.37],[84.11,21.34]]

function corridor(length, width) {
  const centers = channel.slice(0, length)
  const ring = [...centers.map(([lon,lat]) => [lon - width,lat]), ...centers.toReversed().map(([lon,lat]) => [lon + width,lat])]
  return [...ring, ring[0]]
}

export const floodFrames = [
  { minute: 0, depth: 0, depthRange: '0 m', risk: 'Advisory', color: '#59d5ac', area: 0, population: 0, ring: [] },
  { minute: 15, depth: 2.1, depthRange: '0–2.1 m', risk: 'Warning', color: '#30d6e5', area: 9.6, population: 2860, ring: corridor(4, .008) },
  { minute: 30, depth: 5.3, depthRange: '0–5.3 m', risk: 'Critical', color: '#3787ee', area: 24.2, population: 9640, ring: corridor(6, .016) },
  { minute: 60, depth: 8.4, depthRange: '0–8.4 m', risk: 'Critical', color: '#7164f4', area: 42.8, population: 18420, ring: corridor(8, .024) }
]

export function getActiveFrame(minute) {
  const value = Number.isFinite(Number(minute)) ? Number(minute) : 0
  return floodFrames.findLast(frame => frame.minute <= value) || floodFrames[0]
}

export function pointInRing(lon, lat, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

export function closedPositions(frame) {
  return frame.ring.flat()
}

const buildingCenters = [[83.88,21.513],[83.906,21.488],[83.94,21.463],[83.977,21.425],[84.021,21.398],[84.09,21.355]]
export const sampleBuildings = buildingCenters.flatMap(([lon,lat], group) => [-.03,-.01,.003,.014].map((offset, index) => ({
  id: `building-${group * 4 + index + 1}`, name: `Sample building ${group * 4 + index + 1}`, type: 'building', kind: 'Building', lon: lon + offset, lat: lat + index * .001,
  sector: ['Sector A','Sector A','Sector B','Sector B','Sector C','Sector C'][group], height: 18 + index * 8
})))

export const sampleRoads = [
  { id:'road-1',name:'Hirakud approach',points:[[83.855,21.517],[83.905,21.51]] },
  { id:'road-2',name:'Sector A link',points:[[83.895,21.486],[83.94,21.478]] },
  { id:'road-3',name:'Sambalpur crossing',points:[[83.927,21.46],[83.975,21.448]] },
  { id:'road-4',name:'Sector B river road',points:[[83.97,21.419],[84.023,21.41]] },
  { id:'road-5',name:'Sector C access',points:[[84.05,21.371],[84.1,21.359]] }
].map(road => ({ ...road, type:'road', kind:'Road segment', lon:road.points[0][0],lat:road.points[0][1] }))

export const sampleFacilities = [
  { id:'hospital',name:'Sector A Sample Hospital',kind:'Hospital',lon:83.919,lat:21.479 },
  { id:'school',name:'Sector A Sample School',kind:'School',lon:83.939,lat:21.463 },
  { id:'shelter-north',name:'North Ridge Prototype Shelter',kind:'Shelter',lon:84.005,lat:21.495 },
  { id:'police',name:'Sector B Sample Police Post',kind:'Police',lon:83.985,lat:21.417 },
  { id:'fire',name:'Sector C Sample Fire Station',kind:'Fire station',lon:84.078,lat:21.365 },
  { id:'shelter-east',name:'East Ridge Prototype Shelter',kind:'Shelter',lon:84.133,lat:21.395 }
].map(facility => ({ ...facility, type:'facility' }))

export const settlements = [
  { id:'sector-a',name:'Sambalpur Sector A',lon:83.928,lat:21.475,arrival:15,depth:2.7,roadId:'road-2',shelterId:'shelter-north' },
  { id:'sector-b',name:'Mahanadi Sector B',lon:83.989,lat:21.413,arrival:30,depth:5.3,roadId:'road-4',shelterId:'shelter-north' },
  { id:'sector-c',name:'Downstream Sector C',lon:84.074,lat:21.366,arrival:60,depth:8.4,roadId:'road-5',shelterId:'shelter-east' }
]

function segmentCrosses(a, b, c, d) {
  const cross = (p,q,r) => (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
  return cross(a,b,c) * cross(a,b,d) < 0 && cross(c,d,a) * cross(c,d,b) < 0
}

export function assetAffected(asset, frame) {
  if (!frame.ring.length) return false
  if (!asset.points) return pointInRing(asset.lon, asset.lat, frame.ring)
  if (asset.points.some(([lon,lat]) => pointInRing(lon,lat,frame.ring))) return true
  return asset.points.slice(1).some((point, index) => frame.ring.slice(1).some((edge, edgeIndex) => segmentCrosses(asset.points[index], point, frame.ring[edgeIndex], edge)))
}

export function assetThreat(asset, minute) {
  const arrival = floodFrames.find(frame => assetAffected(asset, frame))?.minute ?? null
  const affected = assetAffected(asset, getActiveFrame(minute))
  return { affected, arrival, remaining: arrival === null ? null : Math.max(0, Math.ceil(arrival - minute)), status: affected ? asset.type === 'road' ? 'Blocked (sample)' : 'Flooded (sample)' : arrival === null ? 'Outside sample extent' : 'Threatened (sample)' }
}

export function layerCounts(layers, frame) {
  return Object.fromEntries([['buildings',sampleBuildings.length],['roads',sampleRoads.length],['facilities',sampleFacilities.length],['flood',frame.ring.length ? 1 : 0]].map(([key,total]) => [key,{ total, visible: layers[key] ? total : 0 }]))
}

export function emergencyAlerts(minute) {
  return settlements.map(settlement => ({ ...settlement,
    remaining:Math.max(0,Math.ceil(settlement.arrival-minute)),
    severity:minute>=settlement.arrival?'Critical':settlement.arrival-minute<=15?'Warning':'Advisory',
    road:sampleRoads.find(road=>road.id===settlement.roadId),
    shelter:sampleFacilities.find(facility=>facility.id===settlement.shelterId)
  }))
}

export function prototypeImpact(minute) {
  const frame=getActiveFrame(minute)
  const buildings=sampleBuildings.filter(asset=>assetAffected(asset,frame))
  const roads=sampleRoads.filter(asset=>assetAffected(asset,frame))
  const facilities=sampleFacilities.filter(asset=>assetAffected(asset,frame))
  const shares=frame.minute===0?[0,0,0]:frame.minute===15?[1,0,0]:frame.minute===30?[.6,.4,0]:[.45,.35,.2]
  const a=Math.round(frame.population*shares[0]),b=Math.round(frame.population*shares[1])
  const sectors=[a,b,frame.population-a-b].map((population,index)=>({name:['Sector A','Sector B','Sector C'][index],population,buildings:buildings.filter(asset=>asset.sector===['Sector A','Sector B','Sector C'][index]).length}))
  const critical=Math.floor(frame.population*.55),warning=Math.floor(frame.population*.3)
  return {frame, flooded_area_km2:frame.area,maximum_depth_m:frame.depth,population_exposed:frame.population,buildings_affected:buildings.length,roads_affected:roads.length,facilities_threatened:facilities.length,settlements_at_risk:sectors.filter(sector=>sector.population>0).length,critical_assets:roads.length+facilities.length,sectors,riskBreakdown:[{name:'Critical',population:critical},{name:'Warning',population:warning},{name:'Advisory',population:frame.population-critical-warning}],is_sample:true}
}
