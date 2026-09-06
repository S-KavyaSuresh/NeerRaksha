import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react'

import {
  Viewer as CesiumViewer,
  Cartesian3,
  Cartesian2,
  Color,
  ColorMaterialProperty,
  EllipsoidTerrainProvider,
  UrlTemplateImageryProvider,
  OpenStreetMapImageryProvider,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Cartographic,
  Math as CesiumMath,
  LabelStyle,
  BoundingSphere,
  HeadingPitchRange,
  PolygonHierarchy
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
import {
  assetAffected
} from '../../data/prototype.js'

import IconButton from '../common/IconButton'

import {
  getFloodVisual,
  depthBands
} from './floodVisual.js'

const INITIAL_ORIENTATION = {
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

const PRECOMPUTED_MINUTES = Array.from(
  { length: 60 },
  (_, index) => index + 1
)

function cssColor(value, alpha = 1) {
  return Color.fromCssColorString(value).withAlpha(alpha)
}

function colorMaterial(value, alpha = 1) {
  return new ColorMaterialProperty(
    cssColor(value, alpha)
  )
}

function normalizePath(points) {
  if (!Array.isArray(points)) {
    return []
  }

  if (
    points.length >= 2 &&
    typeof points[0] === 'number'
  ) {
    const output = []

    for (
      let index = 0;
      index < points.length - 1;
      index += 2
    ) {
      const lon = Number(points[index])
      const lat = Number(points[index + 1])

      if (
        Number.isFinite(lon) &&
        Number.isFinite(lat)
      ) {
        output.push([lon, lat])
      }
    }

    return output
  }

  return points
    .map(point => {
      if (
        Array.isArray(point) &&
        point.length >= 2
      ) {
        const lon = Number(point[0])
        const lat = Number(point[1])

        return Number.isFinite(lon) &&
          Number.isFinite(lat)
          ? [lon, lat]
          : null
      }

      if (
        point &&
        typeof point === 'object'
      ) {
        const lon = Number(
          point.lon ??
          point.lng ??
          point.longitude
        )

        const lat = Number(
          point.lat ??
          point.latitude
        )

        return Number.isFinite(lon) &&
          Number.isFinite(lat)
          ? [lon, lat]
          : null
      }

      return null
    })
    .filter(Boolean)
}

function toPolylinePositions(
  points,
  height = 80
) {
  const path = normalizePath(points)
  const values = []

  path.forEach(([lon, lat]) => {
    values.push(lon, lat, height)
  })

  if (values.length < 6) {
    return []
  }

  return Cartesian3.fromDegreesArrayHeights(
    values
  )
}

function toPolygonPositions(
  ring,
  height = 20
) {
  const path = normalizePath(ring)
  const values = []

  path.forEach(([lon, lat]) => {
    values.push(lon, lat, height)
  })

  if (values.length < 9) {
    return []
  }

  return Cartesian3.fromDegreesArrayHeights(
    values
  )
}

function toGroundPositions(ring) {
  const path = normalizePath(ring)

  if (path.length < 3) {
    return []
  }

  const values = []

  path.forEach(([lon, lat]) => {
    values.push(lon, lat)
  })

  return Cartesian3.fromDegreesArray(values)
}

function displayMinuteFor(value) {
  const minute = Number(value)

  if (
    !Number.isFinite(minute) ||
    minute <= 0
  ) {
    return 0
  }

  return Math.max(
    1,
    Math.min(
      60,
      Math.round(minute)
    )
  )
}

export default function MapView() {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)

  const imageryRef = useRef({
    satellite: null,
    streets: null
  })

  const buildingEntities = useRef([])
  const roadEntities = useRef([])
  const facilityEntities = useRef([])
  const studyEntities = useRef([])

  /*
   * Flood entities are PRECOMPUTED.
   *
   * Structure:
   * Map<minute, Array<{ entity, bandId }>>
   *
   * We never mutate polygon geometry during playback.
   * We only change entity.show.
   */
  const floodFramesRef = useRef(
    new Map()
  )

  const metadata = useRef(
    new Map()
  )

  const [
    ready,
    setReady
  ] = useState(false)

  const [
    loading,
    setLoading
  ] = useState(true)

  const [
    mapError,
    setMapError
  ] = useState('')

  const [
    coordinates,
    setCoordinates
  ] = useState({
    lon: 83.87,
    lat: 21.53
  })

  const {
    minute,
    layers,
    toggleLayer,
    selected,
    select,
    focusRequest,
    selectedStudyCase
  } = useDashboard()

  const visualMinute =
    Math.round(
      minute * 4
    ) / 4

  const frame = useMemo(
    () =>
      getFloodVisual(
        visualMinute
      ),
    [visualMinute]
  )

  const activeDisplayMinute =
    displayMinuteFor(
      visualMinute
    )

  const counts = useMemo(() => ({
    buildings: { total: selectedStudyCase?.exposure?.buildings?.length || 0, visible: layers.buildings ? selectedStudyCase?.exposure?.buildings?.length || 0 : 0 },
    roads: { total: selectedStudyCase?.exposure?.roads?.length || 0, visible: layers.roads ? selectedStudyCase?.exposure?.roads?.length || 0 : 0 },
    facilities: { total: selectedStudyCase?.exposure?.facilities?.length || 0, visible: layers.facilities ? selectedStudyCase?.exposure?.facilities?.length || 0 : 0 },
    flood: { total: frame.ring.length ? 1 : 0, visible: layers.flood ? 1 : 0 }
  }), [selectedStudyCase, layers, frame.ring.length])

  const selectedBand =
    frame.bands.find(
      band =>
        band.id ===
        selected?.bandId
    )

  const detail =
    selected?.type ===
    'flood'
      ? {
          ...frame,
          type: 'flood'
        }
      : selected

  const threat =
    detail &&
    ![
      'dam',
      'flood'
    ].includes(detail.type)
      ? assetAffected(
          detail,
          frame
        )
        ? detail.type === 'road'
          ? 'Blocked (sample)'
          : 'Flooded (sample)'
        : 'Outside current flood'
      : null

  /*
   * CREATE CESIUM ONCE
   */
  useEffect(() => {
    if (!containerRef.current) {
      return undefined
    }

    let viewer = null
    let handler = null

    try {
      viewer =
        new CesiumViewer(
          containerRef.current,
          {
            animation: false,
            timeline: false,

            /*
             * Prevent default Cesium Ion imagery.
             */
            baseLayer: false,
            baseLayerPicker: false,

            terrainProvider:
              new EllipsoidTerrainProvider(),

            geocoder: false,
            homeButton: false,
            sceneModePicker: false,
            navigationHelpButton:
              false,
            fullscreenButton: false,
            infoBox: false,
            selectionIndicator:
              false,
            shouldAnimate: false,

            /*
             * Always render after state changes.
             * This avoids stale frames without needing
             * aggressive requestRender calls.
             */
            requestRenderMode: false
          }
        )

      viewerRef.current =
        viewer

      viewer.scene.globe.baseColor =
        cssColor('#172d39')

      /*
       * BASEMAPS
       */
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
            'Tiles © Esri'
        })

      const streets =
        viewer.imageryLayers
          .addImageryProvider(
            streetsProvider
          )

      const satellite =
        viewer.imageryLayers
          .addImageryProvider(
            satelliteProvider
          )

      imageryRef.current = {
        satellite,
        streets
      }

      const satelliteEnabled =
        useDashboard
          .getState()
          .layers
          .satellite

      satellite.show =
        satelliteEnabled

      streets.show =
        !satelliteEnabled

      /*
       * PRECOMPUTE ALL 60 FLOOD FRAMES
       *
       * This is the important anti-blink fix.
       *
       * Cesium does not have to rebuild PolygonGraphics
       * while Play is running.
       */
      PRECOMPUTED_MINUTES.forEach(
        frameMinute => {
          const snapshot =
            getFloodVisual(
              frameMinute
            )

          const entities = []

          snapshot.bands.forEach(
            (
              band,
              index
            ) => {
              const positions =
                toPolygonPositions(
                  band.ring,
                  20 +
                    index * 10
                )

              if (
                positions.length <
                3
              ) {
                return
              }

              const entity =
                viewer.entities.add({
                  id:
                    `prototype-flood-${frameMinute}-${band.id}`,

                  name:
                    `Modelled flood T+${frameMinute} · ${band.label}`,

                  show: false,

                  polygon: {
                    hierarchy:
                      new PolygonHierarchy(
                        positions
                      ),

                    perPositionHeight:
                      true,

                    material:
                      colorMaterial(
                        band.color,
                        0.54
                      ),

                    outline:
                      false
                  }
                })

              metadata.current.set(
                entity.id,
                {
                  type: 'flood',
                  bandId: band.id
                }
              )

              entities.push({
                entity,
                bandId: band.id
              })
            }
          )

          floodFramesRef.current.set(
            frameMinute,
            entities
          )
        }
      )

      /*
       * FEATURE PICKING
       */
      handler =
        new ScreenSpaceEventHandler(
          viewer.scene.canvas
        )

      handler.setInputAction(
        movement => {
          const picked =
            viewer.scene.pick(
              movement.position
            )

          const entity =
            picked?.id

          if (!entity) {
            return
          }

          const item =
            metadata.current.get(
              entity.id
            )

          if (item) {
            useDashboard
              .getState()
              .select(item)
          }
        },
        ScreenSpaceEventType
          .LEFT_CLICK
      )

      /*
       * COORDINATES
       */
      handler.setInputAction(
        movement => {
          const ray =
            viewer.camera
              .getPickRay(
                movement.endPosition
              )

          if (!ray) {
            return
          }

          const position =
            viewer.scene.globe.pick(
              ray,
              viewer.scene
            )

          if (!position) {
            return
          }

          const cartographic =
            Cartographic.fromCartesian(
              position
            )

          setCoordinates({
            lon:
              CesiumMath.toDegrees(
                cartographic.longitude
              ),

            lat:
              CesiumMath.toDegrees(
                cartographic.latitude
              )
          })
        },
        ScreenSpaceEventType
          .MOUSE_MOVE
      )

      setLoading(false)
      setReady(true)

    } catch (error) {
      console.error(error)

      setMapError(
        '3D map initialization failed.'
      )

      setLoading(false)
    }

    return () => {
      if (
        handler &&
        !handler.isDestroyed()
      ) {
        handler.destroy()
      }

      metadata.current.clear()
      floodFramesRef.current.clear()

      buildingEntities.current =
        []

      roadEntities.current =
        []

      facilityEntities.current =
        []

      studyEntities.current = []

      imageryRef.current = {
        satellite: null,
        streets: null
      }

      if (
        viewer &&
        !viewer.isDestroyed()
      ) {
        viewer.destroy()
      }

      viewerRef.current =
        null
    }
  }, [])

  /* Update only case-owned entities and camera; the Cesium Viewer stays mounted. */
  useEffect(() => {
    const viewer = viewerRef.current
    if (!ready || !viewer || viewer.isDestroyed() || !selectedStudyCase) return
    const longitude = Number(selectedStudyCase.longitude)
    const latitude = Number(selectedStudyCase.latitude)
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return

    studyEntities.current.forEach(entity => {
      metadata.current.delete(entity.id)
      viewer.entities.remove(entity)
    })
    studyEntities.current = []
    buildingEntities.current = []
    roadEntities.current = []
    facilityEntities.current = []

    const addPoint = (asset, type, color, size) => {
      const assetLongitude = Number(asset.longitude)
      const assetLatitude = Number(asset.latitude)
      if (!Number.isFinite(assetLongitude) || !Number.isFinite(assetLatitude)) return null
      const entity = viewer.entities.add({
        id: `${type}-${selectedStudyCase.case_id}-${asset.id}`,
        name: asset.name || asset.asset_type || type,
        show: layers[type === 'building' ? 'buildings' : `${type}s`],
        position: Cartesian3.fromDegrees(assetLongitude, assetLatitude, 180),
        point: { pixelSize: size, color, outlineColor: Color.WHITE, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY }
      })
      const item = { ...asset, type, kind: asset.asset_type || type, lon: assetLongitude, lat: assetLatitude }
      metadata.current.set(entity.id, item)
      studyEntities.current.push(entity)
      return { entity, asset: item }
    }

    const dam = viewer.entities.add({
      id: `dam-${selectedStudyCase.case_id}`,
      name: selectedStudyCase.dam_name,
      position: Cartesian3.fromDegrees(longitude, latitude, 180),
      point: { pixelSize: 18, color: cssColor('#60eef2'), outlineColor: Color.WHITE, outlineWidth: 3, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      label: { text: `${selectedStudyCase.dam_name} DAM`.toUpperCase(), font: 'bold 13px sans-serif', fillColor: Color.WHITE, style: LabelStyle.FILL_AND_OUTLINE, outlineColor: cssColor('#102332'), outlineWidth: 4, pixelOffset: new Cartesian2(0, -28), disableDepthTestDistance: Number.POSITIVE_INFINITY }
    })
    metadata.current.set(dam.id, { type: 'dam', name: selectedStudyCase.dam_name })
    studyEntities.current.push(dam)
    buildingEntities.current = (selectedStudyCase.exposure?.buildings || []).map(asset => addPoint(asset, 'building', Color.WHITE, 14)).filter(Boolean)
    roadEntities.current = (selectedStudyCase.exposure?.roads || []).map(asset => addPoint(asset, 'road', cssColor('#ffd166'), 13)).filter(Boolean)
    facilityEntities.current = (selectedStudyCase.exposure?.facilities || []).map(asset => addPoint(asset, 'facility', cssColor('#ffc078'), 16)).filter(Boolean)
    viewer.camera.flyTo({ destination: Cartesian3.fromDegrees(longitude, latitude, 30000), orientation: INITIAL_ORIENTATION, duration: 0.8 })
  }, [ready, selectedStudyCase])

  /*
   * SATELLITE / OSM
   */
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

    satellite.show =
      layers.satellite

    streets.show =
      !layers.satellite
  }, [
    layers.satellite
  ])

  /*
   * TERRAIN
   *
   * There is no real terrain provider yet.
   * Therefore this button is only status for now.
   * Crucially, it DOES NOT swap providers or rebuild Cesium.
   */
  useEffect(() => {
    const viewer =
      viewerRef.current

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }

    viewer.terrainProvider =
      viewer.terrainProvider ||
      new EllipsoidTerrainProvider()
  }, [
    layers.terrain
  ])

  /*
   * FLOOD FRAME VISIBILITY
   *
   * Geometry NEVER changes during playback.
   * Only show flags change.
   */
  useEffect(() => {
    if (!ready) {
      return
    }

    floodFramesRef.current.forEach(
      (
        entities,
        frameMinute
      ) => {
        const visible =
          layers.flood &&
          activeDisplayMinute > 0 &&
          frameMinute ===
            activeDisplayMinute

        entities.forEach(
          ({ entity }) => {
            entity.show =
              visible
          }
        )
      }
    )
  }, [
    ready,
    layers.flood,
    activeDisplayMinute
  ])

  /*
   * BUILDINGS
   */
  useEffect(() => {
    buildingEntities.current.forEach(
      ({
        entity,
        asset
      }) => {
        entity.show =
          layers.buildings

        entity.point.color = Color.WHITE
      }
    )
  }, [
    layers.buildings,
    frame
  ])

  /*
   * ROADS
   */
  useEffect(() => {
    roadEntities.current.forEach(
      ({
        entity,
        asset
      }) => {
        entity.show =
          layers.roads

        entity.point.color = cssColor('#ffd166')
      }
    )
  }, [
    layers.roads,
    frame
  ])

  /*
   * FACILITIES
   */
  useEffect(() => {
    facilityEntities.current.forEach(
      ({
        entity,
        asset
      }) => {
        entity.show =
          layers.facilities

        entity.point.color = cssColor('#ffc078')
      }
    )
  }, [
    layers.facilities,
    frame
  ])

  /*
   * ROBUST FLOOD FOCUS
   */
  const fitFlood =
    useCallback(() => {
      const viewer =
        viewerRef.current

      if (
        !viewer ||
        viewer.isDestroyed()
      ) {
        return
      }

      const current =
        getFloodVisual(
          useDashboard
            .getState()
            .minute
        )

      const points =
        toGroundPositions(
          current.ring
        )

      if (
        points.length < 3
      ) {
        setMapError(
          'No active flood extent to focus.'
        )

        return
      }

      try {
        const sphere =
          BoundingSphere.fromPoints(
            points
          )

        if (
          !sphere ||
          !Number.isFinite(
            sphere.radius
          ) ||
          sphere.radius <= 0
        ) {
          throw new Error(
            'Invalid flood bounds'
          )
        }

        viewer.camera.cancelFlight()

        viewer.camera
          .flyToBoundingSphere(
            sphere,
            {
              duration: 0.8,

              offset:
                new HeadingPitchRange(
                  0,
                  CesiumMath.toRadians(
                    -70
                  ),
                  Math.max(
                    sphere.radius *
                      2.2,
                    5000
                  )
                )
            }
          )

        setMapError('')
      } catch (error) {
        console.error(error)

        /*
         * Fallback view instead of breaking Emergency Mode.
         */
        try {
          const path =
            normalizePath(
              current.ring
            )

          const averageLon =
            path.reduce(
              (
                total,
                point
              ) =>
                total +
                point[0],
              0
            ) /
            path.length

          const averageLat =
            path.reduce(
              (
                total,
                point
              ) =>
                total +
                point[1],
              0
            ) /
            path.length

          viewer.camera.flyTo({
            destination:
              Cartesian3.fromDegrees(
                averageLon,
                averageLat,
                22000
              ),

            orientation: {
              heading: 0,
              pitch:
                CesiumMath.toRadians(
                  -70
                ),
              roll: 0
            },

            duration: 0.8
          })

          setMapError('')
        } catch (fallbackError) {
          console.error(
            fallbackError
          )

          setMapError(
            'Flood focus unavailable.'
          )
        }
      }
    }, [])

  /*
   * EMERGENCY MODE FOCUS
   */
  useEffect(() => {
    if (
      !ready ||
      !focusRequest
    ) {
      return undefined
    }

    const handle =
      requestAnimationFrame(
        fitFlood
      )

    return () => {
      cancelAnimationFrame(
        handle
      )
    }
  }, [
    ready,
    focusRequest,
    fitFlood
  ])

  function recenter() {
    const viewer =
      viewerRef.current

    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }

    viewer.camera.flyTo({
      destination: selectedStudyCase && Number.isFinite(Number(selectedStudyCase.longitude)) && Number.isFinite(Number(selectedStudyCase.latitude))
        ? Cartesian3.fromDegrees(Number(selectedStudyCase.longitude), Number(selectedStudyCase.latitude), 30000)
        : viewer.camera.position,

      orientation:
        INITIAL_ORIENTATION,

      duration: 1
    })
  }

  function zoom(direction) {
    const viewer =
      viewerRef.current

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

    const amount =
      Math.max(
        height * 0.25,
        100
      )

    if (direction > 0) {
      camera.zoomIn(amount)
    } else {
      camera.zoomOut(amount)
    }
  }

  return (
    <div className="map-container">

      <div
        ref={containerRef}
        style={{
          position: 'absolute',
          inset: 0
        }}
      />

      <div className="map-vignette" />

      <div className="map-heading">

        <div className="eyebrow">
          {selectedStudyCase?.river_name || 'STUDY AREA'} RIVER BASIN{' '}
          <span>
            {selectedStudyCase?.state || 'INDIA'}, INDIA
          </span>
        </div>

        <h1>
          Eyes on the water.
          <br />

          <span>
            Intelligence for what’s next.
          </span>
        </h1>

        <div className="map-tags">

          <span>
            <span className="status-dot" />
            {' '}
            3D GEOSPATIAL VIEW
          </span>

          <span>
            SYNTHETIC SIMULATION DATA · not hydraulic output
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
                toggleLayer(key)
              }

              aria-pressed={
                layers[key]
              }
            >

              <Icon size={16} />

              <span>

                {label}

                <small>

                  {counts[key]
                    ? `${counts[key].visible} / ${counts[key].total} visible`

                    : key ===
                      'terrain'

                      ? layers.terrain
                        ? 'DEM pending'
                        : 'Terrain off'

                      : layers.satellite
                        ? '1 / 1 visible'
                        : '0 / 1 visible'}

                </small>

              </span>

            </button>
          )
        )}

      </div>

      <div className="map-navigation glass">

        <IconButton
          label="Recenter"
          onClick={recenter}
        >
          <Crosshair size={19} />
        </IconButton>

        <IconButton
          label="Fit active flood"
          onClick={fitFlood}
        >
          <Focus size={19} />
        </IconButton>

        <IconButton
          label="Zoom in"
          onClick={() =>
            zoom(1)
          }
        >
          <Plus size={19} />
        </IconButton>

        <IconButton
          label="Zoom out"
          onClick={() =>
            zoom(-1)
          }
        >
          <Minus size={19} />
        </IconButton>

      </div>

      <div className="active-frame glass">

        T+
        {frame.minute
          .toFixed(1)
          .padStart(
            4,
            '0'
          )}

        <span>
          0–
          {frame.depth
            .toFixed(1)}
          {' '}
          m · {frame.risk}
        </span>

        <small>
          SYNTHETIC SIMULATION DATA
        </small>

      </div>

      {loading && (
        <div className="map-loading">
          Loading geospatial view
        </div>
      )}

      {mapError && (
        <div
          className="map-notice"
          role="status"
        >
          <TriangleAlert size={15} />
          {mapError}
        </div>
      )}

      {detail && (
        <div className="map-popover glass">

          <IconButton
            label="Close"
            onClick={() =>
              select(null)
            }
          >
            <X size={16} />
          </IconButton>

          <span className="eyebrow">
            <MapPin size={14} />
            {' '}
            SIMULATION FEATURE
          </span>

          <h3>

            {detail.type ===
            'flood'
              ? `Flood extent · T+${frame.minute.toFixed(1)} min`
              : detail.name}

          </h3>

          {detail.type ===
          'flood' && (
            <p>
              {selectedBand?.label ||
                'Flood zone'}

              {' · '}

              {frame.risk}
            </p>
          )}

          {detail.type !==
            'flood' &&
            detail.type !==
              'dam' && (

              <p>
                {detail.kind}
                <br />
                {threat}
              </p>
            )}

          <small>
            SYNTHETIC SIMULATION DATA · not validated hydraulic output.
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
            gap: 8,
            marginTop: 8
          }}
        >

          {depthBands.map(
            band => (

              <span
                key={band.id}

                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5
                }}
              >

                <i
                  style={{
                    width: 12,
                    height: 12,
                    background:
                      band.color,
                    borderRadius: 2
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
          ° N{' '}
          {coordinates.lon.toFixed(4)}
          ° E
        </span>

        <span>
          Elevation —
        </span>

        <span>
          DEM terrain pending
        </span>

      </div>

    </div>
  )
}
