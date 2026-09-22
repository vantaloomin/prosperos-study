import { Dice5, GitBranch, Pencil, GalleryHorizontalEnd, Trash2, History } from 'lucide-react'
import { lazy, Suspense, useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { Branch, Message } from '../../types'
import { RollInspector } from '../mechanics/RollInspector'
import { SendToCompanionButton } from '../collaborator/SendToCompanion'
import { prepareTextContext } from '../collaborator/prepareContext'
import { selectedProse } from '../collaborator/selectedText'
import type { TargetSnapshot } from '../textEdits/types'
const GenerationReview = lazy(() => import('../generation/GenerationReview').then((module) => ({ default: module.GenerationReview })))
const PassageRevision = lazy(() => import('./PassageRevision').then(module => ({ default: module.PassageRevision })))
const TextEditWindow = lazy(() => import('../textEdits/TextEditWindow').then(module => ({ default: module.TextEditWindow })))

interface Props { message: Message; branch: Branch; onBranch: (id: string) => void }

export function MessageCard({ message, branch, onBranch, label, position }: Props & { label: string; position?: string }) {
  const [mode, setMode] = useState<'edit' | 'fork' | 'remove' | null>(null)
  const prose = useRef<HTMLDivElement>(null)
  const prepare = async () => {
    const selection = selectedProse(prose.current, message.text)
    const target = await api<TargetSnapshot>('/text-targets/read', { target: { kind: 'passage', story_id: branch.story_id, branch_id: branch.id, node_id: message.id } })
    if (target.text !== message.text) throw new Error('This passage changed. Reopen its current text before selecting it.')
    return prepareTextContext(target, selection)
  }
  if (message.metadata.removed) return <RemovedPassage message={message} branch={branch} onBranch={onBranch} />
  return <article className={`message message-${message.role}`} id={`message-${message.id}`} aria-label={position}>
    <header data-reading-anchor={`${message.id}:header`}><span className="eyebrow">{label}</span><div className="message-actions"><HistoryActions message={message} branch={branch} onBranch={onBranch} /><button className="icon-button" aria-label="Edit message on a new branch" onClick={() => setMode('edit')}><Pencil size={14} /><span className="action-label">Edit</span></button><button className="icon-button" aria-label="Branch from this message" onClick={() => setMode('fork')}><GitBranch size={14} /><span className="action-label">Branch</span></button><button className="icon-button" aria-label="Remove passage from this path" onClick={() => setMode('remove')}><Trash2 size={14} /><span className="action-label">Remove</span></button></div></header>
    <div ref={prose} className="prose">{message.text.split('\n\n').map((paragraph, index) => <p key={index} data-reading-anchor={`${message.id}:p${index}`}>{paragraph}</p>)}</div>
    <SendToCompanionButton prepare={prepare} />
    {mode === 'remove' && <Suspense fallback={<span role="status">Opening removal…</span>}><PassageRevision message={message} branch={branch} onBranch={onBranch} onClose={() => setMode(null)} /></Suspense>}
    {mode === 'edit' && <Suspense fallback={<span role="status">Opening the text editor…</span>}><TextEditWindow initial={{ target: { kind: 'passage', story_id: branch.story_id, branch_id: branch.id, node_id: message.id } }} onBranch={onBranch} onClose={() => setMode(null)} /></Suspense>}
    {mode === 'fork' && <ForkEditor message={message} branch={branch} onBranch={onBranch} onClose={() => setMode(null)} />}
  </article>
}

function RemovedPassage({ message, branch, onBranch }: Props) {
  const [open, setOpen] = useState(false)
  const original = message.metadata.source_branch_id
  const receipt = typeof message.metadata.edit_receipt_id === 'string' ? message.metadata.edit_receipt_id : ''
  return <article className="message removed-passage" id={`message-${message.id}`}><div data-reading-anchor={`${message.id}:header`}><span>Passage removed</span><button className="text-button" onClick={() => setOpen(true)}>{receipt ? 'View change & Undo' : 'Undo'}</button>{typeof original === 'string' && <button className="text-button" onClick={() => onBranch(original)}>Original path</button>}</div>{open && <Suspense fallback={<span role="status">Opening undo…</span>}>{receipt ? <TextEditWindow initial={{ receiptId: receipt }} onBranch={onBranch} onClose={() => setOpen(false)} /> : <PassageRevision message={message} branch={branch} onBranch={onBranch} onClose={() => setOpen(false)} />}</Suspense>}</article>
}

function HistoryActions({ message, branch, onBranch }: Props) {
  const [view, setView] = useState('')
  const opportunity = typeof message.metadata.opportunity_id === 'string' ? message.metadata.opportunity_id : ''
  const generation = typeof message.metadata.generation_id === 'string' ? message.metadata.generation_id : ''
  const candidate = typeof message.metadata.candidate_id === 'string' ? message.metadata.candidate_id : ''
  return <><EditHistoryAction message={message} branch={branch} onBranch={onBranch} />{opportunity && <button className="icon-button" aria-label="Inspect or reroll this beat" onClick={() => setView('roll')}><Dice5 size={14} /></button>}{generation && <button className="icon-button" aria-label="Other tellings of this response" onClick={() => setView('tellings')}><GalleryHorizontalEnd size={14} /></button>}{view === 'roll' && <RollInspector id={opportunity} branch={branch} onBranch={onBranch} onClose={() => setView('')} />}{view === 'tellings' && <Suspense fallback={<span role="status">Opening tellings…</span>}><GenerationReview id={generation} initialCandidateId={candidate} onBranch={onBranch} onClose={() => setView('')} /></Suspense>}</>
}

function EditHistoryAction({ message, onBranch }: Props) {
  const [open, setOpen] = useState(false)
  const receipt = message.metadata.edit_receipt_id
  if (typeof receipt !== 'string') return null
  return <><button className="icon-button" aria-label="View text change and Undo" onClick={() => setOpen(true)}><History size={14} /></button>{open && <Suspense fallback={<span role="status">Opening change receipt…</span>}><TextEditWindow initial={{ receiptId: receipt }} onBranch={onBranch} onClose={() => setOpen(false)} /></Suspense>}</>
}

function ForkEditor({ message, branch, onBranch, onClose }: Props & { onClose: () => void }) {
  const [name, setName] = useState('A different path')
  const action = useAction()
  const save = () => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/branches/${branch.id}/forks`, {
      operation_id: operationId(), expected_revision: branch.revision, node_id: message.id,
      name, replacement: null,
    })
    onBranch(result.branch_id)
    onClose()
  })
  return <Modal open onClose={onClose} title="Follow another possibility" description="The original path and everything after this moment will remain available.">
    <div className="dialog-body form-stack"><Field label="Branch name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      <ErrorNotice message={action.error} /></div>
    <footer className="dialog-footer"><span className="subtle">No generation is started.</span><button className="button primary" disabled={action.busy || !name.trim()} onClick={save}>{action.busy ? 'Saving…' : 'Create branch'}</button></footer>
  </Modal>
}
