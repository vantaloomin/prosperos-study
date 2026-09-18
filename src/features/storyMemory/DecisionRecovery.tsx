import { useLayoutEffect, useRef, useState } from 'react'
import { ErrorNotice } from '../../components/Feedback'
import { finishMerge, mergeDraft, mergeChoice, type DecisionDraft, type MergeConflict } from './decisionDraft'
import { labels, states, type Entry, type State } from './controlTypes'

export function DecisionRecovery({ draft, error, recovered, onDownload, onDiscard }: {
  draft: DecisionDraft | null; error: string; recovered: boolean; onDownload: () => void; onDiscard: () => void
}) {
  if (!draft && !error) return null
  return <div className="prepared-card form-stack"><p className="subtle" role="status">{recoveryLabel(draft, recovered, error)}</p>
    <ErrorNotice message={error} />
    <div className="import-downloads"><button className="text-button" onClick={onDownload}>Download recovery copy</button>
      {!draft && <button className="text-button" onClick={onDiscard}>Discard unreadable recovery copy</button>}
    </div>
  </div>
}

function recoveryLabel(draft: DecisionDraft | null, recovered: boolean, error: string) {
  if (error) return 'Draft recovery needs attention.'
  if (draft?.pending) return 'The last save has not been confirmed here. Retry the original save to check its outcome; it will not create a duplicate version.'
  if (recovered) return 'Recovered your unsaved draft on this device, including the entry you were editing. It has not been applied to the Story.'
  return 'Unsaved draft kept on this device, including what you are typing. Save author decisions to use them in future requests.'
}

export function DecisionMerge({ draft, current, onKeep, onCancel }: {
  draft: DecisionDraft; current: State; onKeep: (value: DecisionDraft) => void; onCancel: () => void
}) {
  const [choices, setChoices] = useState<Record<string, 'local' | 'saved'>>({})
  const [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const merge = mergeDraft(draft, current)
  const keep = () => { try { onKeep(finishMerge(draft, current, merge, choices)) } catch (failure) { setError((failure as Error).message) } }
  return <div className="prepared-card form-stack decision-merge"><h4 ref={heading} tabIndex={-1}>Review against the latest path</h4>
    <p>Changes to different decisions can be combined. Choose a version where both copies changed. This updates only your draft; saving still checks every source against the current path and pinned editions.</p>
    <p>Ready to combine: {merge.entries.length}. Decisions needing your choice: {merge.conflicts.length}.</p>
    {merge.conflicts.map(conflict => <ConflictChoice key={conflict.id} conflict={conflict} value={mergeChoice(choices, conflict.id)} onChange={value => setChoices({ ...choices, [conflict.id]: value })} />)}
    <details><summary>Inspect the saved decisions being reviewed ({current.entries.length})</summary>{current.entries.map(entry => <DecisionCopy key={entry.id} entry={entry} />)}</details>
    <ErrorNotice message={error} /><div className="import-downloads"><button className="button primary" disabled={merge.conflicts.some(item => !mergeChoice(choices, item.id))} onClick={keep}>Keep reviewed merge in draft</button><button className="button" onClick={onCancel}>Cancel review</button></div>
  </div>
}

function ConflictChoice({ conflict, value, onChange }: { conflict: MergeConflict; value?: 'local' | 'saved'; onChange: (value: 'local' | 'saved') => void }) {
  return <fieldset className="form-stack decision-conflict"><legend>{conflict.unavailable ? 'Evidence or Character no longer available' : 'Both copies changed'}: {conflict.local?.subject || conflict.saved?.subject}</legend>
    <label className="check-row"><input type="radio" name={'merge-' + conflict.id} checked={value === 'local'} onChange={() => onChange('local')} />Keep my draft</label><DecisionCopy entry={conflict.local} />
    <label className="check-row"><input type="radio" name={'merge-' + conflict.id} checked={value === 'saved'} onChange={() => onChange('saved')} />{conflict.unavailable ? 'Retire this unavailable decision, including any restriction' : 'Use the saved decision'}</label><DecisionCopy entry={conflict.unavailable ?? conflict.saved} />
  </fieldset>
}

function DecisionCopy({ entry }: { entry?: Entry }) {
  if (!entry) return <p className="subtle">Removed from this copy.</p>
  return <article className="form-stack"><strong>{entry.subject}</strong><small>{labels[entry.kind]} · {states[entry.kind].find(([value]) => value === entry.stance)?.[1]} · {entry.enabled ? 'Enabled' : 'Disabled'}</small><p>{entry.text}</p>
    <details><summary>Evidence ({entry.sources.length} excerpts)</summary>{entry.sources.map(source => <pre className="authoring-prose" key={source.id} tabIndex={0}>{source.text}</pre>)}</details>
  </article>
}
