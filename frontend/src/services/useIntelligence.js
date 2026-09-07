import { sampleSummary, sampleTimeline } from '../data/sample'

/*
 * Since Phase 5, the Scenario Intelligence panel is driven entirely by the live
 * `backend` store slice (a completed Delft3D / SPH / approximate run). The old
 * dashboard fetch hit a hard-coded placeholder simulation id
 * (`/api/simulations/44444444/...`) which only ever existed in a seeded Neon DB
 * and otherwise produced 503/404 console noise + no useful data.
 *
 * This hook now just supplies the static sample shape that the header timestamp
 * and the notifications panel still read. No network request is made, so no
 * request for the placeholder id is issued.
 */
export function useIntelligence() {
  return {
    summary: sampleSummary,
    timeline: sampleTimeline,
    loading: false,
    fallback: false,
    error: '',
    retry: () => {}
  }
}
