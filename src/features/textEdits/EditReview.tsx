import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { RevisionBoundary, TargetCard, TextComparison } from './EditPresentation'
import { editPreview, type TextProposal, type TextReceipt } from './types'

interface Props { id: string; onReceipt: (id: string) => void; onRebase: (proposal: TextProposal) => void; onClose: () => void }
export function EditReview({ id, ...props }: Props) {
  const query = useQuery({ queryKey: ['text-edit', id], queryFn: () => api<TextProposal>(`/text-edits/${id}`), refetchInterval: 2500 })
  return <><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Reading the saved proposal…" />}{query.data && <ProposalEditor key={id} initial={query.data} {...props} />}</>
}

function ProposalEditor({ initial, onReceipt, onRebase, onClose }: Omit<Props, 'id'> & { initial: TextProposal }) {
  const [proposal, setProposal] = useState(initial)
  const [wording, setWording] = useState(initial.replacement)
  const [reason, setReason] = useState(initial.explanation)
  const [name, setName] = useState('Revised telling')
  const action = useAction()
  const dirty = [wording !== proposal.replacement, reason !== proposal.explanation].some(Boolean)
  const save = () => action.run(async () => {
    const next = await api<TextProposal>(`/text-edits/${proposal.id}`, { operation_id: operationId(), expected_revision: proposal.revision, replacement: wording, explanation: reason }, 'PATCH')
    setProposal(next)
  })
  const apply = () => action.run(async () => {
    const result = await api<TextReceipt>(`/text-edits/${proposal.id}/apply`, { operation_id: operationId(), expected_revision: proposal.revision, branch_name: name, acknowledge_state_reset: proposal.target.ref.kind === 'passage' })
    onReceipt(result.id)
  })
  const dismiss = () => action.run(async () => { await api(`/text-edits/${proposal.id}/dismiss`, { operation_id: operationId(), expected_revision: proposal.revision }); onClose() })
  const decided = ['applied', 'dismissed'].includes(proposal.status)
  const changedElsewhere = [initial.revision !== proposal.revision, initial.status !== proposal.status].some(Boolean)
  const refresh = () => { setProposal(initial); setWording(initial.replacement); setReason(initial.explanation); action.clearError() }
  return <><TargetCard target={proposal.target} />{changedElsewhere && <section role="status"><p>This proposal changed in another view. Your current wording is retained here.</p><button type="button" className="button" onClick={refresh}>{dirty ? 'Load saved proposal and discard my unsaved changes' : 'Refresh saved proposal'}</button></section>}<p className="subtle">Proposal · {proposal.status} · revision {proposal.revision}</p>{proposal.status === 'conflict' && <p role="alert" className="edit-conflict">Newer text is preserved. This change needs an explicit review of the current target before it can be applied.</p>}<label className="field"><span>Proposal wording</span><textarea aria-label="Proposal wording" value={wording} onChange={event => setWording(event.target.value)} rows={7} maxLength={proposal.target.limit} readOnly={decided} /></label><label className="field"><span>Explanation</span><input aria-label="Edit explanation" value={reason} onChange={event => setReason(event.target.value)} maxLength={2000} readOnly={decided} /></label><TextComparison before={proposal.target.text} after={editPreview(proposal.target.text, proposal.selection, proposal.action, wording)} /><PassageOptions proposal={proposal} name={name} onChange={setName} /><ErrorNotice message={action.error} />
    <div className="text-edit-actions">{proposal.receipt && <button className="button" onClick={() => onReceipt(proposal.receipt!.id)}>View applied result</button>}{!decided && <><button className="button" disabled={[!dirty, action.busy, changedElsewhere].some(Boolean)} onClick={() => void save()}>Save proposal wording</button><button className="button primary" disabled={[dirty, action.busy, changedElsewhere, proposal.status === 'conflict', !name.trim()].some(Boolean)} onClick={() => void apply()}>Apply this change</button><button className="button" disabled={action.busy} onClick={() => onRebase({ ...proposal, replacement: wording, explanation: reason })}>Review current target</button><button className="text-button" disabled={action.busy} onClick={() => void dismiss()}>Dismiss proposal</button></>}</div>{dirty && <p className="subtle">Save the wording you want applied before applying this proposal.</p>}
  </>
}

function PassageOptions({ proposal, name, onChange }: { proposal: TextProposal; name: string; onChange: (name: string) => void }) {
  if (proposal.target.ref.kind !== 'passage') return null
  return <><label className="field"><span>Revised telling name</span><input aria-label="Revised telling name" value={name} onChange={event => onChange(event.target.value)} maxLength={120} /></label><RevisionBoundary /></>
}
