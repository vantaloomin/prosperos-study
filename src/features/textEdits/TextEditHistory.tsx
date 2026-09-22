import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextEditWindow } from './TextEditWindow'
import type { EditInitial, TextEditSummary } from './types'

export function TextEditHistory({ storyId, onClose, onBranch, focusOnClose }: { storyId: string; onClose: () => void; onBranch: (id: string) => void; focusOnClose?: () => HTMLElement | null }) {
  const [selected, setSelected] = useState<EditInitial | null>(null)
  const query = useQuery({ queryKey: ['text-edit-history', storyId], queryFn: () => api<TextEditSummary[]>(`/stories/${storyId}/text-edits`) })
  if (selected) return <TextEditWindow initial={selected} onClose={onClose} onBranch={onBranch} focusOnClose={focusOnClose} />
  return <Modal open title="Text changes" description="Return to a saved proposal or applied change. The most recent 100 changes are shown." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}{query.data?.map(proposal => <article key={proposal.id} className="text-target-card"><h3>{proposal.label}</h3><p className="subtle">{proposal.status} · {new Date(proposal.created_at).toLocaleString()}</p><button className="button" onClick={() => setSelected(proposal.receipt_id ? { receiptId: proposal.receipt_id } : { proposalId: proposal.id })}>{proposal.receipt_id ? 'View change & Undo' : 'Review proposal'}</button></article>)}{query.data?.length === 0 && <p className="subtle">No saved text edits in this Story yet.</p>}</div></Modal>
}
