import { ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export default function StudyCaseSelector({ cases, selectedCase, onChange }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const selectedIndex = Math.max(0, cases.findIndex(item => item.case_id === selectedCase?.case_id))

  useEffect(() => {
    const close = event => { if (!rootRef.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  function choose(item) { onChange(item.case_id); setOpen(false) }
  function onKeyDown(event) {
    if (!cases.length) return
    if (event.key === 'Escape') { setOpen(false); return }
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setOpen(value => !value); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const offset = event.key === 'ArrowDown' ? 1 : -1
      choose(cases[(selectedIndex + offset + cases.length) % cases.length])
    }
  }

  return <div className="study-case-selector" ref={rootRef} onKeyDown={onKeyDown}>
    <button type="button" className="study-case-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(value => !value)}>
      <strong>{selectedCase?.dam_name || 'Loading study areas'} {selectedCase?.river_name && <span>/ {selectedCase.river_name}</span>}</strong><ChevronDown size={15}/>
    </button>
    {open && <div className="study-case-menu" role="listbox" aria-label="Select study area">
      {cases.map(item => <button type="button" role="option" aria-selected={item.case_id === selectedCase?.case_id} className={item.case_id === selectedCase?.case_id ? 'selected' : ''} key={item.case_id} onClick={() => choose(item)}><strong>{item.dam_name}</strong><small>{item.river_name} · {item.state}</small></button>)}
    </div>}
  </div>
}
