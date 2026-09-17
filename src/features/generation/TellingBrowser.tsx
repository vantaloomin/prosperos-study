import { useLayoutEffect, useRef, useState, type ReactNode, type KeyboardEvent } from 'react'
import { motion } from 'motion/react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { Candidate, Generation } from './types'
import { CandidateView } from './CandidateView'
import { tellingIndex } from './tellingSwipe'
import { useTellingSwipe } from './useTellingSwipe'

export function TellingBrowser({ generation, initialId, onBranch, onClose, inspector }: { generation: Generation; initialId: string; onBranch: (id: string) => void; onClose: () => void; inspector: ReactNode }) {
  const candidates = generation.candidates
  const [selected, setSelected] = useState(initialId)
  const current = candidates.find((item) => item.id === selected) ?? candidates[0]
  const candidateId = current?.id ?? ''
  const body = useRef<HTMLDivElement>(null)
  const tabs = useRef<HTMLDivElement>(null)
  const positions = useRef(new Map<string, number>())
  const select = (id: string) => {
    if (current && body.current) positions.current.set(current.id, body.current.scrollTop)
    setSelected(id)
  }
  useLayoutEffect(() => {
    if (!candidateId || !body.current) return
    const active = tabs.current?.querySelector<HTMLElement>('.active')
    revealTab(tabs.current, active)
    body.current.scrollTop = positions.current.get(candidateId) ?? 0
    if (document.activeElement === document.body) {
      const destination = body.current.querySelector<HTMLElement>('.telling-swipe-handle') ?? active
      destination?.focus({ preventScroll: true })
    }
  }, [candidateId])
  if (!current) return null
  return <div ref={body} className="dialog-body generation-review">
    <div ref={tabs} className="candidate-tabs" aria-label="Model alternatives">{candidates.map((candidate, index) => <button className={current.id === candidate.id ? 'active' : ''} aria-pressed={current.id === candidate.id} key={candidate.id} onClick={() => select(candidate.id)}><span>{candidate.profile.name}</span><small>Draft {index + 1} · {candidate.status}</small></button>)}</div>
    <TellingSurface candidates={candidates} current={current} onSelect={select}><CandidateView key={current.id} candidate={current} generation={generation} onBranch={onBranch} onClose={onClose} onAlternate={select} /></TellingSurface>
    {inspector}
  </div>
}

function revealTab(tabs: HTMLDivElement | null, active?: HTMLElement | null) {
  if (!tabs || !active) return
  const bounds = tabs.getBoundingClientRect(), button = active.getBoundingClientRect()
  if (button.left < bounds.left) tabs.scrollLeft += button.left - bounds.left
  if (button.right > bounds.right) tabs.scrollLeft += button.right - bounds.right
}

function TellingSurface({ candidates, current, onSelect, children }: { candidates: Candidate[]; current: Candidate; onSelect: (id: string) => void; children: ReactNode }) {
  const index = candidates.findIndex((item) => item.id === current.id)
  const move = (direction: number) => { const next = candidates[index + direction]; if (next) onSelect(next.id) }
  const swipe = useTellingSwipe(index, candidates.length, current.id, move)
  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || event.altKey || event.ctrlKey || event.metaKey) return
    const next = tellingIndex(event.key, index, candidates.length)
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) event.preventDefault()
    if (next !== index) onSelect(candidates[next].id)
  }
  return <div className="telling-surface" {...swipe.events}>
    {candidates.length > 1 && <div className="telling-navigation"><button className="icon-button" aria-label="Previous telling" aria-disabled={index === 0} onClick={() => move(-1)}><ChevronLeft size={17} /></button>
      <div className="telling-swipe-handle" tabIndex={0} role="group" aria-label="Browse tellings. Swipe horizontally or use Left and Right arrows, Home and End." onKeyDown={keyDown}>
        <span role="status" aria-live="polite" aria-atomic="true">Telling {index + 1} of {candidates.length} · {current.profile.name}</span>
        <small>{swipe.hint ? `Release for ${swipe.hint > 0 ? 'next' : 'previous'}` : 'Swipe to preview'}</small>
      </div><button className="icon-button" aria-label="Next telling" aria-disabled={index === candidates.length - 1} onClick={() => move(1)}><ChevronRight size={17} /></button></div>}
    <div className="telling-viewport"><motion.div style={{ transform: swipe.transform }}>{children}</motion.div></div>
  </div>
}
