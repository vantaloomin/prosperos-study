import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, operationId } from '../../api'
import { useAction } from '../../hooks/useAction'
import { publishPersistent, usePersistent } from '../../hooks/usePersistent'

interface PendingRecipe { path: string; body: Record<string, unknown> & { operation_id: string }; rejected?: boolean }
interface Receipt { id: string; job_ids?: string[] }

export function useRecipeOperation(key: string) {
  const [pending, setPending] = usePersistent<PendingRecipe | null>(key, null, true)
  const cache = useQueryClient()
  const action = useAction()
  const receipt = useQuery({ queryKey: ['recipe-operation', pending?.body.operation_id], enabled: !!pending,
    queryFn: () => api<Receipt | null>(`/recipe-runs/operations/${pending!.body.operation_id}`),
    refetchInterval: query => query.state.data ? false : 1500, retry: false })
  const transmit = async (request: PendingRecipe) => {
    // Failure to save the recovery record must happen before the mutation.
    publishPersistent(key, request); setPending(request)
    const existing = await api<Receipt | null>(`/recipe-runs/operations/${request.body.operation_id}`)
    try {
      const result = existing ?? await api<Receipt>(request.path, request.body)
      cache.setQueryData(['recipe-operation', request.body.operation_id], result)
    } catch (error) {
      if (error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) {
        const rejected = { ...request, rejected: true }
        publishPersistent(key, rejected); setPending(rejected)
      }
      throw error
    }
  }
  const send = (path: string, body: Record<string, unknown>) => action.run(async () => {
    const submit = async () => {
      const saved = localStorage.getItem(key)
      const previous = saved ? JSON.parse(saved) as PendingRecipe | null : null
      if (previous) {
        setPending(previous)
        throw new Error('A request is already saved for this view. Check that action before preparing another.')
      }
      await transmit({ path, body: { ...body, operation_id: operationId() } })
    }
    if (navigator.locks) await navigator.locks.request(key, submit)
    else await submit()
  })
  const retry = () => action.run(async () => { if (pending) await transmit(pending) })
  const clear = () => { setPending(null); action.clearError() }
  return { pending, receipt, send, retry, clear, busy: action.busy, error: action.error }
}
