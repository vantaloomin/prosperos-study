import type { AssetContent } from '../../types'
import type { AssetDraft } from '../library/versionChanges'
import type { EditorProps, Run, Target } from './types'

const characterFields = { voice: 'Voice & manner', behavior_rules: 'Behavior & boundaries', scenario: 'Scenario', example_dialogue: 'Example dialogue', author_notes: 'Editor notes' }

export function ownsRun(run: Run, editor: EditorProps): boolean {
  const owner = run.asset_id ? run.asset_id === editor.asset?.asset_id : !editor.asset && run.snapshot.draft_id === editor.draftId
  return owner && (run.snapshot.kind === 'persona' ? 'character' : run.snapshot.kind) === editor.draft.kind
}

export function proseTargets(draft: AssetDraft): Target[] {
  const overview = { key: 'text', label: { character: 'Character & background', lorebook: 'Canon overview', persona: 'Character & background' }[draft.kind], text: draft.content.text ?? '' }
  if (draft.kind === 'lorebook') return [overview, ...(draft.content.lore_definition?.entries ?? []).map((entry) => ({ key: `entry:${entry.id}`, label: `Entry · ${entry.title}`, text: entry.text }))]
  return [overview, ...Object.entries(characterFields).map(([key, label]) => ({ key, label, text: String(draft.content[key] ?? '') })),
    ...(draft.content.greetings ?? []).map((entry) => ({ key: `greeting:${entry.id}`, label: `Opening · ${entry.label}`, text: entry.text }))]
}

export function replaceProse(draft: AssetDraft, key: string, expected: string, proposal: string): AssetDraft {
  const target = proseTargets(draft).find((item) => item.key === key)
  if (!target || target.text !== expected) throw new Error('This field changed after the proposal was prepared. Review its current text and make a new request; your edits are preserved.')
  return { ...draft, content: updateContent(draft.content, key, proposal) }
}

function updateContent(content: AssetContent, key: string, text: string): AssetContent {
  if (key.startsWith('entry:') && content.lore_definition) return { ...content, lore_definition: { ...content.lore_definition, entries: content.lore_definition.entries.map((item) => item.id === key.slice(6) ? { ...item, text } : item) } }
  if (key.startsWith('greeting:')) return { ...content, greetings: content.greetings?.map((item) => item.id === key.slice(9) ? { ...item, text } : item) }
  return { ...content, [key]: text }
}
