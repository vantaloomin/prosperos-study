import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import type { AdoptionChange, AdoptionConflict, AdoptionPreview, AssetVersion } from '../../types'
import { VersionDiffDialog } from './VersionDiff'
import { VersionSelect } from './VersionSelect'

export function AdoptionTargets({ preview, busy, onInclude }: { preview?: AdoptionPreview; busy: boolean; onInclude: (id: string) => void }) {
  const [compare, setCompare] = useState<AdoptionChange | null>(null)
  if (!preview) return null
  if (!preview.targets.length) return <p className="subtle">No Stories use these items yet. Future Stories can use their published versions.</p>
  const after = preview.versions.find((item) => item.id === compare?.after_version_id)
  return <div className="adoption-targets">
    {preview.targets.map((target) => <section className="adoption-target" key={target.story_id}>
      <div className="summary-line"><strong>{target.title}</strong><span>{target.archived && 'Archived · '}{target.changed ? `${target.changes.length} changes` : 'Already current'}</span></div>
      {target.changes.map((change) => <div className="adoption-change" key={change.asset_id}><div><span>{change.name}</span><small>{change.old_version === null ? 'Add' : `v${change.old_version} →`} v{change.new_version}{change.reason === 'dependency' && ' · linked lore'}{change.enabled_after ? ' · active' : ' · inactive'}</small></div><button className="text-button" onClick={() => setCompare(change)}>Compare</button></div>)}
      {target.conflicts.map((conflict) => <LinkedConflict key={conflict.asset_id} conflict={conflict} preview={preview} busy={busy} onInclude={onInclude} />)}
    </section>)}
    {after && compare && <VersionDiffDialog before={preview.versions.find((item) => item.id === compare.before_version_id)} after={after} onClose={() => setCompare(null)} />}
  </div>
}

function LinkedConflict({ conflict, preview, busy, onInclude }: { conflict: AdoptionConflict; preview: AdoptionPreview; busy: boolean; onInclude: (id: string) => void }) {
  return <div className="linked-conflict"><p>{conflict.message}</p>{conflict.references.map((reference, index) => {
    const available = reference.latest_version_id !== reference.version_id && !preview.selected_versions.some((version) => version.asset_id === reference.asset_id)
    return <div key={`${reference.version_id}:${index}`}><small>{reference.name} v{reference.number} requires {conflict.name} v{reference.requires_number}.</small>
      {available && <button className="text-button" disabled={busy} onClick={() => onInclude(reference.latest_version_id)}>Include {reference.name} v{reference.latest_number}</button>}
    </div>
  })}<small>Publish compatible linked versions when needed, then refresh this preview. Including an item also includes every Story using it.</small></div>
}

export function RelatedUpdates({ preview, related, onChange, busy, focusVersion }: { preview: AdoptionPreview; related: string[]; onChange: (ids: string[]) => void; busy: boolean; focusVersion: string | null }) {
  const [open, setOpen] = useState(false)
  const summary = useRef<HTMLElement>(null)
  useEffect(() => {
    if (focusVersion !== '') return
    const frame = requestAnimationFrame(() => summary.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [focusVersion])
  const selected = preview.selected_versions.filter((version) => related.includes(version.id))
  return <section className="related-updates">
    {selected.map((version) => <div className="related-update" key={version.asset_id}><strong>{version.name}</strong><VersionSelect assetId={version.asset_id} name={version.name} value={version.id} disabled={busy} focusOnReady={focusVersion === version.id} onChange={(id) => onChange(related.map((old) => old === version.id ? id : old))} /><button className="text-button" disabled={busy} onClick={() => onChange(related.filter((id) => id !== version.id))}>Remove related update</button></div>)}
    <details onToggle={(event) => setOpen(event.currentTarget.open)}><summary ref={summary}>Include another published item</summary>{open && <RelatedChoices preview={preview} disabled={busy} onInclude={(id) => onChange([...related, id])} />}</details>
  </section>
}

function RelatedChoices({ preview, disabled, onInclude }: { preview: AdoptionPreview; disabled: boolean; onInclude: (id: string) => void }) {
  const query = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const available = query.data?.filter((item) => !preview.selected_versions.some((selected) => selected.asset_id === item.asset_id)) ?? []
  return <div className="form-stack"><p className="subtle">Select an item to review its latest version together with this update. You can then choose an older version.</p><ErrorNotice message={query.error?.message} /><select aria-label="Include published item" value="" disabled={disabled || query.isPending} onChange={(event) => { if (event.target.value) onInclude(event.target.value) }}><option value="">Choose an item…</option>{available.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.number}</option>)}</select></div>
}
