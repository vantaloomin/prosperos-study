import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import { TargetCard, TextComparison } from './EditPresentation'
import { EditReview } from './EditReview'
import { EditReceipt } from './EditReceipt'
import { editPreview, wholeText, type EditAction, type EditInitial, type TargetSnapshot, type TextProposal, type TextSelection, type TextTarget } from './types'
import './textEdits.css'
import { SendToCompanionButton } from '../collaborator/SendToCompanion'
import { prepareTextContext } from '../collaborator/prepareContext'
import { RecipeLauncher } from '../writing/RecipeLauncher'

export function TextEditWindow({ initial, onClose, onBranch, focusOnClose }: { initial: EditInitial; onClose: () => void; onBranch: (id: string) => void; focusOnClose?: () => HTMLElement | null }) {
  const [view, setView] = useState(initial)
  const [nonce, setNonce] = useState(0)
  const open = (next: EditInitial) => { setView(next); setNonce(value => value + 1) }
  return <Modal open wide title="A considered change" description="Review the exact destination and wording. Every applied change keeps a receipt and a way back." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body form-stack">
    {'target' in view && <LoadEditor key={nonce} target={view.target} expectedEdition={view.expectedEdition} expectedVersion={view.expectedVersion} rebase={view.rebase} replacement={view.replacement} onPrepared={id => open({ proposalId: id })} onBranch={onBranch} />}
    {'proposalId' in view && <EditReview key={view.proposalId} id={view.proposalId} onReceipt={id => open({ receiptId: id })} onRebase={proposal => open({ target: proposal.target.ref, rebase: proposal })} onClose={onClose} />}
    {'receiptId' in view && <EditReceipt key={view.receiptId} id={view.receiptId} onReceipt={id => open({ receiptId: id })} onConflict={id => open({ proposalId: id })} onOpen={branchId => { onBranch(branchId); onClose() }} />}
  </div></Modal>
}

function LoadEditor({ target, rebase, onPrepared, expectedEdition, expectedVersion, replacement, onBranch }: { target: TextTarget; rebase?: TextProposal; onPrepared: (id: string) => void; expectedEdition?: string; expectedVersion?: string; replacement?: string; onBranch: (id: string) => void }) {
  // A rebase must open a newly read edition, never freeze a stale cache entry.
  const [readId] = useState(operationId)
  const query = useQuery({ queryKey: ['text-target', target, readId], queryFn: () => api<TargetSnapshot>('/text-targets/read', { target }), staleTime: Infinity, refetchOnWindowFocus: false })
  if (query.data && expectedVersion && query.data.version !== expectedVersion) return <ErrorNotice message="This draft changed in another view. Close this window and review its current text before starting an edit." />
  if (query.data && expectedEdition && query.data.basis.version_id !== expectedEdition) return <ErrorNotice message="A newer edition was published. Close this window and reopen the resource editor to choose its current text." />
  return <><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Reading the exact text target…" />}{query.data && <EditComposer source={query.data} rebase={rebase} replacement={replacement} onPrepared={onPrepared} onBranch={onBranch} />}</>
}

function EditComposer({ source, rebase, onPrepared, replacement: initialReplacement, onBranch }: { source: TargetSnapshot; rebase?: TextProposal; onPrepared: (id: string) => void; replacement?: string; onBranch: (id: string) => void }) {
  // Retain the edition opened by the author while other views refresh their caches.
  const [target] = useState(source)
  const [selection, setSelection] = useState<TextSelection>(() => wholeText(source.text))
  const [kind, setKind] = useState<EditAction>('update')
  const [replacement, setReplacement] = useState(rebase?.replacement ?? initialReplacement ?? source.text)
  const [explanation, setExplanation] = useState(rebase?.explanation ?? '')
  const original = useRef<HTMLTextAreaElement>(null)
  const operation = useRef({ fingerprint: '', id: '' })
  const action = useAction()
  const choose = () => {
    const input = original.current
    if (!input) return
    const next = { start: input.selectionStart, end: input.selectionEnd, text: target.text.slice(input.selectionStart, input.selectionEnd) }
    setSelection(next); setKind('replace'); setReplacement(next.text)
  }
  const changeKind = (next: EditAction) => {
    setKind(next)
    if (next === 'update') setSelection(wholeText(target.text))
    if (next === 'add') setSelection({ start: target.text.length, end: target.text.length, text: '' })
  }
  const save = () => action.run(async () => {
    const body = { target: target.ref, expected_version: target.version, selection, action: kind, replacement, explanation, ...(rebase ? { expected_revision: rebase.revision } : {}) }
    const fingerprint = JSON.stringify(body)
    if (operation.current.fingerprint !== fingerprint) operation.current = { fingerprint, id: operationId() }
    const result = await api<TextProposal>(rebase ? `/text-edits/${rebase.id}/rebase` : '/text-edits', { ...body, operation_id: operation.current.id })
    onPrepared(result.id)
  })
  const sendSelection = () => {
    const input = original.current
    const chosen = input && input.selectionStart !== input.selectionEnd ? { start: input.selectionStart, end: input.selectionEnd, text: target.text.slice(input.selectionStart, input.selectionEnd) } : selection
    return prepareTextContext(target, chosen)
  }
  return <><TargetCard target={target} /><div className="text-edit-actions"><SendToCompanionButton prepare={sendSelection} /><RecipeLauncher selection={{ target, selection, action: kind }} onBranch={onBranch} /></div>{rebase && <p className="edit-conflict" role="status">This is the current target. Review the differences and choose the exact range again before creating a rebased proposal. Preserve any newer wording you want to keep.</p>}<label className="field"><span>Source text · select a range to edit</span><textarea ref={original} aria-label="Edit source text" value={target.text} readOnly rows={7} /></label><button className="button" onClick={choose}>Use selected text</button><label className="field"><span>Text action</span><select aria-label="Text action" value={kind} onChange={event => changeKind(event.target.value as EditAction)}><option value="update">Update the whole field</option><option value="replace">Replace selected text</option><option value="insert-before">Insert before selection</option><option value="insert-after">Insert after selection</option><option value="add">Add at the end</option></select></label><p className="subtle">Selected range: {selection.start}–{selection.end}{selection.text ? ` · “${selection.text.slice(0, 150)}${selection.text.length > 150 ? '…' : ''}”` : ' · insertion point'}</p><label className="field"><span>Proposed wording</span><textarea aria-label="Proposed wording" rows={8} value={replacement} onChange={event => setReplacement(event.target.value)} maxLength={target.limit} /></label><label className="field"><span>Reason for this change (optional)</span><input aria-label="Reason for this change" value={explanation} onChange={event => setExplanation(event.target.value)} maxLength={2000} /></label><TextComparison before={target.text} after={editPreview(target.text, selection, kind, replacement)} /><ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy} onClick={() => void save()}>{rebase ? 'Create rebased proposal' : 'Save edit proposal'}</button></>
}
