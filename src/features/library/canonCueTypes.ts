export interface CanonCue { start: number; end: number; sha256: string; summary: string; topics: string[]; aliases: string[] }
export interface CanonPolicy { mode?: 'full' | 'relevant'; cues?: CanonCue[] }
export interface CueFields { summary: string; topics: string[]; aliases: string[] }
export interface CueSource { origin: 'draft' | 'published'; version: number | null; text: string; offset: number; end: number; length: number; next_offset: number | null }
export interface CueRow { id: string; number: number; cue: CanonCue; status: 'active' | 'stale'; source: CueSource | null }
export interface CueReport { fingerprint: string; total: number; active: number; stale: number; matches: number; offset: number; next_offset: number | null; items: CueRow[] }
export interface CueFilter { query: string; status: 'all' | 'active' | 'stale'; offset: number }
