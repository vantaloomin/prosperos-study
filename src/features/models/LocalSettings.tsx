import { useId } from 'react'
import type { DiscoveredModel } from './discovery'
import type { LocalProtocol, LocalReasoning, ProfileConfig } from './types'
import { localProtocolSettings, nativeLocal } from './localProtocol'

type Props = { config: ProfileConfig; patch: (next: Partial<ProfileConfig>) => void }

export function LocalProtocolField({ config, patch }: Props) {
  const hintId = useId()
  if (config.provider !== 'local') return null
  return <label className="field"><span>Local API</span><select aria-label="Local API" aria-describedby={hintId} value={config.local_protocol ?? 'openai'} onChange={e => patch(localProtocolSettings(config, e.target.value as LocalProtocol))}>
    <option value="openai">OpenAI-compatible</option><option value="lmstudio">LM Studio native</option>
  </select><small id={hintId}>LM Studio native adds per-profile thinking control. Other local servers use the compatible API. Changing the API address requires re-entering any saved key.</small></label>
}

export function LocalThinking({ config, model, patch }: Props & { model?: DiscoveredModel }) {
  const hintId = useId()
  if (!nativeLocal(config)) return null
  const options = model?.reasoning_options ?? []
  const selected = config.local_reasoning ?? ''
  const unsupported = !!selected && !options.includes(selected)
  return <label className="field"><span>Thinking</span><select aria-label="Thinking" aria-describedby={hintId} value={selected} onChange={e => patch({ local_reasoning: (e.target.value || null) as LocalReasoning | null })}>
    <option value="">Model default</option>{unsupported && <option value={selected}>{selected} (saved; verify support)</option>}
    {options.map(value => <option key={value} value={value}>{value === 'off' ? 'Off' : value === 'on' ? 'On' : value}</option>)}
  </select><span id={hintId}><ThinkingHint model={model} selected={selected} /></span>
    <small>Applies only to requests using this profile. LM Studio's default stays unchanged. You can assign a separate profile to Story summaries.</small>
  </label>
}

function ThinkingHint({ model, selected }: { model?: DiscoveredModel; selected: LocalReasoning | '' }) {
  if (!model) return <small>Test the connection and select a model to discover supported options.</small>
  if (!model.reasoning_options?.length) return <small>This model did not report thinking controls. Use its default.</small>
  if (selected && !model.reasoning_options.includes(selected)) return <small role="status">This model does not report support for the saved setting. Choose an available option before generating.</small>
  return <small>Reported model default: {model.reasoning_default ?? 'not reported'}.</small>
}
