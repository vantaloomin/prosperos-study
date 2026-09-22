import type { ModelProfile } from '../models/types'
import { TextField } from '../../components/Fields'
import type { WritingResource } from '../writing/types'
import type { PresetDraft, PresetPreview } from './presetTypes'
import { showValue } from './presetTypes'

type Props = { preview: PresetPreview; draft: PresetDraft; patch: (change: Partial<PresetDraft>) => void }
const toggled = (items: string[], key: string, checked: boolean) => checked ? [...items, key] : items.filter(item => item !== key)

export function PresetInstructions({ preview, draft, patch }: Props) {
  return <section className="form-stack"><h4>Instruction proposals</h4><p className="subtle">Choose source fragments, then place them into the editable recipe below. Foreign roles, order and enable switches are not reproduced. Double-brace macros are retained as literal text.</p>
    {preview.instructions.map(item => <details key={item.key}><summary>{item.label}{!item.supported && ' · too long for a native recipe'}</summary><pre className="migration-prose">{item.text}</pre><label className="check-row"><input type="checkbox" disabled={!item.supported} checked={draft.instruction_keys.includes(item.key)} onChange={event => patch({ instruction_keys: toggled(draft.instruction_keys, item.key, event.target.checked) })} />Select {item.label}</label></details>)}
    {!preview.instructions.length && <p>No portable instruction fields were found in this dialect. You can write your own recipe guidance.</p>}
    <button className="button" disabled={!draft.instruction_keys.length} onClick={() => patch({ instructions: preview.instructions.filter(item => draft.instruction_keys.includes(item.key)).map(item => item.text).join('\n\n') })}>Replace recipe text with selected fragments</button>
    <TextField label="Reviewed recipe instructions" rows={7} maxLength={12000} value={draft.instructions} onChange={event => patch({ instructions: event.target.value })} />
  </section>
}

export function PresetSampling({ preview, draft, patch, profiles }: Props & { profiles: ModelProfile[] }) {
  return <section className="form-stack"><h4>Sampling proposals</h4><p className="subtle">Unchecked values remain reference only. Checked values create a separate model profile using a local connection you choose. The copy has no saved key and is not made Primary Writer. Identical values can behave differently across providers and models.</p>
    {preview.sampling.map(item => <div className="migration-message" key={item.target}><label className="check-row"><input type="checkbox" disabled={!item.supported} checked={draft.sampling_keys.includes(item.target)} onChange={event => { const sampling_keys = toggled(draft.sampling_keys, item.target, event.target.checked); patch({ sampling_keys, ...(!sampling_keys.length ? { base_profile_id: null, expected_profile_version_id: null } : {}) }) }} />{item.source} → {item.target}: {showValue(item.value)}</label><small>{item.note}</small></div>)}
    {!!draft.sampling_keys.length && <label className="field"><span>Local model profile to copy</span><select aria-label="Local model profile to copy" value={draft.base_profile_id ?? ''} onChange={event => { const profile = profiles.find(item => item.profile_id === event.target.value); patch({ base_profile_id: profile?.profile_id ?? null, expected_profile_version_id: profile?.id ?? null }) }}><option value="">Choose a local profile…</option>{profiles.map(profile => <option key={profile.id} value={profile.profile_id}>{profile.name} · {profile.config.provider} · {profile.config.model || 'model not chosen'}</option>)}</select></label>}
    {!!draft.sampling_keys.length && !profiles.length && <p>Create a model profile in Settings → Models before applying sampling proposals.</p>}
  </section>
}

export function PresetDestination({ preview, draft, patch, recipes, hasBatchDuplicate = false }: Props & { recipes: WritingResource[]; hasBatchDuplicate?: boolean }) {
  return <section className="form-stack"><label className="field"><span>Recipe destination</span><select aria-label="Recipe destination" value={draft.target_asset_id ?? ''} onChange={event => { const resource = recipes.find(item => item.asset_id === event.target.value); patch({ target_asset_id: resource?.asset_id ?? null, expected_version_id: resource?.id ?? null }) }}><option value="">New recipe</option>{recipes.map(item => <option key={item.id} value={item.asset_id}>New version of {item.name} · v{item.number}</option>)}</select></label><p className="subtle">A version update leaves earlier versions and Story pins intact. A matching name never identifies an update target.</p>
    {(!!preview.duplicates.length || hasBatchDuplicate) && <div className="import-compatibility"><h4>Duplicate review</h4>{preview.duplicates.map(item => <p key={item.version_id}>{item.name} · {item.match === 'exact-source' ? 'exact original file' : 'equivalent instruction and sampling proposals'}</p>)}{!draft.target_asset_id && <label className="field"><span>Preset duplicate decision</span><select aria-label="Preset duplicate decision" value={draft.duplicate_action} onChange={event => patch({ duplicate_action: event.target.value as 'skip' | 'new' })}><option value="skip">Skip if already imported</option><option value="new">Deliberately create another recipe</option></select></label>}</div>}
  </section>
}
