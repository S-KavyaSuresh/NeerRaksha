import test from 'node:test'
import assert from 'node:assert/strict'
import { buildExport } from '../src/utils/exports.js'
import { scenarioPresets } from '../src/data/scenarios.js'
import { getActiveFrame } from '../src/data/prototype.js'

const now=new Date('2026-09-05T12:00:00Z')
test('JSON and GeoJSON exports contain the current selection and valid closed geographic rings',()=>{
  const json=JSON.parse(buildExport('json',scenarioPresets.major,30,now).content)
  assert.equal(json.metadata.application,'JalDrishti')
  assert.equal(json.metadata.active_timeline_frame,30)
  assert.equal(json.metadata.scenario_name,'Major Breach')
  assert.equal(json.metadata.generation_timestamp,now.toISOString())
  assert.match(json.metadata.validation_status,/Not validated/)
  for(const minute of [0,15,30,60]) {
    const geo=JSON.parse(buildExport('geojson',scenarioPresets.partial,minute,now).content)
    assert.equal(geo.features.length,minute?1:0)
    if(minute) {
      const ring=geo.features[0].geometry.coordinates[0]
      assert.deepEqual(ring,getActiveFrame(minute).ring)
      assert.deepEqual(ring[0],ring.at(-1))
      assert.ok(ring.every(([lon,lat])=>lon>83&&lon<85&&lat>21&&lat<22))
    }
  }
})

test('CSV is quoted and spreadsheet formula names are escaped',()=>{
  const output=buildExport('csv',{...scenarioPresets.custom,name:'=SUM(1,2)'},15,now).content
  assert.equal(output.split('\r\n').length,5)
  assert.ok(output.includes('"\'=SUM(1,2)"'))
  assert.match(output,/active_timeline_frame/)
  assert.match(output,/PROTOTYPE SAMPLE DATA/)
})

test('KML escapes scenario names and omits geometry at T+00',()=>{
  const output=buildExport('kml',{...scenarioPresets.custom,name:'Test <A> & "B"'},60,now).content
  assert.ok(output.includes('xmlns="http://www.opengis.net/kml/2.2"'))
  assert.ok(output.includes('Test &lt;A&gt; &amp; &quot;B&quot;'))
  assert.ok(output.includes('<LinearRing><coordinates>'))
  assert.ok(!buildExport('kml',scenarioPresets.major,0,now).content.includes('<Polygon>'))
  assert.throws(()=>buildExport('shp',scenarioPresets.major,30,now),/Unsupported/)
  assert.throws(()=>buildExport('json',scenarioPresets.major,NaN,now),/timeline/)
})
