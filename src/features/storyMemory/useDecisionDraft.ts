import { useEffect, useRef, useState } from 'react'
import { operationId } from '../../api'
import { draftKey, type DecisionDraft, type DraftScope } from './decisionDraft'
import { readDraft, writeDraft } from './decisionDraftStorage'

const storage = {
  getItem: (key: string) => localStorage.getItem(key),
  setItem: (key: string, value: string) => localStorage.setItem(key, value),
  removeItem: (key: string) => localStorage.removeItem(key),
}

export function useDecisionDraft(scope: DraftScope) {
  const [initial] = useState(() => readDraft(storage, scope))
  const [value, setValue] = useState(initial.value)
  const [error, setError] = useState(initial.error)
  const [unreadable, setUnreadable] = useState(!!initial.error)
  const [recovered, setRecovered] = useState(!!initial.value)
  const current = useRef(value), raw = useRef(initial.raw), blocked = useRef(!!initial.error), alive = useRef(true)
  const key = draftKey(scope)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const report = (message: string) => { if (alive.current) { setError(message); if (!message) setUnreadable(false) } }
  const persist = (next: DecisionDraft | null) => {
    try {
      if (blocked.current && next) throw new Error(initial.error)
      raw.current = writeDraft(storage, key, raw.current, next)
      blocked.current = false
      report('')
    } catch (failure) { report(storageMessage(failure)) }
  }
  const store = (next: DecisionDraft | null, expectedStamp?: string): DecisionDraft | null => {
    if (!alive.current && !expectedStamp) return current.current
    if (!matchesStamp(current.current, expectedStamp)) return current.current
    const stamped = next ? { ...next, stamp: operationId() } : null
    current.current = stamped
    if (alive.current) { setValue(stamped); setRecovered(false) }
    persist(stamped)
    return stamped
  }
  const download = () => {
    const payload = current.current ? JSON.stringify(current.current, null, 2) : raw.current ?? ''
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = 'prospero-author-decisions-draft.json'; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return { value, store, error, recovered, download, unreadable }
}

function storageMessage(failure: unknown) {
  if (failure instanceof Error && failure.message.startsWith('Another view')) return failure.message
  return 'The recovery copy could not be saved on this device. Keep this view open and download your draft, or save the decisions to the Story before leaving.'
}

function matchesStamp(draft: DecisionDraft | null, expected?: string) { return !expected || draft?.stamp === expected }
