import test from 'node:test'
import assert from 'node:assert/strict'
import { useDashboard } from '../src/store/useDashboard.js'
import { pipelineStatus } from '../src/data/pipeline.js'

test('prototype pipeline progresses honestly, skips HEC-RAS and starts playback only at completion',()=>{
  const actions=useDashboard.getState()
  actions.resetRun()
  assert.equal(actions.startRun().ok,true)
  assert.equal(useDashboard.getState().playing,false)
  actions.advanceRun(2.5)
  assert.equal(useDashboard.getState().run.status,'running')
  assert.match(pipelineStatus(useDashboard.getState().run,2),/Not connected/)
  actions.advanceRun(3.5)
  assert.equal(useDashboard.getState().run.status,'completed')
  assert.equal(useDashboard.getState().run.progress,100)
  assert.equal(useDashboard.getState().playing,true)
  assert.equal(useDashboard.getState().minute,0)
})

test('cancelled runs cannot complete from a late timer callback; reset clears progress',()=>{
  const actions=useDashboard.getState()
  actions.startRun()
  actions.advanceRun(1)
  actions.cancelRun()
  actions.advanceRun(20)
  assert.equal(useDashboard.getState().run.status,'cancelled')
  assert.equal(useDashboard.getState().playing,false)
  actions.resetRun()
  assert.equal(useDashboard.getState().run.progress,0)
  assert.equal(useDashboard.getState().run.status,'idle')
})
