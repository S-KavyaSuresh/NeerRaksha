import test from 'node:test'
import assert from 'node:assert/strict'
import { useDashboard } from '../src/store/useDashboard.js'
import { emergencyAlerts } from '../src/data/prototype.js'

test('emergency mode enables risk layers, requests camera focus and restores the previous visibility',()=>{
  const state=useDashboard.getState()
  if(state.emergency) state.toggleEmergency()
  const previous={...useDashboard.getState().layers}
  const focus=useDashboard.getState().focusRequest
  state.toggleEmergency()
  assert.equal(useDashboard.getState().emergency,true)
  for(const key of ['flood','roads','facilities','buildings']) assert.equal(useDashboard.getState().layers[key],true)
  assert.equal(useDashboard.getState().focusRequest,focus+1)
  state.toggleEmergency()
  assert.deepEqual(useDashboard.getState().layers,previous)
})

test('sample alert countdowns and severity respond to simulation time',()=>{
  assert.equal(emergencyAlerts(0)[2].severity,'Advisory')
  assert.equal(emergencyAlerts(5)[0].remaining,10)
  assert.equal(emergencyAlerts(5)[0].severity,'Warning')
  assert.equal(emergencyAlerts(30)[0].remaining,0)
  assert.equal(emergencyAlerts(30)[0].severity,'Critical')
  assert.ok(emergencyAlerts(30).every(alert=>alert.road&&alert.shelter))
})
