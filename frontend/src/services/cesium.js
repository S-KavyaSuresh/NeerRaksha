import {
  Ion,
  IonResource,
  CesiumTerrainProvider,
  EllipsoidTerrainProvider
} from 'cesium'

import { initializeIon } from '../utils/cesiumToken.js'

const tokenDiagnostics = initializeIon(
  Ion,
  import.meta.env.VITE_CESIUM_ION_TOKEN
)

export function isTokenConfigured() {
  return tokenDiagnostics.tokenConfigured
}

export async function loadTerrain(enabled) {
  if (!enabled) {
    return {
      provider: new EllipsoidTerrainProvider(),
      status: 'disabled',
      warning: ''
    }
  }

  if (
    !tokenDiagnostics.tokenConfigured ||
    !tokenDiagnostics.tokenFormatValid
  ) {
    return {
      provider: new EllipsoidTerrainProvider(),
      status: 'fallback',
      warning:
        'Ion terrain unavailable · ellipsoid terrain active. Check Vite token configuration and restart Vite.'
    }
  }

  try {
    const resource = await IonResource.fromAssetId(1, {
      accessToken: Ion.defaultAccessToken
    })

    const provider = await CesiumTerrainProvider.fromUrl(resource)

    return {
      provider,
      status: 'active',
      warning: ''
    }
  } catch {
    return {
      provider: new EllipsoidTerrainProvider(),
      status: 'fallback',
      warning:
        'Ion terrain could not be loaded · ellipsoid terrain active. Other layers remain available.'
    }
  }
}