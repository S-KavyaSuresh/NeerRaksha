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

import IconButton from '../common/IconButton'

import {
  getFloodVisual,
  depthBands
} from './floodVisual.js'
import { ujjaniFrame, depthPalette } from '../../data/ujjaniModel.js'
import {
  buildFrameDataSource,
  nearestFrameMinute,
  frameFeatureCount,
  featureCollectionBounds
} from './backendFlood.js'


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
  return Color
    .fromCssColorString(value)
    .withAlpha(alpha)
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

        if (
          Number.isFinite(lon) &&
          Number.isFinite(lat)
        ) {
          return [lon, lat]
        }

        return null
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

        if (
          Number.isFinite(lon) &&
          Number.isFinite(lat)
        ) {
          return [lon, lat]
        }

        return null
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

  if (path.length < 2) {
    return []
  }

  const values = []

  path.forEach(([lon, lat]) => {
    values.push(
      lon,
      lat,
      height
    )
  })

  return Cartesian3.fromDegreesArrayHeights(
    values
  )
}


function toPolygonPositions(
  ring,
  height = 20
) {
  const path = normalizePath(ring)

  if (path.length < 3) {
    return []
  }

  const values = []

  path.forEach(([lon, lat]) => {
    values.push(
      lon,
      lat,
      height
    )
  })

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
    values.push(
      lon,
      lat
    )
  })

  return Cartesian3.fromDegreesArray(
    values
  )
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


/*
 * Creates the temporary synthetic Ujjani inundation corridor.
 *
 * IMPORTANT:
 * This is only a visualization derived from the supplied synthetic
 * river + breach hydrograph.
 *
 * It is NOT HEC-RAS / Delft3D / SPH hydraulic output.
 */
function buildUjjaniFloodRing(studyCase, minute, scenario) {
  return ujjaniFrame(studyCase, minute, scenario).ring
}


