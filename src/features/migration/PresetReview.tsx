import { useEffect, useRef, useState, type RefObject } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Field } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { ProfileList } from '../models/types'
import type { WritingResource } from '../writing/types'
import { PresetDownloads } from './PresetDownloads'
import { PresetDestination, PresetInstructions, PresetSampling } from './PresetFields'
import type { ConfigurationProposal, PresetDraft, PresetPreview, PresetResult } from './presetTypes'
import { showValue } from './presetTypes'

export function PresetReview({ preview, publishChoices, hasBatchDuplicate = false, draftKey }: { preview: PresetPreview; publishChoices?: (choices: object) => Promise<PresetResult>; hasBatchDuplicate?: boolean; draftKey?: string }) {
  const [draft, setDraft] = usePersistent<PresetDraft>(draftKey ?? `roleplay:preset-review:${preview.id}`, {
    operation: operationId(), name: preview.name, instructions: '', instruction_keys: [], sampling_keys: [],
    base_profile_id: null, expected_profile_version_id: null, target_asset_id: null, expected_version_id: null, duplicate_action: 'skip', reviewed: false,
  })
  const [result, setResult] = useState<PresetResult | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [preview.id, result])
  const options = usePresetOptions(preview.id, draft)
  const action = useAction()
  const patch = (change: Partial<PresetDraft>) => setDraft({ ...draft, ...change, operation: operationId(), reviewed: false })
  const publish = () => action.run(async () => {
    const { operation, ...choices } = draft
    const send = publishChoices ?? ((body: object) => api<PresetResult>(`/migration/presets/${preview.id}/publish`, body))
    setResult(await send({ ...choices, operation_id: operation, source_sha256: preview.source_sha256 }))
  })
  if (result) return <PresetSaved result={result} id={preview.id} heading={heading} onAgain={() => { patch({}); setResult(null) }} />
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>{preview.filename}</h3><p className="subtle">{preview.format} · Inactive proposals</p><PresetDownloads id={preview.id} />
    <details className="import-compatibility" open><summary>Preset compatibility</summary><ul>{preview.notes.map(note => <li key={note}>{note}</li>)}</ul><p>The original source is retained in private workspace archives. Portable recipe bundles contain the reviewed instructions and sampling proposals, without the original file or foreign connection values.</p><details><summary>Source fields for reference</summary><p className="migration-prose">{preview.source_fields.join(', ')}</p><p className="migration-prose">{preview.parameter_fields.join(', ')}</p></details></details>
    <fieldset className="migration-review-fields form-stack" disabled={action.busy}><legend>Review preset choices</legend><Field label="Imported recipe name" maxLength={120} value={draft.name} onChange={event => patch({ name: event.target.value })} />
      <PresetInstructions preview={preview} draft={draft} patch={patch} /><PresetSampling preview={preview} draft={draft} patch={patch} profiles={options.profiles} />
      <ConfigurationPreview draft={draft} query={options.configuration} />
      <PresetDestination preview={preview} draft={draft} patch={patch} recipes={options.recipes} hasBatchDuplicate={hasBatchDuplicate} />
      <label className="check-row"><input type="checkbox" checked={draft.reviewed} onChange={event => setDraft({ ...draft, reviewed: event.target.checked })} />I reviewed the recipe text, sampling changes, destination and compatibility losses.</label>
    </fieldset><ErrorNotice message={action.error || options.error} /><PublishButton draft={draft} ready={options.ready} busy={action.busy} onPublish={publish} />
  </section>
}

function usePresetOptions(id: string, draft: PresetDraft) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles') })
  const resources = useQuery({ queryKey: ['writing-resources'], queryFn: () => api<WritingResource[]>('/writing-resources?include_archived=true') })
  const selection = { sampling_keys: draft.sampling_keys, base_profile_id: draft.base_profile_id, expected_profile_version_id: draft.expected_profile_version_id }
  const configuration = useQuery({ queryKey: ['preset-configuration', id, selection], queryFn: () => api<ConfigurationProposal>(`/migration/presets/${id}/configuration-preview`, selection), enabled: !!draft.sampling_keys.length && !!draft.base_profile_id, retry: false })
  const ready = !draft.sampling_keys.length || configuration.isSuccess
  return { configuration, ready, profiles: profiles.data?.profiles ?? [], recipes: availableRecipes(resources.data), error: profiles.error?.message || resources.error?.message }
}

function availableRecipes(resources?: WritingResource[]) {
  return (resources ?? []).filter(item => item.kind === 'recipe' && !item.archived)
}

function ConfigurationPreview({ draft, query }: { draft: PresetDraft; query: ReturnType<typeof usePresetOptions>['configuration'] }) {
  if (!draft.sampling_keys.length || !draft.base_profile_id) return null
  return <section className="import-compatibility"><h4>Profile copy preview</h4>{query.isFetching && <Loading label="Checking local profile capabilities…" />}<ErrorNotice message={query.error?.message} />{query.data && <><p>Based on {query.data.base_name}</p><ul>{query.data.changes.map(item => <li key={item.field}>{item.field}: {showValue(item.before)} → {showValue(item.after)}</li>)}</ul></>}</section>
}

function PublishButton({ draft, ready, busy, onPublish }: { draft: PresetDraft; ready: boolean; busy: boolean; onPublish: () => void }) {
  return <button className="button primary" disabled={!ready || !draft.reviewed || !draft.name.trim() || busy} onClick={onPublish}>{busy ? 'Publishing…' : draft.target_asset_id ? 'Publish reviewed recipe version' : 'Publish reviewed recipe'}</button>
}

function PresetSaved({ result, id, heading, onAgain }: { result: PresetResult; id: string; heading: RefObject<HTMLHeadingElement | null>; onAgain: () => void }) {
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>{result.status === 'imported' ? 'Your reviewed recipe is saved' : 'Duplicate left unchanged'}</h3><p>{result.activation || 'This source or equivalent proposals already belong to a recipe. No new recipe or model profile was created.'}</p>{result.resource && <p>{result.resource.name} · v{result.resource.number} · Find it in Library → Styles & recipes → Writing recipes.</p>}{result.profile && <p>Profile copy: {result.profile.name}. Review it in Settings → Models and add credentials if needed.</p>}<PresetDownloads id={id} /><button className="button" onClick={onAgain}>Review preset again</button></section>
}
