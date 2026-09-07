import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts'
import { ArrowUpRight, ChevronDown, ShieldAlert, Waves, MoveVertical, Gauge } from 'lucide-react'
import { useDashboard } from '../../store/useDashboard'
import { ujjaniFrame } from '../../data/ujjaniModel.js'

const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? (0).toFixed(d) : Number(v).toFixed(d))
const riskFor = depth => (depth >= 6 ? 'Critical' : depth >= 3 ? 'Severe' : depth >= 1 ? 'Warning' : 'Advisory')

/* Nearest timeline point at or before the current minute (backend frames). */
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

  // A completed, non-fallback backend run is the source of truth.
  const useBackend = backend?.status === 'completed' && !backend.fallbackUsed &&
    Array.isArray(backend.timeline) && backend.timeline.length > 0

  const synthetic = ujjaniFrame(selectedStudyCase, minute, scenario)

  const view = useMemo(() => {
    if (!useBackend) {
      return {
        source: 'APPROXIMATE MODEL',
        area: synthetic.area, depth: synthetic.depth, velocity: synthetic.velocity,
        risk: synthetic.risk,
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
      chart: backend.timeline.map(t => ({
        minute: Number(t.minute), depth_m: Number(Number(t.max_depth_m ?? 0).toFixed(2))
      })),
      disclaimer: backend.disclaimer ||
        'MODEL OUTPUT · NOT VALIDATED FOR OPERATIONAL PREDICTION (calibration: NO · physical validation: NO).'
    }
  }, [useBackend, backend, minute, scenario, selectedStudyCase, synthetic.area, synthetic.depth, synthetic.velocity, synthetic.risk])

  return <aside className={`intelligence glass ${expanded ? 'sheet-expanded' : ''}`} aria-label="Scenario intelligence">
    <button className="sheet-handle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>Scenario intelligence <ChevronDown size={16} /></button>
    <div className="panel-scroll">
      <div className="eyebrow"><span className="status-dot" /> SCENARIO INTELLIGENCE <ArrowUpRight size={15} /></div>
      <h2>{useBackend ? (backend.engineLabel || scenario.name) : scenario.name}</h2>
      <div className="risk-line"><span className="critical-badge"><ShieldAlert size={13} /> {view.risk.toUpperCase()} RISK</span><span>{view.source}</span></div>
      <div className="primary-stat"><span><Waves size={16} /> Flooded area</span><div>{num(view.area, useBackend ? 3 : 1)}<small>km²</small></div><p>{useBackend ? 'Modelled inundation' : 'Approximate inundation'} at T+{Math.round(minute)}</p></div>
      <div className="secondary-stats">
        <div><span><MoveVertical size={14} /> Max. depth</span><strong>{num(view.depth, 1)}<small>m</small></strong></div>
        <div><span><Gauge size={14} /> Max. velocity</span><strong>{num(view.velocity, 1)}<small>m/s</small></strong></div>
      </div>
      <div className="chart-heading"><h3>Depth over time</h3><span>METRES</span></div>
      <div className="depth-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={view.chart} margin={{ top: 5, right: 5, left: -28, bottom: 0 }}>
        <defs><linearGradient id="depthGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#49dcea" stopOpacity={0.35} /><stop offset="100%" stopColor="#49dcea" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="#233343" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="minute" type="number" domain={[0, 60]} ticks={[0, 15, 30, 60]} tick={{ fill: '#8da5b8', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={value => `${value}m`} />
        <YAxis tick={{ fill: '#8da5b8', fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: '#102131', border: '1px solid #365165', borderRadius: 8, color: '#eaf6ff' }} labelFormatter={value => `T+${value} min`} formatter={value => [`${value} m`, 'Depth']} />
        <ReferenceLine x={minute} stroke="#91eff3" strokeDasharray="3 3" />
        <Area type="monotone" dataKey="depth_m" stroke="#53dfeb" strokeWidth={2} fill="url(#depthGradient)" isAnimationActive={false} />
      </AreaChart></ResponsiveContainer></div>
      <button className="briefing-toggle" onClick={() => setBriefing(!briefing)} aria-expanded={briefing}><span><ShieldAlert size={16} /> Model notes</span><ChevronDown size={16} className={briefing ? 'rotated' : ''} /></button>
      {briefing && <ol className="briefing-list">
        {useBackend
          ? <>
            <li>{backend.engineLabel || 'Delft3D D-Flow FM'} — {backend.dataClass || 'MODEL OUTPUT'}</li>
            <li>{backend.provenance || 'Breach released at the Ujjani dam coordinate on the real terrain mesh'}</li>
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
