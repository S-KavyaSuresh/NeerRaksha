import { useEffect } from 'react'
import { useDashboard } from '../store/useDashboard'

export function useMapTools() {
  useEffect(() => {
    const context = document.modelContext
    if (!context?.registerTool) return
    const lifecycle = new AbortController()
    try {
      Promise.resolve(context.registerTool({
        name: 'set_sample_flood_time',
        description: 'Set the visible prototype flood replay time between zero and sixty minutes. Does not run a hydraulic model.',
        inputSchema: { type: 'object', properties: { minute: { type: 'number', minimum: 0, maximum: 60 } }, required: ['minute'], additionalProperties: false },
        annotations: { readOnlyHint: false, untrustedContentHint: false },
        async execute(input) {
          if (!input || typeof input.minute !== 'number' || !Number.isFinite(input.minute) || input.minute < 0 || input.minute > 60 || Object.keys(input).some(key => key !== 'minute')) throw new Error('minute must be a number from 0 to 60')
          const state = useDashboard.getState()
          if (state.playing) state.togglePlaying()
          state.setMinute(input.minute)
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
          return { minute: useDashboard.getState().minute, is_sample: true }
        }
      }, { signal: lifecycle.signal })).catch(() => {})
    } catch {}
    return () => lifecycle.abort()
  }, [])
}
