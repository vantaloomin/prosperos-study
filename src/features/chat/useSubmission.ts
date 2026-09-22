import { api, ApiError, operationId } from '../../api'
import { useAction } from '../../hooks/useAction'
import type { Branch, Role } from '../../types'
import type { MessageReceipt } from '../generation/continuation'
import { recoverRequest, type SavedRequest } from '../generation/requestRecovery'
import { useRecovery } from '../generation/useRecovery'
import type { TargetSnapshot } from '../textEdits/types'

interface Submission { request: SavedRequest; continue: boolean; rejected?: boolean }
interface Input { text: string; role: Role; opportunity: string | null; continue: boolean; prepare: () => Promise<TargetSnapshot> }

export function useSubmission(branch: Branch, onSubmitted: (receipt: MessageReceipt) => Promise<void>, onSaved: (saved: Submission) => Promise<void>) {
  const key = `roleplay:pending-message:${branch.id}`
  const { pending, store, latest, problem } = useRecovery<Submission>(key)
  const action = useAction()
  const send = (input: Input) => action.run(async () => {
    let saved = latest()
    if (!saved) {
      const draft = await input.prepare()
      if (draft.text !== input.text) throw new Error('The draft changed. Review the current wording before sending it.')
      saved = { continue: input.continue, request: { kind: 'message', path: `/branches/${branch.id}/messages`,
        body: { operation_id: operationId(), expected_revision: branch.revision, text: input.text, role: input.role, opportunity_id: input.opportunity, expected_document_version: draft.version } } }
    }
    store(saved)
    try {
      const receipt = await recoverRequest<MessageReceipt>(saved.request, api)
      if (saved.continue) await onSubmitted(receipt)
      await onSaved(saved)
      store(null)
    } catch (error) {
      if (error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) store({ ...saved, rejected: true })
      throw error
    }
  })
  return { ...action, error: problem || action.error, pending, send,
    editRejected: () => action.run(async () => { if (pending?.rejected) store(null) }),
  }
}
