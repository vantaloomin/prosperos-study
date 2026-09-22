import { useState } from 'react'
import { api } from '../../api'
import type { RequestPreview } from './SideRequestPreview'

export function useSidePreview(key: string) {
  const [saved, setSaved] = useState<{ key: string; value: RequestPreview }>()
  const [open, setOpen] = useState(false)
  const current = saved?.key === key
  const load = async (threadId: string, body: object) => {
    const value = await api<RequestPreview>(`/side-conversations/${threadId}/preview`, body)
    setSaved({ key, value })
    setOpen(true)
  }
  return { value: saved?.value, open, current, fingerprint: current ? saved?.value.fingerprint : undefined, load, close: () => setOpen(false) }
}
