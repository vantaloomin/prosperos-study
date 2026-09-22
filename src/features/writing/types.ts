export type WritingKind = 'style' | 'recipe'
export interface StyleContent {
  prose: string; viewpoint: string; tense: string; dialogue: string; rhythm: string; description: string; avoid: string
  examples: { label: string; text: string }[]
}
export interface RecipeVariable {
  name: string; label: string; description?: string; example?: string; type?: 'text' | 'number' | 'choice'
  required?: boolean; choices?: string[]; default?: string | number | null
}
export interface RecipeContent {
  purpose: 'draft' | 'review' | 'revise'; instructions: string; style: string; variables: RecipeVariable[]
  steps: { task: 'writer' | 'review' | 'revision'; instructions?: string; profile_id?: string | null; lenses?: string[] }[]
  disabled_tasks: string[]; randomness: Record<string, unknown> | null
}
export interface WritingResource {
  id: string; asset_id: string; number: number; kind: WritingKind; name: string; description: string
  content: StyleContent | RecipeContent; note: string; archived: number; revision: number
  unsupported: Record<string, unknown>
}
export interface WritingDraft { kind: WritingKind; name: string; description: string; content: StyleContent | RecipeContent; note: string; unsupported: Record<string, unknown> }
export interface Starter { key: string; name: string; description: string; content: RecipeContent }
export interface WritingChoices { style: string; recipe: string; variables: Record<string, string | number> }
export interface WritingPins { story_revision: number; style: string; recipe: string }
export const inheritedWriting: WritingChoices = { style: 'inherit', recipe: 'inherit', variables: {} }
export const emptyStyle: StyleContent = { prose: '', viewpoint: '', tense: '', dialogue: '', rhythm: '', description: '', avoid: '', examples: [] }
export const emptyRecipe: RecipeContent = { purpose: 'draft', instructions: '', style: 'inherit', variables: [], steps: [], disabled_tasks: [], randomness: null }

export function newWritingDraft(kind: WritingKind, source?: WritingResource | Starter): WritingDraft {
  return { kind, name: source?.name ?? '', description: source?.description ?? '', note: '', unsupported: source && 'unsupported' in source ? structuredClone(source.unsupported) : {},
    content: structuredClone(source?.content ?? (kind === 'style' ? emptyStyle : emptyRecipe)) }
}
