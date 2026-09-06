import { Component } from 'react'
import { TriangleAlert } from 'lucide-react'

export default class ErrorBoundary extends Component {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  render() {
    if (this.state.error) return <div className="map-error"><TriangleAlert size={28} /><h2>3D map unavailable</h2><p>Your browser could not initialize the map. Enable WebGL and hardware acceleration, then reload.</p><button onClick={() => window.location.reload()}>Reload dashboard</button></div>
    return this.props.children
  }
}
