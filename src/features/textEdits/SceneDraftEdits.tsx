import { lazy, Suspense, useRef, useState } from 'react'
import type { SceneRun } from '../scenes/types'
import { SceneTextBoundary } from './EditPresentation'
import type { EditInitial } from './types'
const TextEditWindow = lazy(() => import('./TextEditWindow').then(module => ({ default: module.TextEditWindow })))

export function SceneDraftEdits({ run, onBranch }: { run: SceneRun; onBranch: (id: string) => void }) {
  const [selected, setSelected] = useState('')
  const [view, setView] = useState<EditInitial | null>(null)
  const trigger = useRef<HTMLElement | null>(null)
  const targets = run.text_targets ?? []
  const target = targets.find(item => item.ref.kind === 'scene-block' && item.ref.item_id === selected) ?? targets[0]
  if (!target || target.ref.kind !== 'scene-block') return null
  const edit = run.state.draft_edits?.[target.ref.item_id]
  const open = (initial: EditInitial, button: HTMLElement) => { trigger.current = button; setView(initial) }
  return <section className="form-stack" aria-label="Scene draft text changes"><label className="field"><span>Scene text block</span><select aria-label="Scene text block" value={target.ref.item_id} onChange={event => setSelected(event.target.value)}>{targets.map(item => item.ref.kind === 'scene-block' && <option key={item.ref.item_id} value={item.ref.item_id}>{item.label}</option>)}</select></label>
    <SceneTextBoundary />{edit && <p className="subtle">This block contains an author revision. Original wording is preserved in its specialist result.</p>}
    <div className="text-edit-actions">{!run.state.accepted && <button className="button" onClick={event => open({ target: target.ref, expectedVersion: target.version }, event.currentTarget)}>Edit selected scene block</button>}{edit && <button className="text-button" onClick={event => open({ receiptId: edit.receipt_id }, event.currentTarget)}>View scene change and Undo</button>}</div>
    {view && <Suspense fallback={<span role="status">Opening scene text change…</span>}><TextEditWindow initial={view} onBranch={onBranch} onClose={() => setView(null)} focusOnClose={() => trigger.current} /></Suspense>}
  </section>
}
