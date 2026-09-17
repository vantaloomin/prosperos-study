import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { api } from '../../api'
import { TextField } from '../../components/Fields'
import type { AssetVersion, OpeningSource } from '../../types'
import { characterGreetings } from '../library/greetings'
import { useVersions } from '../library/versionQueries'
import { openingSourceAttached, pinAsset, type SetupAsset, type SetupDraft } from './setup'

export function SetupOpening({ draft, selected, patch }: { draft: SetupDraft; selected: SetupAsset[]; patch: (next: Partial<SetupDraft>) => void }) {
  const [choice, setChoice] = useState('')
  const characters = selected.filter((item) => item.kind !== 'lorebook')
  const queries = useQueries({ queries: characters.map((item) => ({ queryKey: ['versions', item.asset_id], queryFn: () => api<AssetVersion[]>(`/library/${item.asset_id}/versions`) })) })
  const options = queries.flatMap((query, index) => {
    const version = query.data?.find((item) => item.id === characters[index].version_id)
    return version ? characterGreetings(version.content).map((greeting) => ({ version, greeting, key: `${version.id}:${greeting.id}` })) : []
  })
  const preview = options.find((item) => item.key === choice)
  const useGreeting = () => {
    if (!preview) return
    patch({ opening: preview.greeting.text, opening_source: { asset_id: preview.version.asset_id, version_id: preview.version.id, greeting_id: preview.greeting.id } })
  }
  return <section className="form-stack setup-opening-choice" aria-label="Choose an opening"><div><h3>Choose how it begins</h3><p className="subtle">Optional. Preview a greeting from a selected character, or keep your own opening. Nothing is sent until you start.</p></div>
    {queries.some((query) => query.isPending) && <p className="subtle" role="status">Reading greetings from your selected versions…</p>}
    {queries.some((query) => query.isError) && <div className="setup-callout" role="alert">Some greetings could not be loaded. Your opening is unchanged. <button className="text-button" onClick={() => queries.forEach((query) => { if (query.isError) void query.refetch() })}>Retry greetings</button></div>}
    {options.length > 0 && <label className="field"><span>Preview a character greeting</span><select value={preview?.key ?? ''} onChange={(e) => setChoice(e.target.value)}><option value="">Choose a greeting…</option>{options.map((item) => <option key={item.key} value={item.key}>{item.version.name} v{item.version.number} · {item.greeting.label}</option>)}</select></label>}
    {preview && <div className="setup-callout"><div className="setup-opening prose">{preview.greeting.text}</div><button className="button" onClick={useGreeting}>{draft.opening ? 'Replace current opening with this greeting' : 'Use this greeting'}</button></div>}
    {draft.opening_source && <GreetingSource source={draft.opening_source} selected={selected} patch={patch} />}
    <OpeningPassage draft={draft} patch={patch} />
  </section>
}

function GreetingSource({ source, selected, patch }: { source: OpeningSource; selected: SetupAsset[]; patch: (next: Partial<SetupDraft>) => void }) {
  const versions = useVersions(source.asset_id)
  const version = versions.data?.find((item) => item.id === source.version_id)
  const attached = openingSourceAttached(source, selected)
  const pinned = selected.find((item) => item.version_id === source.version_id)
  const restoreSource = () => { if (version) patch({ assets: [...selected.filter((item) => item.asset_id !== source.asset_id), pinAsset(version)] }) }
  return <div className="setup-callout"><p className="subtle">{attached ? `Based on ${pinned?.name} v${pinned?.number}. It will begin as an assistant contribution; you can edit the wording below.` : 'The source character version is no longer selected. Restore it, choose another greeting, or keep this text as a custom narrator opening before continuing.'}</p>
    {!attached && <button className="button" disabled={!version} onClick={restoreSource}>Restore greeting’s character version</button>}
    <button className="text-button" onClick={() => patch({ opening_source: null })}>Keep as custom narrator opening</button>
  </div>
}

export function OpeningPassage({ draft, patch }: { draft: SetupDraft; patch: (next: Partial<SetupDraft>) => void }) {
  return <TextField label="Opening passage" value={draft.opening} rows={6} maxLength={100000} onChange={(event) => patch({ opening: event.target.value, opening_source: event.target.value.trim() ? draft.opening_source : null })} hint={draft.opening_source ? 'Your selected greeting becomes the opening passage once. The Library version stays unchanged.' : 'Your words become the opening passage. Leave blank to start without one. No model is called.'} />
}
