export interface ReadingPosition {
  block: string | null
  offset: number
  fraction: number
  pixels: number
  atEnd: boolean
}

function isPosition(value: Partial<ReadingPosition> | null): value is ReadingPosition {
  if (!value || typeof value !== 'object') return false
  const validBlock = value.block === null || typeof value.block === 'string'
  return validBlock && typeof value.atEnd === 'boolean'
    && [value.offset, value.fraction, value.pixels].every(Number.isFinite)
}

export function loadPosition(branchId: string): ReadingPosition | null {
  try {
    const saved = sessionStorage.getItem(`reading:${branchId}`)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (isPosition(parsed)) return parsed
    }
    const legacy = sessionStorage.getItem(`scroll:${branchId}`)
    if (legacy === null || !Number.isFinite(Number(legacy))) return null
    return { block: null, offset: 0, fraction: 0, pixels: Number(legacy), atEnd: false }
  } catch { return null }
}

function firstVisible(blocks: HTMLElement[], top: number) {
  let low = 0
  let high = blocks.length
  while (low < high) {
    const middle = Math.floor((low + high) / 2)
    if (blocks[middle].getBoundingClientRect().bottom <= top) low = middle + 1
    else high = middle
  }
  return blocks[low]
}

export function capture(element: HTMLElement, messages: HTMLElement[]): ReadingPosition {
  const top = element.getBoundingClientRect().top
  // Read contained message bounds first; probing offscreen paragraphs would force their layout.
  const message = firstVisible(messages, top)
  const blocks = Array.from(message?.querySelectorAll<HTMLElement>('[data-reading-anchor]') ?? [])
  const block = firstVisible(blocks, top)
  const rect = block?.getBoundingClientRect()
  const offset = rect ? top - rect.top : 0
  return {
    block: block?.dataset.readingAnchor ?? null,
    offset,
    fraction: rect ? Math.max(0, offset) / Math.max(1, rect.height) : 0,
    pixels: element.scrollTop,
    atEnd: element.scrollHeight - element.scrollTop - element.clientHeight < 80,
  }
}

export function restore(element: HTMLElement, blocks: Map<string, HTMLElement>, position: ReadingPosition | null) {
  if (!position || position.atEnd) { element.scrollTop = element.scrollHeight; return }
  const block = blocks.get(position.block ?? '')
  if (!block) { element.scrollTop = position.pixels; return }
  const rect = block.getBoundingClientRect()
  const offset = position.offset < 0 ? position.offset : position.fraction * rect.height
  element.scrollTop += rect.top - element.getBoundingClientRect().top + offset
}

/** Keep branch-local passage anchors without rerendering React during scrolling. */
export class TranscriptPosition {
  private blocks: HTMLElement[] = []
  private byId = new Map<string, HTMLElement>()
  private position: ReadingPosition | null
  private frame = 0
  private restoredPixels: number | null = null
  private observer: ResizeObserver
  private column: Element | null = null
  private element: HTMLElement
  private branchId: string

  constructor(element: HTMLElement, branchId: string) {
    this.element = element
    this.branchId = branchId
    this.position = loadPosition(branchId)
    this.observer = new ResizeObserver(this.restorePosition)
    this.observer.observe(element)
    this.refresh()
    element.addEventListener('scroll', this.onScroll, { passive: true })
    window.addEventListener('pagehide', this.save)
  }

  refresh = () => {
    if (this.column) this.observer.unobserve(this.column)
    this.column = this.element.firstElementChild
    if (this.column) this.observer.observe(this.column)
    this.blocks = Array.from(this.element.querySelectorAll<HTMLElement>('.message'))
    const anchors = Array.from(this.element.querySelectorAll<HTMLElement>('[data-reading-anchor]'))
    this.byId = new Map(anchors.map((block) => [block.dataset.readingAnchor!, block]))
    this.restorePosition()
  }

  private restorePosition = () => {
    restore(this.element, this.byId, this.position)
    this.restoredPixels = this.element.scrollTop
  }

  private onScroll = () => {
    // Layout and our own restoration emit scroll events too. Preserve the saved
    // passage while contained messages expand; only a different scroll adopts it.
    if (this.restoredPixels !== null && Math.abs(this.element.scrollTop - this.restoredPixels) < 1) return
    this.restoredPixels = null
    this.position = capture(this.element, this.blocks)
    if (!this.frame) this.frame = requestAnimationFrame(this.save)
  }

  private save = () => {
    cancelAnimationFrame(this.frame)
    this.frame = 0
    try { sessionStorage.setItem(`reading:${this.branchId}`, JSON.stringify(this.position)) }
    catch { /* Reading still works when browser storage is unavailable. */ }
  }

  dispose = () => {
    this.save()
    this.observer.disconnect()
    this.element.removeEventListener('scroll', this.onScroll)
    window.removeEventListener('pagehide', this.save)
  }
}
