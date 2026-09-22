export interface Cleanup {
  id: string
  attempt: number
  status: 'running' | 'done' | 'skipped' | 'error' | 'cancelled' | 'interrupted' | 'stale'
  selected: 'original' | 'cleaned'
  stale: boolean
  cleaned: string
  output: string
  edits: { start: number; end: number; text: string }[]
  usage: Record<string, unknown>
  error: string
  snapshot: {
    original: string
    original_sha256: string
    algorithm?: string
    passage_count: number
    limited: boolean
    evidence: { start: number; end: number; quote: string; count: number }[]
  }
}

// Detector offsets are Unicode code points; JavaScript strings use UTF-16.
export const originalWords = (text: string, start: number, end: number) => Array.from(text).slice(start, end).join('')

export function draftWording(original: string, cleanup?: Cleanup | null, edited?: { text: string } | null) {
  if (edited) return edited.text
  return cleanup?.selected === 'cleaned' && cleanup.status === 'done' && !cleanup.stale ? cleanup.cleaned : original
}
