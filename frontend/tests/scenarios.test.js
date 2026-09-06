import test from 'node:test'
import assert from 'node:assert/strict'
import { scenarioPresets,validateScenario,readSavedScenario } from '../src/data/scenarios.js'
import { useDashboard } from '../src/store/useDashboard.js'

test('presets validate and invalid scenario parameters cannot replace the saved scenario',()=>{
  for(const scenario of Object.values(scenarioPresets)) assert.deepEqual(validateScenario(scenario),{})
  const original=useDashboard.getState().scenario
  const result=useDashboard.getState().saveScenario({...original,breach_width_m:-1})
  assert.equal(result.ok,false)
  assert.ok(result.errors.breach_width_m)
  assert.deepEqual(useDashboard.getState().scenario,original)
  assert.ok(validateScenario({...original,breach_time_minutes:''}).breach_time_minutes)
})

test('a custom scenario persists, restores and is shared with simulation state',()=>{
  const data=new Map()
  globalThis.localStorage={getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value)}
  const custom={...scenarioPresets.custom,breach_width_m:'165',simulation_duration_minutes:'90'}
  assert.equal(useDashboard.getState().saveScenario(custom).persistent,true)
  assert.equal(useDashboard.getState().scenario.breach_width_m,165)
  assert.equal(readSavedScenario().simulation_duration_minutes,90)
  data.set('jaldrishti.prototype-scenario','broken')
  assert.equal(readSavedScenario().preset,'major')
  delete globalThis.localStorage
})
