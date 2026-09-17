import { useRef, useState } from 'react'
import { freshSetup, restoreSetup, type SetupDraft } from './setup'

const storageKey = 'roleplay:onboarding'
function readSetup() {
  try {
    const stored = localStorage.getItem(storageKey)
    return stored ? restoreSetup(JSON.parse(stored)) : freshSetup()
  } catch { return freshSetup() }
}

export function useSetupDraft() {
  const [draft, setDraft] = useState(readSetup)
  const current = useRef(draft)
  const [storageError, setStorageError] = useState('')
  const update = (next: SetupDraft) => {
    current.current = next
    setDraft(next)
    try { localStorage.setItem(storageKey, JSON.stringify(next)); setStorageError('') }
    catch { setStorageError('This browser could not save the unfinished setup. Keep this window open until your Story is created.') }
  }
  const patch = (change: Partial<SetupDraft>) => update({ ...current.current, ...change })
  return { draft, patch, reset: () => update(freshSetup()), storageError }
}
