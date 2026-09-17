export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

function errorMessage(data: { detail?: unknown }): string {
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).join('; ')
  return 'The request could not be completed. Please try again.'
}

export async function api<T>(path: string, body?: unknown, method?: string, observe?: (stage: 'headers' | 'parsed', serverTiming?: string | null) => void): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json', 'X-Roleplay-Client': 'workspace' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  observe?.('headers', response.headers.get('Server-Timing'))
  const data = await response.json()
  observe?.('parsed')
  if (!response.ok) throw new ApiError(errorMessage(data), response.status)
  return data as T
}

export const operationId = () => crypto.randomUUID()
