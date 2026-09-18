import type { CharacterIdentity } from './ControlSources'
import type { Source } from './types'

export type Kind = 'knowledge' | 'conflict' | 'emphasis'
export interface Entry { id: string; kind: Kind; character_id?: string; subject: string; text: string; stance: string; enabled: boolean; sources: Source[] }
export interface State { version_id: string | null; revision: number; entries: Entry[]; unavailable_entries?: Entry[]; characters: CharacterIdentity[] }
export const labels = { knowledge: 'Character knowledge', conflict: 'Conflicting accounts', emphasis: 'Emphasis & recall' }
export const states = {
  knowledge: [['knows', 'Knows'], ['believes', 'Believes'], ['unaware', 'Does not know'], ['uncertain', 'Uncertain']],
  conflict: [['unresolved', 'Needs review'], ['intentional', 'Intentional ambiguity'], ['resolved', 'Author resolution']],
  emphasis: [['pin', 'Keep this evidence'], ['exclude', 'Exclude from optional recall'], ['motif', 'Echo this motif'], ['avoid', 'Avoid this wording']],
}
