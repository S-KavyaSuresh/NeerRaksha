import test from 'node:test'
import assert from 'node:assert/strict'
import { comparisonScenarios,comparisonMetrics } from '../src/data/comparison.js'

test('comparison provides two complete scenario datasets with unit-specific chart metrics',()=>{
  assert.equal(comparisonScenarios.length,2)
  assert.equal(comparisonMetrics.length,6)
  for(const scenario of comparisonScenarios) for(const metric of comparisonMetrics) assert.ok(Number.isFinite(scenario[metric.key]))
  assert.ok(comparisonScenarios[0].area<comparisonScenarios[1].area)
  assert.ok(comparisonScenarios[0].arrival>comparisonScenarios[1].arrival)
})
