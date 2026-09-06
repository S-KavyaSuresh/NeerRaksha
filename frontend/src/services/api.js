import axios from 'axios'
import { simulationId } from '../data/sample'

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000', timeout: 6500, headers: { Accept: 'application/json' } })
export async function fetchDashboard(signal) {
  const [summary, timeline] = await Promise.all([
    api.get(`/api/simulations/${simulationId}/summary`, { signal }),
    api.get(`/api/simulations/${simulationId}/timeline`, { signal })
  ])
  const fields = ['flooded_area_km2', 'maximum_depth_m', 'population_exposed', 'critical_assets', 'buildings_affected']
  if (!fields.every(field => Number.isFinite(summary.data[field])) || !Array.isArray(timeline.data.values) || !timeline.data.values.length || !timeline.data.values.every(point => Number.isFinite(point.minute) && Number.isFinite(point.depth_m))) throw new Error('Invalid dashboard response')
  return { summary: summary.data, timeline: timeline.data.values }
}
