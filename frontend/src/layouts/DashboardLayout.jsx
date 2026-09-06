import { lazy, Suspense, useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Activity, Bell, ChevronLeft, ChevronRight, CircleHelp, LayoutDashboard, SlidersHorizontal, Play, ChartNoAxesCombined, ShieldAlert, Download, MapPin, X, RefreshCw } from 'lucide-react'
import { useDashboard } from '../store/useDashboard'
import { useIntelligence } from '../services/useIntelligence'
import IntelligencePanel from '../components/dashboard/IntelligencePanel'
import EmergencyBriefing from '../components/dashboard/EmergencyBriefing'
import Timeline from '../components/simulation/Timeline'
import IconButton from '../components/common/IconButton'
import ErrorBoundary from '../components/common/ErrorBoundary'
import StudyCaseSelector from '../components/dashboard/StudyCaseSelector'
import WorkspacePage from '../pages/WorkspacePage'
import { sampleTimestamp } from '../data/sample'
import { useMapTools } from '../services/useMapTools'
import { usePrototypeRun } from '../services/usePrototypeRun'
import '../styles/branding.css'

const MapView = lazy(() => import('../components/map/MapView'))
const navigation = [['overview',LayoutDashboard,'Overview'],['scenario',SlidersHorizontal,'Scenario Studio'],['simulation',Play,'Simulation'],['comparison',ChartNoAxesCombined,'Model Comparison'],['impact',ShieldAlert,'Impact Analysis'],['exports',Download,'Export Center']]

export default function DashboardLayout() {
  useMapTools()
  usePrototypeRun()
  const { collapsed, toggleCollapsed, emergency, toggleEmergency, playing, studyCases, selectedStudyCase, selectedStudyCaseId, setStudyCases, selectStudyCase, setSelectedStudyCase } = useDashboard()
  const [notifications,setNotifications] = useState(false)
  const [help,setHelp] = useState(false)
  const data = useIntelligence()
  const location = useLocation()
  useEffect(()=>{const controller=new AbortController();fetch((import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')+'/api/study-cases',{signal:controller.signal}).then(response=>response.ok?response.json():[]).then(cases=>{if(Array.isArray(cases))setStudyCases(cases)}).catch(()=>{});return()=>controller.abort()},[setStudyCases])
  useEffect(()=>{if(!selectedStudyCaseId)return undefined;const controller=new AbortController();fetch((import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')+'/api/study-cases/'+selectedStudyCaseId,{signal:controller.signal}).then(response=>response.ok?response.json():null).then(caseItem=>{if(caseItem)setSelectedStudyCase(caseItem)}).catch(()=>{});return()=>controller.abort()},[selectedStudyCaseId,setSelectedStudyCase])
  return <div className={`dashboard ${collapsed?'rail-collapsed':''} ${emergency?'emergency-mode':''} ${location.pathname!=='/overview'?'has-workspace':''}`}>
    <header className="command-bar"><NavLink to="/overview" className="brand" aria-label="NeerRaksha overview"><img className="brand-logo" src="/branding/neerraksha-logo.png" alt=""/><div><strong>NeerRaksha</strong><small>Dam Break & Flood Intelligence Platform</small></div></NavLink><div className="study-area"><MapPin size={17}/><div><small>STUDY AREA</small><StudyCaseSelector cases={studyCases} selectedCase={selectedStudyCase} onChange={selectStudyCase}/></div></div><div className="system-status"><span><i className="status-dot"/>{playing?'Replay running':'Simulation ready'}</span><small>{selectedStudyCase?.state || new Date(data.summary.updated_at || sampleTimestamp).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Kolkata'})+' IST'}</small></div><IconButton label="Show notifications" onClick={()=>setNotifications(!notifications)} aria-expanded={notifications}><Bell size={19}/><i className="notification-dot"/></IconButton><button className="emergency-button" onClick={toggleEmergency} aria-pressed={emergency}><ShieldAlert size={17}/><span>{emergency?'Exit Emergency Mode':'Emergency Mode'}</span></button><div className="avatar" title="Control room operator">OP</div></header>
    <nav className="navigation-rail" aria-label="Main navigation"><span className="rail-label">WORKSPACE</span><div className="nav-items">{navigation.map(([path,Icon,title])=><NavLink key={path} to={`/${path}`} title={title} data-tooltip={title} aria-label={title}><Icon size={20}/><span>{title}</span></NavLink>)}</div><div className="rail-footer"><button title="Platform information" aria-label="Platform information" onClick={()=>setHelp(!help)}><CircleHelp size={20}/><span>About NeerRaksha</span></button><button onClick={toggleCollapsed} aria-label={collapsed?'Expand navigation':'Collapse navigation'} title={collapsed?'Expand navigation':'Collapse navigation'}>{collapsed?<ChevronRight size={19}/>:<ChevronLeft size={19}/>}<span>Collapse panel</span></button></div></nav>
    <main className="command-workspace"><ErrorBoundary><Suspense fallback={<div className="map-loading"><span className="spinner"/> Initializing 3D intelligence</div>}><MapView/></Suspense></ErrorBoundary><motion.div className="intelligence-motion" initial={{opacity:0,x:15}} animate={{opacity:1,x:0}} transition={{duration:.4}}>{emergency?<EmergencyBriefing/>:<IntelligencePanel data={data}/>}</motion.div><WorkspacePage key={location.pathname} data={data}/><Timeline/><div className={`data-state ${data.fallback?'fallback':''}`} role="status"><Activity size={13}/>{data.loading?'Connecting to intelligence API…':data.fallback?'SYNTHETIC SIMULATION DATA · API offline':'API CONNECTED · SYNTHETIC SIMULATION DATA'}{data.fallback&&<button onClick={data.retry} title={data.error} aria-label="Retry API connection"><RefreshCw size={13}/></button>}</div></main>
    {notifications&&<div className="notifications glass" role="dialog" aria-label="Notifications"><div><h3>Notifications</h3><IconButton label="Close notifications" onClick={()=>setNotifications(false)}><X size={16}/></IconButton></div><strong>Simulation session active</strong><p>All alerts and metrics are synthetic. No live emergency feeds are connected.</p>{data.fallback&&<p>{data.error}</p>}</div>}
    {help&&<div className="help-panel glass" role="dialog" aria-label="About NeerRaksha"><IconButton label="Close platform information" onClick={()=>setHelp(false)}><X size={16}/></IconButton><h3>NeerRaksha</h3><p>Explore the selected study area, replay synthetic flood extents, and inspect hypothetical impact data.</p><p>Drag to pan, scroll to zoom, and use Ctrl + drag to tilt the 3D map. Select the dam or a visible flood extent for details.</p><p>Buildings, roads, facilities, geometry and impact values are illustrative.</p></div>}
  </div>
}

function ChevronDownIcon() { return <span className="study-chevron">⌄</span> }
