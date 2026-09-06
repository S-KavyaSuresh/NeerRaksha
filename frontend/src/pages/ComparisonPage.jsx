import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Cell } from 'recharts'
import { comparisonScenarios, comparisonMetrics } from '../data/comparison.js'
import { number } from '../utils/format'

export default function ComparisonPage() {
  const [metric,setMetric]=useState('area')
  const selected=comparisonMetrics.find(item=>item.key===metric)
  return <><p>Current comparison: synthetic breach scenarios.</p><div className="context-note">Predefined comparison estimates at T+60. They are independent synthetic assumptions, not calculations from edited inputs or the illustrative asset inventory.</div>
    <label className="chart-selector">Compare metric<select value={metric} onChange={event=>setMetric(event.target.value)} aria-label="Comparison metric">{comparisonMetrics.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
    <div className="comparison-chart" role="img" aria-label={selected.label+' comparison; exact values in the table below'}><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><BarChart data={comparisonScenarios} layout="vertical" margin={{left:0,right:18,top:10,bottom:5}}><CartesianGrid stroke="#2a4050" horizontal={false}/><XAxis type="number" tick={{fill:'#a6bdce',fontSize:11}}/><YAxis type="category" dataKey="name" width={95} tick={{fill:'#d3e4ed',fontSize:11}}/><Tooltip contentStyle={{background:'#122b3b',border:'1px solid #365b70'}} formatter={value=>[number(value)+' '+selected.unit,selected.label]}/><Bar dataKey={metric} radius={[0,4,4,0]} isAnimationActive={false}>{comparisonScenarios.map((item,index)=><Cell key={item.name} fill={index?'#7776f5':'#59dde8'}/>)}</Bar></BarChart></ResponsiveContainer></div>
    <div className="table-scroll"><table><caption>Prototype sample scenario comparison</caption><thead><tr><th>Metric</th><th>Partial</th><th>Major</th></tr></thead><tbody>{comparisonMetrics.map(item=><tr key={item.key}><td>{item.label}<small> {item.unit}</small></td>{comparisonScenarios.map(scenario=><td key={scenario.name}>{number(scenario[item.key])}</td>)}</tr>)}</tbody></table></div>
    <p className="prototype-disclaimer">HEC-RAS vs Delft3D vs SPH comparison will become available after solver integration.</p>
  </>
}
