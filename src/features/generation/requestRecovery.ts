export interface SavedRequest {
  kind: 'message' | 'generate' | 'alternate' | 'continuity_revision'
  path: string
  body: { operation_id: string; [key: string]: unknown }
}

export type Transport = <T>(path: string, body?: unknown) => Promise<T>

// Read the receipt before replaying an uncertain mutation. The replay retains
// exactly the same operation ID and payload, even if the branch has moved on.
export async function recoverRequest<T>(request: SavedRequest, transport: Transport): Promise<T> {
  const receipt = await transport<{ kind: string | null; result: T | null }>(`/operations/${request.body.operation_id}`)
  if (receipt.kind && receipt.kind !== request.kind) throw new Error('This saved action belongs to a different operation.')
  if (receipt.result !== null) return receipt.result
  return transport<T>(request.path, request.body)
}

export function readRecovery<T>(key: string): T | null {
  const value = localStorage.getItem(key)
  if (!value) return null
  const parsed = JSON.parse(value)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('Invalid recovery record.')
  return parsed as T
}

export function writeRecovery<T>(key: string, value: T | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    throw new Error('The recovery record could not be saved on this device. Your text has not been resent. Check browser storage and try again.')
  }
}
