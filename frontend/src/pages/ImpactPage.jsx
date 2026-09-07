import { useDashboard } from '../store/useDashboard'

export default function ImpactPage() {
  const { selectedStudyCase } = useDashboard()
  const roads=selectedStudyCase?.spatial?.real_roads?.features || []
  const facilities=selectedStudyCase?.spatial?.real_facilities?.features || []
  const buildings=selectedStudyCase?.spatial?.buildings?.features || []
  return <><p className="prototype-disclaimer">Ujjani reference assets loaded for later flood-intersection analysis.</p>
    <div className="impact-metrics">
      <div><span>Population exposure</span><strong>—</strong><small>data unavailable</small></div>
      <div><span>Buildings</span><strong>{buildings.length || '—'}</strong><small>{buildings.length?'records loaded':'data unavailable'}</small></div>
      <div><span>Roads</span><strong>{roads.length}</strong><small>records loaded</small></div>
      <div><span>Facilities</span><strong>{facilities.length}</strong><small>records loaded</small></div>
    </div>
    <div className="context-note">Affected-asset counts will be calculated by spatial intersection with the active routing frame; unavailable data is not reported as zero exposure.</div>
  </>
}
