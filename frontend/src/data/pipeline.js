export const pipelineStages = ['Data Validation','Terrain Preparation','HEC-RAS','Processing','Visualization']
export const idleRun = () => ({status:'idle',elapsed:0,progress:0,scenario:null})

export function pipelineStatus(run,index) {
  if(index===2) return 'Not connected · skipped'
  if(run.status==='completed') return 'Complete (sample)'
  if(run.status==='idle') return 'Waiting'
  const current=Math.min(4,Math.floor(run.elapsed/1.2))
  if(index<current) return 'Complete (sample)'
  if(run.status==='cancelled') return index===current?'Cancelled':'Not run'
  return index===current?'Preparing sample':'Waiting'
}

export function advanceRun(run,seconds) {
  if(run.status!=='running'||!Number.isFinite(seconds)||seconds<0) return run
  const elapsed=Math.min(6,run.elapsed+seconds)
  return {...run,elapsed,progress:Math.round(elapsed/6*100),status:elapsed>=6?'completed':'running'}
}
