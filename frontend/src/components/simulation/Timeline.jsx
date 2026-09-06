import { useEffect } from 'react'
import { Pause, Play, RotateCcw, Timer } from 'lucide-react'
import { useDashboard } from '../../store/useDashboard'
import { timeLabel } from '../../utils/format'
import IconButton from '../common/IconButton'

export default function Timeline() {
  const { minute, playing, speed, setMinute, setSpeed, togglePlaying, restart, tick } = useDashboard()
  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    const timer = setInterval(() => { const now = performance.now(); tick((now - last) / 1000); last = now }, 100)
    return () => clearInterval(timer)
  }, [playing, tick])
  return <section className="timeline glass" aria-label="Simulation timeline">
    <div className="timeline-heading"><span><Timer size={15} /> SIMULATION TIMELINE</span><span className="metadata">60-minute sample window</span></div>
    <div className="timeline-body"><button className="play-button" onClick={togglePlaying} aria-label={playing ? 'Pause simulation' : 'Play simulation'}>{playing ? <Pause size={19} /> : <Play size={19} fill="currentColor" />}</button><IconButton label="Restart simulation" onClick={restart}><RotateCcw size={17}/></IconButton><strong className="time-value">{timeLabel(minute)}</strong><div className="timeline-track"><input aria-label="Simulation time in minutes" type="range" min="0" max="60" step="0.1" value={minute} onChange={event => setMinute(event.target.value)} style={{ '--progress': `${minute / 60 * 100}%` }} /><div className="ticks">{[0,15,30,60].map(value => <button key={value} style={{left:`${value / 60 * 100}%`}} onClick={() => setMinute(value)} aria-label={`Jump to ${value} minutes`}>{value === 0 ? '00' : value} min</button>)}</div></div><label className="speed"><span>Speed</span><select aria-label="Playback speed" value={speed} onChange={event => setSpeed(event.target.value)}><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option></select></label></div>
  </section>
}
