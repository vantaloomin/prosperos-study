import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { RevisionBoundary, TargetCard, TextComparison } from './EditPresentation'
import type { TextProposal, TextReceipt } from './types'

interface Props { id: string; onReceipt: (id: string) => void; onConflict: (id: string) => void; onOpen: (branchId: string) => void }
export function EditReceipt({ id, ...props }: Props) {
  const query = useQuery({ queryKey: ['text-edit-receipt', id], queryFn: () => api<TextReceipt>(`/text-edit-receipts/${id}`) })
  return <><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Reading the applied change…" />}{query.data && <ReceiptContent receipt={query.data} {...props} />}</>
}

function ReceiptContent({ receipt, onReceipt, onConflict, onOpen }: Omit<Props, 'id'> & { receipt: TextReceipt }) {
  const action = useAction()
  const passage = receipt.after_target.ref.kind === 'passage'
  const undo = () => action.run(async () => {
    const result = await api<{ status: 'applied'; receipt: TextReceipt } | { status: 'conflict'; proposal: TextProposal }>(`/text-edit-receipts/${receipt.id}/undo`, { operation_id: operationId(), acknowledge_state_reset: passage })
    if (result.status === 'applied') onReceipt(result.receipt.id)
    else onConflict(result.proposal.id)
  })
  const open = () => {
    if (!receipt.result.branch_id) return
    try { sessionStorage.setItem(`reading:${receipt.result.branch_id}`, JSON.stringify({ block: `${receipt.result.node_id}:header`, offset: 0, fraction: 0, pixels: 0, atEnd: false })) } catch { /* The saved telling remains available. */ }
    onOpen(receipt.result.branch_id)
  }
  return <><p role="status" className="edit-applied">{receipt.undo_of ? 'Undo change applied.' : 'Text change applied.'}</p><TargetCard target={receipt.after_target} /><TextComparison before={receipt.before_target.text} after={receipt.after_target.text} /><p className="subtle">{receipt.explanation || 'Author-directed text change.'}{passage ? ` ${receipt.result.preserved_suffix_count} later passage(s) preserved.` : ''}</p>{passage && <RevisionBoundary />}<ErrorNotice message={action.error} /><div className="text-edit-actions">{passage && <button className="button primary" onClick={open}>Open revised telling</button>}<button className="button" disabled={action.busy} onClick={() => void undo()}>Undo / restore previous text</button></div><p className="subtle">Undo preserves independent later work. If this text changed again, it creates an inverse proposal for you to review.</p><details><summary>Change receipt</summary><dl><dt>Applied</dt><dd>{new Date(receipt.created_at).toLocaleString()}</dd><dt>Proposal</dt><dd>{receipt.proposal_id}</dd><dt>Receipt</dt><dd>{receipt.id}</dd></dl></details></>
}
