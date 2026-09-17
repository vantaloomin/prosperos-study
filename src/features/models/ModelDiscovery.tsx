import { Check, PlugZap } from 'lucide-react'
import { ModelCombobox } from './ModelCombobox'
import { ErrorNotice } from '../../components/Feedback'
import type { ProfileConfig } from './types'
import { discoveredSettings, type Discovery, type DiscoveredModel } from './discovery'

interface Props { config: ProfileConfig; result: Discovery | null; busy: boolean; error: string; connect: () => void; patch: (next: Partial<ProfileConfig>) => void }
export function ModelDiscovery({ config, result, busy, error, connect, patch }: Props) {
  const blocked = config.provider === 'compatible' && !config.base_url.trim()
  return <section className="model-discovery form-stack" aria-label="Connection and models">
    <div className="connection-test"><button type="button" className="button" disabled={busy || blocked} onClick={connect}><PlugZap size={16} />{busy ? 'Connecting…' : 'Test connection'}</button>{result && <span className="connection-success" role="status"><Check size={15} />Connected</span>}</div>
    <ErrorNotice message={error} />
    {result && <><p className="subtle">{result.note}</p><ModelOptions models={result.model_details ?? []} config={config} patch={patch} /></>}
  </section>
}

function ModelOptions({ models, config, patch }: { models: DiscoveredModel[]; config: ProfileConfig; patch: Props['patch'] }) {
  const selected = models.find(model => model.id === config.model)
  if (!models.length) return null
  const choose = (id: string) => { const model = models.find(item => item.id === id); if (model) patch(discoveredSettings(model, config)) }
  return <><ModelCombobox models={models} value={selected?.id ?? ''} onChange={choose} /><p className="subtle">Search by model name, provider, or ID. You can also enter an ID below.</p>{selected && <ModelLimits model={selected} />}</>
}

function ModelLimits({ model }: { model: DiscoveredModel }) {
  return <><div className="model-limits"><span>Reported context <strong>{model.context_tokens?.toLocaleString() ?? 'Not reported'}</strong></span><span>Output ceiling <strong>{model.max_output_tokens?.toLocaleString() ?? 'Not reported'}</strong></span></div><p className="subtle">Reported limits fill your allowance; your preferred output length stays within the reported ceiling. Models with unreported limits need a manual allowance under Generation settings.</p></>
}
