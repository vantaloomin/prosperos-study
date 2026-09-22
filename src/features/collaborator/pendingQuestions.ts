import type { SavedRequest } from '../generation/requestRecovery'

const prefix = (threadId: string) => `roleplay:side-pending:${threadId}:`
const key = (threadId: string, request: SavedRequest) => prefix(threadId) + request.body.operation_id

export function pendingQuestions(threadId: string): SavedRequest[] {
  const result: SavedRequest[] = []
  for (let index = 0; index < localStorage.length; index++) {
    const name = localStorage.key(index)
    if (!name?.startsWith(prefix(threadId))) continue
    result.push(readRequest(threadId, name))
  }
  return result
}

function readRequest(threadId: string, name: string): SavedRequest {
  try {
    const value = JSON.parse(localStorage.getItem(name)!) as SavedRequest
    if (value?.kind === 'side-question' && value.path === `/side-conversations/${threadId}/questions` &&
        typeof value.body?.operation_id === 'string' && key(threadId, value) === name &&
        typeof value.body.question === 'string' && typeof value.body.expected_draft_version === 'string') return value
  } catch { /* Keep damaged records for recovery instead of silently discarding them. */ }
  throw new Error('A question recovery record cannot be read. Check saved conversation requests before sending another question.')
}

export function retainQuestion(threadId: string, request: SavedRequest) {
  const name = key(threadId, request), text = JSON.stringify(request), existing = localStorage.getItem(name)
  if (existing && existing !== text) throw new Error('This saved question has different inputs. Review its existing request.')
  localStorage.setItem(name, text)
}

export const forgetQuestion = (threadId: string, request: SavedRequest) => localStorage.removeItem(key(threadId, request))
