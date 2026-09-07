import { useState } from 'react'
import { Play, Square, RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDashboard } from '../store/useDashboard'
import { pipelineStages, pipelineStatus } from '../data/pipeline.js'
import { scenarioFields } from '../data/scenarios.js'

const BACKEND_LABEL = {
  idle:'Not started', queued:'Queued', running:'Running', completed:'Completed',
  failed:'Failed', cancelled:'Cancelled', error:'API unavailable'
}

const ENGINE_NOTE = {
  approximate: 'Automated approximate 2D flood-routing prototype · not validated hydraulic output.',
  delft3d: 'Delft3D D-Flow FM · Phase-4 Ujjani scenario: breach released at the physical dam coordinate (18.0739 N, 75.1200 E) on the real terrain mesh · MODEL DEMONSTRATION · NOT VALIDATED FOR OPERATIONAL PREDICTION.',
  sph: 'SPH demonstration-scale model; genuine weakly-compressible SPH dam-break mapped to a demonstration footprint · not validated for operational prediction.'
}

export default function SimulationPage() {
  const { scenario,run,startRun,cancelRun,resetRun,backend,simEngine,setSimEngine }=useDashboard()
  const [error,setError]=useState('')
  function start() {const result=startRun();setError(result.ok?'':Object.values(result.errors).join(' '))}
  const frameCount=backend?.availableFrames?.length||0
  const meshFaces=backend?.mesh?.faces
  return <><p className="prototype-disclaimer">Automated approximate 2D flood-routing prototype · not validated operational hydraulic output.</p>
    <div className="selected-scenario"><span>SELECTED SCENARIO</span><strong>{scenario.name}</strong><Link to="/scenario">Edit assumptions →</Link></div>
    <ol className="pipeline">{pipelineStages.map((stage,index)=><li key={stage} className={index===2?'pipeline-skipped':pipelineStatus(run,index).startsWith('Complete')?'pipeline-complete':''}><span>{String(index+1).padStart(2,'0')}</span><div><strong>{stage}</strong><small>{pipelineStatus(run,index)}</small></div></li>)}</ol>
    <div className="run-status"><span className="status-dot"/>{run.status.toUpperCase()}<strong>{run.progress}% · {run.elapsed.toFixed(1)}s</strong></div><div className="progress-bar" role="progressbar" aria-label="Prototype preparation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={run.progress}><span style={{width:run.progress+'%'}}/></div>
    <label className="speed" style={{display:'flex',gap:8,alignItems:'center',margin:'8px 0'}}><span>Engine</span>
      <select aria-label="Simulation engine" value={simEngine} onChange={e=>setSimEngine(e.target.value)} disabled={backend?.status==='running'||backend?.status==='queued'}>
        <option value="approximate">Approximate 2D routing (fast)</option>
        <option value="delft3d">Delft3D D-Flow FM — Ujjani breach at the dam (Phase 4)</option>
        <option value="sph">SPH (demonstration)</option>
      </select></label>
    <p className="prototype-disclaimer">{ENGINE_NOTE[simEngine]}{simEngine==='delft3d'?<> Full breach controls: <Link to="/ujjani-scenario">Ujjani Dam-Break page →</Link></>:null}</p>
    <div className="form-actions"><button className="action-button" onClick={start} disabled={run.status==='running'}><Play size={16}/> Run Simulation</button>{run.status==='running'&&<button onClick={cancelRun}><Square size={15}/> Cancel</button>}<button onClick={resetRun}><RotateCcw size={15}/> Reset</button></div>{error&&<p role="alert" className="field-error">{error}</p>}
    <div className="run-status" style={{marginTop:12}}><span className="status-dot"/>BACKEND SIMULATION API · {BACKEND_LABEL[backend?.status]||backend?.status}<strong>{backend?.progress||0}%{backend?.id?` · ${backend.id}`:''}</strong></div>
    <div className="progress-bar" role="progressbar" aria-label="Backend simulation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={backend?.progress||0}><span style={{width:(backend?.progress||0)+'%'}}/></div>
    <dl className="workspace-values">
      <div><dt>Status message</dt><dd>{backend?.message||'—'}</dd></div>
      <div><dt>Engine</dt><dd>{backend?.engineLabel||'—'}{backend?.fallbackUsed?' (approximate fallback)':''}</dd></div>
      <div><dt>Data class</dt><dd>{backend?.dataClass||'—'}</dd></div>
      <div><dt>Provenance</dt><dd>{backend?.provenance||'—'}</dd></div>
      <div><dt>Validated hydraulic output</dt><dd>{backend?.validatedHydraulicOutput?'yes':'no (demonstration)'}</dd></div>
      <div><dt>Flood timeline frames</dt><dd>{frameCount?`${frameCount} frames (T+${backend.availableFrames[0]}…T+${backend.availableFrames[frameCount-1]} min)`:'—'}</dd></div>
      {simEngine==='delft3d'&&<div><dt>Mesh faces</dt><dd>{meshFaces||'—'}</dd></div>}
      {simEngine==='delft3d'&&backend?.damLocation&&<div><dt>Dam location</dt><dd>{Number(backend.damLocation.lat).toFixed(4)}° N, {Number(backend.damLocation.lon).toFixed(4)}° E · in domain: {String(backend.damLocation.in_domain)} · terrain {Number(backend.damLocation.terrain_elev_m).toFixed(1)} m (REAL DEM)</dd></div>}
      {simEngine==='delft3d'&&<div><dt>Map frames</dt><dd>{backend?.mapFrames||'—'}</dd></div>}
      {simEngine==='sph'&&<div><dt>Particles</dt><dd>{backend?.particleCount||'—'}</dd></div>}
      {simEngine==='sph'&&<div><dt>Timesteps</dt><dd>{backend?.timesteps||'—'}</dd></div>}
      {simEngine==='sph'&&<div><dt>Density (min / max)</dt><dd>{backend?.minDensity!=null?`${Number(backend.minDensity).toFixed(0)} / ${Number(backend.maxDensity).toFixed(0)} kg/m³`:'—'}</dd></div>}
      {simEngine==='sph'&&<div><dt>Max particle displacement</dt><dd>{backend?.maxDisplacementM!=null?`${Number(backend.maxDisplacementM).toFixed(2)} m`:'—'}</dd></div>}
      {(simEngine==='delft3d'||simEngine==='sph')&&<div><dt>Max depth / velocity</dt><dd>{backend?.maxDepthM!=null?`${Number(backend.maxDepthM).toFixed(2)} m / ${Number(backend.maxVelocityMps).toFixed(2)} m/s`:'—'}</dd></div>}
      {(simEngine==='delft3d'||simEngine==='sph')&&<div><dt>Solver runtime</dt><dd>{backend?.runtimeSeconds!=null?`${Number(backend.runtimeSeconds).toFixed(1)} s`:'—'}</dd></div>}
    </dl>
    {backend?.error&&<p role="alert" className="field-error">{backend.error}</p>}
    {backend?.status==='completed'&&<p className="prototype-disclaimer">Move the simulation timeline below — the Cesium flood layer follows these {frameCount} model frames. Not validated operational hydraulic output.</p>}
    <details className="technical-log"><summary>Selected parameters & technical status</summary><dl className="workspace-values"><div><dt>Breach type</dt><dd>{scenario.breach_type}</dd></div>{scenarioFields.map(field=><div key={field.key}><dt>{field.label}</dt><dd>{scenario[field.key]}</dd></div>)}</dl><ul><li>Data validation checks prototype parameter ranges.</li><li>Terrain preparation stages the existing map context; no terrain analysis runs.</li><li>The local routing model prepares scenario-specific propagation and depth bands.</li><li>Processing prepares continuous 0–60 minute scenario playback.</li><li>Visualization starts 0–60 minute sample playback on completion.</li><li>Elapsed time measures preparation of the interactive prototype scenario.</li></ul></details>
  </>
}