export default function MapView() {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)

  const imageryRef = useRef({
    satellite: null,
    streets: null
  })

  const buildingEntities =
    useRef([])

  const roadEntities =
    useRef([])

  const facilityEntities =
    useRef([])

  const studyEntities =
    useRef([])

  const ujjaniFloodRefs = useRef(new Map())

  /* Backend simulation flood frames (real time-dependent GeoJSON from the API). */
  const backendDsRef = useRef(new Map())
  const [backendTick, setBackendTick] = useState(0)

  /*
   * Old prototype flood frames are preserved for legacy cases.
   *
   * Ujjani does NOT use these frames.
   */
  const floodFramesRef =
    useRef(
      new Map()
    )

  const metadata =
    useRef(
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
    lon: 75.120278,
    lat: 18.075
  })

  const {
    minute,
    layers,
    toggleLayer,
    selected,
    select,
    focusRequest,
    selectedStudyCase,
    scenario,
    backend
  } = useDashboard()

  const backendFloodActive =
    selectedStudyCase?.case_id === 'ujjani' &&
    backend?.status === 'completed' &&
    backend?.frames &&
    Object.keys(backend.frames).length > 0

  const backendPoint = (() => {
    if (!backendFloodActive || !Array.isArray(backend.timeline) || !backend.timeline.length) return null
    let pick = null
    for (const point of backend.timeline) {
      if (Number(point.minute) <= Number(minute || 0)) pick = point
    }
    return pick || backend.timeline[0]
  })()


  const visualMinute =
    Math.round(
      Number(minute || 0) * 4
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


  const ujjaniFloodRing =
    useMemo(
      () =>
        buildUjjaniFloodRing(
          selectedStudyCase,
          visualMinute,
          scenario
        ),
      [
        selectedStudyCase,
        visualMinute,
        scenario
      ]
    )


  const counts =
    useMemo(() => {
      const buildingTotal =
        selectedStudyCase?.case_id === 'ujjani'
          ? 0
          : selectedStudyCase
          ?.spatial
          ?.buildings
          ?.features
          ?.length ??
        selectedStudyCase
          ?.exposure
          ?.buildings
          ?.length ??
        0

      const roadTotal =
        selectedStudyCase
          ?.spatial
          ?.real_roads
          ?.features
          ?.length ??
        selectedStudyCase
          ?.exposure
          ?.roads
          ?.length ??
        0

      const facilityTotal =
        selectedStudyCase
          ?.spatial
          ?.real_facilities
          ?.features
          ?.length ??
        selectedStudyCase
          ?.exposure
          ?.facilities
          ?.length ??
        0

      const floodAvailable =
        selectedStudyCase
          ?.case_id ===
        'ujjani'
          ? visualMinute > 0
          : frame.ring.length >= 4

      return {
        buildings: {
          total:
            buildingTotal,

          visible:
            layers.buildings
              ? buildingTotal
              : 0
        },

        roads: {
          total:
            roadTotal,

          visible:
            layers.roads
              ? roadTotal
              : 0
        },

        facilities: {
          total:
            facilityTotal,

          visible:
            layers.facilities
              ? facilityTotal
              : 0
        },

        flood: {
          total:
            floodAvailable
              ? 1
              : 0,

          visible:
            layers.flood &&
            floodAvailable
              ? 1
              : 0
        }
      }
    }, [
      selectedStudyCase,
      layers,
      frame.ring.length,
      ujjaniFloodRing.length
    ])


  const activeFrame = selectedStudyCase?.case_id === 'ujjani'
    ? ujjaniFrame(selectedStudyCase, visualMinute, scenario)
    : frame


  const selectedBand =
    activeFrame.bands.find(
      band =>
        band.id ===
        selected?.bandId
    )


  const detail =
    selected?.type ===
    'flood'
      ? {
          ...activeFrame,
          type: 'flood'
        }
      : selected


  /*
   * ----------------------------------------------------------
   * CREATE CESIUM VIEWER ONCE
   * ----------------------------------------------------------
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

            requestRenderMode: false
          }
        )


      viewerRef.current =
        viewer

      if (typeof window !== 'undefined') window.__NR_VIEWER__ = viewer


      viewer.scene.globe.baseColor =
        cssColor(
          '#172d39'
        )


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
       * LEGACY / NON-UJJANI PROTOTYPE FLOOD FRAMES
       *
       * These are hidden completely whenever Ujjani is active.
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
                !Array.isArray(
                  positions
                ) ||
                positions.length < 3
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
                  type:
                    'flood',

                  bandId:
                    band.id
                }
              )


              entities.push({
                entity,
                bandId:
                  band.id
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
       * MOUSE COORDINATES
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
            Cartographic
              .fromCartesian(
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
      console.error(
        'Cesium initialization error:',
        error
      )

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

      floodFramesRef
        .current
        .clear()


      buildingEntities.current =
        []

      roadEntities.current =
        []

      facilityEntities.current =
        []

      studyEntities.current =
        []


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


  /*
   * ----------------------------------------------------------
   * CREATE / RECREATE CASE-OWNED ENTITIES ONLY WHEN CASE CHANGES
   * ----------------------------------------------------------
   *
   * Viewer itself stays alive.
   */
  useEffect(() => {
    const viewer =
      viewerRef.current


    if (
      !ready ||
      !viewer ||
      viewer.isDestroyed() ||
      !selectedStudyCase
    ) {
      return
    }


    const longitude =
      Number(
        selectedStudyCase.longitude
      )

    const latitude =
      Number(
        selectedStudyCase.latitude
      )


    if (
      !Number.isFinite(longitude) ||
      !Number.isFinite(latitude)
    ) {
      console.error(
        'Invalid study-case coordinates',
        selectedStudyCase
      )

      return
    }


    /*
     * Remove ONLY the previous case entities.
     */
    studyEntities.current.forEach(
      entity => {
        if (!entity) {
          return
        }

        metadata.current.delete(
          entity.id
        )

        try {
          viewer.entities.remove(
            entity
          )
        } catch (error) {
          console.warn(
            'Failed to remove entity:',
            entity?.id,
            error
          )
        }
      }
    )


    studyEntities.current =
      []

    buildingEntities.current =
      []

    roadEntities.current =
      []

    facilityEntities.current =
      []

    ujjaniFloodRefs.current = new Map()


    /*
     * Helper for legacy point-based assets.
     */
    const addPoint = (
      asset,
      type,
      color,
      size
    ) => {
      const assetLongitude =
        Number(
          asset.longitude
        )

      const assetLatitude =
        Number(
          asset.latitude
        )

      if (
        !Number.isFinite(
          assetLongitude
        ) ||
        !Number.isFinite(
          assetLatitude
        )
      ) {
        return null
      }


      const layerKey =
        type === 'building'
          ? 'buildings'
          : type === 'road'
            ? 'roads'
            : 'facilities'


      const entity =
        viewer.entities.add({
          id:
            `${type}-${selectedStudyCase.case_id}-${asset.id}`,

          name:
            asset.name ||
            asset.asset_type ||
            type,

          show:
            Boolean(
              layers[layerKey]
            ),

          position:
            Cartesian3.fromDegrees(
              assetLongitude,
              assetLatitude,
              180
            ),

          point: {
            pixelSize:
              size,

            color,

            outlineColor:
              Color.WHITE,

            outlineWidth:
              2,

            disableDepthTestDistance:
              Number
                .POSITIVE_INFINITY
          }
        })


      const item = {
        ...asset,

        type,

        kind:
          asset.asset_type ||
          type,

        lon:
          assetLongitude,

        lat:
          assetLatitude
      }


      metadata.current.set(
        entity.id,
        item
      )


      studyEntities.current.push(
        entity
      )


      return {
        entity,
        asset:
          item
      }
    }


    /*
     * DAM
     */
    const dam =
      viewer.entities.add({
        id:
          `dam-${selectedStudyCase.case_id}`,

        name:
          selectedStudyCase.dam_name,

        show: true,

        position:
          Cartesian3.fromDegrees(
            longitude,
            latitude,
            180
          ),

        point: {
          pixelSize:
            18,

          color:
            cssColor(
              '#60eef2'
            ),

          outlineColor:
            Color.WHITE,

          outlineWidth:
            3,

          disableDepthTestDistance:
            Number
              .POSITIVE_INFINITY
        },

        label: {
          text:
            `${selectedStudyCase.dam_name} DAM`
              .toUpperCase(),

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

          outlineWidth:
            4,

          pixelOffset:
            new Cartesian2(
              0,
              -28
            ),

          disableDepthTestDistance:
            Number
              .POSITIVE_INFINITY
        }
      })


    metadata.current.set(
      dam.id,
      {
        type: 'dam',
        name:
          selectedStudyCase
            .dam_name
      }
    )


    studyEntities.current.push(
      dam
    )


    /*
     * --------------------------------------------------------
     * UJJANI DATA-DRIVEN CASE
     * --------------------------------------------------------
     */
    if (
      selectedStudyCase.case_id ===
      'ujjani'
    ) {
      const spatial =
        selectedStudyCase.spatial ||
        {}


      /*
       * Generic safe entity-add helper.
       */
      const addStudyEntity = (
        feature,
        layer,
        entityDefinition,
        fallbackId
      ) => {
        if (
          !feature ||
          !feature.geometry
        ) {
          return null
        }


        const props =
          feature.properties ||
          {}


        const id =
          props.building_id ||
          props.road_id ||
          props.facility_id ||
          props.settlement_id ||
          props.id ||
          fallbackId


        try {
          const entity =
            viewer.entities.add({
              id:
                `${layer}-ujjani-${id}`,

              name:
                props.name ||
                props.building_type ||
                props.road_type ||
                layer,

              ...entityDefinition
            })


          studyEntities.current.push(
            entity
          )


          metadata.current.set(
            entity.id,
            {
              ...props,
              type:
                layer ===
                'buildings'
                  ? 'building'
                  : layer ===
                    'roads'
                    ? 'road'
                    : layer ===
                      'facilities'
                      ? 'facility'
                      : layer
            }
          )


          return {
            entity,
            asset:
              props
          }

        } catch (error) {
          console.error(
            `Failed to create ${layer} entity`,
            feature,
            error
          )

          return null
        }
      }


      /*
       * RESERVOIR
       *
       * Always visible as geographic context.
       */
      const reservoirFeatures = []


      reservoirFeatures.forEach(
        (
          feature,
          index
        ) => {
          if (
            feature
              ?.geometry
              ?.type !==
            'Polygon'
          ) {
            return
          }


          const ring =
            feature
              .geometry
              .coordinates
              ?.[0]


          const positions =
            toPolygonPositions(
              ring,
              10
            )


          if (
            positions.length <
            3
          ) {
            return
          }


          addStudyEntity(
            feature,
            'reservoir',
            {
              show: true,

              polygon: {
                hierarchy:
                  new PolygonHierarchy(
                    positions
                  ),

                perPositionHeight:
                  true,

                material:
                  colorMaterial(
                    '#3a9fd1',
                    0.35
                  ),

                /*
                 * Disable outline to avoid Cesium
                 * terrain-clamping outline warning.
                 */
                outline:
                  false
              }
            },

            `reservoir-${index}`
          )
        }
      )


      /*
       * BHIMA RIVER CENTERLINE
       *
       * Always visible as geographic context.
       */
      const riverFeatures =
        spatial
          ?.real_river
          ?.features ||
        []


      riverFeatures.forEach(
        (
          feature,
          index
        ) => {
          if (feature?.geometry?.type !== 'LineString') {
            return
          }


          const positions =
            toPolylinePositions(
              feature
                .geometry
                .coordinates,
              55
            )


          if (
            positions.length <
            2
          ) {
            return
          }


          addStudyEntity(
            feature,
            'river',
            {
              show: true,

              polyline: {
                positions,

                width:
                  4,

                material:
                  colorMaterial(
                    '#60eef2',
                    0.95
                  ),

                clampToGround:
                  true
              },

              label: index === 0 ? {
                text: 'Bhima River',
                font: 'bold 12px sans-serif',
                fillColor: cssColor('#60eef2'),
                style: LabelStyle.FILL_AND_OUTLINE,
                outlineColor: cssColor('#102332'),
                outlineWidth: 3,
                pixelOffset: new Cartesian2(0, -18),
                disableDepthTestDistance: Number.POSITIVE_INFINITY
              } : undefined,

              position: index === 0 ? positions[0] : undefined
            },

            `river-${index}`
          )
        }
      )

      /*
       * TEMPORARY VISUAL DIAGNOSTIC ONLY.
       * This line is intentionally not used by flood, timeline, or exposure code.
       */
      const demTestRiverFeatures = []

      demTestRiverFeatures.forEach(
        (feature, index) => {
          const geometry = feature?.geometry
          const parts = geometry?.type === 'LineString'
            ? [geometry.coordinates]
            : geometry?.type === 'MultiLineString'
              ? geometry.coordinates
              : []

          parts.forEach((coordinates, partIndex) => {
            if (!Array.isArray(coordinates) || coordinates.length < 2) return
            const flatCoordinates = coordinates.flatMap(point =>
              Array.isArray(point) && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]))
                ? [Number(point[0]), Number(point[1])]
                : []
            )
            if (flatCoordinates.length < 4) return
            try {
              const positions = Cartesian3.fromDegreesArray(flatCoordinates)
              const entity = viewer.entities.add({
                id: `dem-test-river-ujjani-${index}-${partIndex}`,
                name: 'DEM TEST RIVER',
                polyline: { positions, width: 5, material: colorMaterial('#ff3dbb', 1), clampToGround: true },
                label: partIndex === 0 ? {
                  text: 'DEM TEST RIVER', font: 'bold 12px sans-serif', fillColor: cssColor('#ff70cd'), style: LabelStyle.FILL_AND_OUTLINE,
                  outlineColor: cssColor('#102332'), outlineWidth: 3, pixelOffset: new Cartesian2(0, -18),
                  disableDepthTestDistance: Number.POSITIVE_INFINITY
                } : undefined,
                position: partIndex === 0 ? positions[0] : undefined
              })
              studyEntities.current.push(entity)
            } catch (error) {
              console.warn('DEM test river visual unavailable', error)
            }
          })
        }
      )


      /*
       * BUILDING FOOTPRINTS
       *
       * The uploaded file contains valid Polygon features.
       * They must remain POLYGONS, not points.
       */
      const buildingFeatures = []


      buildingEntities.current =
        buildingFeatures
          .map(
            (
              feature,
              index
            ) => {
              if (
                feature
                  ?.geometry
                  ?.type !==
                'Polygon'
              ) {
                console.warn(
                  'Skipping unsupported building geometry',
                  feature
                    ?.geometry
                    ?.type
                )

                return null
              }


              const ring =
                feature
                  .geometry
                  .coordinates
                  ?.[0]


              const positions =
                toPolygonPositions(
                  ring,
                  42
                )


              if (
                positions.length <
                3
              ) {
                console.warn(
                  'Skipping invalid building polygon',
                  feature
                    ?.properties
                    ?.building_id
                )

                return null
              }


              return addStudyEntity(
                feature,
                'buildings',
                {
                  show:
                    Boolean(
                      layers
                        .buildings
                    ),

                  polygon: {
                    hierarchy:
                      new PolygonHierarchy(
                        positions
                      ),

                    perPositionHeight:
                      true,

                    material:
                      colorMaterial(
                        '#ffffff',
                        0.72
                      ),

                    outline:
                      false
                  }
                },

                `building-${index}`
              )
            }
          )
          .filter(Boolean)


      /*
       * ROAD LINES
       *
       * The uploaded roads file contains proper LineStrings.
       */
      const roadFeatures =
        (spatial?.real_roads?.features || []).flatMap(feature =>
          feature?.geometry?.type === 'MultiLineString'
            ? feature.geometry.coordinates.map((coordinates, part) => ({ ...feature, geometry: { ...feature.geometry, type: 'LineString', coordinates }, properties: { ...feature.properties, road_part: part } }))
            : [feature]
        )


      roadEntities.current =
        roadFeatures
          .map(
            (
              feature,
              index
            ) => {
              if (
                feature
                  ?.geometry
                  ?.type !==
                'LineString'
              ) {
                console.warn(
                  'Skipping unsupported road geometry',
                  feature
                    ?.geometry
                    ?.type
                )

                return null
              }


              const positions =
                toPolylinePositions(
                  feature
                    .geometry
                    .coordinates,
                  58
                )


              if (
                positions.length <
                2
              ) {
                console.warn(
                  'Skipping invalid road',
                  feature
                    ?.properties
                    ?.road_id
                )

                return null
              }


              return addStudyEntity(
                feature,
                'roads',
                {
                  show:
                    Boolean(
                      layers.roads
                    ),

                  polyline: {
                    positions,

                    width:
                      ['motorway', 'trunk', 'primary'].includes(feature?.properties?.highway)
                        ? 2.5
                        : ['secondary', 'tertiary'].includes(feature?.properties?.highway)
                          ? 1.8
                          : 1,

                    material:
                      colorMaterial(
                        '#d6a956',
                        0.72
                      ),

                    clampToGround:
                      true
                  }
                },

                `road-${index}`
              )
            }
          )
          .filter(Boolean)


      /*
       * FACILITIES
       */
      /* Keep OSM facilities in case data; do not render point markers before exposure modelling. */
      const facilityFeatures = []


      facilityEntities.current =
        facilityFeatures
          .map(
            (
              feature,
              index
            ) => {
              if (
                feature
                  ?.geometry
                  ?.type !==
                'Point'
              ) {
                console.warn(
                  'Skipping unsupported facility geometry',
                  feature
                    ?.geometry
                    ?.type
                )

                return null
              }


              const coords =
                feature
                  ?.geometry
                  ?.coordinates


              if (
                !Array.isArray(
                  coords
                ) ||
                coords.length < 2
              ) {
                return null
              }


              const lon =
                Number(
                  coords[0]
                )

              const lat =
                Number(
                  coords[1]
                )


              if (
                !Number.isFinite(
                  lon
                ) ||
                !Number.isFinite(
                  lat
                )
              ) {
                return null
              }


              return addStudyEntity(
                {
                  ...feature,
                  properties: {
                    ...feature.properties,
                    name: feature?.properties?.name || 'Unnamed facility'
                  }
                },
                'facilities',
                {
                  show:
                    Boolean(
                      layers
                        .facilities
                    ),

                  position:
                    Cartesian3
                      .fromDegrees(
                        lon,
                        lat,
                        120
                      ),

                  point: {
                    pixelSize:
                      7,

                    color:
                      feature?.properties?.amenity === 'hospital' || feature?.properties?.amenity === 'clinic'
                        ? cssColor('#ff7869')
                        : feature?.properties?.amenity === 'police' || feature?.properties?.amenity === 'fire_station'
                          ? cssColor('#ffcf5b')
                          : cssColor('#59d5ac'),

                    outlineColor:
                      Color.WHITE,

                    outlineWidth:
                      2,

                    disableDepthTestDistance:
                      Number
                        .POSITIVE_INFINITY
                  }
                },

                `facility-${index}`
              )
            }
          )
          .filter(Boolean)

      /* Persistent Ujjani depth-band entities. They are updated in-place by the timeline. */
      for (const band of depthPalette) {
        const flood = viewer.entities.add({
          id: `ujjani-flood-${band.id}`,
          name: `Ujjani flood depth · ${band.label}`,
          show: false
        })
        metadata.current.set(flood.id, { type:'flood', bandId:band.id, name:`Water depth ${band.label}` })
        ujjaniFloodRefs.current.set(band.id, flood)
        studyEntities.current.push(flood)
      }

    } else {

      /*
       * Legacy cases remain point-based only where
       * the API itself supplies point assets.
       */
      buildingEntities.current =
        (
          selectedStudyCase
            .exposure
            ?.buildings ||
          []
        )
          .map(
            asset =>
              addPoint(
                asset,
                'building',
                Color.WHITE,
                14
              )
          )
          .filter(Boolean)


      roadEntities.current =
        (
          selectedStudyCase
            .exposure
            ?.roads ||
          []
        )
          .map(
            asset =>
              addPoint(
                asset,
                'road',
                cssColor(
                  '#ffd166'
                ),
                13
              )
          )
          .filter(Boolean)


      facilityEntities.current =
        (
          selectedStudyCase
            .exposure
            ?.facilities ||
          []
        )
          .map(
            asset =>
              addPoint(
                asset,
                'facility',
                cssColor(
                  '#ffc078'
                ),
                16
              )
          )
          .filter(Boolean)
    }


    /*
     * ALWAYS fly directly to selected dam.
     *
     * Do NOT calculate destination from exposure bounds.
     */
    try {
      viewer.camera.cancelFlight()

      viewer.camera.flyTo({
        destination:
          Cartesian3.fromDegrees(
            longitude,
            latitude,
            12000
          ),

        orientation: { heading:0, pitch:CesiumMath.toRadians(-90), roll:0 },

        duration:
          0.8
      })

    } catch (error) {
      console.error(
        'Camera flyTo failed:',
        error
      )
    }


    setMapError('')

  }, [
    ready,
    selectedStudyCase
  ])


  /*
   * ----------------------------------------------------------
   * UJJANI FLOOD UPDATE
   * ----------------------------------------------------------
   * Scenario-specific, continuous approximate routing along the real Bhima reference.
   * Entities persist for the life of the selected study case, so playback cannot blink.
   */
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed() || selectedStudyCase?.case_id !== 'ujjani') return

    const model = ujjaniFrame(selectedStudyCase, minute, scenario)
    const bandById = new Map(model.bands.map(band => [band.id, band]))

    for (const paletteBand of depthPalette) {
      const entity = ujjaniFloodRefs.current.get(paletteBand.id)
      if (!entity) continue
      const band = bandById.get(paletteBand.id)
      // Real backend flood frames take over once the simulation API has returned.
      if (backendFloodActive || !layers.flood || !band?.ring?.length) { entity.show = false; continue }
      const positions = toPolygonPositions(band.ring, 34 + depthPalette.findIndex(item => item.id === paletteBand.id) * 2)
      if (positions.length < 3) { entity.show = false; continue }
      try {
        if (!entity.polygon) entity.polygon = {}
        entity.polygon.hierarchy = new PolygonHierarchy(positions)
        entity.polygon.perPositionHeight = true
        entity.polygon.material = colorMaterial(paletteBand.color, paletteBand.id === 'shallow' ? 0.42 : 0.52)
        entity.polygon.outline = false
        entity.show = true
      } catch (error) {
        console.warn('Ujjani depth band update skipped', paletteBand.id, error)
        entity.show = false
      }
    }
    setMapError('')
  }, [minute, layers.flood, selectedStudyCase, scenario, backendFloodActive])


  /*
   * ----------------------------------------------------------
   * BACKEND SIMULATION FLOOD FRAMES
   * ----------------------------------------------------------
   * Time-dependent flood GeoJSON from POST /api/simulations. Each available
   * minute becomes a hidden GeoJsonDataSource; the timeline effect below shows
   * the frame matching the current minute so the water visibly expands/contracts.
   */
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return undefined

    backendDsRef.current.forEach(source => {
      try { viewer.dataSources.remove(source, true) } catch { /* already gone */ }
    })
    backendDsRef.current = new Map()
    setBackendTick(tick => tick + 1)

    if (!backendFloodActive) return undefined

    let cancelled = false
    const frames = backend.frames
    ;(async () => {
      const minutes = Object.keys(frames).map(Number).sort((a, b) => a - b)
      for (const frameMinute of minutes) {
        if (cancelled) return
        try {
          const source = await buildFrameDataSource(frameMinute, frames[frameMinute])
          if (cancelled) { try { source.entities.removeAll() } catch { /* noop */ } return }
          await viewer.dataSources.add(source)
          backendDsRef.current.set(frameMinute, source)
        } catch (error) {
          console.warn('Backend flood frame failed', frameMinute, error)
        }
      }
      if (!cancelled) setBackendTick(tick => tick + 1)
    })()

    return () => { cancelled = true }
  }, [backendFloodActive, backend.frames])


  /* Show the backend frame matching the current timeline minute. */
  useEffect(() => {
    const sources = backendDsRef.current
    if (!sources.size) return
    const available = [...sources.keys()]
    const target = layers.flood ? nearestFrameMinute(available, minute) : null
    sources.forEach((source, frameMinute) => { source.show = frameMinute === target })
    const viewer = viewerRef.current
    if (viewer && !viewer.isDestroyed()) viewer.scene.requestRender?.()
  }, [minute, layers.flood, backendTick])


  /* Fly to the modelled flood extent once, when a new backend run's frames arrive. */
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed() || !backendFloodActive) return
    const minutes = Object.keys(backend.frames).map(Number).sort((a, b) => b - a)
    let bounds = null
    for (const frameMinute of minutes) {
      bounds = featureCollectionBounds(backend.frames[frameMinute])
      if (bounds) break
    }
    if (!bounds) return
    const [west, south, east, north] = bounds
    const pad = 0.01
    const handle = requestAnimationFrame(() => {
      try {
        const sphere = BoundingSphere.fromPoints(Cartesian3.fromDegreesArray([
          west - pad, south - pad, east + pad, south - pad,
          east + pad, north + pad, west - pad, north + pad
        ]))
        viewer.camera.cancelFlight()
        viewer.camera.flyToBoundingSphere(sphere, {
          duration: 1.2,
          offset: new HeadingPitchRange(0, CesiumMath.toRadians(-78), Math.max(sphere.radius * 2.4, 6000))
        })
      } catch (error) {
        console.warn('Flood auto-fly failed', error)
      }
    })
    return () => cancelAnimationFrame(handle)
  }, [backendFloodActive, backend.id])


  /*
   * SATELLITE / STREET BASEMAP
   */
  useEffect(() => {
    const {
      satellite,
      streets
    } =
      imageryRef.current


    if (
      !satellite ||
      !streets
    ) {
      return
    }


    satellite.show =
      Boolean(
        layers.satellite
      )

    streets.show =
      !layers.satellite

  }, [
    layers.satellite
  ])


  /*
   * TERRAIN STATUS ONLY.
   *
   * Real DEM terrain rendering is not connected yet.
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


    if (
      !viewer.terrainProvider
    ) {
      viewer.terrainProvider =
        new EllipsoidTerrainProvider()
    }

  }, [
    layers.terrain
  ])


  /*
   * LEGACY PROTOTYPE FLOOD VISIBILITY
   *
   * Ujjani never shows these.
   */
  useEffect(() => {
    if (!ready) {
      return
    }


    floodFramesRef
      .current
      .forEach(
        (
          entities,
          frameMinute
        ) => {
          const visible =
            selectedStudyCase
              ?.case_id !==
              'ujjani' &&
            layers.flood &&
            activeDisplayMinute >
              0 &&
            frameMinute ===
              activeDisplayMinute


          entities.forEach(
            ({ entity }) => {
              if (entity) {
                entity.show =
                  visible
              }
            }
          )
        }
      )

  }, [
    ready,
    layers.flood,
    activeDisplayMinute,
    selectedStudyCase
  ])


  /*
   * ----------------------------------------------------------
   * BUILDINGS VISIBILITY
   * ----------------------------------------------------------
   *
   * CRITICAL FIX:
   *
   * Ujjani buildings are POLYGONS.
   *
   * Never assume entity.point exists.
   */
  useEffect(() => {
    buildingEntities
      .current
      .forEach(
        item => {
          const entity =
            item?.entity

          if (!entity) {
            return
          }


          entity.show =
            Boolean(
              layers.buildings
            )


          if (entity.point) {
            entity.point.color =
              Color.WHITE
          }


          if (entity.polygon) {
            entity
              .polygon
              .material =
              colorMaterial(
                '#ffffff',
                0.72
              )
          }
        }
      )

  }, [
    layers.buildings
  ])


  /*
   * ----------------------------------------------------------
   * ROADS VISIBILITY
   * ----------------------------------------------------------
   *
   * CRITICAL FIX:
   *
   * Ujjani roads are POLYLINES.
   *
   * Never assume entity.point exists.
   */
  useEffect(() => {
    roadEntities
      .current
      .forEach(
        item => {
          const entity =
            item?.entity

          if (!entity) {
            return
          }


          entity.show =
            Boolean(
              layers.roads
            )


          if (entity.point) {
            entity.point.color =
              cssColor(
                '#ffd166'
              )
          }


          if (entity.polyline) {
            entity
              .polyline
              .material =
              colorMaterial(
                '#ffd166',
                0.95
              )
          }
        }
      )

  }, [
    layers.roads
  ])


  /*
   * FACILITIES VISIBILITY
   */
  useEffect(() => {
    facilityEntities
      .current
      .forEach(
        item => {
          const entity =
            item?.entity

          if (!entity) {
            return
          }


          entity.show =
            Boolean(
              layers.facilities
            )


          if (entity.point) {
            entity.point.color =
              cssColor(
                '#ffc078'
              )
          }
        }
      )

  }, [
    layers.facilities
  ])


  /*
   * ----------------------------------------------------------
   * FIT ACTIVE FLOOD
   * ----------------------------------------------------------
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


      let ring = []


      const liveBackend = useDashboard.getState().backend
      if (
        liveBackend?.status === 'completed' &&
        liveBackend.frames &&
        Object.keys(liveBackend.frames).length
      ) {
        const orderedMinutes = Object.keys(liveBackend.frames).map(Number).sort((a, b) => b - a)
        for (const frameMinute of orderedMinutes) {
          const bounds = featureCollectionBounds(liveBackend.frames[frameMinute])
          if (bounds) {
            const [w, s, e, n] = bounds
            ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
            break
          }
        }
      }


      if (ring.length >= 3) {
        // backend flood bounds already resolved
      } else if (
        selectedStudyCase
          ?.case_id ===
        'ujjani'
      ) {
        ring =
          buildUjjaniFloodRing(
            selectedStudyCase,
            useDashboard.getState().minute,
            useDashboard.getState().scenario
          )

      } else {
        const current =
          getFloodVisual(
            useDashboard
              .getState()
              .minute
          )

        ring =
          current.ring
      }


      const points =
        toGroundPositions(
          ring
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
          BoundingSphere
            .fromPoints(
              points
            )


        if (
          !sphere ||
          !Number.isFinite(
            sphere.radius
          ) ||
          sphere.radius <=
            0
        ) {
          throw new Error(
            'Invalid flood bounds'
          )
        }


        viewer.camera
          .cancelFlight()


        viewer.camera
          .flyToBoundingSphere(
            sphere,
            {
              duration:
                0.8,

              offset:
                new HeadingPitchRange(
                  0,

                  CesiumMath
                    .toRadians(
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
        console.error(
          'Flood focus failed:',
          error
        )

        setMapError(
          'Flood focus unavailable.'
        )
      }

    }, [
      selectedStudyCase
    ])


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


  /*
   * RECENTER
   */
  function recenter() {
    const viewer =
      viewerRef.current


    if (
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }


    const longitude =
      Number(
        selectedStudyCase
          ?.longitude
      )

    const latitude =
      Number(
        selectedStudyCase
          ?.latitude
      )


    if (
      !Number.isFinite(
        longitude
      ) ||
      !Number.isFinite(
        latitude
      )
    ) {
      return
    }


    try {
      viewer.camera
        .cancelFlight()


      viewer.camera
        .flyTo({
          destination:
            Cartesian3
              .fromDegrees(
                longitude,
                latitude,
                12000
              ),

          orientation: { heading:0, pitch:CesiumMath.toRadians(-90), roll:0 },

          duration:
            0.8
        })

    } catch (error) {
      console.error(
        'Recenter failed:',
        error
      )
    }
  }


  /*
   * ZOOM
   */
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
      !Number.isFinite(
        height
      )
    ) {
      return
    }


    const amount =
      Math.max(
        height * 0.25,
        100
      )


    if (direction > 0) {
      camera.zoomIn(
        amount
      )
    } else {
      camera.zoomOut(
        amount
      )
    }
  }


  return (
    <div className="map-container">

      <div
        ref={containerRef}
        style={{
          position:
            'absolute',

          inset:
            0
        }}
      />


      <div className="map-vignette" />


      <div className="map-heading">

        <div className="eyebrow">

          {selectedStudyCase
            ?.river_name ||
            'STUDY AREA'}

          {' '}
          RIVER BASIN

          {' '}

          <span>

            {selectedStudyCase
              ?.state ||
              'INDIA'}

            , INDIA

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
            {selectedStudyCase?.case_id === 'ujjani'
              ? 'AUTOMATED APPROXIMATE 2D FLOOD-ROUTING PROTOTYPE'
              : 'APPROXIMATE FLOOD-ROUTING MODEL'}
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
                        ? '30 m DEM · simulation input'
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
          onClick={
            recenter
          }
        >
          <Crosshair size={19} />
        </IconButton>


        <IconButton
          label="Fit active flood"
          onClick={
            fitFlood
          }
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
        {(backendPoint ? Number(minute || 0) : activeFrame.minute)
          .toFixed(1)
          .padStart(
            4,
            '0'
          )}


        <span>
          {backendPoint
            ? `max ${Number(backendPoint.max_depth_m || 0).toFixed(1)} m · ${Number(backendPoint.flooded_area_km2 || 0).toFixed(2)} km²`
            : `0–${activeFrame.depth.toFixed(1)} m · ${activeFrame.risk}`}
        </span>


        <small>
          {backendPoint
            ? `${(backend?.engineLabel || 'BACKEND SIMULATION').toUpperCase()} · ${(backend?.dataClass || 'MODEL OUTPUT')}`
            : selectedStudyCase?.case_id === 'ujjani'
              ? 'AUTOMATED APPROXIMATE 2D FLOOD-ROUTING PROTOTYPE'
              : 'APPROXIMATE FLOOD-ROUTING MODEL'}
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
          {' '}
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

              ? `Flood extent · T+${activeFrame.minute.toFixed(1)} min`

              : detail.name ||
                detail.building_type ||
                detail.road_type ||
                detail.type}

          </h3>


          {detail.type ===
          'flood' && (
            <p>
              {selectedBand?.label ||
                'Flood zone'}

              {' · '}

              {activeFrame.risk}
            </p>
          )}


          {detail.type !==
            'flood' &&
            detail.type !==
            'dam' && (

              <p>

                {detail.kind ||
                  detail.amenity ||
                  detail.building_type ||
                  detail.road_type ||
                  detail.type}

                {detail.source && (
                  <><br />Source: {detail.source}</>
                )}

              </p>
            )}


          <small>
            Approximate 2D flood-routing model · not validated operational hydraulic output.
          </small>

        </div>
      )}


      <div className="depth-legend glass">

        <span>
          WATER DEPTH{' '}

          <small>
            approximate model
          </small>
        </span>


        <div
          style={{
            display:
              'grid',

            gridTemplateColumns:
              '1fr 1fr',

            gap:
              8,

            marginTop:
              8
          }}
        >

          {depthBands.map(
            band => (

              <span
                key={band.id}

                style={{
                  display:
                    'flex',

                  alignItems:
                    'center',

                  gap:
                    5
                }}
              >

                <i
                  style={{
                    width:
                      12,

                    height:
                      12,

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
          {coordinates.lat
            .toFixed(4)}
          ° N{' '}

          {coordinates.lon
            .toFixed(4)}
          ° E
        </span>


        <span>
          Elevation —
        </span>


        <span>
          30 m DEM · simulation input
        </span>

      </div>

    </div>
  )
}
