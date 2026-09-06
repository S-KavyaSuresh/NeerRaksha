import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig({
  plugins: [react(), viteStaticCopy({ targets: ['Workers', 'ThirdParty', 'Assets', 'Widgets'].map(name => ({ src: `node_modules/cesium/Build/Cesium/${name}`, dest: 'cesium' })) })],
  define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') },
  build: { chunkSizeWarningLimit: 2500, rollupOptions: { output: { manualChunks: { cesium: ['cesium', 'resium'], charts: ['recharts'] } } } }
})
