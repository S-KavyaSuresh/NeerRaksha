import { ShieldAlert, X, Focus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useDashboard } from '../../store/useDashboard'
import { emergencyAlerts } from '../../data/prototype.js'

export default function EmergencyBriefing() {
  const { minute, toggleEmergency, select, focusFlood, selectedStudyCase } = useDashboard()
  const alerts = selectedStudyCase?.case_id === 'ujjani' ? [] : emergencyAlerts(minute)
  const roads = selectedStudyCase?.exposure?.roads || []
  const facilities = selectedStudyCase?.exposure?.facilities || []
  const panel = useRef(null)
  const mapItem = asset => ({ ...asset, type: asset.category === 'roads' ? 'road' : 'facility', lon: asset.longitude, lat: asset.latitude, kind: asset.asset_type })
  useEffect(() => { const trigger = document.activeElement; panel.current?.focus(); return () => { if (trigger?.isConnected) trigger.focus() } }, [])
  return <aside ref={panel} className="intelligence emergency-briefing glass" aria-label="Emergency Briefing" tabIndex={-1} onKeyDown={event => { if (event.key === 'Escape') toggleEmergency() }}>
    <div className="panel-scroll"><div className="critical-mode-banner"><ShieldAlert size={18}/><strong>CRITICAL MODE</strong><button aria-label="Exit Emergency Mode" onClick={toggleEmergency}><X size={16}/></button></div>
      <h2>Emergency Briefing</h2><p className="prototype-disclaimer">Synthetic simulation intelligence. Not live or official warning data.</p>
      <button className="action-button" onClick={focusFlood}><Focus size={16}/> Focus active flood</button>
      <h3 className="section-title">{selectedStudyCase?.case_id === 'ujjani' ? 'Current Ujjani exposure records' : 'Top 3 priority alerts'}</h3>
      {alerts.map(alert => <article className={'priority-alert severity-' + alert.severity.toLowerCase()} key={alert.id}><span className="severity-label">{alert.severity}</span><h3>{alert.name}</h3><strong>{alert.remaining === 0 ? 'Modelled arrival reached' : `Estimated arrival: ${alert.remaining} min`}</strong><dl><div><dt>Modelled max. depth</dt><dd>{alert.depth} m</dd></div></dl><small>Source: Synthetic simulation intelligence</small></article>)}
      <h3 className="section-title">Road exposure records</h3><ul className="risk-asset-list">{roads.map(road => <li key={road.id}><button onClick={() => select(mapItem(road))}>{road.name}</button><span>{road.population_exposed?.toLocaleString('en-IN') || 0} exposed</span></li>)}</ul>
      <h3 className="section-title">Facility exposure records</h3><ul className="risk-asset-list">{facilities.map(asset => <li key={asset.id}><button onClick={() => select(mapItem(asset))}>{asset.name}</button><span>{asset.criticality || 'Unclassified'}</span></li>)}</ul>
      <button className="exit-emergency" onClick={toggleEmergency}>Exit Emergency Mode</button>
    </div>
  </aside>
}
