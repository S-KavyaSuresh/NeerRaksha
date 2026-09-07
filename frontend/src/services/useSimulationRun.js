import { useEffect } from 'react'
import { useDashboard } from '../store/useDashboard'
import {
  createSimulation,
  getSimulation,
  getSimulationTimeline,
  getSimulationFrame,
  getSimulationSummary,
  runScenario,
  getScenario,
  getScenarioResults,
  getScenarioFrame
} from './api'

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const TERMINAL = ['completed', 'failed', 'cancelled']
const processed = new Set()

/*
 * Bridges the "Run Simulation" action on /simulation to a real backend run.
 *
 *  - engine "delft3d"  -> Phase-4 Ujjani scenario workflow (POST /api/scenarios/run):
 *      internal breach source at the physical Ujjani Dam on the real terrain mesh.
 *  - engine "approximate" / "sph" -> the /api/simulations lifecycle.
 *
 * Both paths populate the same `backend` store slice, so the Cesium flood layer,
 * the timeline and the Scenario Intelligence panel all read one source of truth.
 * Keyed on runNonce so the local prototype timer completing cannot abort the load.
 */
export function useSimulationRun() {
  const runNonce = useDashboard(state => state.runNonce)
  const setBackend = useDashboard(state => state.setBackend)

  useEffect(() => {
    if (!runNonce || processed.has(runNonce)) return
    processed.add(runNonce)
    const engine = useDashboard.getState().simEngine || 'approximate'

    const resetFields = {
      status: 'queued', progress: 0, message: 'Submitting scenario', error: '',
      frames: {}, availableFrames: [], timeline: [], summary: null,
      engineLabel: null, dataClass: null, provenance: null, disclaimer: null,
      validatedHydraulicOutput: false, fallbackUsed: false,
      maxDepthM: null, maxVelocityMps: null, mapFrames: null, runtimeSeconds: null,
      particleCount: null, timesteps: null, maxDensity: null, minDensity: null,
      maxDisplacementM: null, mesh: null, damLocation: null
    }

    if (engine === 'delft3d') {
      runPhase4Scenario(setBackend, resetFields)
    } else {
      runSimulationLifecycle(engine, setBackend, resetFields)
    }
  }, [runNonce, setBackend])
}

/* ---------- Phase-4 Ujjani scenario (breach at the physical dam) ------------ */
async function runPhase4Scenario(setBackend, resetFields) {
  const sc = useDashboard.getState().scenario || {}
  const preset = sc.breach_type === 'partial'
    ? 'small_breach'
    : sc.breach_type === 'major' ? 'large_rapid_breach' : 'medium_breach'
  const params = {}
  if (Number.isFinite(Number(sc.breach_width_m))) params.breach_width_m = Number(sc.breach_width_m)
  if (Number.isFinite(Number(sc.breach_time_minutes))) params.breach_formation_time_s = Number(sc.breach_time_minutes) * 60
  params.simulation_duration_s = Number.isFinite(Number(sc.simulation_duration_minutes))
    ? Number(sc.simulation_duration_minutes) * 60 : 1800
  params.output_interval_s = 300

  try {
    setBackend(resetFields)
    const created = await runScenario({ engine: 'delft3d', preset, params })
    setBackend({ id: created.id, status: created.status, progress: created.progress, message: created.message })

    let snap = created
    let guard = 0
    while (!TERMINAL.includes(snap.status) && guard < 900) {
      await sleep(800); guard += 1
      snap = await getScenario(created.id)
      setBackend({
        status: snap.status, progress: snap.progress, message: snap.message,
        engineLabel: snap.engine_label, dataClass: snap.data_class,
        validatedHydraulicOutput: snap.validation_status === 'VALIDATED',
        maxDepthM: snap.max_depth_m, maxVelocityMps: snap.max_velocity_mps,
        mesh: snap.mesh, mapFrames: (snap.available_frames || []).length,
        runtimeSeconds: snap.runtime_seconds, damLocation: snap.dam_location,
        provenance: snap.release_representation
      })
    }
    if (snap.status !== 'completed') {
      const detail = snap.error && (snap.error.detail || snap.error.reason)
      setBackend({ error: `Delft3D (Ujjani scenario) failed: ${detail || snap.message || 'no output'}` })
      return
    }

    const results = await getScenarioResults(created.id)
    const minutes = results.available_frames || []
    const loaded = await Promise.all(minutes.map(async m => {
      try { return [m, await getScenarioFrame(created.id, m)] }
      catch { return [m, { type: 'FeatureCollection', features: [] }] }
    }))
    const frames = {}
    for (const [m, fc] of loaded) frames[m] = fc

    setBackend({
      frames, availableFrames: minutes,
      timeline: (results.summary && results.summary.timeline) || [],
      summary: results.summary,
      status: 'completed', progress: 100,
      message: 'Ujjani breach flood timeline ready',
      engineLabel: results.engine_label || 'Delft3D D-Flow FM — internal breach at Ujjani dam',
      dataClass: 'MODEL OUTPUT',
      provenance: results.provenance,
      disclaimer: 'MODEL DEMONSTRATION / SCENARIO SIMULATION · NOT VALIDATED FOR OPERATIONAL PREDICTION',
      validatedHydraulicOutput: false, fallbackUsed: false,
      maxDepthM: results.max_depth_m, maxVelocityMps: results.max_velocity_mps,
      mesh: results.mesh, damLocation: results.dam_location
    })
  } catch (error) {
    setBackend({ status: 'error', error: 'Ujjani scenario API unavailable — start the backend and retry.' })
  }
}

