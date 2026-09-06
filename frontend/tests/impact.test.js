import test from 'node:test'
import assert from 'node:assert/strict'
import { prototypeImpact, floodFrames } from '../src/data/prototype.js'

test('every impact summary changes with frame and breakdowns reconcile to total population',()=>{
  const impacts=floodFrames.map(frame=>prototypeImpact(frame.minute))
  for(const impact of impacts) {
    assert.equal(impact.sectors.reduce((sum,sector)=>sum+sector.population,0),impact.population_exposed)
    assert.equal(impact.riskBreakdown.reduce((sum,risk)=>sum+risk.population,0),impact.population_exposed)
    assert.equal(impact.critical_assets,impact.roads_affected+impact.facilities_threatened)
  }
  assert.equal(impacts[0].buildings_affected,0)
  assert.equal(impacts[0].facilities_threatened,0)
  for(let i=1;i<impacts.length;i++) {
    assert.ok(impacts[i].flooded_area_km2>impacts[i-1].flooded_area_km2)
    assert.ok(impacts[i].population_exposed>impacts[i-1].population_exposed)
    assert.ok(impacts[i].buildings_affected>impacts[i-1].buildings_affected)
    assert.ok(impacts[i].roads_affected>=impacts[i-1].roads_affected)
  }
})
