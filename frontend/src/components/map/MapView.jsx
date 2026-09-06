import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react'

import {
  Viewer,
  Entity,
  CameraFlyTo
} from 'resium'

import {
  Cartesian3,
  Cartesian2,
  Color,
  EllipsoidTerrainProvider,
  UrlTemplateImageryProvider,
  OpenStreetMapImageryProvider,
  Math as CesiumMath,
  HeightReference,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Cartographic,
  defined,
  LabelStyle,
  Rectangle
} from 'cesium'

import {
  Crosshair,
  Minus,
  Plus,
  X,
  MapPin,
  Layers,
  Mountain,
  Satellite,
  Waves,
  Building2,
  Route,
  Hospital,
  TriangleAlert,
  Focus
} from 'lucide-react'

import { useDashboard } from '../../store/useDashboard'

import { riverPath } from '../../data/sample'

import {
  sampleBuildings,
  sampleRoads,
  sampleFacilities,
  assetAffected,
  layerCounts
} from '../../data/prototype.js'

import IconButton from '../common/IconButton'

import {
  loadTerrain,
  isTokenConfigured
} from '../../services/cesium'

import {
  getFloodVisual,
  depthBands,
  validFloodBounds
} from './floodVisual.js'


const destination = Cartesian3.fromDegrees(
  83.97,
  21.32,
  30000
)

const orientation = {
  heading: 0,
  pitch: CesiumMath.toRadians(-58),
  roll: 0
}

const layerOptions = [
  ['terrain', Mountain, 'Terrain'],
  ['satellite', Satellite, 'Satellite'],
  ['flood', Waves, 'Flood Depth'],
  ['buildings', Building2, 'Buildings'],
  ['roads', Route, 'Roads'],
  ['facilities', Hospital, 'Facilities']
]

const cssColor = (
  value,
  alpha = 1
) => Color
  .fromCssColorString(value)
  .withAlpha(alpha)

const assetPositions = new Map(
  [
    ...sampleBuildings,
    ...sampleFacilities
  ].map(asset => [
    asset.id,
    Cartesian3.fromDegrees(
      asset.lon,
      asset.lat
    )
  ])
)

const roadGeometry = new Map(
  sampleRoads.map(asset => [
    asset.id,
    Cartesian3.fromDegreesArray(
      asset.points.flat()
    )
  ])
)

const riverPositions = Cartesian3.fromDegreesArray(
  riverPath
)


