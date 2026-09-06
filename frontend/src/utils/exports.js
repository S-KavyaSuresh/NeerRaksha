import { getActiveFrame, floodFrames, prototypeImpact } from '../data/prototype.js'
import { validateScenario, normalizedScenario } from '../data/scenarios.js'

const xml = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&apos;')
const csv = value => {
  let text=String(value)
  if(typeof value==='string'&&/^[=+@\-\t\r]/.test(text)) text="'"+text
  return '"'+text.replaceAll('"','""')+'"'
}

export function buildExport(format,scenario,minute,now=new Date()) {
  if(Object.keys(validateScenario(scenario)).length) throw new Error('Save a valid prototype scenario before exporting.')
  if(!Number.isFinite(Number(minute))||Number(minute)<0||Number(minute)>60) throw new Error('Select a timeline position from 0 to 60 minutes.')
  const frame=getActiveFrame(minute)
  if(frame.ring.some(point=>point.length!==2||!Number.isFinite(point[0])||!Number.isFinite(point[1])||Math.abs(point[0])>180||Math.abs(point[1])>90)) throw new Error('Sample geometry contains invalid geographic coordinates.')
  const metadata={application:'JalDrishti',data_classification:'PROTOTYPE SAMPLE DATA',scenario_name:scenario.name.trim(),active_timeline_frame:frame.minute,timeline_minute:Number(minute),generation_timestamp:now.toISOString(),validation_status:'Not validated hydraulic output',data_source:'Prototype simulation intelligence',geometry_basis:'Prebuilt illustrative flood states; not HEC-RAS output'}
  const feature={type:'Feature',properties:{...metadata,sample_depth_m:frame.depth,prototype_risk:frame.risk},geometry:{type:'Polygon',coordinates:[frame.ring]}}
  const geojson={type:'FeatureCollection',metadata,features:frame.ring.length?[feature]:[]}
  const name='jaldrishti-prototype-T'+String(frame.minute).padStart(2,'0')
  if(format==='json') return {name:name+'.json',type:'application/json',content:JSON.stringify({metadata,scenario:normalizedScenario(scenario),impact:prototypeImpact(minute),active_extent:geojson},null,2)}
  if(format==='geojson') return {name:name+'.geojson',type:'application/geo+json',content:JSON.stringify(geojson,null,2)}
  if(format==='csv') {
    const rows=floodFrames.map(point=>({...metadata,sample_frame_minute:point.minute,sample_depth_m:point.depth,sample_flooded_area_km2:point.area,sample_population:point.population}))
    const keys=Object.keys(rows[0])
    return {name:name+'.csv',type:'text/csv;charset=utf-8',content:[keys.map(csv).join(','),...rows.map(row=>keys.map(key=>csv(row[key])).join(','))].join('\r\n')}
  }
  if(format==='kml') {
    const extended=Object.entries(metadata).map(([key,value])=>'<Data name="'+xml(key)+'"><value>'+xml(value)+'</value></Data>').join('')
    const polygon=frame.ring.length?'<Placemark><name>'+xml(scenario.name)+' · T+'+frame.minute+'</name><description>PROTOTYPE SAMPLE DATA. Not validated hydraulic output. Sample depth '+frame.depth+' m; prototype risk '+frame.risk+'.</description><ExtendedData>'+extended+'</ExtendedData><Style><PolyStyle><color>99766471</color><outline>0</outline></PolyStyle></Style><Polygon><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>'+frame.ring.map(([lon,lat])=>lon+','+lat+',0').join(' ')+'</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>':''
    return {name:name+'.kml',type:'application/vnd.google-earth.kml+xml',content:'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>JalDrishti prototype flood</name><description>PROTOTYPE SAMPLE DATA · '+(frame.ring.length?'active inundation':'T+00: no downstream inundation')+'</description><ExtendedData>'+extended+'</ExtendedData>'+polygon+'</Document></kml>'}
  }
  throw new Error('Unsupported export format.')
}
