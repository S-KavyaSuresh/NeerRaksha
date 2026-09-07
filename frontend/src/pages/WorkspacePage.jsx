import { useLocation } from 'react-router-dom'
import ScenarioStudio from './ScenarioStudio'
import SimulationPage from './SimulationPage'
import ComparisonPage from './ComparisonPage'
import BenchmarkPage from './BenchmarkPage'
import ScenarioRunPage from './ScenarioRunPage'
import ImpactPage from './ImpactPage'
import ExportsPage from './ExportsPage'

const pages={
  scenario:['01 / SCENARIO STUDIO','Explore the breach assumptions',ScenarioStudio],
  simulation:['02 / SIMULATION','A minute-by-minute perspective',SimulationPage],
  'ujjani-scenario':['03 / UJJANI DAM-BREAK','Physical scenario: breach at the dam on real terrain',ScenarioRunPage],
  comparison:['04 / MODEL COMPARISON','Compare breach simulation scenarios',ComparisonPage],
  benchmark:['05 / BENCHMARK','Dam-break verification: SPH vs Delft3D vs Ritter (1892)',BenchmarkPage],
  impact:['06 / IMPACT ANALYSIS','Where the water meets the city',ImpactPage],
  exports:['07 / EXPORT CENTER','Take the intelligence with you',ExportsPage]
}

export default function WorkspacePage() {
  const page=pages[useLocation().pathname.slice(1)]
  if(!page) return null
  const [label,title,Content]=page
  return <section className="workspace-page glass" aria-label={label}><div className="eyebrow">{label}</div><h2>{title}</h2><Content/></section>
}

