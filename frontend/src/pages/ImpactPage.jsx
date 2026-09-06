import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useDashboard } from '../store/useDashboard'
import { number } from '../utils/format'

export default function ImpactPage() {
  const { select, selectedStudyCase } = useDashboard()
  const exposure = selectedStudyCase?.exposure || {}
  const assets = [...(exposure.facilities || []), ...(exposure.roads || [])]
  const settlements = exposure.settlements || []
  const populationExposed = settlements.reduce((total, item) => total + Number(item.population_exposed || 0), 0)
  const populationTotal = settlements.reduce((total, item) => total + Number(item.population_total || 0), 0)
  const sectors = Object.values(settlements.reduce((groups, item) => {
    const name = item.district || item.location || 'Unspecified'
    groups[name] = groups[name] || { name, population: 0 }
    groups[name].population += Number(item.population_exposed || 0)
    return groups
  }, {}))
  const selectAsset = asset => select({ ...asset, type: asset.category === 'roads' ? 'road' : 'facility', lon: asset.longitude, lat: asset.latitude, kind: asset.asset_type })
  return <><p className="prototype-disclaimer">Selected study-area exposure records. Flood impact remains a synthetic simulation.</p>
    <div className="impact-metrics">{[['Population exposure', number(populationExposed), 'people'], ['Settlement population', number(populationTotal), 'people'], ['Buildings', exposure.buildings?.length || 0, 'records'], ['Roads', exposure.roads?.length || 0, 'records'], ['Facilities', exposure.facilities?.length || 0, 'records'], ['Settlements', settlements.length, 'records']].map(([label, value, unit]) => <div key={label}><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>)}</div>
    <h3 className="section-title">Settlement exposure by district</h3><div className="sector-chart" role="img" aria-label="Selected study area population exposure by district"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><BarChart data={sectors} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}><CartesianGrid stroke="#243e4e" vertical={false}/><XAxis dataKey="name" tick={{ fill: '#a1bbce', fontSize: 11 }}/><YAxis tick={{ fill: '#a1bbce', fontSize: 11 }}/><Tooltip contentStyle={{ background: '#102b3c', border: '1px solid #3d6076' }}/><Bar dataKey="population" name="Exposed population" fill="#59dde8" radius={[4, 4, 0, 0]} isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <h3 className="section-title">Selected study-area assets</h3><div className="table-scroll"><table className="assets-table"><caption>Exposure records from the selected study area</caption><thead><tr><th>Asset</th><th>Category</th><th>Exposed population</th></tr></thead><tbody>{assets.map(asset => <tr key={asset.id}><td><button onClick={() => selectAsset(asset)}>{asset.name}</button><small>{asset.district || asset.location}</small></td><td>{asset.asset_type}</td><td>{asset.population_exposed?.toLocaleString('en-IN') || '—'}</td></tr>)}</tbody></table></div>
  </>
}
