export interface PhraseEvidence {
  node_id: string; passage: number; role: string; start: number; end: number
  quote: string; before: string; after: string; more_before: boolean; more_after: boolean; sha256: string
}

export interface PhraseFinding {
  id: string; phrase_id: string; phrase: string; words: number; count: number
  passage_count: number; evidence: PhraseEvidence[]; omitted_evidence: number
}

export type PhraseScope = 'recent' | 'extended' | 'path'
export interface PhraseReport {
  algorithm: string; branch_id: string; revision: number; head_id: string | null
  scope: PhraseScope; minimum: number; passage_count: number; characters: number; word_count: number
  limited: boolean; character_limit: number; word_limit: number
  findings: PhraseFinding[]; more_findings: boolean
}

export interface PhraseChoice { id: string; phrase: string }
export interface PhrasePreferences { version: 1; enabled: boolean; dismissed: PhraseChoice[]; intentional: PhraseChoice[] }
