import type { TargetSnapshot, TextTarget } from './types'

export type DocumentTarget = Extract<TextTarget, { kind: 'document' }>
export interface DraftSnapshot { text: string; version: string; basis: { revision: number }; limit: number }
export interface DraftCopy<T = DocumentTarget, S extends DraftSnapshot = TargetSnapshot> { id: string; target: T; text: string; base: S | null; savedAt: string }
export interface DraftState<T = DocumentTarget, S extends DraftSnapshot = TargetSnapshot> {
  text: string; base: S | null; remote: S | null
  phase: 'loading' | 'ready' | 'saving' | 'conflict' | 'offline'
  dirty: boolean; error: string; copies: DraftCopy<T, S>[]
}
export interface DraftIO<T = DocumentTarget, S extends DraftSnapshot = TargetSnapshot> {
  read: () => Promise<S>
  write: (base: S, text: string) => Promise<S>
  retain: (copy: DraftCopy<T, S>) => void
  remove: (id: string) => void
  copies: () => DraftCopy<T, S>[]
}

// A per-view working copy. Server versions arbitrate writers; local copies retain
// keystrokes through unmounts, reloads and failed requests, without sharing owners.
export class DraftController<T = DocumentTarget, S extends DraftSnapshot = TargetSnapshot> {
  readonly target: T
  private io: DraftIO<T, S>
  private id: string
  private imported: DraftCopy<T, S> | null = null
  private listeners = new Set<() => void>()
  private queue: Promise<unknown> = Promise.resolve()
  private refreshing: Promise<void> | null = null
  private state: DraftState<T, S> = { text: '', base: null, remote: null, phase: 'loading', dirty: false, error: '', copies: [] }

  constructor(target: T, io: DraftIO<T, S>, id: string) { this.target = target; this.io = io; this.id = id }
  getState = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private update(value: Partial<DraftState<T, S>>) { this.state = { ...this.state, ...value }; this.listeners.forEach(listener => listener()) }
  private serial<T>(work: () => Promise<T>): Promise<T> {
    const next = this.queue.then(work, work)
    this.queue = next.catch(() => {})
    return next
  }
  private retain() {
    this.io.retain({ id: this.id, target: this.target, text: this.state.text, base: this.state.base, savedAt: new Date().toISOString() })
  }
  private clean(current: S) {
    this.io.remove(this.id)
    if (this.imported?.text === current.text) { this.io.remove(this.imported.id); this.imported = null }
    this.update({ base: current, remote: null, text: current.text, dirty: false, phase: 'ready', error: '' })
  }
  private receive(current: S) {
    if (!this.state.dirty || this.state.text === current.text) { this.clean(current); return }
    if (this.state.base?.version === current.version) { this.update({ phase: 'ready', remote: null, error: '' }); return }
    this.update({ remote: current, phase: 'conflict', error: '' })
  }
  edit = (text: string) => {
    this.update({ text, dirty: true })
    try { this.retain() } catch { this.update({ error: 'Browser recovery storage is unavailable. Keep this view open until the draft is saved.' }) }
  }
  refresh = () => {
    if (this.refreshing) return this.refreshing
    this.refreshing = this.serial(async () => {
      try {
        this.receive(await this.io.read())
        this.update({ copies: this.io.copies().filter(copy => copy.id !== this.id) })
      } catch (error) { this.update({ phase: 'offline', error: error instanceof Error ? error.message : 'The saved draft is unavailable.' }) }
    }).finally(() => { this.refreshing = null })
    return this.refreshing
  }
  importLegacy = () => {
    const copies = this.state.copies.filter(copy => copy.id.startsWith('legacy:'))
    if (this.state.dirty || this.state.base?.basis.revision !== 0 || copies.length !== 1) return
    this.imported = copies[0]
    this.edit(copies[0].text)
  }
  flush = () => this.serial(async () => {
    // Re-read even clean drafts before acting, so an unseen remote change cannot
    // cause submission or a proposal against an unintended text version.
    const visible = this.state.text
    const prior = this.state.base?.version
    try {
      this.receive(await this.io.read())
      if (this.state.phase === 'conflict') throw new Error('Review both draft versions before continuing.')
      if (prior && visible !== this.state.text) throw new Error('The saved draft changed in another view. Review its current text before continuing.')
      while (this.state.dirty) await this.saveCurrent()
      return this.state.base!
    } catch (error) {
      await this.reconcileFailure(error)
      throw error
    }
  })
  private async saveCurrent() {
    const base = this.state.base!
    const text = this.state.text
    this.update({ phase: 'saving' })
    const result = await this.io.write(base, text)
    // New typing during the request remains a distinct unsaved working copy.
    if (this.state.text === text) this.clean(result)
    else { this.update({ base: result, phase: 'ready' }); this.retain() }
  }
  private async reconcileFailure(error: unknown) {
    try { this.receive(await this.io.read()) }
    catch { this.update({ phase: 'offline' }) }
    this.update({ error: error instanceof Error ? error.message : 'The draft could not be saved.' })
  }
  reviewLocal = (id: string) => {
    const copy = this.io.copies().find(item => item.id === id)
    if (!copy || !this.state.base) return
    // Keep the source copy, including one still being edited in another window.
    const remote = this.state.remote ?? this.state.base
    this.update({ text: copy.text, base: copy.base, dirty: true, remote, phase: 'conflict', error: '' })
    try { this.retain() } catch { this.update({ error: 'This recovery copy could not be retained in this view.' }) }
  }
  discardCopy = (id: string) => { this.io.remove(id); this.update({ copies: this.io.copies().filter(copy => copy.id !== this.id) }) }
  useRemote = () => { if (this.state.remote) this.clean(this.state.remote) }
  saveReviewed = () => {
    if (!this.state.remote) return Promise.resolve()
    this.update({ base: this.state.remote, remote: null, phase: 'ready', dirty: true, error: '' })
    this.retain()
    return this.flush().then(() => {})
  }
}
