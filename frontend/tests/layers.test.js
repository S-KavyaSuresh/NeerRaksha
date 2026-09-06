import test from 'node:test'
import assert from 'node:assert/strict'
import { sampleBuildings, sampleRoads, sampleFacilities, floodFrames, assetAffected, layerCounts } from '../src/data/prototype.js'

test('sample inventory contains 24 buildings, five roads and every requested facility type', () => {
  assert.equal(sampleBuildings.length,24)
  assert.equal(sampleRoads.length,5)
  for (const kind of ['Hospital','School','Shelter','Police','Fire station']) assert.ok(sampleFacilities.some(asset => asset.kind === kind))
})

test('affected assets grow with active frame and road crossings are detected', () => {
  for (const assets of [sampleBuildings,sampleRoads,sampleFacilities]) {
    const counts = floodFrames.map(frame => assets.filter(asset => assetAffected(asset,frame)).length)
    assert.equal(counts[0],0)
    assert.ok(counts.at(-1)>0)
    for (let i=1;i<counts.length;i++) assert.ok(counts[i]>=counts[i-1])
  }
  assert.ok(assetAffected(sampleRoads[0],floodFrames[1]))
})

test('visible/total counts are derived from layer state and inventory', () => {
  const on = layerCounts({buildings:true,roads:true,facilities:true,flood:true},floodFrames[3])
  assert.deepEqual(on.buildings,{visible:24,total:24})
  assert.deepEqual(on.roads,{visible:5,total:5})
  const off = layerCounts({},floodFrames[0])
  assert.deepEqual(off.facilities,{visible:0,total:6})
  assert.deepEqual(off.flood,{visible:0,total:0})
})
