import { useEffect } from 'react'
import { useDashboard } from '../store/useDashboard'

export function usePrototypeRun() {
  const running=useDashboard(state=>state.run.status==='running')
  const advance=useDashboard(state=>state.advanceRun)
  useEffect(()=>{
    if(!running) return
    let previous=performance.now()
    const timer=setInterval(()=>{const now=performance.now();advance((now-previous)/1000);previous=now},100)
    return ()=>clearInterval(timer)
  },[running,advance])
}
