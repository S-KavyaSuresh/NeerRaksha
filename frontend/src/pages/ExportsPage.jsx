import { useState } from 'react'
import { Download, Check } from 'lucide-react'
import { useDashboard } from '../store/useDashboard'
import { buildExport } from '../utils/exports.js'
import { downloadFile } from '../utils/format'
import { getActiveFrame } from '../data/prototype.js'

export default function ExportsPage() {
  const {scenario,minute}=useDashboard()
  const [status,setStatus]=useState({format:'',message:'',error:false})
  function exportData(format) {
    try {
      const file=buildExport(format,scenario,minute)
      downloadFile(file.name,file.content,file.type)
      setStatus({format,message:file.name+' download requested. Check your browser downloads.',error:false})
    } catch(error) {setStatus({format:'',message:error.message||'Export could not be generated. Try again.',error:true})}
  }
  return <><p><strong>{scenario.name}</strong> · active sample frame T+{getActiveFrame(minute).minute}</p><p>Every file contains the scenario, active frame, generation timestamp, source and “not validated hydraulic output” metadata.</p>
    {[['json','JSON · current impact','Selected assumptions and current frame estimates'],['csv','CSV · sample timeline','Four sample frames, with current selection metadata'],['geojson','GeoJSON · active flood','WGS84 longitude/latitude polygon'],['kml','KML · active flood','Current prototype extent for geographic viewers']].map(([format,title,description])=><button className="export-item" key={format} onClick={()=>exportData(format)}><span><strong>{title}</strong><small>{description}</small></span>{status.format===format?<Check size={20}/>:<Download size={20}/>}</button>)}
    <p className={'download-status '+(status.error?'field-error':'')} role={status.error?'alert':'status'}>{status.message||'T+00 exports contain metadata and no downstream flood polygon.'}</p><div className="context-note">PROTOTYPE SAMPLE DATA. These files are not solver results. SHP export is not implemented.</div>
  </>
}
