import { useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts'
import { ArrowUpRight, ChevronDown, Radio, ShieldAlert, Waves, Users, Building2, MoveVertical } from 'lucide-react'
import { useDashboard } from '../../store/useDashboard'
import { number } from '../../utils/format'
import { prototypeImpact, emergencyAlerts } from '../../data/prototype.js'

export default function IntelligencePanel({ data }) {
  const [briefing, setBriefing] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const minute = useDashboard(state => state.minute)
  const { timeline, loading } = data
  const summary = prototypeImpact(minute)
  const scenario = useDashboard(state=>state.scenario)
  const arrival = emergencyAlerts(minute)[0]
  return <aside className={`intelligence glass ${expanded ? 'sheet-expanded' : ''}`} aria-label="Scenario intelligence">
    <button className="sheet-handle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>Scenario intelligence <ChevronDown size={16}/></button>
    <div className="panel-scroll"><div className="eyebrow"><span className="status-dot"/> SCENARIO INTELLIGENCE <ArrowUpRight size={15}/></div><h2>{scenario.name}</h2><div className="risk-line"><span className="critical-badge"><ShieldAlert size={13}/> {summary.frame.risk.toUpperCase()} RISK</span><span>SAMPLE</span></div>
    <div className={`primary-stat ${loading ? 'skeleton' : ''}`}><span><Waves size={16}/> Flooded area</span><div>{summary.flooded_area_km2}<small>km²</small></div><p>Sample inundation at T+{summary.frame.minute}</p></div>
    <div className="secondary-stats"><div className={loading ? 'skeleton' : ''}><span><MoveVertical size={14}/> Max. depth</span><strong>{summary.maximum_depth_m}<small>m</small></strong></div><div className={loading ? 'skeleton' : ''}><span><Users size={14}/> Exposed population</span><strong>{number(summary.population_exposed)}</strong></div></div>
    <div className="asset-stat"><span><Building2 size={16}/> Roads / facilities affected</span><strong>{summary.critical_assets}<ArrowUpRight size={15}/></strong></div>
    <div className="arrival-alert"><Radio size={20}/><div><span>FLOOD ARRIVAL ALERT · SAMPLE</span><strong>Sambalpur Sector A</strong><p>{arrival.remaining===0?'Arrival reached in sample':'Estimated arrival in '+arrival.remaining+' min'}</p></div></div>
    <div className="chart-heading"><h3>Depth over time</h3><span>METRES</span></div><div className="depth-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={timeline} margin={{top:5,right:5,left:-28,bottom:0}}><defs><linearGradient id="depthGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#49dcea" stopOpacity={0.35}/><stop offset="100%" stopColor="#49dcea" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#233343" strokeDasharray="3 5" vertical={false}/><XAxis dataKey="minute" type="number" domain={[0,60]} ticks={[0,15,30,60]} tick={{fill:'#8da5b8',fontSize:11}} axisLine={false} tickLine={false} tickFormatter={value=>`${value}m`}/><YAxis tick={{fill:'#8da5b8',fontSize:11}} axisLine={false} tickLine={false} domain={[0,10]} ticks={[0,5,10]}/><Tooltip contentStyle={{background:'#102131',border:'1px solid #365165',borderRadius:8,color:'#eaf6ff'}} labelFormatter={value=>`T+${value} min`} formatter={value=>[`${value} m`,'Depth']}/><ReferenceLine x={minute} stroke="#91eff3" strokeDasharray="3 3"/><Area type="monotone" dataKey="depth_m" stroke="#53dfeb" strokeWidth={2} fill="url(#depthGradient)" isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>
    <button className="briefing-toggle" onClick={() => setBriefing(!briefing)} aria-expanded={briefing} aria-controls="briefing"><span><ShieldAlert size={16}/> Emergency Briefing</span><ChevronDown size={16} className={briefing?'rotated':''}/></button>{briefing && <ol id="briefing" className="briefing-list"><li>Alert downstream settlements</li><li>Prioritize hospitals and schools</li><li>Restrict vulnerable road segments</li></ol>}
    <p className="sample-note">Prototype sample estimates from prebuilt frames; not GIS-derived exposure or an operational advisory.</p></div>
  </aside>
}
