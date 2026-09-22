import { api, ApiError, operationId } from '../../api'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { continuationRequest, type MessageReceipt } from './continuation'
import type { AssessmentChoice, WritingResult } from './assessmentTypes'
import { recoverRequest, type SavedRequest } from './requestRecovery'
import { useRecovery } from './useRecovery'
import { cleanupChoices } from '../phrases/cleanupRequest'
import type { WritingChoices } from '../writing/types'

interface Continuation { receipt: MessageReceipt; profile: string; usePrepared: boolean; choice: AssessmentChoice; knowledge: string; writing?: WritingChoices; cleanup_choices?: ReturnType<typeof cleanupChoices> }
interface PendingWriting { request?: SavedRequest; continuation?: Continuation; anchor: string | null; rejected?: boolean }
export interface WritingSelection { id: string; kind: 'generation' | 'assessment'; anchor: string | null }

export function useWritingRequest(branch: Branch, receive: (selection: WritingSelection) => void) {
  const storageKey = `roleplay:pending-writing:${branch.id}`
  const { pending, store, latest, problem } = useRecovery<PendingWriting>(storageKey)
  const action = useAction()
  const execute = async (saved: PendingWriting) => {
    let prepared = saved
    try {
      const existing = await continuationReceipt(saved)
      if (!existing) {
        prepared = saved.request ? saved : await prepareContinuation(saved)
        store(prepared)
      }
      const result = existing ?? await recoverRequest<WritingResult>(prepared.request!, api)
      receive(result.assessment_id
        ? { id: result.assessment_id, kind: 'assessment', anchor: saved.anchor }
        : { id: result.id!, kind: 'generation', anchor: saved.anchor })
      store(null)
    } catch (error) {
      if (error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) store({ ...prepared, rejected: true })
      throw error
    }
  }
  const generate = (body: Record<string, unknown>) => action.run(async () => {
    if (latest()) throw new Error('Resolve the saved writing request before starting another.')
    const saved: PendingWriting = { request: { kind: 'generate', path: `/branches/${branch.id}/generations`, body: { ...body, cleanup_choices: cleanupChoices(branch.id), operation_id: operationId() } }, anchor: branch.head_id }
    store(saved)
    await execute(saved)
  })
  const onSubmitted = async (continuation: Continuation) => {
    // Store the handoff before letting the composer forget its submission.
    const current = latest()
    if (current && current.anchor !== continuation.receipt.node_id) throw new Error('Finish the earlier writing request first. This passage is saved and can be checked again afterward.')
    const saved = current ?? { continuation: { ...continuation, cleanup_choices: cleanupChoices(branch.id) }, anchor: continuation.receipt.node_id }
    store(saved)
    await action.run(() => execute(saved))
  }
  return { ...action, error: problem || action.error, pending, generate, onSubmitted,
    retry: () => action.run(async () => { if (pending) await execute(pending) }),
    clearRejected: () => action.run(async () => { if (pending?.rejected) store(null) }),
  }
}

async function prepareContinuation(saved: PendingWriting): Promise<PendingWriting> {
  const continuation = saved.continuation!
  if (continuation.knowledge) throw new ApiError('Your passage is saved. Update this character’s evidence and continue from Writing tools.', 409)
  const { receipt, profile, usePrepared, choice } = continuation
  const branch = await api<Branch>(`/branches/${receipt.branch_id}`)
  if (branch.head_id !== receipt.node_id) throw new ApiError('Your passage is saved, but this path moved on. Review the current story before starting a new request.', 409)
  const body = { ...continuationRequest(branch, receipt, profile, usePrepared, choice), ...(continuation.writing ? { writing: continuation.writing } : {}), cleanup_choices: continuation.cleanup_choices ?? null }
  return { ...saved, request: { kind: 'generate', path: `/branches/${receipt.branch_id}/generations`, body } }
}

async function continuationReceipt(saved: PendingWriting) {
  if (saved.request || !saved.continuation) return null
  const id = `continue-${saved.continuation.receipt.node_id}`
  const receipt = await api<{ kind: string | null; result: WritingResult | null }>(`/operations/${id}`)
  if (receipt.kind && receipt.kind !== 'generate') throw new Error('The continuation identifier belongs to a different operation.')
  return receipt.result
}
