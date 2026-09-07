import axios from 'axios'
import { simulationId } from '../data/sample'

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000', timeout: 6500, headers: { Accept: 'application/json' } })

// --- Real simulation lifecycle -------------------------------------------------
export async function createSimulation(scenario, engine = 'approximate', signal) {
  const { data } = await api.post('/api/simulations', { scenario, engine }, { signal, timeout: 15000 })
  return data
}
export async function getSimulation(id, signal) {
  const { data } = await api.get(`/api/simulations/${id}`, { signal })
  return data
}
export async function getSimulationTimeline(id, signal) {
  const { data } = await api.get(`/api/simulations/${id}/timeline`, { signal })
  return data
}
export async function getSimulationFrame(id, minute, signal) {
  const { data } = await api.get(`/api/simulations/${id}/timeline/${minute}`, { signal, timeout: 15000 })
  return data
}
export async function getSimulationSummary(id, signal) {
  const { data } = await api.get(`/api/simulations/${id}/summary`, { signal })
  return data
}
export async function cancelSimulation(id, signal) {
  const { data } = await api.post(`/api/simulations/${id}/cancel`, null, { signal })
  return data
}

// --- Phase 3 benchmark (dam-break verification: SPH vs Delft3D vs Ritter) -----
export async function runBenchmark(options = {}, signal) {
  const { data } = await api.post('/api/benchmarks/run', { options }, { signal, timeout: 15000 })
  return data
}
export async function getBenchmark(id, signal) {
  const { data } = await api.get(`/api/benchmarks/${id}`, { signal })
  return data
}
export async function getBenchmarkComparison(id, signal) {
  const { data } = await api.get(`/api/benchmarks/${id}/comparison`, { signal })
  return data
}

// --- Phase 4 generalized Ujjani dam-break scenario ---------------------------
export async function getScenarioPresets(signal) {
  const { data } = await api.get('/api/scenarios/presets', { signal })
  return data
}
export async function runScenario(body, signal) {
  const { data } = await api.post('/api/scenarios/run', body, { signal, timeout: 15000 })
  return data
}
export async function getScenario(id, signal) {
  const { data } = await api.get(`/api/scenarios/${id}`, { signal })
  return data
}
export async function getScenarioResults(id, signal) {
  const { data } = await api.get(`/api/scenarios/${id}/results`, { signal })
  return data
}
export async function getScenarioHydrograph(id, signal) {
  const { data } = await api.get(`/api/scenarios/${id}/hydrograph`, { signal })
  return data
}
export async function getScenarioFrame(id, minute, signal) {
  const { data } = await api.get(`/api/scenarios/${id}/timeline/${minute}`, { signal, timeout: 15000 })
  return data
}

// --- Phase 5: impact analysis, SPH particles, GIS export --------------------
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export async function getScenarioImpact(id, signal) {
  const { data } = await api.get(`/api/scenarios/${id}/impact`, { signal, timeout: 20000 })
  return data
}
export async function getSimulationImpact(id, signal) {
  const { data } = await api.get(`/api/simulations/${id}/impact`, { signal, timeout: 20000 })
  return data
}
export async function getScenarioParticles(id, signal) {
  const { data } = await api.get(`/api/scenarios/${id}/particles`, { signal, timeout: 20000 })
  return data
}
export async function getSimulationParticles(id, signal) {
  const { data } = await api.get(`/api/simulations/${id}/particles`, { signal, timeout: 20000 })
  return data
}
export const scenarioExportUrl = (id, fmt) => `${API_BASE}/api/scenarios/${id}/export/${fmt}`
export const simulationExportUrl = (id, fmt) => `${API_BASE}/api/simulations/${id}/export/${fmt}`
export async function fetchDashboard(signal) {
  const [summary, timeline] = await Promise.all([
    api.get(`/api/simulations/${simulationId}/summary`, { signal }),
    api.get(`/api/simulations/${simulationId}/timeline`, { signal })
  ])
  const fields = ['flooded_area_km2', 'maximum_depth_m', 'population_exposed', 'critical_assets', 'buildings_affected']
  if (!fields.every(field => Number.isFinite(summary.data[field])) || !Array.isArray(timeline.data.values) || !timeline.data.values.length || !timeline.data.values.every(point => Number.isFinite(point.minute) && Number.isFinite(point.depth_m))) throw new Error('Invalid dashboard response')
  return { summary: summary.data, timeline: timeline.data.values }
}
