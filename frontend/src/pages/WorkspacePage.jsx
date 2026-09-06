import { useLocation } from 'react-router-dom'
import ScenarioStudio from './ScenarioStudio'
import SimulationPage from './SimulationPage'
import ComparisonPage from './ComparisonPage'
import ImpactPage from './ImpactPage'
import ExportsPage from './ExportsPage'

const pages={
  scenario:['01 / SCENARIO STUDIO','Explore the breach assumptions',ScenarioStudio],
  simulation:['02 / SIMULATION','A minute-by-minute perspective',SimulationPage],
  comparison:['03 / MODEL COMPARISON','Compare synthetic breach scenarios',ComparisonPage],
  impact:['04 / IMPACT ANALYSIS','Where the water meets the city',ImpactPage],
  exports:['05 / EXPORT CENTER','Take the intelligence with you',ExportsPage]
}

export default function WorkspacePage() {
  const page=pages[useLocation().pathname.slice(1)]
  if(!page) return null
  const [label,title,Content]=page
  return <section className="workspace-page glass" aria-label={label}><div className="eyebrow">{label}</div><h2>{title}</h2><Content/></section>
}

