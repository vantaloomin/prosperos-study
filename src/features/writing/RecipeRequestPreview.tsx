import { SourceMemoryCoverage } from '../workflow/SourceMemoryCoverage'
import { TargetCard } from '../textEdits/EditPresentation'
import { stepLabels } from './recipeEditorTypes'
import type { RecipeGuidance, RecipePlanPreview, RecipeRequest, RecipeSwitches } from './recipeRunTypes'

export function RecipeRequestPreview({ request }: { request: RecipeRequest }) {
  return <article className="recipe-request form-stack"><h4>{request.reader?.lenses?.join(', ') || request.step}</h4><p>{request.profile.name} · {request.profile.config.model} · {request.profile_source} model</p><p className="subtle">Scope: {request.scope}. {request.estimated_input_tokens === null ? 'Input size depends on an earlier result.' : `About ${request.estimated_input_tokens.toLocaleString()} input tokens.`} Input allowance {request.input_allowance.toLocaleString()}; maximum output {request.profile.config.max_output_tokens.toLocaleString()} tokens. Provider cost is unknown.</p>{request.awaiting && <p className="recipe-awaiting">Awaiting: {request.awaiting}. These inputs are not final.</p>}{request.source_memory?.coverage && <SourceMemoryCoverage memory={request.source_memory} />}
    <details><summary>Inspect instructions & {request.awaiting ? 'available' : 'exact'} inputs</summary><div className="form-stack"><h5>Instructions</h5><pre className="recipe-literal" tabIndex={0}>{request.instructions}</pre><h5>Input text</h5><pre className="recipe-literal" tabIndex={0}>{request.content ?? 'Prepared after the preceding step finishes.'}</pre></div></details>
  </article>
}

export function RecipeGuidanceCard({ value }: { value: RecipeGuidance }) {
  return <section className="text-target-card"><h3>{value.recipe.name} · v{value.recipe.number}</h3><p>Style: {value.style ? `${value.style.name} · v${value.style.number}` : 'none'}</p><details><summary>Resolved recipe & style guidance</summary><pre className="recipe-literal" tabIndex={0}>{JSON.stringify({ recipe: value.resolved_recipe, style: value.style?.content ?? null }, null, 2)}</pre></details></section>
}

export function RecipeSwitchPreview({ value }: { value: RecipeSwitches }) {
  return <details><summary>Task inheritance and optional calls</summary><p className="subtle">Workspace disables remain a ceiling. Your explicit run choices override recipe and Story choices. Tasks without a run choice inherit their recipe and Story defaults.</p><dl className="recipe-inheritance">{[['Workspace disabled', value.workspace_disabled.join(', ')], ['Story disabled', value.story_disabled.join(', ')], ['Recipe disabled', value.recipe_disabled.join(', ')], ['Run choices', Object.entries(value.run_switches).map(([key, enabled]) => `${key}: ${enabled ? 'on' : 'off'}`).join(', ')], ['Effective disabled', value.effective_disabled.join(', ')]].map(([label, text]) => <div key={label}><dt>{label}</dt><dd>{text || 'None'}</dd></div>)}</dl></details>
}

export function RecipePlanCard({ preview, busy, onSave }: { preview: RecipePlanPreview; busy: boolean; onSave: () => void }) {
  return <section className="form-stack recipe-plan" aria-label="Complete recipe preview"><h3>Review the complete recipe</h3><TargetCard target={preview.target} /><RecipeGuidanceCard value={preview.writing} /><p>{preview.maximum_calls} planned model request{preview.maximum_calls === 1 ? '' : 's'}. Each step waits for your explicit start.</p><RecipeSwitchPreview value={preview.switches} />
    <ol className="recipe-stages">{preview.plan.map((stage, index) => <li key={index}><h3>{stepLabels[stage.task]}</h3>{stage.skipped ? <p className="subtle">Skipped: {stage.reason}</p> : stage.requests.map(request => <RecipeRequestPreview key={request.step} request={request} />)}</li>)}</ol>
    <p className="subtle">Chance: {preview.chance.applicable ? preview.chance.beat ? 'One result will be recorded when you save this run. Review its exact effect before starting the first model request.' : 'No chance draw for this run.' : 'Inapplicable to reviewing or revising existing wording.'}</p><p className="subtle">{preview.notice}</p><button className="button primary" disabled={busy} onClick={onSave}>{preview.chance.beat ? 'Save run & prepare its chance result' : 'Save this recipe run'}</button><small>Saving starts no model requests and applies no text changes.</small>
  </section>
}
