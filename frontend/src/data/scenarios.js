export const scenarioPresets = {
  partial:{ preset:'partial',name:'Partial Breach',breach_type:'partial',breach_width_m:80,breach_time_minutes:45,initial_water_level_m:192,simulation_duration_minutes:60 },
  major:{ preset:'major',name:'Major Breach',breach_type:'major',breach_width_m:250,breach_time_minutes:30,initial_water_level_m:192,simulation_duration_minutes:60 },
  custom:{ preset:'custom',name:'Custom Simulation Scenario',breach_type:'major',breach_width_m:150,breach_time_minutes:35,initial_water_level_m:190,simulation_duration_minutes:60 }
}
export const scenarioFields = [
  { key:'breach_width_m',label:'Breach width (m)',min:10,max:1000 },
  { key:'breach_time_minutes',label:'Breach formation time (min)',min:1,max:180 },
  { key:'initial_water_level_m',label:'Initial reservoir water level (m)',min:100,max:220 },
  { key:'simulation_duration_minutes',label:'Simulation duration (min)',min:60,max:180 }
]

export function validateScenario(scenario) {
  const errors={}
  if(!scenario || typeof scenario!=='object') return {name:'Choose a simulation scenario.'}
  if(typeof scenario.name!=='string'||!scenario.name.trim()||scenario.name.length>80) errors.name='Enter a name of 1–80 characters.'
  if(!['partial','major'].includes(scenario.breach_type)) errors.breach_type='Choose partial or major breach.'
  for(const field of scenarioFields) {
    const value=scenario[field.key]
    if(value===''||value===null||!Number.isFinite(Number(value))||Number(value)<field.min||Number(value)>field.max) errors[field.key]=`Use a value from ${field.min} to ${field.max}.`
  }
  return errors
}

export function normalizedScenario(scenario) {
  return {preset:scenario.preset in scenarioPresets?scenario.preset:'custom',name:scenario.name.trim(),breach_type:scenario.breach_type,...Object.fromEntries(scenarioFields.map(field=>[field.key,Number(scenario[field.key])]))}
}

export function readSavedScenario() {
  try {
    const saved=JSON.parse(globalThis.localStorage?.getItem('jaldrishti.prototype-scenario') || 'null')
    if(saved&&!Object.keys(validateScenario(saved)).length) return normalizedScenario(saved)
  } catch {}
  return {...scenarioPresets.major}
}
