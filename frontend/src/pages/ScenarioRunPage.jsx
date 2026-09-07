import { useCallback, useEffect, useRef, useState } from 'react'
import { Play, MapPin } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useDashboard } from '../store/useDashboard'
import {
  getScenarioPresets, runScenario, getScenario, getScenarioResults,
  getScenarioHydrograph, getScenarioFrame
} from '../services/api'

const sleep = ms => new Promise(r => setTimeout(r, ms))
const fmt = (v, d = 2) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(d))

const FIELDS = [
  ['reservoir_level_m', 'Reservoir level (m) — ASSUMED', 'number'],
  ['breach_width_m', 'Breach width (m)', 'number'],
  ['breach_depth_m', 'Breach depth (m)', 'number'],
  ['breach_formation_time_s', 'Breach formation time (s)', 'number'],
  ['simulation_duration_s', 'Simulation duration (s)', 'number'],
  ['output_interval_s', 'Output interval (s)', 'number'],
  ['manning_n', "Manning n (optional)", 'number']
]

export default function ScenarioRunPage() {
  const setBackend = useDashboard(s => s.setBackend)
  const [presets, setPresets] = useState(null)
  const [engine, setEngine] = useState('delft3d')
  const [preset, setPreset] = useState('medium_breach')
  const [params, setParams] = useState({})
  const [state, setState] = useState({ status: 'idle', progress: 0, message: '' })
  const [result, setResult] = useState(null)
  const [hydro, setHydro] = useState(null)
  const [err, setErr] = useState('')
  const token = useRef(0)

  useEffect(() => { getScenarioPresets().then(setPresets).catch(() => {}) }, [])

  const start = useCallback(async () => {
    const mine = ++token.current
    setErr(''); setResult(null); setHydro(null)
    setState({ status: 'queued', progress: 0, message: 'Submitting scenario' })
    try {
      const created = await runScenario({ engine, preset, params })
      let snap = created
      while (!['completed', 'failed'].includes(snap.status)) {
        await sleep(1000)
        if (mine !== token.current) return
        snap = await getScenario(created.id)
        setState({ status: snap.status, progress: snap.progress, message: snap.message })
      }
      if (snap.status === 'failed') {
        setErr(snap.message || 'Scenario run failed')
        setHydro(await getScenarioHydrograph(created.id).catch(() => null))
        return
      }
      const [res, hg] = await Promise.all([
        getScenarioResults(created.id), getScenarioHydrograph(created.id).catch(() => null)
      ])
      if (mine !== token.current) return
      setResult(res); setHydro(hg)

      // feed the flood frames into the shared Cesium layer (existing timeline + map)
      const minutes = res.available_frames || []
      const loaded = await Promise.all(minutes.map(async m => {
        try { return [m, await getScenarioFrame(created.id, m)] }
        catch { return [m, { type: 'FeatureCollection', features: [] }] }
      }))
      if (mine !== token.current) return
      const frames = {}
      for (const [m, fc] of loaded) frames[m] = fc
      setBackend({
        status: 'completed', frames, availableFrames: minutes,
        timeline: (res.summary && res.summary.timeline) || [],
        engineLabel: res.engine_label, dataClass: 'MODEL OUTPUT',
        provenance: res.provenance, validatedHydraulicOutput: false,
        maxDepthM: res.max_depth_m, maxVelocityMps: res.max_velocity_mps,
        mapFrames: minutes.length
      })
    } catch (e) {
      setErr('Scenario API unavailable — start the backend and retry.')
    }
  }, [engine, preset, params, setBackend])

  const hgSeries = hydro?.series
    ? hydro.series.time_s.map((t, i) => ({ t, q: hydro.series.discharge_m3s[i] }))
    : []
  const running = ['queued', 'running'].includes(state.status)

  return <>
    <p className="prototype-disclaimer">
      <strong>MODEL DEMONSTRATION / SCENARIO SIMULATION</strong> on the real Ujjani 30 m DEM.
      Reservoir level, head and breach parameters are <strong>ASSUMPTIONS</strong> — not observed
      historical events. Validation: <strong>NOT PERFORMED</strong>. Modelled output is not observed flood extent.
    </p>

    <label className="speed" style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '6px 0' }}>
      <span>Engine</span>
      <select value={engine} onChange={e => setEngine(e.target.value)} disabled={running}>
        <option value="delft3d">Delft3D D-Flow FM — internal breach at dam (real terrain)</option>
        <option value="sph">SPH (genuine WCSPH — reduced-resolution prototype)</option>
        <option value="approximate">Approximate 2D routing (demo)</option>
      </select>
    </label>
    <label className="speed" style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '6px 0' }}>
      <span>Preset</span>
      <select value={preset} onChange={e => { setPreset(e.target.value); setParams({}) }} disabled={running}>
        {['small_breach', 'medium_breach', 'large_rapid_breach'].map(p => <option key={p} value={p}>{p}</option>)}
        <option value="custom">custom</option>
      </select>
    </label>

    <dl className="workspace-values">
      {FIELDS.map(([k, label]) => {
        const dflt = presets?.presets?.[preset]?.[k]
        return <div key={k}>
          <dt>{label}</dt>
          <dd><input type="number" style={{ width: 130 }} disabled={running}
            placeholder={dflt != null ? `${dflt} (preset)` : 'default'}
            value={params[k] ?? ''}
            onChange={e => setParams(p => ({ ...p, [k]: e.target.value === '' ? undefined : Number(e.target.value) }))} /></dd>
        </div>
      })}
    </dl>

    <div className="form-actions">
      <button className="action-button" onClick={start} disabled={running}><Play size={16} /> Run scenario</button>
    </div>
    <div className="run-status"><span className="status-dot" /> SCENARIO · {String(state.status).toUpperCase()}<strong>{state.progress || 0}%</strong></div>
    <div className="progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.progress || 0}><span style={{ width: (state.progress || 0) + '%' }} /></div>
    <p><small>{state.message}</small></p>
    {err && <p role="alert" className="field-error">{err}</p>}

    {hgSeries.length > 0 && <>
      <div className="context-note">Breach discharge hydrograph — {hydro.formulation}. Peak {fmt(hydro.peak_discharge_m3s, 0)} m³/s @ {fmt(hydro.time_of_peak_s, 0)} s. {hydro.provenance}</div>
      <div className="comparison-chart" style={{ height: 180 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={hgSeries} margin={{ left: 4, right: 12, top: 8, bottom: 4 }}>
            <CartesianGrid stroke="#2a4050" />
            <XAxis dataKey="t" tick={{ fill: '#a6bdce', fontSize: 10 }} unit="s" />
            <YAxis tick={{ fill: '#a6bdce', fontSize: 10 }} width={54} />
            <Tooltip contentStyle={{ background: '#122b3b', border: '1px solid #365b70' }} formatter={v => [`${fmt(v, 1)} m³/s`, 'Q']} />
            <Area dataKey="q" stroke="#59dde8" fill="#1c4d5c" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </>}

    {result && <>
      <dl className="workspace-values">
        <div><dt>Engine</dt><dd>{result.engine_label || result.engine}</dd></div>
        <div><dt><MapPin size={12} /> Dam location</dt><dd>{fmt(result.dam_location?.lat, 4)}° N, {fmt(result.dam_location?.lon, 4)}° E · UTM ({fmt(result.dam_location?.x_m, 0)}, {fmt(result.dam_location?.y_m, 0)}) · in domain: {String(result.dam_location?.in_domain)} · terrain {fmt(result.dam_location?.terrain_elev_m, 1)} m (REAL DEM)</dd></div>
        <div><dt>Release representation</dt><dd>{result.release_representation || result.sph_status || '—'}</dd></div>
        <div><dt>Reservoir level</dt><dd>{fmt(result.reservoir_level_m, 1)} m — <em>{result.reservoir_level_class}</em></dd></div>
        <div><dt>Breach</dt><dd>width {fmt(result.breach?.width_m, 0)} m · depth {fmt(result.breach?.depth_m, 0)} m · formation {fmt(result.breach?.formation_time_s, 0)} s</dd></div>
        <div><dt>Peak discharge</dt><dd>{fmt(result.hydrograph?.peak_discharge_m3s, 0)} m³/s @ {fmt(result.hydrograph?.time_of_peak_s, 0)} s — <em>MODEL INPUT / DERIVED</em></dd></div>
        <div><dt>Max depth / velocity</dt><dd>{fmt(result.max_depth_m, 2)} m / {fmt(result.max_velocity_mps, 2)} m/s <em>(MODEL OUTPUT)</em></dd></div>
        {result.mesh && <div><dt>Mesh</dt><dd>{result.mesh.faces} faces · bed {fmt(result.mesh.bed_level_min_m, 0)}–{fmt(result.mesh.bed_level_max_m, 0)} m · ~{fmt(result.mesh.approx_cell_size_m, 0)} m cells</dd></div>}
        {result.particle_count && <div><dt>SPH</dt><dd>{result.particle_count} particles · {result.timesteps} steps · {fmt(result.physical_duration_s, 2)} s physical · {result.sph_status}</dd></div>}
        <div><dt>Frames / arrival</dt><dd>{(result.available_frames || []).length} frames · arrival raster: {String(result.arrival_available)}</dd></div>
        <div><dt>Outputs</dt><dd>{(result.outputs || []).join(', ')}</dd></div>
        <div><dt>Data classification</dt><dd>{result.data_classification}</dd></div>
        <div><dt>Validation status</dt><dd><strong>{result.validation_status}</strong> · {result.run_class}</dd></div>
      </dl>
      <details className="technical-log"><summary>Assumptions ({(result.assumptions || []).length})</summary>
        <ul>{(result.assumptions || []).map((a, i) => <li key={i}>{a}</li>)}</ul>
      </details>
      <details className="technical-log"><summary>Limitations ({(result.limitations || []).length})</summary>
        <ul>{(result.limitations || []).map((a, i) => <li key={i}>{a}</li>)}</ul>
      </details>
      <p className="prototype-disclaimer">
        Move the timeline below to scrub the modelled flood on the map. This is a scenario demonstration on
        real terrain — not a calibrated or validated Ujjani prediction, and not an observed flood extent.
      </p>
    </>}
  </>
}
