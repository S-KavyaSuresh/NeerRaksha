export const pipelineStages = ['Data Validation','DEM / River Context','Scenario Routing','Depth Bands','Visualization']
export const idleRun = () => ({status:'idle',elapsed:0,progress:0,scenario:null})

export function pipelineStatus(run,index) {
  if(run.status==='completed') return 'Complete'
  if(run.status==='idle') return 'Waiting'
  const current=Math.min(4,Math.floor(run.elapsed/0.45))
  if(index<current) return 'Complete'
  if(run.status==='cancelled') return index===current?'Cancelled':'Not run'
  return index===current?'Processing':'Waiting'
}

export function advanceRun(run,seconds) {
  if(run.status!=='running'||!Number.isFinite(seconds)||seconds<0) return run
  const elapsed=Math.min(2.25,run.elapsed+seconds)
  return {...run,elapsed,progress:Math.round(elapsed/2.25*100),status:elapsed>=2.25?'completed':'running'}
}
