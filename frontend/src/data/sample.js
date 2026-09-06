import { floodFrames } from './prototype.js'
export const simulationId = '44444444-4444-4444-8444-444444444444'
export const sampleTimestamp = '2026-09-05T06:01:00Z'
export const sampleSummary = { flooded_area_km2: 42.8, maximum_depth_m: 8.4, population_exposed: 18420, buildings_affected: 3260, critical_assets: 27, is_sample: true, updated_at: sampleTimestamp }
export const sampleTimeline = floodFrames.map(frame => ({ minute:frame.minute, depth_m:frame.depth, flooded_area_km2:frame.area }))
export const riverPath = [83.865,21.535, 83.881,21.509, 83.908,21.484, 83.939,21.469, 83.962,21.445, 83.982,21.418, 84.022,21.396, 84.068,21.374, 84.102,21.348]
