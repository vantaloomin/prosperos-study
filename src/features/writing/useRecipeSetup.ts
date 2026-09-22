import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { BranchSummary } from '../../types'
import type { MechanicsContext, RngSettings } from '../mechanics/types'
import type { RecipeOptions } from './recipeEditorTypes'
import { emptyRecipeBeat, type RecipePlanPreview, type RecipeRunBody, type RecipeRunChoices, type RecipeSelection } from './recipeRunTypes'
import { inheritedWriting, type RecipeContent } from './types'
import { useEffectiveWriting } from './useEffectiveWriting'

const initialChoices: RecipeRunChoices = { direction: '', writing: inheritedWriting, profiles: {}, task_switches: {}, review_lenses: null, randomness: null, beat: null }

function chanceSettings(content: RecipeContent | undefined, mechanics: MechanicsContext | undefined, options: RecipeOptions | undefined) {
  if (!mechanics || !options) return null
  return { ...options.randomness_defaults, ...(content?.randomness ?? mechanics.settings) }
}

function runBody(value: RecipeRunChoices, initial: RecipeSelection, revision: number, needsBeat: boolean): RecipeRunBody {
  return { ...value, selection: initial.selection, action: initial.action, target: initial.target.ref,
    expected_version: initial.target.version, expected_revision: revision, beat: needsBeat ? value.beat ?? emptyRecipeBeat : null }
}

function requiresBeat(content: RecipeContent | undefined, settings: RngSettings | null) {
  return content?.purpose === 'draft' && !!settings?.enabled
}

export function useRecipeSetup(initial: RecipeSelection, branch: BranchSummary) {
  const [value, setValue] = usePersistent(`prospero:recipe-options:${branch.id}:${initial.target.version}`, initialChoices)
  const [preview, setPreview] = useState<{ body: RecipeRunBody; report: RecipePlanPreview } | null>(null)
  const action = useAction()
  const writing = useEffectiveWriting(branch.story_id, value.writing)
  const options = useQuery({ queryKey: ['recipe-editor-options'], queryFn: () => api<RecipeOptions>('/writing-recipes/options') })
  const mechanics = useQuery({ queryKey: ['mechanics', branch.id], queryFn: () => api<MechanicsContext>(`/branches/${branch.id}/mechanics`) })
  const effective = chanceSettings(writing.content, mechanics.data, options.data)
  const needsBeat = requiresBeat(writing.content, value.randomness ?? effective)
  const body = runBody(value, initial, branch.revision, needsBeat)
  const prepare = () => action.run(async () => { const report = await api<RecipePlanPreview>(`/branches/${branch.id}/writing-recipes/preview`, body); setPreview({ body, report }) })
  const current = !!preview && JSON.stringify(body) === JSON.stringify(preview.body)
  const changeWriting = (next: RecipeRunChoices['writing']) => setValue({ ...value, writing: next,
    ...(next.recipe !== value.writing.recipe ? { profiles: {}, review_lenses: null } : {}) })
  return { value, setValue, preview, current, action, writing, options, mechanics, effective, needsBeat, prepare, changeWriting }
}
