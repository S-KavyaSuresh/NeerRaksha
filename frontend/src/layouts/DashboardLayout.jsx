import { lazy, Suspense, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Bell, ChevronLeft, ChevronRight, CircleHelp, LayoutDashboard, SlidersHorizontal, Play, ChartNoAxesCombined, FlaskConical, Waves, ShieldAlert, Download, MapPin, X } from 'lucide-react'
import { useDashboard } from '../store/useDashboard'
import { useIntelligence } from '../services/useIntelligence'
import IntelligencePanel from '../components/dashboard/IntelligencePanel'
import EmergencyBriefing from '../components/dashboard/EmergencyBriefing'
import Timeline from '../components/simulation/Timeline'
import IconButton from '../components/common/IconButton'
import ErrorBoundary from '../components/common/ErrorBoundary'
import WorkspacePage from '../pages/WorkspacePage'
import { sampleTimestamp } from '../data/sample'
import { useMapTools } from '../services/useMapTools'
import { usePrototypeRun } from '../services/usePrototypeRun'
import { useSimulationRun } from '../services/useSimulationRun'
import '../styles/branding.css'

const MapView = lazy(() => import('../components/map/MapView'))
const navigation = [['overview',LayoutDashboard,'Overview'],['scenario',SlidersHorizontal,'Scenario Studio'],['simulation',Play,'Simulation'],['ujjani-scenario',Waves,'Ujjani Dam-Break'],['comparison',ChartNoAxesCombined,'Model Comparison'],['benchmark',FlaskConical,'Benchmark'],['impact',ShieldAlert,'Impact Analysis'],['exports',Download,'Export Center']]

export default function DashboardLayout() {
  useMapTools()
  usePrototypeRun()
  useSimulationRun()
  const { collapsed, toggleCollapsed, emergency, toggleEmergency, playing, selectedStudyCase } = useDashboard()
  const [notifications,setNotifications] = useState(false)
  const [help,setHelp] = useState(false)
  const data = useIntelligence()
  const location = useLocation()
  // The Ujjani study case comes from FALLBACK_UJJANI in the store plus the
  // Phase-4 scenario workflow; the study-case repository endpoint (which is not
  // deployed here and always 404s) is intentionally not called.
  return <div className={`dashboard ${collapsed?'rail-collapsed':''} ${emergency?'emergency-mode':''} ${location.pathname!=='/overview'?'has-workspace':''}`}>
    <header className="command-bar"><NavLink to="/overview" className="brand" aria-label="NeerRaksha overview"><img className="brand-logo" src="/branding/neerraksha-logo.png" alt=""/><div><strong>NeerRaksha</strong><small>Dam Break & Flood Intelligence Platform</small></div></NavLink><div className="study-area"><MapPin size={17}/><div><small>STUDY AREA</small><strong>Ujjani Dam / Bhima River</strong></div></div><div className="system-status"><span><i className="status-dot"/>{playing?'Replay running':'Simulation ready'}</span><small>{selectedStudyCase?.state || new Date(data.summary.updated_at || sampleTimestamp).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Kolkata'})+' IST'}</small></div><IconButton label="Show notifications" onClick={()=>setNotifications(!notifications)} aria-expanded={notifications}><Bell size={19}/><i className="notification-dot"/></IconButton><button className="emergency-button" onClick={toggleEmergency} aria-pressed={emergency}><ShieldAlert size={17}/><span>{emergency?'Exit Emergency Mode':'Emergency Mode'}</span></button><div className="avatar" title="Control room operator">OP</div></header>
    <nav className="navigation-rail" aria-label="Main navigation"><span className="rail-label">WORKSPACE</span><div className="nav-items">{navigation.map(([path,Icon,title])=><NavLink key={path} to={`/${path}`} title={title} data-tooltip={title} aria-label={title}><Icon size={20}/><span>{title}</span></NavLink>)}</div><div className="rail-footer"><button title="Platform information" aria-label="Platform information" onClick={()=>setHelp(!help)}><CircleHelp size={20}/><span>About NeerRaksha</span></button><button onClick={toggleCollapsed} aria-label={collapsed?'Expand navigation':'Collapse navigation'} title={collapsed?'Expand navigation':'Collapse navigation'}>{collapsed?<ChevronRight size={19}/>:<ChevronLeft size={19}/>}<span>Collapse panel</span></button></div></nav>
    <main className="command-workspace"><ErrorBoundary><Suspense fallback={<div className="map-loading"><span className="spinner"/> Initializing 3D intelligence</div>}><MapView/></Suspense></ErrorBoundary><motion.div className="intelligence-motion" initial={{opacity:0,x:15}} animate={{opacity:1,x:0}} transition={{duration:.4}}>{emergency?<EmergencyBriefing/>:<IntelligencePanel data={data}/>}</motion.div><WorkspacePage key={location.pathname} data={data}/><Timeline/></main>
    {notifications&&<div className="notifications glass" role="dialog" aria-label="Notifications"><div><h3>Notifications</h3><IconButton label="Close notifications" onClick={()=>setNotifications(false)}><X size={16}/></IconButton></div><strong>Simulation session active</strong><p>Scenario outputs are from the approximate 2D flood-routing prototype.</p>{data.fallback&&<p>{data.error}</p>}</div>}
    {help&&<div className="help-panel glass" role="dialog" aria-label="About NeerRaksha"><IconButton label="Close platform information" onClick={()=>setHelp(false)}><X size={16}/></IconButton><h3>NeerRaksha</h3><p>Explore Ujjani Dam, replay approximate flood-routing scenarios, and inspect scenario impacts.</p><p>Drag to pan, scroll to zoom, and use Ctrl + drag to tilt the 3D map. Select the dam or a visible flood extent for details.</p><p>The routing model is a prototype and is not validated operational hydraulic output.</p></div>}
  </div>
}

function ChevronDownIcon() { return <span className="study-chevron">⌄</span> }
