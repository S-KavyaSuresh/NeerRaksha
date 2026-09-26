import { useCallback, useEffect, useRef, useState } from 'react'
import { useDashboard } from '../store/useDashboard'
import {
  getObservationStatus, runObservation, getObservationJob,
  getObservationResult, compareObservationToModel
} from '../services/api'

const sleep = ms => new Promise(r => setTimeout(r, ms))
const num = (v, d = 3) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(d))
const TERMINAL = ['completed', 'unavailable', 'error']

export default function ObservationPage() {
  const scenarioId = useDashboard(s => s.backend?.id)
  const [gee, setGee] = useState(null)
  const [form, setForm] = useState({
    observation_start: '', observation_end: '',
    reference_start: '', reference_end: '',
    polarization: 'VV', orbit_pass: '', threshold_db: ''
  })
  const [job, setJob] = useState(null)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [compareId, setCompareId] = useState('')
  const [agreement, setAgreement] = useState(null)
  const token = useRef(0)

  useEffect(() => { getObservationStatus().then(setGee).catch(() => setGee(null)) }, [])
  useEffect(() => { if (scenarioId && !compareId) setCompareId(scenarioId) }, [scenarioId]) // eslint-disable-line

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const start = useCallback(async () => {
    const mine = ++token.current
    setErr(''); setResult(null); setAgreement(null); setBusy(true); setJob(null)
    try {
      const body = {
        observation_start: form.observation_start, observation_end: form.observation_end,
        polarization: form.polarization
      }
      if (form.reference_start && form.reference_end) {
        body.reference_start = form.reference_start
        body.reference_end = form.reference_end
      }
      if (form.orbit_pass) body.orbit_pass = form.orbit_pass
      if (form.threshold_db !== '') body.threshold_db = Number(form.threshold_db)

      let snap = await runObservation(body)
      setJob(snap)
      while (!TERMINAL.includes(snap.status)) {
        await sleep(1000)
        if (mine !== token.current) return
        snap = await getObservationJob(snap.id)
        setJob(snap)
      }
      const full = await getObservationResult(snap.id).catch(() => null)
      if (mine !== token.current) return
      setResult(full)
    } catch (e) {
      setErr('Observation API unavailable — start the backend and retry.')
    } finally {
      setBusy(false)
    }
  }, [form])

  const compare = useCallback(async () => {
    if (!job?.id || !compareId) return
    setAgreement(null)
    try { setAgreement(await compareObservationToModel(job.id, compareId.trim())) }
    catch (e) { setAgreement({ status: 'unavailable', reason: e?.response?.data?.detail?.message || 'comparison failed' }) }
  }, [job, compareId])

  const method = result?.method || job?.method
  const okResult = result?.status === 'ok'

  return <>
    <p className="prototype-disclaimer">
      <strong>SATELLITE OBSERVATION — WATER/FLOOD EVIDENCE.</strong> Sentinel-1 C-band
      SAR via Google Earth Engine. This is the <strong>OBSERVATION</strong> branch,
      independent of the Delft3D/SPH <strong>MODEL</strong> branch:
      <em> modelled flood ≠ satellite-observed water evidence.</em> Not ground truth,
      not confirmed inundation, not validated hydraulic output. Sentinel-1 passes are
      discrete acquisitions (near-real-time / event-window), not a live flood sensor.
    </p>

    <div className="context-note">
      Google Earth Engine: <strong>{gee ? (gee.gee_available ? 'available' : 'not configured') : '…'}</strong>
      {gee && !gee.gee_available && <> — {gee.reason}. An observation can still be requested; it will
      return a truthful <code>unavailable</code> result rather than a fabricated one.</>}
      {gee && <><br /><small>Default AOI (EPSG:4326): [{(gee.default_aoi_bbox_wgs84 || []).map(v => Number(v).toFixed(3)).join(', ')}] — Ujjani DEM extent.</small></>}
    </div>

    <dl className="workspace-values" style={{ marginTop: 12 }}>
      <div><dt>Observation window</dt><dd>
        <input type="date" value={form.observation_start} onChange={e => set('observation_start', e.target.value)} />
        <span style={{ margin: '0 6px' }}>→</span>
        <input type="date" value={form.observation_end} onChange={e => set('observation_end', e.target.value)} />
      </dd></div>
      <div><dt>Reference window <small>(optional — enables change detection)</small></dt><dd>
        <input type="date" value={form.reference_start} onChange={e => set('reference_start', e.target.value)} />
        <span style={{ margin: '0 6px' }}>→</span>
        <input type="date" value={form.reference_end} onChange={e => set('reference_end', e.target.value)} />
      </dd></div>
      <div><dt>Polarization</dt><dd>
        <select value={form.polarization} onChange={e => set('polarization', e.target.value)}>
          <option value="VV">VV</option><option value="VH">VH</option>
        </select></dd></div>
      <div><dt>Orbit pass</dt><dd>
        <select value={form.orbit_pass} onChange={e => set('orbit_pass', e.target.value)}>
          <option value="">any</option><option value="ASCENDING">ASCENDING</option><option value="DESCENDING">DESCENDING</option>
        </select></dd></div>
      <div><dt>Threshold (dB) <small>scene-dependent; blank = default</small></dt><dd>
        <input type="number" step="0.5" placeholder={form.reference_start ? '-3' : '-17'}
          value={form.threshold_db} onChange={e => set('threshold_db', e.target.value)} style={{ width: 90 }} />
      </dd></div>
    </dl>

    <div className="form-actions">
      <button className="action-button" disabled={busy || !form.observation_start || !form.observation_end} onClick={start}>
        {busy ? 'Requesting Sentinel-1…' : 'Request observation'}
      </button>
      <span style={{ alignSelf: 'center', fontSize: 12, opacity: 0.8 }}>
        method: {form.reference_start && form.reference_end ? 'SAR change detection' : 'single-scene low backscatter'}
      </span>
    </div>

    {err && <p className="download-status field-error">{err}</p>}

    {job && <div className="table-scroll"><table>
      <caption>Sentinel-1 observation — {method || '…'} · <strong>SATELLITE OBSERVATION</strong>, not validated hydraulic output</caption>
      <tbody>
        <tr><td>Status</td><td>{job.status}{job.message ? ` — ${job.message}` : ''}</td></tr>
        <tr><td>Collection</td><td>{result?.source?.collection || job.collection || 'COPERNICUS/S1_GRD'} · {result?.source?.polarization || job.polarization} · IW</td></tr>
        <tr><td>Observation acquisitions</td><td>{result?.acquisitions?.observation
          ? `${result.acquisitions.observation.scene_count} scene(s) · ${result.acquisitions.observation.first} … ${result.acquisitions.observation.last}`
          : (job.observation_period ? `${job.observation_period.start} … ${job.observation_period.end}` : '—')}</td></tr>
        {result?.acquisitions?.reference && <tr><td>Reference acquisitions</td><td>
          {result.acquisitions.reference.scene_count} scene(s) · {result.acquisitions.reference.first} … {result.acquisitions.reference.last}</td></tr>}
        <tr><td>Method / threshold</td><td>{method} · {num(result?.threshold_db ?? job.threshold_db, 1)} dB</td></tr>
        <tr><td>Water/flood evidence area</td><td>{okResult ? `${num(result.water_evidence_area_km2, 4)} km² (${result.water_evidence_cells} cells)` : '—'}</td></tr>
        <tr><td>CRS / AOI</td><td>{result?.crs || 'EPSG:4326'} · [{(result?.aoi_bbox_wgs84 || job.aoi_bbox_wgs84 || []).map(v => Number(v).toFixed(3)).join(', ')}]</td></tr>
        {!okResult && <tr><td>Reason</td><td>{result?.reason || job.reason || '—'}</td></tr>}
      </tbody>
    </table></div>}

    {job && result && <>
      <div className="form-actions" style={{ flexWrap: 'wrap' }}>
        <span style={{ alignSelf: 'center', fontSize: 12, opacity: 0.8 }}>Spatial agreement with a Delft3D scenario:</span>
        <input placeholder="scn-… scenario id" value={compareId} onChange={e => setCompareId(e.target.value)} style={{ width: 220 }} />
        <button className="action-button" disabled={!okResult || !compareId} onClick={compare}>Compute indicator</button>
      </div>
      {agreement && <div className="context-note">
        {agreement.status === 'ok'
          ? <>
              <strong>Spatial agreement indicator</strong> (not a validation score):
              IoU {num(agreement.iou, 3)} · intersection {num(agreement.intersection_area_km2, 4)} km² ·
              model-only {num(agreement.model_only_area_km2, 4)} km² · satellite-only {num(agreement.satellite_only_area_km2, 4)} km².
              <br /><small>{agreement.disclaimer}</small>
            </>
          : <>Comparison unavailable — {agreement.reason}</>}
      </div>}
    </>}

    <div className="context-note">
      Provenance recorded per observation: provider (Google Earth Engine), collection
      (COPERNICUS/S1_GRD), polarization, instrument mode (IW), acquisition period,
      reference period, method, threshold (dB), AOI, CRS, processing scale, timestamp,
      and the Copernicus Sentinel attribution. Backscatter varies with land cover;
      vegetation, wet soil, radar shadow and permanent water can all be confused with
      inundation — the dB threshold is explicit and configurable, never universal.
    </div>
  </>
}
