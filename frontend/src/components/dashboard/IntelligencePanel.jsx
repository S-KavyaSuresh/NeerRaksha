import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts'
import { ArrowUpRight, ChevronDown, ShieldAlert, Waves, MoveVertical, Gauge } from 'lucide-react'
import { useDashboard } from '../../store/useDashboard'
import { ujjaniFrame } from '../../data/ujjaniModel.js'

const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? (0).toFixed(d) : Number(v).toFixed(d))
const riskFor = depth => (depth >= 6 ? 'Critical' : depth >= 3 ? 'Severe' : depth >= 1 ? 'Warning' : 'Advisory')

function pointAt(timeline, minute) {
  if (!Array.isArray(timeline) || !timeline.length) return null
  let pick = timeline[0]
  for (const p of timeline) if (Number(p.minute) <= Number(minute || 0)) pick = p
  return pick
}

export default function IntelligencePanel() {
  const [briefing, setBriefing] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const { minute, scenario, selectedStudyCase, backend } = useDashboard()

  const isSph = !!backend?.particleData && Array.isArray(backend.particleData.particle_frames)
  const useBackend = backend?.status === 'completed' && !backend.fallbackUsed &&
    Array.isArray(backend.timeline) && backend.timeline.length > 0
  const impact = backend?.impact
  const sphSummary = backend?.summary && backend.summary.engine === 'sph_wcsph' ? backend.summary : null

  const synthetic = ujjaniFrame(selectedStudyCase, minute, scenario)

  const sphFrame = useMemo(() => {
    if (!isSph) return null
    const frames = backend.particleData.particle_frames
    const av = frames.map((_, i) => i)
    let idx = 0
    for (const i of av) if (i <= Number(minute || 0)) idx = i
    return { idx: Math.min(idx, frames.length - 1), frame: frames[Math.min(idx, frames.length - 1)] }
  }, [isSph, backend, minute])

  const view = useMemo(() => {
    if (!useBackend) {
      return {
        source: 'APPROXIMATE MODEL',
        area: synthetic.area, depth: synthetic.depth, velocity: synthetic.velocity, risk: synthetic.risk,
        chart: Array.from({ length: 13 }, (_, i) => {
          const f = ujjaniFrame(selectedStudyCase, i * 5, scenario)
          return { minute: i * 5, depth_m: Number(f.depth.toFixed(2)) }
        }),
        disclaimer: 'Automated approximate 2D flood-routing prototype · not validated operational hydraulic output.'
      }
    }
    const p = pointAt(backend.timeline, minute) || {}
    const depth = Number(p.max_depth_m ?? backend.maxDepthM ?? 0)
    return {
      source: (backend.engineLabel || 'Delft3D D-Flow FM') + ' · ' + (backend.dataClass || 'MODEL OUTPUT'),
      area: Number(p.flooded_area_km2 ?? 0),
      depth,
      velocity: Number(p.max_velocity_mps ?? backend.maxVelocityMps ?? 0),
      risk: riskFor(depth),
      chart: backend.timeline.map((t, i) => ({
        minute: isSph ? i : Number(t.minute),
        depth_m: Number(Number(t.max_depth_m ?? 0).toFixed(2))
      })),
      disclaimer: backend.disclaimer ||
        'MODEL OUTPUT · NOT VALIDATED FOR OPERATIONAL PREDICTION (calibration: NO · physical validation: NO).'
    }
  }, [useBackend, backend, minute, scenario, selectedStudyCase, isSph, synthetic.area, synthetic.depth, synthetic.velocity, synthetic.risk])

  const frameLabel = isSph && sphFrame
    ? `Frame ${sphFrame.idx} · SPH t ${num(sphFrame.frame?.sph_time_s, 2)} s`
    : `T+${Math.round(minute)}${useBackend ? ' min' : ''}`

  return <aside className={`intelligence glass ${expanded ? 'sheet-expanded' : ''}`} aria-label="Scenario intelligence">
    <button className="sheet-handle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>Scenario intelligence <ChevronDown size={16} /></button>
    <div className="panel-scroll">
      <div className="eyebrow"><span className="status-dot" /> SCENARIO INTELLIGENCE <ArrowUpRight size={15} /></div>
      <h2>{useBackend ? (backend.engineLabel || scenario.name) : scenario.name}</h2>
      <div className="risk-line"><span className="critical-badge"><ShieldAlert size={13} /> {view.risk.toUpperCase()} RISK</span><span>{view.source}</span></div>
      <div className="primary-stat"><span><Waves size={16} /> Flooded area</span><div>{num(view.area, useBackend ? 3 : 1)}<small>km²</small></div><p>{useBackend ? 'Modelled inundation' : 'Approximate inundation'} · {frameLabel}</p></div>
      <div className="secondary-stats">
        <div><span><MoveVertical size={14} /> Max. depth</span><strong>{num(view.depth, 1)}<small>m</small></strong></div>
        <div><span><Gauge size={14} /> Max. velocity</span><strong>{num(isSph && sphFrame ? sphFrame.frame?.max_speed_mps : view.velocity, 1)}<small>m/s</small></strong></div>
      </div>

      {useBackend && <dl className="workspace-values" style={{ marginTop: 6 }}>
        {isSph && sphSummary && <>
          <div><dt>Particles</dt><dd>{sphSummary.particle_count}</dd></div>
          <div><dt>SPH timesteps</dt><dd>{sphSummary.timesteps}</dd></div>
          <div><dt>Physical time</dt><dd>{num(sphSummary.physical_duration_s, 2)} s</dd></div>
          <div><dt>Density (median err)</dt><dd>{num(sphSummary.density_relative_error_pct, 2)}% · min {num(sphSummary.density_min, 0)} / max {num(sphSummary.density_max, 0)} kg/m³</dd></div>
          <div><dt>Max displacement</dt><dd>{num(sphSummary.max_displacement_m, 2)} m</dd></div>
          <div><dt>Frames</dt><dd>{sphSummary.frames}</dd></div>
        </>}
        <div><dt>Roads affected</dt><dd>{impact?.roads?.status === 'ok' ? `${impact.roads.affected_count} / ${impact.roads.total_in_dataset} (~${num(impact.roads.approx_flooded_length_km, 1)} km)` : 'Unavailable'}</dd></div>
        <div><dt>Facilities affected</dt><dd>{impact?.facilities?.status === 'ok' ? `${impact.facilities.affected_count} / ${impact.facilities.total_in_dataset}` : 'Unavailable'}</dd></div>
        <div><dt>Settlements affected</dt><dd>Unavailable{impact?.settlements?.reason ? ` — ${impact.settlements.reason}` : ''}</dd></div>
        <div><dt>Population exposure</dt><dd>Unavailable — no population dataset connected</dd></div>
        <div><dt>Validation</dt><dd><strong>NOT PERFORMED</strong></dd></div>
      </dl>}

      <div className="chart-heading"><h3>{isSph ? 'Max depth per frame' : 'Depth over time'}</h3><span>METRES</span></div>
      <div className="depth-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={view.chart} margin={{ top: 5, right: 5, left: -28, bottom: 0 }}>
        <defs><linearGradient id="depthGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#49dcea" stopOpacity={0.35} /><stop offset="100%" stopColor="#49dcea" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="#233343" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="minute" type="number" domain={isSph ? [0, view.chart.length - 1] : [0, 60]} tick={{ fill: '#8da5b8', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={value => (isSph ? `f${value}` : `${value}m`)} />
        <YAxis tick={{ fill: '#8da5b8', fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: '#102131', border: '1px solid #365165', borderRadius: 8, color: '#eaf6ff' }} labelFormatter={value => (isSph ? `Frame ${value}` : `T+${value} min`)} formatter={value => [`${value} m`, 'Depth']} />
        <ReferenceLine x={isSph && sphFrame ? sphFrame.idx : minute} stroke="#91eff3" strokeDasharray="3 3" />
        <Area type="monotone" dataKey="depth_m" stroke="#53dfeb" strokeWidth={2} fill="url(#depthGradient)" isAnimationActive={false} />
      </AreaChart></ResponsiveContainer></div>

      <button className="briefing-toggle" onClick={() => setBriefing(!briefing)} aria-expanded={briefing}><span><ShieldAlert size={16} /> Model notes</span><ChevronDown size={16} className={briefing ? 'rotated' : ''} /></button>
      {briefing && <ol className="briefing-list">
        {useBackend
          ? <>
            <li>{backend.engineLabel || 'Delft3D D-Flow FM'} — {backend.dataClass || 'MODEL OUTPUT'}</li>
            <li>{isSph
              ? 'SPH particles animate through real solver frames; footprint is NOT georeferenced'
              : (backend.provenance || 'Breach released at the Ujjani dam coordinate on the real terrain mesh')}</li>
            <li>Calibration: NOT PERFORMED · Physical validation: NOT PERFORMED · not an operational warning</li>
          </>
          : <>
            <li>{scenario.breach_type === 'major' ? 'Major' : 'Partial'} breach propagation active</li>
            <li>Depth bands update continuously along the Bhima corridor</li>
            <li>Prototype output is not an operational warning</li>
          </>}
      </ol>}
      <p className="sample-note">{view.disclaimer}</p>
    </div>
  </aside>
}
