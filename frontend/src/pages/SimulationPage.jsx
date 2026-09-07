import { useState } from 'react'
import { Play, Square, RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDashboard } from '../store/useDashboard'
import { pipelineStages, pipelineStatus } from '../data/pipeline.js'
import { scenarioFields } from '../data/scenarios.js'

export default function SimulationPage() {
  const { scenario,run,startRun,cancelRun,resetRun }=useDashboard()
  const [error,setError]=useState('')
  function start() {const result=startRun();setError(result.ok?'':Object.values(result.errors).join(' '))}
  return <><p className="prototype-disclaimer">Automated approximate 2D flood-routing prototype · not validated operational hydraulic output.</p>
    <div className="selected-scenario"><span>SELECTED SCENARIO</span><strong>{scenario.name}</strong><Link to="/scenario">Edit assumptions →</Link></div>
    <ol className="pipeline">{pipelineStages.map((stage,index)=><li key={stage} className={index===2?'pipeline-skipped':pipelineStatus(run,index).startsWith('Complete')?'pipeline-complete':''}><span>{String(index+1).padStart(2,'0')}</span><div><strong>{stage}</strong><small>{pipelineStatus(run,index)}</small></div></li>)}</ol>
    <div className="run-status"><span className="status-dot"/>{run.status.toUpperCase()}<strong>{run.progress}% · {run.elapsed.toFixed(1)}s</strong></div><div className="progress-bar" role="progressbar" aria-label="Prototype preparation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={run.progress}><span style={{width:run.progress+'%'}}/></div>
    <div className="form-actions"><button className="action-button" onClick={start} disabled={run.status==='running'}><Play size={16}/> Run Simulation</button>{run.status==='running'&&<button onClick={cancelRun}><Square size={15}/> Cancel</button>}<button onClick={resetRun}><RotateCcw size={15}/> Reset</button></div>{error&&<p role="alert" className="field-error">{error}</p>}
    <details className="technical-log"><summary>Selected parameters & technical status</summary><dl className="workspace-values"><div><dt>Breach type</dt><dd>{scenario.breach_type}</dd></div>{scenarioFields.map(field=><div key={field.key}><dt>{field.label}</dt><dd>{scenario[field.key]}</dd></div>)}</dl><ul><li>Data validation checks prototype parameter ranges.</li><li>Terrain preparation stages the existing map context; no terrain analysis runs.</li><li>The local routing model prepares scenario-specific propagation and depth bands.</li><li>Processing prepares continuous 0–60 minute scenario playback.</li><li>Visualization starts 0–60 minute sample playback on completion.</li><li>Elapsed time measures preparation of the interactive prototype scenario.</li></ul></details>
  </>
}
