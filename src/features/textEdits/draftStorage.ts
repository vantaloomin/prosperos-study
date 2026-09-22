import type { DraftCopy, DraftSnapshot, DocumentTarget } from './draftState'
import type { TargetSnapshot } from './types'

const prefix = 'roleplay:text-recovery:'
export function retainedDrafts<T = DocumentTarget, S extends DraftSnapshot = TargetSnapshot>(target: T): DraftCopy<T, S>[] {
  const copies: DraftCopy<T, S>[] = []
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index)
    if (!key?.startsWith(prefix)) continue
    try {
      const copy = JSON.parse(localStorage.getItem(key)!) as DraftCopy<T, S>
      if (matches(copy, target)) copies.push(copy)
    } catch { /* Leave an unreadable recovery copy untouched. */ }
  }
  return copies.sort((a, b) => b.savedAt.localeCompare(a.savedAt))
}
function matches<T, S extends DraftSnapshot>(copy: DraftCopy<T, S>, target: T) {
  const identity = (value: unknown) => value && typeof value === 'object' ? JSON.stringify(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))) : null
  return identity(copy.target) === identity(target) && typeof copy.text === 'string'
}
export const retainDraft = <T, S extends DraftSnapshot>(copy: DraftCopy<T, S>) => localStorage.setItem(prefix + copy.id, JSON.stringify(copy))
export const removeDraft = (id: string) => localStorage.removeItem(prefix + id)

export function legacyText(key: string): string {
  try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? 'null'); return typeof value === 'string' ? value : '' } catch { return '' }
}

// Preserve before removing the old slot. Existing saved text is never replaced
// by an old browser draft; the author can explicitly review this recovery copy.
export function retainLegacy<T>(target: T, key: string, text: string, clear: () => void) {
  if (!text) return
  retainDraft({ id: `legacy:${key}`, target, text, base: null, savedAt: new Date().toISOString() })
  clear()
}
