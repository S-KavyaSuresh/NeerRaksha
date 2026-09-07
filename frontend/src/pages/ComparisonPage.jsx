import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Cell } from 'recharts'
import { ujjaniScenarioSummary } from '../data/ujjaniModel.js'
import { number } from '../utils/format'

const scenarios=[ujjaniScenarioSummary('partial'),ujjaniScenarioSummary('major')]
const metrics=[
  {key:'area',label:'Flooded area',unit:'km²'},
  {key:'depth',label:'Maximum modelled depth',unit:'m'},
  {key:'velocity',label:'Maximum velocity',unit:'m/s'},
  {key:'peak',label:'Peak breach discharge',unit:'m³/s'},
  {key:'arrival',label:'Downstream arrival indicator',unit:'min'}
]

export default function ComparisonPage() {
  const [metric,setMetric]=useState('area')
  const selected=metrics.find(item=>item.key===metric)
  return <><p>Partial Breach and Major Breach use separate Ujjani routing parameters.</p><div className="context-note">Comparison is generated from the same automated approximate 2D flood-routing model used by the map.</div>
    <label className="chart-selector">Compare metric<select value={metric} onChange={event=>setMetric(event.target.value)} aria-label="Comparison metric">{metrics.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
    <div className="comparison-chart" role="img" aria-label={selected.label+' comparison'}><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><BarChart data={scenarios} layout="vertical" margin={{left:0,right:18,top:10,bottom:5}}><CartesianGrid stroke="#2a4050" horizontal={false}/><XAxis type="number" tick={{fill:'#a6bdce',fontSize:11}}/><YAxis type="category" dataKey="name" width={95} tick={{fill:'#d3e4ed',fontSize:11}}/><Tooltip contentStyle={{background:'#122b3b',border:'1px solid #365b70'}} formatter={value=>[number(value)+' '+selected.unit,selected.label]}/><Bar dataKey={metric} radius={[0,4,4,0]} isAnimationActive={false}>{scenarios.map((item,index)=><Cell key={item.name} fill={index?'#ef8f5a':'#59dde8'}/>)}</Bar></BarChart></ResponsiveContainer></div>
    <div className="table-scroll"><table><caption>Ujjani breach scenario comparison</caption><thead><tr><th>Metric</th><th>Partial</th><th>Major</th></tr></thead><tbody>{metrics.map(item=><tr key={item.key}><td>{item.label}<small> {item.unit}</small></td>{scenarios.map(scenario=><td key={scenario.name}>{number(scenario[item.key])}</td>)}</tr>)}</tbody></table></div>
    <p className="prototype-disclaimer">Approximate routing prototype comparison · not validated operational hydraulic output.</p>
  </>
}
