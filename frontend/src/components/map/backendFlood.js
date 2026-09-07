import { Color, GeoJsonDataSource } from 'cesium'

/*
 * Renders time-dependent flood GeoJSON returned by the backend simulation API
 * (MODEL OUTPUT from the approximate 2D flood-routing prototype) as depth-banded
 * Cesium polygons clamped to the globe surface.
 */
export const BACKEND_DEPTH_STYLE = [
  { min: 0.05, color: '#22D3EE', alpha: 0.42, label: '0.05–1 m' },
  { min: 1, color: '#3B82F6', alpha: 0.5, label: '1–3 m' },
  { min: 3, color: '#6366F1', alpha: 0.55, label: '3–6 m' },
  { min: 6, color: '#A855F7', alpha: 0.62, label: '6+ m' }
]

function readNumber(value) {
  if (value == null) return NaN
  if (typeof value === 'number') return value
  if (typeof value.getValue === 'function') return Number(value.getValue())
  return Number(value)
}

function styleFor(depthMin) {
  let chosen = BACKEND_DEPTH_STYLE[0]
  for (const band of BACKEND_DEPTH_STYLE) {
    if (depthMin >= band.min) chosen = band
  }
  return chosen
}

export async function buildFrameDataSource(minute, featureCollection) {
  const source = await GeoJsonDataSource.load(featureCollection, {
    clampToGround: true,
    fill: Color.CYAN.withAlpha(0.4),
    strokeWidth: 0
  })
  source.name = `backend-flood-${minute}`
  for (const entity of source.entities.values) {
    if (!entity.polygon) continue
    const props = entity.properties || {}
    const depthMin = readNumber(props.depth_min_m)
    const band = styleFor(Number.isFinite(depthMin) ? depthMin : 0.05)
    entity.polygon.material = Color.fromCssColorString(band.color).withAlpha(band.alpha)
    entity.polygon.outline = false
    entity.polygon.classificationType = undefined
  }
  source.show = false
  return source
}

/* Largest available frame minute that is <= the current timeline minute. */
export function nearestFrameMinute(available, minute) {
  if (!available || !available.length) return null
  const sorted = [...available].map(Number).sort((a, b) => a - b)
  let pick = sorted[0]
  for (const value of sorted) {
    if (value <= minute) pick = value
  }
  return pick
}

export function frameFeatureCount(featureCollection) {
  return Array.isArray(featureCollection?.features) ? featureCollection.features.length : 0
}

/* [west, south, east, north] over every coordinate in a FeatureCollection. */
export function featureCollectionBounds(featureCollection) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity
  const visit = coords => {
    if (typeof coords[0] === 'number') {
      const [lon, lat] = coords
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        west = Math.min(west, lon); east = Math.max(east, lon)
        south = Math.min(south, lat); north = Math.max(north, lat)
      }
      return
    }
    for (const child of coords) visit(child)
  }
  for (const feature of featureCollection?.features || []) {
    if (feature?.geometry?.coordinates) visit(feature.geometry.coordinates)
  }
  if (!Number.isFinite(west) || west > east || south > north) return null
  return [west, south, east, north]
}
