import { build } from 'esbuild'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'

const folder=path.resolve('node_modules/.cache/jaldrishti')
await mkdir(folder,{recursive:true})
const outfile=path.join(folder,'render-check.cjs')
await build({stdin:{contents:`
import React from 'react'
import {renderToString} from 'react-dom/server'
import {MemoryRouter} from 'react-router-dom'
import assert from 'node:assert/strict'
import WorkspacePage from './src/pages/WorkspacePage.jsx'
import EmergencyBriefing from './src/components/dashboard/EmergencyBriefing.jsx'
import {useDashboard} from './src/store/useDashboard.js'
for(const [route,required] of [['scenario','Continue to Simulation'],['simulation','Run Prototype Simulation'],['comparison','Current comparison: prototype breach scenarios.'],['impact','PROTOTYPE SAMPLE ESTIMATES'],['exports','KML']]) {
  const html=renderToString(<MemoryRouter initialEntries={['/'+route]}><WorkspacePage/></MemoryRouter>)
  assert.ok(html.includes(required),route)
  assert.ok(!html.includes('NaN'),route)
}
useDashboard.getState().toggleEmergency()
const emergency=renderToString(<EmergencyBriefing/>)
assert.ok(emergency.includes('Top 3 prototype priority alerts'))
assert.ok(emergency.includes('Exit Emergency Mode'))
console.log('Server-render checks passed for five workspace pages and the Emergency Briefing. No browser interactions were performed.')
`,resolveDir:process.cwd(),loader:'jsx'},outfile,bundle:true,platform:'node',format:'cjs',jsx:'automatic',packages:'external',logLevel:'silent'})
createRequire(import.meta.url)(outfile)
