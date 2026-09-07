import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts'
import { ArrowUpRight, ChevronDown, ShieldAlert, Waves, MoveVertical, Gauge } from 'lucide-react'
import { useDashboard } from '../../store/useDashboard'
import { ujjaniFrame } from '../../data/ujjaniModel.js'

export default function IntelligencePanel() {
  const [briefing,setBriefing]=useState(true)
  const [expanded,setExpanded]=useState(false)
  const { minute, scenario, selectedStudyCase }=useDashboard()
  const summary=ujjaniFrame(selectedStudyCase,minute,scenario)
  const timeline=useMemo(()=>Array.from({length:13},(_,i)=>{const f=ujjaniFrame(selectedStudyCase,i*5,scenario);return {minute:i*5,depth_m:Number(f.depth.toFixed(2))}}),[selectedStudyCase,scenario])
  return <aside className={`intelligence glass ${expanded?'sheet-expanded':''}`} aria-label="Scenario intelligence">
    <button className="sheet-handle" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>Scenario intelligence <ChevronDown size={16}/></button>
    <div className="panel-scroll"><div className="eyebrow"><span className="status-dot"/> SCENARIO INTELLIGENCE <ArrowUpRight size={15}/></div><h2>{scenario.name}</h2><div className="risk-line"><span className="critical-badge"><ShieldAlert size={13}/> {summary.risk.toUpperCase()} RISK</span><span>APPROXIMATE MODEL</span></div>
    <div className="primary-stat"><span><Waves size={16}/> Flooded area</span><div>{summary.area.toFixed(1)}<small>km²</small></div><p>Approximate inundation at T+{Math.round(minute)}</p></div>
    <div className="secondary-stats"><div><span><MoveVertical size={14}/> Max. depth</span><strong>{summary.depth.toFixed(1)}<small>m</small></strong></div><div><span><Gauge size={14}/> Max. velocity</span><strong>{summary.velocity.toFixed(1)}<small>m/s</small></strong></div></div>
    <div className="chart-heading"><h3>Depth over time</h3><span>METRES</span></div><div className="depth-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={timeline} margin={{top:5,right:5,left:-28,bottom:0}}><defs><linearGradient id="depthGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#49dcea" stopOpacity={0.35}/><stop offset="100%" stopColor="#49dcea" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#233343" strokeDasharray="3 5" vertical={false}/><XAxis dataKey="minute" type="number" domain={[0,60]} ticks={[0,15,30,60]} tick={{fill:'#8da5b8',fontSize:11}} axisLine={false} tickLine={false} tickFormatter={value=>`${value}m`}/><YAxis tick={{fill:'#8da5b8',fontSize:11}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#102131',border:'1px solid #365165',borderRadius:8,color:'#eaf6ff'}} labelFormatter={value=>`T+${value} min`} formatter={value=>[`${value} m`,'Depth']}/><ReferenceLine x={minute} stroke="#91eff3" strokeDasharray="3 3"/><Area type="monotone" dataKey="depth_m" stroke="#53dfeb" strokeWidth={2} fill="url(#depthGradient)" isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>
    <button className="briefing-toggle" onClick={()=>setBriefing(!briefing)} aria-expanded={briefing}><span><ShieldAlert size={16}/> Model notes</span><ChevronDown size={16} className={briefing?'rotated':''}/></button>{briefing&&<ol className="briefing-list"><li>{scenario.breach_type==='major'?'Major':'Partial'} breach propagation active</li><li>Depth bands update continuously along the Bhima corridor</li><li>Prototype output is not an operational warning</li></ol>}
    <p className="sample-note">Automated approximate 2D flood-routing prototype · not validated operational hydraulic output.</p></div>
  </aside>
}
