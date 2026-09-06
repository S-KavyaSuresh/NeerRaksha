import { mkdir,writeFile } from 'node:fs/promises'
import { buildExport } from '../src/utils/exports.js'
import { scenarioPresets } from '../src/data/scenarios.js'

const folder=new URL('../../data/exports/verification/',import.meta.url)
await mkdir(folder,{recursive:true})
for(const minute of [0,15,30,60]) {
  for(const format of ['json','csv','geojson','kml']) {
    const file=buildExport(format,{...scenarioPresets.custom,name:'Verification <A> & "B"'},minute,new Date('2026-09-05T12:00:00Z'))
    await writeFile(new URL(file.name,folder),file.content,'utf8')
  }
}
console.log('Generated 16 export verification files in data/exports/verification.')
