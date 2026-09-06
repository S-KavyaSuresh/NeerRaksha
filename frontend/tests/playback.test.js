import test from 'node:test'
import assert from 'node:assert/strict'
import { useDashboard } from '../src/store/useDashboard.js'

test('changing speed retains timeline position and subsequent playback uses the new speed', () => {
  const actions = useDashboard.getState()
  actions.restart()
  actions.togglePlaying()
  actions.tick(10)
  actions.setSpeed(2)
  assert.equal(useDashboard.getState().minute, 10)
  actions.tick(2)
  assert.equal(useDashboard.getState().minute, 14)
  actions.setSpeed(0.5)
  actions.tick(2)
  assert.equal(useDashboard.getState().minute, 15)
  actions.togglePlaying()
  assert.equal(useDashboard.getState().playing, false)
  assert.equal(useDashboard.getState().minute, 15)
})

test('replay finishes at 60, restarts explicitly, and scrubbing is bounded', () => {
  const actions = useDashboard.getState()
  actions.restart()
  actions.setSpeed(2)
  actions.togglePlaying()
  actions.tick(100)
  assert.equal(useDashboard.getState().minute, 60)
  assert.equal(useDashboard.getState().playing, false)
  actions.togglePlaying()
  assert.equal(useDashboard.getState().minute, 0)
  assert.equal(useDashboard.getState().playing, true)
  actions.setMinute(-10)
  assert.equal(useDashboard.getState().minute, 0)
  actions.setMinute(90)
  assert.equal(useDashboard.getState().minute, 60)
  actions.restart()
  assert.equal(useDashboard.getState().playing, false)
})

test('layer controls do not change playback or unrelated layers', () => {
  const actions = useDashboard.getState()
  actions.setMinute(30)
  const before = { ...useDashboard.getState().layers }
  actions.toggleLayer('flood')
  assert.equal(useDashboard.getState().layers.flood, !before.flood)
  assert.equal(useDashboard.getState().layers.terrain, before.terrain)
  assert.equal(useDashboard.getState().minute, 30)
})
