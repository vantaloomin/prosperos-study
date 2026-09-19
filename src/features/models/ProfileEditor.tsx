import { useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ModelDiscovery } from './ModelDiscovery'
import { useModelDiscovery } from './useModelDiscovery'
import { discoveredSettings, typedModelSettings, type Discovery } from './discovery'
import { profileSaveState } from './profileReadiness'
import { LocalProtocolField } from './LocalSettings'
import { localAddressHint } from './localProtocol'
import { GenerationSettings } from './GenerationSettings'
import { BackgroundVerification } from './BackgroundVerification'
import { EmbeddingSettings } from './EmbeddingSettings'
import { initialConfig, providers } from './types'
import type { ModelProfile, ProfileConfig, Provider } from './types'

function profileDefaults(profile?: ModelProfile) {
  return { name: profile?.name ?? '', config: profile?.config ?? initialConfig, savedKey: profile?.has_saved_key ?? false }
}

export function ProfileEditor({ profile, first, onClose, onSaved }: { profile?: ModelProfile; first?: boolean; onClose: () => void; onSaved?: (profile: ModelProfile) => void }) {
  const initial = profileDefaults(profile)
  const [name, setName] = useState(initial.name)
  const [config, setConfig] = useState(initial.config)
  const [key, setKey] = useState('')
  const [primary, setPrimary] = useState(!!first)
  const action = useAction()
  const discovery = useModelDiscovery(profile)
  const patch = (change: Partial<ProfileConfig>) => { if (change.base_url !== undefined || change.local_protocol !== undefined) discovery.reset(); setConfig(current => ({ ...current, ...change })) }
  const changeProvider = (provider: Provider) => { discovery.reset(); setConfig({ ...initialConfig, provider, base_url: providers[provider].url }); setKey('') }
  const onDiscovered = (result: Discovery) => setConfig(current => applyDiscovered(result, current))
  const { ready, savedKey, canSave } = profileSaveState(config, key, initial)
  const save = () => action.run(async () => {
    const body = { name: name.trim() || `${providers[config.provider].name} connection`, config, api_key: key || null, make_primary: primary && ready }
    const result = profile
      ? await api<ModelProfile>(`/profiles/${profile.profile_id}`, { ...body, expected_version_id: profile.id }, 'PUT')
      : await api<ModelProfile>('/profiles', body)
    setKey('')
    onSaved?.(result)
    onClose()
  })
  return <Modal open onClose={onClose} title={profile ? 'Edit model profile' : 'Find your writing partner'} description="Save a configuration you can reuse for writing, review, or collaboration." wide>
    <div className="dialog-body profile-editor"><div className="provider-picker" aria-label="Provider">{(Object.keys(providers) as Provider[]).map((provider) => <button key={provider} className={config.provider === provider ? 'selected' : ''} aria-pressed={config.provider === provider} onClick={() => changeProvider(provider)}>{providers[provider].name}</button>)}</div><div className="form-stack"><p className="subtle">{providers[config.provider].description}</p><Field label="Profile name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Everyday prose, careful review…" />
      <ConnectionFields config={config} apiKey={key} saved={savedKey} patch={patch} onKey={(value) => { discovery.reset(); setKey(value) }} />
      <ModelDiscovery config={config} result={discovery.result} busy={discovery.busy} error={discovery.error} connect={() => { void discovery.connect(config, key, onDiscovered) }} patch={patch} />
      <Field label="Model ID" value={config.model} onChange={(e) => patch(typedModelSettings(e.target.value, config, discovery.result?.model_details))} placeholder="Choose a returned model, or enter an ID" />
      <details className="advanced-settings"><summary>Generation settings</summary><GenerationSettings config={config} patch={patch} model={discovery.result?.model_details?.find(model => model.id === config.model)} /></details>
      <SavedProfileVerification profile={profile} config={config} apiKey={key} />
      <EmbeddingSettings config={config} patch={patch} />
      <label className="check-row"><input type="checkbox" disabled={!ready} checked={primary && ready} onChange={(e) => setPrimary(e.target.checked)} />Use as Primary Writer</label>{!ready && <p className="subtle">Save your API key now and finish setup later. Choose a model before using this connection for writing.</p>}<ErrorNotice message={action.error} />
    </div></div><footer className="dialog-footer"><span className="subtle">API keys stay in your OS credential vault.</span><button className="button primary" onClick={save} disabled={!canSave || action.busy}>{action.busy ? 'Saving…' : ready ? 'Save profile' : 'Save connection'}</button></footer>
  </Modal>
}

function ConnectionFields({ config, apiKey, saved, patch, onKey }: { config: ProfileConfig; apiKey: string; saved: boolean; patch: (next: Partial<ProfileConfig>) => void; onKey: (key: string) => void }) {
  if (config.provider === 'codex') return <p className="connection-note">Uses the CLI's existing authentication. No API key is needed here. Codex runs in an isolated temporary folder with shell, plugins, and web tools disabled.</p>
  const local = config.provider === 'local' || config.provider === 'kobold'
  return <><LocalProtocolField config={config} patch={patch} />{(local || config.provider === 'compatible') && <Field label="Server address" value={config.base_url} onChange={(e) => patch({ base_url: e.target.value })} hint={localAddressHint(config)} />}<TokenEntry key={config.provider} saved={saved} value={apiKey} onChange={onKey} /></>
}

function SavedProfileVerification({ profile, config, apiKey }: { profile?: ModelProfile; config: ProfileConfig; apiKey: string }) {
  return profile ? <BackgroundVerification profileId={profile.profile_id} dirty={Boolean(apiKey) || JSON.stringify(config) !== JSON.stringify(profile.config)} /> : null
}

function TokenEntry({ saved, value, onChange }: { saved: boolean; value: string; onChange: (value: string) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div className="token-entry"><p>{saved ? 'API key configured' : 'No API key stored for this connection'}</p><button className="button" onClick={() => setEditing(true)}>{saved ? 'Replace key' : 'Add API key'}</button><small>Local servers and environment credentials can leave this blank.</small></div>
  return <div className="token-entry"><Field label="API key (visible while editing)" type="text" name="connection-token" autoComplete="off" autoCapitalize="none" spellCheck={false} value={value} onChange={event => onChange(event.target.value)} placeholder="Paste an API token" hint="Stored in your OS credential vault when saved. Never shown again or included in story exports." /><button className="text-button" onClick={() => { onChange(''); setEditing(false) }}>Cancel key entry</button></div>
}

function applyDiscovered(result: Discovery, config: ProfileConfig): ProfileConfig {
  const models = result.model_details ?? []
  const selected = models.find(model => model.id === config.model) ?? (!config.model && models.length === 1 ? models[0] : undefined)
  return selected ? { ...config, ...discoveredSettings(selected, config) } : config
}
