import { ShieldAlert, X, Focus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useDashboard } from '../../store/useDashboard'
import { emergencyAlerts, sampleRoads, sampleFacilities, assetThreat } from '../../data/prototype.js'

export default function EmergencyBriefing() {
  const { minute,toggleEmergency,select,focusFlood }=useDashboard()
  const alerts=emergencyAlerts(minute)
  const panel=useRef(null)
  useEffect(()=>{const trigger=document.activeElement;panel.current?.focus();return ()=>{if(trigger?.isConnected) trigger.focus()}},[])
  return <aside ref={panel} className="intelligence emergency-briefing glass" aria-label="Emergency Briefing" tabIndex={-1} onKeyDown={event=>{if(event.key==='Escape') toggleEmergency()}}>
    <div className="panel-scroll"><div className="critical-mode-banner"><ShieldAlert size={18}/><strong>CRITICAL MODE</strong><button aria-label="Exit Emergency Mode" onClick={toggleEmergency}><X size={16}/></button></div>
      <h2>Emergency Briefing</h2><p className="prototype-disclaimer">Prototype simulation intelligence. Not live or official warning data.</p>
      <button className="action-button" onClick={focusFlood}><Focus size={16}/> Focus active flood</button>
      <h3 className="section-title">Top 3 prototype priority alerts</h3>
      {alerts.map(alert=><article className={'priority-alert severity-'+alert.severity.toLowerCase()} key={alert.id}><span className="severity-label">{alert.severity}</span><h3>{alert.name}</h3><strong>{alert.remaining===0?'Arrival reached in sample':`Estimated arrival: ${alert.remaining} min`}</strong><dl><div><dt>Prototype max. depth</dt><dd>{alert.depth} m</dd></div><div><dt>Threatened road</dt><dd><button onClick={()=>select(alert.road)}>{alert.road.name}</button></dd></div><div><dt>Nearest prototype shelter</dt><dd><button onClick={()=>select(alert.shelter)}>{alert.shelter.name}</button></dd></div></dl><small>Source: Prototype simulation intelligence</small></article>)}
      <h3 className="section-title">Blocked / threatened roads</h3><ul className="risk-asset-list">{sampleRoads.map(road=><li key={road.id}><button onClick={()=>select(road)}>{road.name}</button><span>{assetThreat(road,minute).status}</span></li>)}</ul>
      <h3 className="section-title">Threatened facilities</h3><ul className="risk-asset-list">{sampleFacilities.filter(asset=>assetThreat(asset,minute).arrival!==null).map(asset=><li key={asset.id}><button onClick={()=>select(asset)}>{asset.name}</button><span>{assetThreat(asset,minute).remaining===0?'Reached in sample':`${assetThreat(asset,minute).remaining} min · sample arrival`}</span></li>)}</ul>
      <button className="exit-emergency" onClick={toggleEmergency}>Exit Emergency Mode</button>
    </div>
  </aside>
}
