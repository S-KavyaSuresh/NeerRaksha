import { loadEnv } from 'vite'
import { initializeIon } from '../src/utils/cesiumToken.js'

const ion={}
const diagnostics=initializeIon(ion,loadEnv('development',process.cwd(),'VITE_').VITE_CESIUM_ION_TOKEN)
console.log(JSON.stringify(diagnostics))
if(!diagnostics.tokenConfigured||!diagnostics.tokenFormatValid) process.exitCode=1
else {
  try {
    const endpoint=new URL('https://api.cesium.com/v1/assets/1/endpoint')
    endpoint.searchParams.set('access_token',ion.defaultAccessToken)
    const response=await fetch(endpoint,{signal:AbortSignal.timeout(12000)})
    if(!response.ok) process.exitCode=1
    else {
      const asset=await response.json()
      if(asset.type!=='TERRAIN') process.exitCode=1
    }
  } catch { process.exitCode=1 }
}
