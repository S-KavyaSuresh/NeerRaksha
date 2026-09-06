import test from 'node:test'
import assert from 'node:assert/strict'
import { getActiveFrame, floodFrames, pointInRing } from '../src/data/prototype.js'
import { useDashboard } from '../src/store/useDashboard.js'

test('timeline selects the four frames at their exact boundaries', () => {
  for (const [minute, expected] of [[0,0],[14.9,0],[15,15],[29.9,15],[30,30],[59.9,30],[60,60]]) {
    useDashboard.getState().setMinute(minute)
    assert.equal(getActiveFrame(useDashboard.getState().minute).minute, expected)
  }
})

test('progressive sample rings are closed, nested and extend farther downstream', () => {
  assert.equal(floodFrames[0].ring.length, 0)
  for (let index = 1; index < floodFrames.length; index++) {
    const frame = floodFrames[index]
    assert.deepEqual(frame.ring[0], frame.ring.at(-1))
    assert.ok(frame.area > floodFrames[index - 1].area)
    if (index > 1) {
      const previous = floodFrames[index - 1]
      assert.ok(Math.min(...frame.ring.map(point => point[1])) < Math.min(...previous.ring.map(point => point[1])))
      for (const [lon,lat] of previous.ring.filter(point => point[1] < 21.545)) assert.ok(pointInRing(lon, lat, frame.ring))
    }
  }
})

test('pause prevents clock ticks; hiding flood does not stop the clock; restart clears frame', () => {
  const actions = useDashboard.getState()
  actions.restart()
  actions.tick(20)
  assert.equal(useDashboard.getState().minute, 0)
  actions.setSpeed(1)
  actions.togglePlaying()
  actions.toggleLayer('flood')
  actions.tick(30)
  assert.equal(getActiveFrame(useDashboard.getState().minute).minute, 30)
  actions.togglePlaying()
  actions.tick(20)
  assert.equal(useDashboard.getState().minute, 30)
  actions.restart()
  assert.equal(getActiveFrame(useDashboard.getState().minute).ring.length, 0)
})
