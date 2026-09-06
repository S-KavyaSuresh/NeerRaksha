import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Save } from 'lucide-react'
import { useDashboard } from '../store/useDashboard'
import { scenarioPresets, scenarioFields, validateScenario } from '../data/scenarios.js'

export default function ScenarioStudio() {
  const selected=useDashboard(state=>state.scenario)
  const saveScenario=useDashboard(state=>state.saveScenario)
  const [draft,setDraft]=useState({...selected})
  const [errors,setErrors]=useState({})
  const [message,setMessage]=useState('')
  const navigate=useNavigate()
  function change(key,value) {
    const next={...draft,[key]:value,preset:'custom'}
    setDraft(next)
    setErrors(validateScenario(next))
    setMessage('Unsaved simulation assumptions')
  }
  function save(continueToSimulation=false) {
    const result=saveScenario(draft)
    setErrors(result.errors||{})
    if(!result.ok) {setMessage('Correct the highlighted fields before continuing.');return}
    setMessage(result.persistent?'Scenario saved on this browser origin.':'Scenario saved for this session; browser storage unavailable.')
    if(continueToSimulation) navigate('/simulation')
  }
  return <><p>Editable simulation assumptions. These inputs do not recalculate the prebuilt flood states.</p>
    <div className="segmented" aria-label="Scenario presets">{[['partial','Partial Breach'],['major','Major Breach'],['custom','Custom']].map(([key,label])=><button key={key} aria-pressed={draft.preset===key} onClick={()=>{setDraft({...scenarioPresets[key]});setErrors({});setMessage('Preset loaded. Save to use these assumptions.')}}>{label}</button>)}</div>
    <form className="scenario-form" onSubmit={event=>{event.preventDefault();save()}} noValidate>
      <label htmlFor="scenario-name">Scenario name<input id="scenario-name" value={draft.name} maxLength={80} onChange={event=>change('name',event.target.value)} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name?'error-name':undefined}/>{errors.name&&<small id="error-name" className="field-error">{errors.name}</small>}</label>
      <label htmlFor="breach-type">Breach type<select id="breach-type" value={draft.breach_type} onChange={event=>change('breach_type',event.target.value)}><option value="partial">Partial</option><option value="major">Major</option></select></label>
      {scenarioFields.map(field=><label key={field.key} htmlFor={field.key}>{field.label}<input id={field.key} type="number" min={field.min} max={field.max} step="any" value={draft[field.key]} onChange={event=>change(field.key,event.target.value)} aria-invalid={Boolean(errors[field.key])} aria-describedby={'help-'+field.key}/><small id={'help-'+field.key} className={errors[field.key]?'field-error':''}>{errors[field.key]||`Prototype range: ${field.min}–${field.max}`}</small></label>)}
      <div className="form-actions"><button className="action-button" type="submit"><Save size={15}/> Save scenario</button><button type="button" className="action-button" onClick={()=>save(true)}>Continue to Simulation <ArrowRight size={15}/></button></div>
    </form><p className="form-status" role="status">{message}</p><div className="context-note">Playback uses the same 0–60 minute sample geometry for every input set. Longer durations are saved assumptions for future solver configuration.</div>
  </>
}
