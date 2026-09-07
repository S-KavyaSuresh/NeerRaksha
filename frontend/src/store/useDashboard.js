import { create } from 'zustand'
import { readSavedScenario, validateScenario, normalizedScenario } from '../data/scenarios.js'
import { idleRun, advanceRun } from '../data/pipeline.js'


const FALLBACK_UJJANI = {
  case_id:'ujjani', dam_name:'Ujjani', river_name:'Bhima', state:'Maharashtra',
  latitude:18.075, longitude:75.120278,
  // Deliberately no invented fallback river geometry. The map waits for the real
  // backend river instead of drawing a false straight flood corridor.
  spatial:{ real_river:{ type:'FeatureCollection', features:[] }, real_roads:{type:'FeatureCollection',features:[]}, real_facilities:{type:'FeatureCollection',features:[]} },
  exposure:{roads:[],facilities:[],buildings:[],settlements:[]}
}


export const useDashboard = create((set,get) => ({
  minute: 0, playing: false, speed: 1, emergency: false, collapsed: true, selected: null,
  studyCases: [FALLBACK_UJJANI], selectedStudyCaseId: 'ujjani', selectedStudyCase: FALLBACK_UJJANI,
  previousLayers: null, focusRequest: 0,
  scenario:readSavedScenario(),
  run:idleRun(),
  startRun:()=>{
    const scenario=get().scenario
    const errors=validateScenario(scenario)
    if(Object.keys(errors).length) return {ok:false,errors}
    set({run:{...idleRun(),status:'running',scenario:{...scenario}},minute:0,playing:false})
    return {ok:true}
  },
  advanceRun:seconds=>set(state=>{
    const run=advanceRun(state.run,seconds)
    if(run===state.run) return state
    return run.status==='completed'?{run,minute:0,playing:true}:{run}
  }),
  cancelRun:()=>set(state=>state.run.status==='running'?{run:{...state.run,status:'cancelled'},playing:false}:state),
  resetRun:()=>set({run:idleRun(),minute:0,playing:false}),
  saveScenario:scenario=>{
    const errors=validateScenario(scenario)
    if(Object.keys(errors).length) return {ok:false,errors}
    const saved=normalizedScenario(scenario)
    let persistent=false
    try { if(globalThis.localStorage) { globalThis.localStorage.setItem('jaldrishti.prototype-scenario',JSON.stringify(saved)); persistent=true } } catch {}
    set({scenario:saved,minute:0,playing:false,run:idleRun()})
    return {ok:true,persistent}
  },
  layers: { terrain: true, satellite: true, flood: true, buildings: false, roads: false, facilities: true },
  setMinute: minute => { if (Number.isFinite(Number(minute))) set({ minute: Math.max(0, Math.min(60, Number(minute))) }) },
  setSpeed: speed => { if ([0.5, 1, 2].includes(Number(speed))) set({ speed: Number(speed) }) },
  togglePlaying: () => set(state => ({ playing: !state.playing, minute: state.minute >= 60 ? 0 : state.minute })),
  restart: () => set({ minute: 0, playing: false }),
  tick: seconds => set(state => { if (!state.playing || !Number.isFinite(seconds) || seconds < 0) return state; const minute = Math.min(60, state.minute + seconds * state.speed); return { minute, playing: minute < 60 } }),
  toggleLayer: layer => set(state => ({ layers: { ...state.layers, [layer]: !state.layers[layer] } })),
  toggleEmergency: () => set(state => state.emergency ? { emergency:false, layers:state.previousLayers || state.layers, previousLayers:null } : { emergency:true, previousLayers:{...state.layers}, layers:{...state.layers,flood:true,roads:true,facilities:true,buildings:true}, focusRequest:state.focusRequest+1 }),
  focusFlood: () => set(state => ({ focusRequest:state.focusRequest+1 })),
  toggleCollapsed: () => set(state => ({ collapsed: !state.collapsed })),
  select: selected => set({ selected }),
  setStudyCases: studyCases => set(state => {
    const ujjani = (studyCases || []).find(caseItem => caseItem.case_id === 'ujjani') || state.selectedStudyCase || FALLBACK_UJJANI
    return { studyCases:[ujjani], selectedStudyCaseId:'ujjani', selectedStudyCase:ujjani }
  }),
  selectStudyCase: selectedStudyCaseId => set(state => {
    const selectedStudyCase = state.studyCases.find(caseItem => caseItem.case_id === selectedStudyCaseId)
    return selectedStudyCase ? { selectedStudyCaseId, selectedStudyCase } : state
  }),
  setSelectedStudyCase: selectedStudyCase => set(state => selectedStudyCase ? {
    selectedStudyCaseId: selectedStudyCase.case_id,
    selectedStudyCase,
    studyCases: state.studyCases.map(caseItem => caseItem.case_id === selectedStudyCase.case_id ? { ...caseItem, ...selectedStudyCase } : caseItem)
  } : state)
}))
