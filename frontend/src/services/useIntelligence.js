import { useEffect, useState } from 'react'
import { fetchDashboard } from './api'
import { sampleSummary, sampleTimeline } from '../data/sample'

export function useIntelligence() {
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState({ summary: sampleSummary, timeline: sampleTimeline, loading: true, fallback: false, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    setData(previous => ({ ...previous, loading: true }))
    fetchDashboard(controller.signal).then(result => setData({ ...result, loading: false, fallback: false, error: '' })).catch(error => {
      if (controller.signal.aborted) return
      setData({ summary: sampleSummary, timeline: sampleTimeline, loading: false, fallback: true, error: error.response?.data?.error?.message || 'API unavailable. Using local prototype dashboard metrics.' })
    })
    return () => controller.abort()
  }, [attempt])
  return { ...data, retry: () => setAttempt(value => value + 1) }
}
