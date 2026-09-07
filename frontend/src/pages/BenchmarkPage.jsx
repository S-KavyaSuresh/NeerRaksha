import { useCallback, useRef, useState } from 'react'
import { Play, FlaskConical } from 'lucide-react'
import { runBenchmark, getBenchmark, getBenchmarkComparison } from '../services/api'

const sleep = ms => new Promise(r => setTimeout(r, ms))
const fmt = (v, d = 3) => (v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d))

export default function BenchmarkPage() {
  const [state, setState] = useState({ status: 'idle', progress: 0, message: '' })
  const [cmp, setCmp] = useState(null)
  const [err, setErr] = useState('')
  const token = useRef(0)

  const start = useCallback(async () => {
    const mine = ++token.current
    setErr(''); setCmp(null)
    setState({ status: 'queued', progress: 0, message: 'Submitting benchmark' })
    try {
      const created = await runBenchmark({})
      let snap = created
      while (!['completed', 'failed'].includes(snap.status)) {
        await sleep(800)
        if (mine !== token.current) return
        snap = await getBenchmark(created.id)
        setState({ status: snap.status, progress: snap.progress, message: snap.message })
      }
      if (snap.status === 'failed') { setErr(snap.message || 'Benchmark failed'); return }
      const comparison = await getBenchmarkComparison(created.id)
      if (mine !== token.current) return
      setCmp(comparison)
    } catch (e) {
      setErr('Benchmark API unavailable — start the backend and retry.')
    }
  }, [])

  const m = cmp?.metrics
  const b = cmp?.benchmark
  const fp = m?.front_position
  const wr = m?.wet_region_at_t
  const at = m?.arrival_time_at_gauge

  return <>
    <p className="prototype-disclaimer">
      Benchmark / verification against the <strong>Ritter (1892)</strong> analytical dry-bed dam-break —
      this is <strong>not</strong> calibration and <strong>not</strong> operational validation.
    </p>

    <div className="form-actions">
      <button className="action-button" onClick={start} disabled={['queued', 'running'].includes(state.status)}>
        <Play size={16} /> Run benchmark (SPH + Delft3D)
      </button>
    </div>
    <div className="run-status"><span className="status-dot" /><FlaskConical size={14} /> BENCHMARK · {String(state.status).toUpperCase()}<strong>{state.progress || 0}%</strong></div>
    <div className="progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.progress || 0}><span style={{ width: (state.progress || 0) + '%' }} /></div>
    <p><small>{state.message}</small></p>
    {err && <p role="alert" className="field-error">{err}</p>}

    {cmp && <>
      <dl className="workspace-values">
        <div><dt>Benchmark</dt><dd>{b?.name}</dd></div>
        <div><dt>Reference source</dt><dd>{cmp.reference?.name} — {b?.reference?.primary_source}</dd></div>
        <div><dt>Geometry</dt><dd>column {fmt(b?.geometry?.column_width_a_m, 3)} m × {fmt(b?.geometry?.column_height_H0_m, 3)} m (H₀ = 2a), flat frictionless bed, g = 9.81</dd></div>
        <div><dt>SPH</dt><dd>genuine WCSPH · {cmp.sph_result?.particle_count} particles · {cmp.sph_result?.timesteps} steps · ρ median err {fmt(cmp.sph_result?.density_relative_error_pct, 2)}% · {fmt(cmp.sph_result?.runtime_seconds, 1)} s</dd></div>
        <div><dt>Delft3D</dt><dd>D-Flow FM · {cmp.delft3d_result?.mesh?.faces} faces · {cmp.delft3d_result?.frames} frames · depth max {fmt(cmp.delft3d_result?.depth_max_m, 3)} m · {fmt(cmp.delft3d_result?.runtime_seconds, 1)} s</dd></div>
      </dl>

      <div className="table-scroll"><table>
        <caption>Front-position agreement (leading edge vs time, over {fmt(fp?.common_time_window_s?.[1], 2)} s)</caption>
        <thead><tr><th>Pair</th><th>RMSE (m)</th><th>MAE (m)</th><th>Mean rel. error</th></tr></thead>
        <tbody>
          <tr><td>SPH vs Ritter</td><td>{fmt(fp?.sph_vs_ritter?.rmse_m)}</td><td>{fmt(fp?.sph_vs_ritter?.mae_m)}</td><td>{fmt(fp?.sph_vs_ritter?.mean_relative_error, 2)}</td></tr>
          <tr><td>Delft3D vs Ritter</td><td>{fmt(fp?.delft3d_vs_ritter?.rmse_m)}</td><td>{fmt(fp?.delft3d_vs_ritter?.mae_m)}</td><td>{fmt(fp?.delft3d_vs_ritter?.mean_relative_error, 2)}</td></tr>
          <tr><td>SPH vs Delft3D</td><td>{fmt(fp?.sph_vs_delft3d?.rmse_m)}</td><td>{fmt(fp?.sph_vs_delft3d?.mae_m)}</td><td>—</td></tr>
        </tbody>
      </table></div>

      <div className="table-scroll"><table>
        <caption>Wet-region overlap at t = {fmt(wr?.t_s, 2)} s (threshold {fmt(wr?.threshold_m, 3)} m, grid {fmt(wr?.raster_resolution_m, 4)} m)</caption>
        <thead><tr><th>Pair</th><th>IoU</th><th>Arrival @ gauge {fmt(at?.gauge_x_m, 3)} m</th></tr></thead>
        <tbody>
          <tr><td>SPH vs Delft3D</td><td>{fmt(wr?.iou_sph_delft3d?.iou)}</td><td>SPH {fmt(at?.sph_s, 3)} s (err {fmt(at?.sph_abs_error_s, 3)} s)</td></tr>
          <tr><td>SPH vs Ritter</td><td>{fmt(wr?.iou_sph_ritter?.iou)}</td><td>Delft3D {fmt(at?.delft3d_s, 3)} s (err {fmt(at?.delft3d_abs_error_s, 3)} s)</td></tr>
          <tr><td>Delft3D vs Ritter</td><td>{fmt(wr?.iou_delft3d_ritter?.iou)}</td><td>Ritter {fmt(at?.ritter_s, 3)} s</td></tr>
        </tbody>
      </table></div>

      <dl className="workspace-values">
        <div><dt>Verification</dt><dd>{cmp.status?.verification}</dd></div>
        <div><dt>Benchmarking</dt><dd>{cmp.status?.benchmarking}</dd></div>
        <div><dt>Calibration</dt><dd>{cmp.status?.calibration}</dd></div>
        <div><dt>Validation</dt><dd>{cmp.status?.validation}</dd></div>
      </dl>
      <details className="technical-log"><summary>Limitations</summary>
        <ul>{(cmp.limitations || []).map((l, i) => <li key={i}>{l}</li>)}</ul>
      </details>
      <p className="prototype-disclaimer">
        Independent-solver agreement (SPH vs Delft3D) and analytical-benchmark agreement (vs Ritter) are
        reported above. No experimental reference values are used; no accuracy is claimed against real observations.
      </p>
    </>}
  </>
}
