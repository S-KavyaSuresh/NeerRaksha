import { BarChart,Bar,XAxis,YAxis,Tooltip,ResponsiveContainer,CartesianGrid } from 'recharts'
import { useDashboard } from '../store/useDashboard'
import { prototypeImpact, sampleFacilities, sampleRoads, assetThreat } from '../data/prototype.js'
import { number } from '../utils/format'

export default function ImpactPage() {
  const {minute,select}=useDashboard()
  const impact=prototypeImpact(minute)
  return <><p className="prototype-disclaimer">PROTOTYPE SAMPLE ESTIMATES · active frame T+{impact.frame.minute}. Population and area are illustrative estimates, not GIS-derived exposure.</p>
    <div className="impact-metrics">{[['Flooded area',impact.flooded_area_km2,'km²'],['Population affected',number(impact.population_exposed),'people'],['Buildings affected',impact.buildings_affected,'of 24 samples'],['Roads blocked',impact.roads_affected,'of 5 samples'],['Facilities threatened',impact.facilities_threatened,'of 6 samples'],['Settlements at risk',impact.settlements_at_risk,'of 3 samples']].map(([label,value,unit])=><div key={label}><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>)}</div>
    <h3 className="section-title">Affected sectors · sample population</h3><div className="sector-chart" role="img" aria-label="Sample population affected by sector"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><BarChart data={impact.sectors} margin={{top:10,right:10,left:-10,bottom:5}}><CartesianGrid stroke="#243e4e" vertical={false}/><XAxis dataKey="name" tick={{fill:'#a1bbce',fontSize:11}}/><YAxis tick={{fill:'#a1bbce',fontSize:11}}/><Tooltip contentStyle={{background:'#102b3c',border:'1px solid #3d6076'}}/><Bar dataKey="population" name="Sample people" fill="#59dde8" radius={[4,4,0,0]} isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <div className="risk-breakdown">{impact.riskBreakdown.map(risk=><div key={risk.name}><span className={'severity-label severity-'+risk.name.toLowerCase()}>{risk.name}</span><strong>{number(risk.population)}</strong></div>)}</div>
    <h3 className="section-title">Critical assets · select to inspect</h3><div className="table-scroll"><table className="assets-table"><caption>All locations are prototype samples</caption><thead><tr><th>Asset</th><th>Frame state</th><th>Arrival</th></tr></thead><tbody>{[...sampleFacilities,...sampleRoads].map(asset=>{const threat=assetThreat(asset,minute);return <tr key={asset.id}><td><button onClick={()=>select(asset)}>{asset.name}</button><small>{asset.kind}</small></td><td>{threat.affected?'Affected':threat.arrival===null?'Outside extent':'Threatened'}</td><td>{threat.remaining===null?'—':threat.remaining===0?'Reached':threat.remaining+' min'}</td></tr>})}</tbody></table></div>
  </>
}