/* ---------- /api/simulations lifecycle (approximate / sph demos) ----------- */
async function runSimulationLifecycle(engine, setBackend, resetFields) {
  const scenario = useDashboard.getState().scenario
  const maxPolls = engine === 'sph' ? 900 : 120
  try {
    setBackend(resetFields)
    const created = await createSimulation(scenario, engine)
    setBackend({ id: created.id, status: created.status, progress: created.progress, message: created.message })

    let snapshot = created
    let guard = 0
    while (!TERMINAL.includes(snapshot.status) && guard < maxPolls) {
      await sleep(700); guard += 1
      snapshot = await getSimulation(created.id)
      setBackend({
        status: snapshot.status, progress: snapshot.progress, message: snapshot.message,
        engineLabel: snapshot.engine_label, dataClass: snapshot.data_class,
        provenance: snapshot.provenance, validatedHydraulicOutput: snapshot.validated_hydraulic_output,
        disclaimer: snapshot.disclaimer, fallbackUsed: snapshot.fallback_used,
        maxDepthM: snapshot.max_depth_m, maxVelocityMps: snapshot.max_velocity_mps,
        mapFrames: snapshot.map_frames, runtimeSeconds: snapshot.runtime_seconds, mesh: snapshot.mesh,
        particleCount: snapshot.particle_count, timesteps: snapshot.timesteps,
        maxDensity: snapshot.max_density, minDensity: snapshot.min_density,
        maxDisplacementM: snapshot.max_displacement_m
      })
    }
    if (snapshot.status !== 'completed') {
      const detail = snapshot.error && snapshot.error.detail
      const label = engine === 'sph' ? 'SPH' : null
      setBackend({ error: label ? `${label} failed: ${detail || snapshot.message || 'no output'}` : (snapshot.message || 'Simulation did not complete.') })
      return
    }

    const timeline = await getSimulationTimeline(created.id)
    const minutes = (timeline.available_frames && timeline.available_frames.length)
      ? timeline.available_frames : (snapshot.available_frames || [])
    const loaded = await Promise.all(minutes.map(async minute => {
      try { return [minute, await getSimulationFrame(created.id, minute)] }
      catch { return [minute, { type: 'FeatureCollection', features: [] }] }
    }))
    const frames = {}
    for (const [minute, collection] of loaded) frames[minute] = collection
    const summary = await getSimulationSummary(created.id).catch(() => null)

    setBackend({
      frames, availableFrames: minutes, timeline: timeline.values || [], summary,
      status: 'completed', progress: 100,
      message: snapshot.fallback_used ? 'Completed via approximate fallback engine' : 'Flood timeline ready'
    })
  } catch (error) {
    setBackend({ status: 'error', error: 'Backend simulation API unavailable — showing local approximate preview.' })
  }
}