export default function MapView() {
  const viewerRef = useRef(null)

  const imageryRef = useRef({
    satellite: null,
    streets: null
  })

  const [ready, setReady] = useState(false)

  const [mapError, setMapError] = useState('')

  const [terrainError, setTerrainError] = useState('')

  const [loading, setLoading] = useState(true)

  const [initializationFailed, setInitializationFailed] =
    useState(false)

  const [terrainActive, setTerrainActive] =
    useState(false)

  const [coordinates, setCoordinates] = useState({
    lon: 83.87,
    lat: 21.53,
    elevation: null
  })

  const {
    minute,
    layers,
    toggleLayer,
    selected,
    select,
    focusRequest
  } = useDashboard()

  const visualMinute =
    Math.floor(minute * 4) / 4

  const frame = useMemo(
    () => getFloodVisual(visualMinute),
    [visualMinute]
  )

  const floodGeometry = useMemo(
    () =>
      frame.bands.map(band => ({
        ...band,
        positions: Cartesian3.fromDegreesArray(
          band.ring.flat()
        )
      })),
    [frame]
  )

  const counts = layerCounts(
    layers,
    frame
  )

  const reduced =
    window
      .matchMedia(
        '(prefers-reduced-motion: reduce)'
      )
      .matches

  const attachViewer = useCallback(node => {
    viewerRef.current = node

    if (
      node?.cesiumElement &&
      !node.cesiumElement.isDestroyed()
    ) {
      setReady(true)
      setInitializationFailed(false)
    }
  }, [])

  const detail =
    selected?.type === 'flood'
      ? {
          ...frame,
          type: 'flood'
        }
      : selected

  const threat =
    detail &&
    !['dam', 'flood'].includes(
      detail.type
    )
      ? assetAffected(
          detail,
          frame
        )
        ? detail.type === 'road'
          ? 'Blocked (sample)'
          : 'Flooded (sample)'
        : 'Outside current flood'
      : null

  const selectedBand =
    frame.bands.find(
      band =>
        band.id === selected?.bandId
    )


  useEffect(() => {
    if (ready) {
      return undefined
    }

    const timer = setTimeout(
      () =>
        setInitializationFailed(true),
      12000
    )

    return () => {
      clearTimeout(timer)
    }
  }, [ready])


  useEffect(() => {
    if (!ready) {
      return undefined
    }

    const viewer =
      viewerRef.current?.cesiumElement

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return undefined
    }

    const imageryLayers =
      viewer.imageryLayers

    if (!imageryLayers) {
      setMapError(
        'Imagery system unavailable. Map overlays remain available.'
      )

      return undefined
    }

    try {
      imageryLayers.removeAll()

      const streetsProvider =
        new OpenStreetMapImageryProvider({
          url:
            'https://tile.openstreetmap.org/'
        })

      const satelliteProvider =
        new UrlTemplateImageryProvider({
          url:
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          maximumLevel: 18,
          credit:
            'Tiles © Esri — Esri, Maxar, Earthstar Geographics and the GIS User Community'
        })

      const streets =
        imageryLayers.addImageryProvider(
          streetsProvider
        )

      const satellite =
        imageryLayers.addImageryProvider(
          satelliteProvider
        )

      const satelliteEnabled =
        useDashboard
          .getState()
          .layers
          .satellite

      satellite.show =
        satelliteEnabled

      streets.show =
        !satelliteEnabled

      imageryRef.current = {
        satellite,
        streets
      }

      viewer.scene.globe.baseColor =
        cssColor('#172d39')

      const removeStreetError =
        streetsProvider
          .errorEvent
          .addEventListener(() => {
            setMapError(
              'Some street-map tiles are unavailable. Sample overlays remain usable.'
            )
          })

      const removeSatelliteError =
        satelliteProvider
          .errorEvent
          .addEventListener(() => {
            setMapError(
              'Some satellite tiles are unavailable. Sample overlays remain usable.'
            )
          })

      return () => {
        removeStreetError()
        removeSatelliteError()

        imageryRef.current = {
          satellite: null,
          streets: null
        }
      }
    } catch {
      setMapError(
        'Basemap initialization failed. Sample overlays remain available.'
      )

      return undefined
    }
  }, [ready])


  useEffect(() => {
    if (!ready) {
      return undefined
    }

    const viewer =
      viewerRef.current?.cesiumElement

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return undefined
    }

    const removeError =
      viewer
        .scene
        .renderError
        .addEventListener(() => {
          setMapError(
            'The 3D renderer stopped. Reload to restore the map.'
          )
        })

    const removeLoading =
      viewer
        .scene
        .globe
        .tileLoadProgressEvent
        .addEventListener(count => {
          if (!count) {
            setLoading(false)
          }
        })

    const timer = setTimeout(
      () =>
        setLoading(false),
      8000
    )

    let handler = null

    try {
      handler =
        new ScreenSpaceEventHandler(
          viewer.scene.canvas
        )

      handler.setInputAction(
        event => {
          if (
            viewer.isDestroyed()
          ) {
            return
          }

          const ray =
            viewer
              .camera
              .getPickRay(
                event.endPosition
              )

          const point =
            ray &&
            viewer
              .scene
              .globe
              .pick(
                ray,
                viewer.scene
              )

          if (
            defined(point)
          ) {
            const position =
              Cartographic
                .fromCartesian(point)

            setCoordinates({
              lon:
                CesiumMath
                  .toDegrees(
                    position.longitude
                  ),
              lat:
                CesiumMath
                  .toDegrees(
                    position.latitude
                  ),
              elevation:
                terrainActive
                  ? position.height
                  : null
            })
          }
        },
        ScreenSpaceEventType.MOUSE_MOVE
      )
    } catch {
      setMapError(
        'Map pointer inspection is unavailable.'
      )
    }

    return () => {
      removeError()
      removeLoading()
      clearTimeout(timer)

      if (
        handler &&
        !handler.isDestroyed()
      ) {
        handler.destroy()
      }
    }
  }, [
    ready,
    terrainActive
  ])


  useEffect(() => {
    if (!ready) {
      return undefined
    }

    const viewer =
      viewerRef.current?.cesiumElement

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return undefined
    }

    let cancelled = false

    let removeTerrainError =
      () => {}

    setTerrainActive(false)

    setTerrainError('')

    viewer.terrainProvider =
      new EllipsoidTerrainProvider()

    loadTerrain(
      layers.terrain
    ).then(result => {
      if (
        cancelled ||
        viewer.isDestroyed()
      ) {
        return
      }

      viewer.terrainProvider =
        result.provider

      setTerrainActive(
        result.status === 'active'
      )

      setTerrainError(
        result.warning
      )

      if (
        result.provider
          ?.errorEvent
          ?.addEventListener
      ) {
        removeTerrainError =
          result.provider
            .errorEvent
            .addEventListener(
              () => {
                if (
                  cancelled ||
                  viewer.isDestroyed()
                ) {
                  return
                }

                viewer.terrainProvider =
                  new EllipsoidTerrainProvider()

                setTerrainActive(false)

                setTerrainError(
                  'Ion terrain tiles unavailable · ellipsoid terrain active'
                )
              }
            )
      }
    })

    return () => {
      cancelled = true

      removeTerrainError()
    }
  }, [
    ready,
    layers.terrain
  ])


  useEffect(() => {
    const {
      satellite,
      streets
    } = imageryRef.current

    if (
      !satellite ||
      !streets
    ) {
      return
    }

    try {
      if (
        satellite.isDestroyed?.() ||
        streets.isDestroyed?.()
      ) {
        return
      }

      satellite.show =
        layers.satellite

      streets.show =
        !layers.satellite

      setMapError('')
    } catch {
      setMapError(
        'Unable to change basemap visibility.'
      )
    }
  }, [
    ready,
    layers.satellite
  ])


  const fitFlood =
    useCallback(() => {
      const viewer =
        viewerRef
          .current
          ?.cesiumElement

      if (
        !viewer ||
        viewer.isDestroyed()
      ) {
        return
      }

      const activeFrame =
        getFloodVisual(
          useDashboard
            .getState()
            .minute
        )

      const bounds =
        validFloodBounds(
          activeFrame.ring
        )

      if (!bounds) {
        setMapError(
          'No valid active flood extent to focus. The map remains available.'
        )

        return
      }

      try {
        const finiteCartesian =
          point =>
            point &&
            [
              point.x,
              point.y,
              point.z
            ].every(
              Number.isFinite
            )

        const canvas =
          viewer.scene.canvas

        if (
          !canvas ||
          canvas.clientWidth <= 0 ||
          canvas.clientHeight <= 0
        ) {
          return
        }

        if (
          !finiteCartesian(
            viewer.camera.position
          )
        ) {
          return
        }

        const values = [
          bounds.west,
          bounds.south,
          bounds.east,
          bounds.north
        ]

        if (
          !values.every(
            Number.isFinite
          )
        ) {
          setMapError(
            'Flood focus unavailable. The map remains available.'
          )

          return
        }

        if (
          bounds.west >=
            bounds.east ||
          bounds.south >=
            bounds.north
        ) {
          setMapError(
            'Flood focus unavailable. The map remains available.'
          )

          return
        }

        const rectangle =
          Rectangle.fromDegrees(
            bounds.west,
            bounds.south,
            bounds.east,
            bounds.north
          )

        const target =
          viewer
            .camera
            .getRectangleCameraCoordinates(
              rectangle,
              new Cartesian3()
            )

        if (
          !finiteCartesian(
            target
          )
        ) {
          setMapError(
            'Flood focus unavailable. The map remains available.'
          )

          return
        }

        viewer.camera.cancelFlight()

        viewer.camera.setView({
          destination: target,
          orientation: {
            heading: 0,
            pitch:
              -Math.PI / 2,
            roll: 0
          }
        })

        setMapError('')
      } catch {
        setMapError(
          'Flood focus unavailable. The map remains available.'
        )
      }
    }, [])


  useEffect(() => {
    if (
      ready &&
      focusRequest
    ) {
      fitFlood()
    }
  }, [
    ready,
    focusRequest,
    fitFlood
  ])


  useEffect(() => {
    if (!selected) {
      return undefined
    }

    const close = event => {
      if (
        event.key === 'Escape'
      ) {
        select(null)
      }
    }

    window.addEventListener(
      'keydown',
      close
    )

    return () => {
      window.removeEventListener(
        'keydown',
        close
      )
    }
  }, [
    selected,
    select
  ])


  function recenter() {
    const viewer =
      viewerRef
        .current
        ?.cesiumElement

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }

    viewer.camera.flyTo({
      destination,
      orientation,
      duration:
        reduced
          ? 0
          : 1.5
    })
  }


  function zoom(direction) {
    const viewer =
      viewerRef
        .current
        ?.cesiumElement

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }

    const camera =
      viewer.camera

    const height =
      camera
        .positionCartographic
        ?.height

    if (
      !Number.isFinite(height)
    ) {
      return
    }

    camera[
      direction > 0
        ? 'zoomIn'
        : 'zoomOut'
    ](
      Math.max(
        height * 0.3,
        100
      )
    )
  }


  return (
    <div className="map-container">

      <Viewer
        ref={attachViewer}
        full
        animation={false}
        timeline={false}
        baseLayerPicker={false}
        geocoder={false}
        homeButton={false}
        sceneModePicker={false}
        navigationHelpButton={false}
        fullscreenButton={false}
        infoBox={false}
        selectionIndicator={false}
        shouldAnimate={false}
      >

        <CameraFlyTo
          destination={
            destination
          }
          orientation={
            orientation
          }
          duration={
            reduced
              ? 0
              : 2.4
          }
          once
        />

        <Entity
          name="Hirakud Dam"
          position={
            Cartesian3
              .fromDegrees(
                83.87,
                21.53
              )
          }
          point={{
            pixelSize: 15,
            color:
              cssColor(
                '#60eef2'
              ),
            outlineColor:
              Color.WHITE,
            outlineWidth: 3,
            heightReference:
              HeightReference
                .CLAMP_TO_GROUND,
            disableDepthTestDistance:
              Infinity
          }}
          label={{
            text:
              'HIRAKUD DAM',
            font:
              'bold 13px sans-serif',
            fillColor:
              Color.WHITE,
            style:
              LabelStyle
                .FILL_AND_OUTLINE,
            outlineColor:
              cssColor(
                '#102332'
              ),
            outlineWidth: 4,
            pixelOffset:
              new Cartesian2(
                0,
                -28
              ),
            heightReference:
              HeightReference
                .CLAMP_TO_GROUND,
            disableDepthTestDistance:
              Infinity
          }}
          onClick={() =>
            select({
              type: 'dam',
              name:
                'Hirakud Dam'
            })
          }
        />

        <Entity
          name="Approximate Mahanadi channel"
          polyline={{
            positions:
              riverPositions,
            width: 4,
            material:
              cssColor(
                '#73e7f0',
                0.8
              ),
            clampToGround:
              true
          }}
        />

        {floodGeometry.map(
          band => (
            <Entity
              key={
                band.id
              }
              id={
                'prototype-flood-' +
                band.id
              }
              name={
                'PROTOTYPE SAMPLE DATA · ' +
                band.label
              }
              show={
                layers.flood
              }
              polygon={{
                hierarchy:
                  band.positions,
                material:
                  cssColor(
                    band.color,
                    0.72
                  ),
                outline:
                  false,
                zIndex:
                  band.zIndex
              }}
              onClick={() =>
                select({
                  type:
                    'flood',
                  bandId:
                    band.id
                })
              }
            />
          )
        )}

        {floodGeometry.length >
          0 && (
          <Entity
            name="Prototype flood boundary"
            show={
              layers.flood
            }
            polyline={{
              positions:
                floodGeometry[0]
                  .positions,
              width: 2,
              material:
                cssColor(
                  depthBands[0]
                    .color
                ),
              clampToGround:
                true,
              zIndex: 10
            }}
            onClick={() =>
              select({
                type:
                  'flood',
                bandId:
                  'shallow'
              })
            }
          />
        )}

        {sampleBuildings.map(
          asset => (
            <Entity
              key={
                asset.id
              }
              name={
                asset.name
              }
              show={
                layers.buildings
              }
              position={
                assetPositions
                  .get(
                    asset.id
                  )
              }
              point={{
                pixelSize:
                  12,
                color:
                  cssColor(
                    assetAffected(
                      asset,
                      frame
                    )
                      ? '#ff807e'
                      : '#b6d6d9'
                  ),
                outlineColor:
                  cssColor(
                    '#112432'
                  ),
                outlineWidth:
                  2,
                heightReference:
                  HeightReference
                    .CLAMP_TO_GROUND,
                disableDepthTestDistance:
                  Infinity
              }}
              onClick={() =>
                select(asset)
              }
            />
          )
        )}

        {sampleRoads.map(
          asset => (
            <Entity
              key={
                asset.id
              }
              name={
                asset.name
              }
              show={
                layers.roads
              }
              polyline={{
                positions:
                  roadGeometry
                    .get(
                      asset.id
                    ),
                width: 6,
                material:
                  cssColor(
                    assetAffected(
                      asset,
                      frame
                    )
                      ? '#ff807e'
                      : '#ffc078'
                  ),
                clampToGround:
                  true,
                zIndex: 20
              }}
              onClick={() =>
                select(asset)
              }
            />
          )
        )}

        {sampleFacilities.map(
          asset => (
            <Entity
              key={
                asset.id
              }
              name={
                asset.name
              }
              show={
                layers.facilities
              }
              position={
                assetPositions
                  .get(
                    asset.id
                  )
              }
              point={{
                pixelSize:
                  16,
                color:
                  cssColor(
                    assetAffected(
                      asset,
                      frame
                    )
                      ? '#ff807e'
                      : asset.kind ===
                          'Shelter'
                        ? '#59d5ac'
                        : '#ffc078'
                  ),
                outlineColor:
                  cssColor(
                    '#112432'
                  ),
                outlineWidth:
                  3,
                heightReference:
                  HeightReference
                    .CLAMP_TO_GROUND,
                disableDepthTestDistance:
                  Infinity
              }}
              label={{
                text:
                  asset.kind,
                font:
                  'bold 12px sans-serif',
                fillColor:
                  Color.WHITE,
                style:
                  LabelStyle
                    .FILL_AND_OUTLINE,
                outlineColor:
                  cssColor(
                    '#112432'
                  ),
                outlineWidth:
                  3,
                showBackground:
                  true,
                backgroundColor:
                  cssColor(
                    '#112432',
                    0.9
                  ),
                pixelOffset:
                  new Cartesian2(
                    0,
                    -24
                  ),
                heightReference:
                  HeightReference
                    .CLAMP_TO_GROUND,
                disableDepthTestDistance:
                  Infinity
              }}
              onClick={() =>
                select(asset)
              }
            />
          )
        )}

      </Viewer>


      <div className="map-vignette" />


      <div className="map-heading">

        <div className="eyebrow">
          MAHANADI RIVER BASIN{' '}
          <span>
            ODISHA, INDIA
          </span>
        </div>

        <h1>
          Eyes on the water.
          <br />
          <span>
            Intelligence for
            what’s next.
          </span>
        </h1>

        <div className="map-tags">

          <span>
            <span className="status-dot" />
            {' '}
            3D GEOSPATIAL VIEW
          </span>

          <span>
            PROTOTYPE SAMPLE
            DATA · not HEC-RAS
          </span>

        </div>

      </div>


      <div
        className="layer-controls glass"
        aria-label="Map layers"
      >

        <span>
          <Layers size={15} />
          {' '}
          LAYERS
        </span>

        {layerOptions.map(
          ([
            key,
            Icon,
            label
          ]) => (
            <button
              key={key}
              className={
                layers[key]
                  ? 'active'
                  : ''
              }
              onClick={() =>
                toggleLayer(
                  key
                )
              }
              aria-pressed={
                layers[key]
              }
              aria-label={
                'Toggle ' +
                label
              }
              title={
                'Toggle ' +
                label
              }
            >

              <Icon
                size={16}
              />

              <span>

                {label}

                <small>

                  {counts[key]
                    ? (
                        counts[key]
                          .visible +
                        ' / ' +
                        counts[key]
                          .total +
                        ' visible'
                      )
                    : key ===
                        'terrain'
                      ? (
                          terrainActive
                            ? 'Ion active'
                            : layers.terrain
                              ? 'Ellipsoid fallback'
                              : 'Ellipsoid'
                        )
                      : layers.satellite
                        ? '1 / 1 visible'
                        : '0 / 1 visible'}

                </small>

              </span>

              <i />

            </button>
          )
        )}

      </div>


      <div className="map-navigation glass">

        <IconButton
          label="Recenter on Hirakud Dam"
          onClick={
            recenter
          }
        >
          <Crosshair
            size={19}
          />
        </IconButton>

        <IconButton
          label="Fit to active flood"
          onClick={
            fitFlood
          }
        >
          <Focus
            size={19}
          />
        </IconButton>

        <span />

        <IconButton
          label="Zoom in"
          onClick={() =>
            zoom(1)
          }
        >
          <Plus
            size={19}
          />
        </IconButton>

        <IconButton
          label="Zoom out"
          onClick={() =>
            zoom(-1)
          }
        >
          <Minus
            size={19}
          />
        </IconButton>

      </div>


      <div
        className="active-frame glass"
        role="status"
      >

        T+
        {frame.minute
          .toFixed(1)
          .padStart(
            4,
            '0'
          )}

        <span>
          {'0–' +
            frame.depth
              .toFixed(1) +
            ' m'}
          {' · '}
          {frame.risk}
        </span>

        <small>
          PROTOTYPE SAMPLE DATA
        </small>

      </div>


      {loading && (
        <div className="map-loading">

          <span className="spinner" />

          Loading geospatial
          view

        </div>
      )}


      {(mapError ||
        terrainError ||
        initializationFailed) && (
        <div
          className="map-notice"
          role="status"
        >

          <TriangleAlert
            size={15}
          />

          {mapError ||
            terrainError ||
            'Cesium is still initializing.'}

        </div>
      )}


      {detail && (
        <div
          className="map-popover glass"
          role="dialog"
          aria-label="Map feature details"
        >

          <IconButton
            label="Close map details"
            onClick={() =>
              select(null)
            }
          >
            <X
              size={16}
            />
          </IconButton>

          <span className="eyebrow">
            <MapPin
              size={14}
            />
            {' '}
            PROTOTYPE FEATURE
          </span>

          <h3>

            {detail.type ===
            'flood'
              ? (
                  'Flood extent · T+' +
                  frame.minute +
                  ' min'
                )
              : detail.name}

          </h3>

          {detail.type ===
          'dam'
            ? (
                <p>
                  Mahanadi River ·
                  Odisha
                  <br />
                  21.5300° N ·
                  83.8700° E
                </p>
              )
            : detail.type ===
                'flood'
              ? (
                  <dl>

                    <div>
                      <dt>
                        Selected depth
                        zone
                      </dt>
                      <dd>
                        {selectedBand
                          ?.label ||
                          'No active zone'}
                      </dd>
                    </div>

                    <div>
                      <dt>
                        Prototype risk
                      </dt>
                      <dd>
                        {frame.risk}
                      </dd>
                    </div>

                  </dl>
                )
              : (
                  <dl>

                    <div>
                      <dt>
                        Type
                      </dt>
                      <dd>
                        {detail.kind}
                      </dd>
                    </div>

                    <div>
                      <dt>
                        Threat state
                      </dt>
                      <dd>
                        {threat}
                      </dd>
                    </div>

                  </dl>
                )}

          <small>
            PROTOTYPE SAMPLE DATA ·
            not validated hydraulic
            output.
          </small>

        </div>
      )}


      <div className="depth-legend glass">

        <span>
          WATER DEPTH{' '}
          <small>
            sample
          </small>
        </span>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns:
              '1fr 1fr',
            gap: '8px',
            marginTop: 8
          }}
        >

          {depthBands.map(
            band => (
              <span
                key={
                  band.id
                }
                style={{
                  display:
                    'flex',
                  alignItems:
                    'center',
                  gap: 5
                }}
              >

                <i
                  style={{
                    width: 12,
                    height: 12,
                    background:
                      band.color,
                    borderRadius:
                      2
                  }}
                />

                {band.label}

              </span>
            )
          )}

        </div>

      </div>


      <div className="coordinate-strip">

        <span>
          {coordinates.lat.toFixed(4)}
          ° N
          {'  '}
          {coordinates.lon.toFixed(4)}
          ° E
        </span>

        <span>
          Elevation{' '}
          {coordinates.elevation ===
          null
            ? '—'
            : (
                coordinates.elevation
                  .toFixed(0) +
                ' m'
              )}
        </span>

        <span>
          {terrainActive
            ? 'World Terrain'
            : layers.terrain
              ? 'Ellipsoid fallback'
              : 'Ellipsoid terrain'}
        </span>

      </div>


      <span className="sr-only">
        Token configured:{' '}
        {String(
          isTokenConfigured()
        )}
        . Terrain mode:{' '}
        {terrainActive
          ? 'ion'
          : 'ellipsoid'}
        .
      </span>

    </div>
  )
}