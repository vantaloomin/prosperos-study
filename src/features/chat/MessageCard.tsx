import { Dice5, GitBranch, Pencil, GalleryHorizontalEnd } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { api, operationId } from '../../api'
import { TextField, Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { Branch, Message } from '../../types'
import { RollInspector } from '../mechanics/RollInspector'
const GenerationReview = lazy(() => import('../generation/GenerationReview').then((module) => ({ default: module.GenerationReview })))

interface Props { message: Message; branch: Branch; onBranch: (id: string) => void }

export function MessageCard({ message, branch, onBranch, label, position }: Props & { label: string; position?: string }) {
  const [mode, setMode] = useState<'edit' | 'fork' | null>(null)
  return <article className={`message message-${message.role}`} id={`message-${message.id}`} aria-label={position}>
    <header data-reading-anchor={`${message.id}:header`}><span className="eyebrow">{label}</span><div className="message-actions"><HistoryActions message={message} branch={branch} onBranch={onBranch} /><button className="icon-button" aria-label="Edit message on a new branch" onClick={() => setMode('edit')}><Pencil size={14} /></button><button className="icon-button" aria-label="Branch from this message" onClick={() => setMode('fork')}><GitBranch size={14} /></button></div></header>
    <div className="prose">{message.text.split('\n\n').map((paragraph, index) => <p key={index} data-reading-anchor={`${message.id}:p${index}`}>{paragraph}</p>)}</div>
    {mode && <ForkEditor mode={mode} message={message} branch={branch} onBranch={onBranch} onClose={() => setMode(null)} />}
  </article>
}

function HistoryActions({ message, branch, onBranch }: Props) {
  const [view, setView] = useState('')
  const opportunity = typeof message.metadata.opportunity_id === 'string' ? message.metadata.opportunity_id : ''
  const generation = typeof message.metadata.generation_id === 'string' ? message.metadata.generation_id : ''
  const candidate = typeof message.metadata.candidate_id === 'string' ? message.metadata.candidate_id : ''
  return <>{opportunity && <button className="icon-button" aria-label="Inspect or reroll this beat" onClick={() => setView('roll')}><Dice5 size={14} /></button>}{generation && <button className="icon-button" aria-label="Other tellings of this response" onClick={() => setView('tellings')}><GalleryHorizontalEnd size={14} /></button>}{view === 'roll' && <RollInspector id={opportunity} branch={branch} onBranch={onBranch} onClose={() => setView('')} />}{view === 'tellings' && <Suspense fallback={<span role="status">Opening tellings…</span>}><GenerationReview id={generation} initialCandidateId={candidate} onBranch={onBranch} onClose={() => setView('')} /></Suspense>}</>
}

function ForkEditor({ mode, message, branch, onBranch, onClose }: Props & { mode: 'edit' | 'fork'; onClose: () => void }) {
  const [text, setText] = useState(message.text)
  const [name, setName] = useState(mode === 'edit' ? 'An edited path' : 'A different path')
  const action = useAction()
  const save = () => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/branches/${branch.id}/forks`, {
      operation_id: operationId(), expected_revision: branch.revision, node_id: message.id,
      name, replacement: mode === 'edit' ? text : null,
    })
    onBranch(result.branch_id)
    onClose()
  })
  return <Modal open onClose={onClose} title={mode === 'edit' ? 'A new version of this moment' : 'Follow another possibility'} description="The original path and everything after this moment will remain available.">
    <div className="dialog-body form-stack"><Field label="Branch name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      {mode === 'edit' && <TextField label="Revised message" rows={10} value={text} onChange={(e) => setText(e.target.value)} autoFocus />}
      <ErrorNotice message={action.error} /></div>
    <footer className="dialog-footer"><span className="subtle">No generation is started.</span><button className="button primary" disabled={action.busy || !text.trim() || !name.trim()} onClick={save}>{action.busy ? 'Saving…' : 'Create branch'}</button></footer>
  </Modal>
}
