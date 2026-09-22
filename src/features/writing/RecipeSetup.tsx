import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import type { BranchSummary } from '../../types'
import type { RngSettings } from '../mechanics/types'
import { TargetCard } from '../textEdits/EditPresentation'
import { RecipeBeat } from './RecipeBeat'
import { RecipePlanCard } from './RecipeRequestPreview'
import { RecipeRunOptions } from './RecipeRunOptions'
import { RecipeRandomness } from './RecipeSettings'
import { RequestWritingChoices } from './RequestWritingChoices'
import { purposeHints } from './recipeEditorTypes'
import { emptyRecipeBeat, type RecipePlanPreview, type RecipeRunBody, type RecipeSelection } from './recipeRunTypes'
import { useRecipeSetup } from './useRecipeSetup'

type Setup = ReturnType<typeof useRecipeSetup>
export function RecipeSetup({ initial, branch, busy, onSave }: { initial: RecipeSelection; branch: BranchSummary; busy: boolean; onSave: (body: RecipeRunBody, preview: RecipePlanPreview) => void }) {
  const setup = useRecipeSetup(initial, branch)
  const { value, setValue, writing, preview, current, action } = setup
  return <div className="form-stack"><TargetCard target={initial.target} /><p>Action: {initial.action.replaceAll('-', ' ')} · selected range {initial.selection.start}–{initial.selection.end}</p><pre className="recipe-selection" tabIndex={0}>{initial.selection.text || '(insertion point)'}</pre>
    <RequestWritingChoices storyId={branch.story_id} value={value.writing} onChange={setup.changeWriting} recipePurpose="all" expanded />{writing.content && <p>{purposeHints[writing.content.purpose]}</p>}<TextField label="Direction for this recipe run" rows={4} maxLength={30000} value={value.direction} onChange={event => setValue({ ...value, direction: event.target.value })} hint="Describe what to draft, preserve or improve. Your selected text remains the destination." />
    <RecipeSetupOptions setup={setup} scene={initial.target.ref.kind === 'scene-block'} /><RecipeSetupFeedback setup={setup} />
    <button className="button" disabled={busy || action.busy || !writing.content || !setup.effective} onClick={() => void setup.prepare()}>Preview complete recipe</button>{preview && <RecipePreviewState preview={preview} current={current} busy={busy} onSave={onSave} />}
  </div>
}

function RecipeSetupOptions({ setup, scene }: { setup: Setup; scene: boolean }) {
  const { value, setValue, writing, options, mechanics, effective, needsBeat } = setup
  return <>{options.data && <RecipeRunOptions value={value} content={writing.content} options={options.data} scene={scene} onChange={setValue} />}
    {effective && <details className="advanced-settings"><summary>Chance for this run</summary><div className="form-stack"><RecipeRandomness run value={value.randomness as unknown as Record<string, unknown> | null} defaults={effective} onChange={randomness => setValue({ ...value, randomness: randomness as unknown as RngSettings | null })} /></div></details>}
    {needsBeat && <RecipeBeat value={value.beat ?? emptyRecipeBeat} tables={mechanics.data?.tables ?? []} onChange={beat => setValue({ ...value, beat })} />}</>
}

function RecipeSetupFeedback({ setup }: { setup: Setup }) {
  const { options, mechanics, writing, action } = setup
  const error = [options.error?.message, mechanics.error?.message, writing.error, action.error].find(Boolean)
  return <>{(options.isPending || mechanics.isPending) && <Loading label="Reading the effective recipe settings…" />}<ErrorNotice message={error} /></>
}

function RecipePreviewState({ preview, current, busy, onSave }: { preview: NonNullable<Setup['preview']>; current: boolean; busy: boolean; onSave: (body: RecipeRunBody, preview: RecipePlanPreview) => void }) {
  if (!current) return <p role="status">Your choices changed. Preview the complete recipe again before saving.</p>
  return <RecipePlanCard preview={preview.report} busy={busy} onSave={() => onSave(preview.body, preview.report)} />
}
