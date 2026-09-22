export type ImportRole = 'skip' | 'user' | 'assistant' | 'narrator' | 'ooc'
export const roleLabels: Record<ImportRole, string> = { skip: 'Keep as reference only', user: 'Character contribution', assistant: 'Story text', narrator: 'Narrator text', ooc: 'Author note' }
export interface TranscriptMessage {
  index: number; speaker: string; source_role: string; timestamp: string
  variants: string[]; protected: boolean; proposed_role: ImportRole
}
export interface TranscriptDuplicate { story_id: string; title: string; receipt_id: string; match: 'exact-source' | 'message-content' }
export interface TranscriptPreview {
  id: string; filename: string; source_sha256: string; format: string
  messages: TranscriptMessage[]; notes: string[]; duplicates: TranscriptDuplicate[]
}
export interface TranscriptChoice { index: number; variant: number; role: ImportRole }
export interface TranscriptResult {
  status: 'imported' | 'skipped'; story_id?: string; branch_id?: string; selected_messages?: number
  duplicates?: TranscriptDuplicate[]
}
