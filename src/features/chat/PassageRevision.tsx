import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { Branch, Message } from '../../types'

export function PassageRevision({ message, branch, onBranch, onClose }: { message: Message; branch: Branch; onBranch: (id: string) => void; onClose: () => void }) {
  const restoring = !!message.metadata.removed
  const [name, setName] = useState(restoring ? 'A restored path' : 'A revised path')
  const [acknowledged, setAcknowledged] = useState(false)
  const [operation] = useState(operationId)
  const committed = useRef(false)
  const action = useAction()
  const save = () => action.run(async () => {
    const result = await api<{ branch_id: string; node_id: string }>(`/branches/${branch.id}/passage-revisions`, {
      operation_id: operation, expected_revision: branch.revision, node_id: message.id,
      action: restoring ? 'restore' : 'remove', name, acknowledge_state_reset: acknowledged,
    })
    rememberPassage(result.branch_id, result.node_id)
    committed.current = true
    onBranch(result.branch_id)
    onClose()
  })
  return <Modal open onClose={onClose} focusOnClose={() => committed.current ? document.querySelector<HTMLElement>('[aria-label="Story history"]') : null} title={restoring ? 'Undo passage removal' : 'Remove passage from this path'} description="Creates a revised path. The original path and historical copies remain available.">
    <div className="dialog-body form-stack"><Field label="Revised path name" value={name} onChange={event => setName(event.target.value)} maxLength={120} />
      <p>Later prose stays in order. Plans, memory decisions, summaries, character evidence, and chance or background state from this point onward are left on the original path. This path starts from the state before this passage; no model runs or rolls are replayed.</p>
      <label className="check-row"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I will review the later prose and rebuild any affected memory or plans before continuing.</label>
      <ErrorNotice message={action.error} /></div>
    <footer className="dialog-footer"><button className="button" onClick={onClose}>Cancel</button><button className="button primary" disabled={!acknowledged || !name.trim() || action.busy} onClick={save}>{restoring ? 'Restore passage on revised path' : 'Remove passage'}</button></footer>
  </Modal>
}

function rememberPassage(branchId: string, nodeId: string) {
  try { sessionStorage.setItem(`reading:${branchId}`, JSON.stringify({ block: `${nodeId}:header`, offset: 0, fraction: 0, pixels: 0, atEnd: false })) }
  catch { /* The saved path still opens if browser reading-position storage is unavailable. */ }
}
