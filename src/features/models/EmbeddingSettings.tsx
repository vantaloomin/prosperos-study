import { Field } from '../../components/Fields'
import type { ProfileConfig } from './types'

export function EmbeddingSettings({ config, patch }: { config: ProfileConfig; patch: (change: Partial<ProfileConfig>) => void }) {
  if (!['local', 'compatible', 'openai'].includes(config.provider)) return null
  return <details className="advanced-settings"><summary>Semantic story recall</summary><Field
    label="Embedding model ID (optional)" value={config.embedding_model ?? ''} maxLength={200}
    onChange={event => patch({ embedding_model: event.target.value })}
    hint="Use an embedding model available on this connection. Story setup must also enable semantic recall. It sends accepted earlier prose and search queries to this connection; it never uses the writing model as an embedding model. Saving the profile starts a fresh embedding cache version." />
    <label className="field"><span>Embedding input format</span><select aria-label="Embedding input format"
      value={config.embedding_input_format ?? 'plain'}
      onChange={event => patch({ embedding_input_format: event.target.value as ProfileConfig['embedding_input_format'] })}>
      <option value="plain">Plain text</option><option value="nomic-search-v1">Nomic search prefixes</option>
    </select><small>Choose Nomic search prefixes for Nomic Embed Text models that require separate document and query instructions. Plain text keeps existing behavior. Changing the format starts a separate cache.</small></label>
  </details>
}
