import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { DraftSnapshot } from './draftState'
import type { DraftSession } from './useDraftSession'
import './textEdits.css'

export function DraftRecovery<T, S extends DraftSnapshot>({ draft }: { draft: DraftSession<T, S> }) {
  const action = useAction()
  return <div className="document-tools"><p className="subtle" role="status">{draftStatus(draft)}</p><ErrorNotice message={draft.error || action.error} />
    {draft.remote && <ConflictReview draft={draft} />}
    {(draft.error || draft.phase === 'offline') && <button type="button" className="button" onClick={() => void action.run(async () => { await draft.controller.flush() })}>Reconnect and save draft</button>}
    {!!draft.copies.length && <details><summary>Recover local drafts ({draft.copies.length})</summary><p className="subtle">Copies may include work still open in another window. Review before replacing the saved draft.</p>{draft.copies.map(copy => <section className="draft-copy" key={copy.id}><p>{new Date(copy.savedAt).toLocaleString()}</p><pre>{copy.text}</pre><button type="button" className="button" disabled={!draft.base} onClick={() => draft.controller.reviewLocal(copy.id)}>Review this local copy</button><button type="button" className="text-button" onClick={() => draft.controller.discardCopy(copy.id)}>Discard this recovery copy</button></section>)}</details>}
  </div>
}

function draftStatus({ phase, dirty }: { phase: string; dirty: boolean }) {
  if (phase === 'loading') return 'Opening the saved draft…'
  if (phase === 'conflict') return 'This draft changed in another view. Your text is retained below.'
  if (phase === 'offline') return 'Draft not synchronized. Keep this view open or recover its local copy when reconnected.'
  return dirty ? 'Saving unsent text…' : 'Unsent text saved in this workspace. Saving does not send it.'
}

function ConflictReview<T, S extends DraftSnapshot>({ draft }: { draft: DraftSession<T, S> }) {
  const action = useAction()
  return <section className="edit-conflict" aria-label="Draft conflict"><p>The saved version changed. Review both versions and combine any words you want to keep in “Your reviewed draft”.</p><label className="field"><span>Current saved draft</span><textarea aria-label="Current saved draft" rows={5} readOnly value={draft.remote!.text} /></label><label className="field"><span>Your reviewed draft</span><textarea aria-label="Your reviewed draft" rows={5} maxLength={draft.remote!.limit} value={draft.text} onChange={event => draft.controller.edit(event.target.value)} /></label><ErrorNotice message={action.error} /><div className="text-edit-actions"><button type="button" className="button" disabled={action.busy} onClick={() => void action.run(draft.controller.saveReviewed)}>Save my reviewed draft</button><button type="button" className="text-button" disabled={action.busy} onClick={draft.controller.useRemote}>Discard my changes and use saved draft</button></div></section>
}
