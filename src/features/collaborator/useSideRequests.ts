import { useCallback, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../api'
import { recoverRequest, type SavedRequest } from '../generation/requestRecovery'
import { forgetQuestion, pendingQuestions, retainQuestion } from './pendingQuestions'

function read(threadId: string) {
  try { return { pending: pendingQuestions(threadId), error: '' } }
  catch (error) { return { pending: [] as SavedRequest[], error: error instanceof Error ? error.message : 'Question recovery storage is unavailable.' } }
}

export function useSideRequests(threadId: string) {
  const [state, setState] = useState(() => read(threadId))
  const cache = useQueryClient()
  const refresh = useCallback(async () => {
    const current = read(threadId)
    setState(current)
    for (const request of current.pending) {
      const receipt = await api<{ kind: string | null; result: unknown }>(`/operations/${request.body.operation_id}`)
      if (receipt.kind === 'side-question' && receipt.result !== null) {
        forgetQuestion(threadId, request)
        setState(read(threadId))
        await cache.invalidateQueries({ queryKey: ['side-thread', threadId] })
      }
    }
  }, [threadId, cache])
  useEffect(() => {
    let running = false
    const check = () => {
      if (running) return
      running = true
      void refresh().catch(() => {}).finally(() => { running = false })
    }
    const sync = () => setState(read(threadId))
    check()
    const timer = window.setInterval(check, 2500)
    window.addEventListener('storage', sync)
    window.addEventListener('focus', check)
    return () => { window.clearInterval(timer); window.removeEventListener('storage', sync); window.removeEventListener('focus', check) }
  }, [threadId, refresh])
  const submit = async (request: SavedRequest) => {
    retainQuestion(threadId, request)
    setState(read(threadId))
    try {
      await recoverRequest(request, api)
      forgetQuestion(threadId, request)
    } catch (error) {
      if (error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) forgetQuestion(threadId, request)
      throw error
    } finally { setState(read(threadId)) }
  }
  return { ...state, submit, refresh }
}
