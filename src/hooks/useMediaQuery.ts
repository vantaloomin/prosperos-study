import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string) {
  const subscribe = (callback: () => void) => {
    const media = window.matchMedia(query)
    media.addEventListener('change', callback)
    return () => media.removeEventListener('change', callback)
  }
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches)
}
