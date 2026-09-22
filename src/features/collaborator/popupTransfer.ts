import { api, ApiError, operationId } from '../../api'
import { recoverRequest, type SavedRequest } from '../generation/requestRecovery'
import type { TargetSnapshot, TextTarget } from '../textEdits/types'

// One explicit transfer retains its exact operation through a lost response.
export function popupTransfer(target: Extract<TextTarget, { kind: 'document' }>) {
  let saved: { text: string; request: SavedRequest } | null = null
  return async (text: string) => {
    if (!saved || saved.text !== text) {
      const source = await api<TargetSnapshot>('/text-targets/read', { target })
      saved = { text, request: { kind: 'text-document-save', path: '/text-documents', body: {
        operation_id: operationId(), target, expected_version: source.version, text: [source.text, text].filter(Boolean).join('\n\n'),
      } } }
    }
    try { await recoverRequest(saved.request, (path, body) => api(path, body, body === undefined ? 'GET' : 'PUT')) }
    catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        saved = null
        throw new Error('The saved composer changed. Review it in the workspace, then choose Add to unsent draft again.')
      }
      throw error
    }
  }
}
