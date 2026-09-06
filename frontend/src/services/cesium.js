import {
  EllipsoidTerrainProvider
} from 'cesium'

export function isTokenConfigured() {
  return false
}

export async function loadTerrain(enabled) {
  return {
    provider: new EllipsoidTerrainProvider(),
    status: enabled ? 'fallback' : 'disabled',
    warning: enabled
      ? 'Ellipsoid terrain active · real DEM terrain pending.'
      : ''
  }
}