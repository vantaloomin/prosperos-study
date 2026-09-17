import { capture, loadPosition, restore, type ReadingPosition } from './readingPosition.ts'

/** Observe only mounted passages; the virtual list owns item-height measurement. */
export class VirtualReadingPosition {
  private position: ReadingPosition | null
  private locked = true
  private frame = 0
  private readyFrame = 0
  private resize: ResizeObserver
  private mutations: MutationObserver
  private width = 0
  private height = 0
  private disposed = false
  private element: HTMLElement
  private branchId: string
  private lastMessageId: string
  private requestTarget?: (position: ReadingPosition | null) => void

  constructor(element: HTMLElement, branchId: string, lastMessageId: string, hasAnchor?: (block: string) => boolean, requestTarget?: (position: ReadingPosition | null) => void) {
    this.element = element
    this.branchId = branchId
    this.lastMessageId = lastMessageId
    this.requestTarget = requestTarget
    this.position = loadPosition(branchId)
    if (this.position?.block && hasAnchor && !hasAnchor(this.position.block)) this.position = { ...this.position, block: null }
    this.resize = new ResizeObserver(this.onResize)
    this.mutations = new MutationObserver(this.refresh)
    this.resize.observe(element)
    this.mutations.observe(element, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] })
    element.addEventListener('scroll', this.refresh, { passive: true })
    element.addEventListener('wheel', this.unlock, { passive: true })
    element.addEventListener('pointerdown', this.unlock, { passive: true })
    element.addEventListener('touchstart', this.unlock, { passive: true })
    element.addEventListener('keydown', this.onKey)
    window.addEventListener('pagehide', this.save)
    this.refresh()
  }

  refresh = () => {
    if (this.disposed) return
    this.invalidate()
    if (!this.frame) this.frame = requestAnimationFrame(this.reconcile)
  }

  seek = (position: ReadingPosition | null, lastMessageId = this.lastMessageId) => {
    this.position = position
    this.lastMessageId = lastMessageId
    this.locked = true
    this.element.dataset.transcriptReady = 'false'
    this.refresh()
  }

  private unlock = () => { this.locked = false }

  private onKey = (event: KeyboardEvent) => {
    if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', 'Tab'].includes(event.key)) this.unlock()
  }

  private onResize = () => {
    if (this.width === this.element.clientWidth && this.height === this.element.clientHeight) return
    this.width = this.element.clientWidth
    this.height = this.element.clientHeight
    this.locked = true
    this.refresh()
  }

  private reconcile = () => {
    this.frame = 0
    const messages = Array.from(this.element.querySelectorAll<HTMLElement>('.message'))
    if (!messages.length) { this.mountTarget(); return }
    if (this.locked) {
      if (!this.restoreMounted()) return
    } else if (this.hasVisiblePassage(messages)) {
      this.position = capture(this.element, messages)
    }
    this.save()
    this.markReady()
  }

  private hasVisiblePassage(messages = Array.from(this.element.querySelectorAll<HTMLElement>('.message'))) {
    const top = this.element.getBoundingClientRect().top
    return messages.some((message) => {
      const rect = message.getBoundingClientRect()
      return rect.bottom > top && rect.top < top + this.element.clientHeight
        && getComputedStyle(message).visibility === 'visible'
    })
  }

  private restoreMounted() {
    const anchors = Array.from(this.element.querySelectorAll<HTMLElement>('[data-reading-anchor]'))
    const byId = new Map(anchors.map((item) => [item.dataset.readingAnchor!, item]))
    const target = this.position?.block
    if (target && !this.position?.atEnd && !byId.has(target)) return this.mountTarget()
    if ((!this.position || this.position.atEnd) && !byId.has(`${this.lastMessageId}:header`)) return this.mountTarget()
    restore(this.element, byId, this.position)
    return true
  }

  private invalidate() {
    cancelAnimationFrame(this.readyFrame)
    this.element.dataset.transcriptReady = 'false'
  }

  private mountTarget() {
    this.invalidate()
    if (this.locked) this.requestTarget?.(this.position)
    return false
  }

  private markReady = () => {
    cancelAnimationFrame(this.readyFrame)
    this.readyFrame = requestAnimationFrame(() => {
      if (this.disposed) return
      // Initial positioning can finish after the last size or DOM notification.
      if (this.hasVisiblePassage()) {
        this.element.dataset.transcriptReady = 'true'
        this.element.dataset.readingTarget = this.position?.block ?? 'end'
      } else {
        this.refresh()
      }
    })
  }

  private save = () => {
    try { sessionStorage.setItem(`reading:${this.branchId}`, JSON.stringify(this.position)) }
    catch { /* The current passage remains usable without browser storage. */ }
  }

  dispose = () => {
    this.save()
    this.disposed = true
    cancelAnimationFrame(this.frame)
    cancelAnimationFrame(this.readyFrame)
    this.resize.disconnect()
    this.mutations.disconnect()
    this.element.removeEventListener('scroll', this.refresh)
    this.element.removeEventListener('wheel', this.unlock)
    this.element.removeEventListener('pointerdown', this.unlock)
    this.element.removeEventListener('touchstart', this.unlock)
    this.element.removeEventListener('keydown', this.onKey)
    window.removeEventListener('pagehide', this.save)
  }
}
