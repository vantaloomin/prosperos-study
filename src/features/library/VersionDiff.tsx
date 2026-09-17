import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import type { AssetVersion, VersionReference } from '../../types'
import { versionChanges } from './versionChanges'
import { useReferences } from './versionQueries'
import { artworkUrl } from './artworkUrl'

function showValue(key: string, value: unknown, references: VersionReference[]) {
  if (value === undefined) return 'Not present'
  if (key === 'lorebook_versions' && Array.isArray(value)) return value.map((id) => {
    const reference = references.find((item) => item.id === id)
    return reference ? `${reference.name} · v${reference.number}` : String(id)
  }).join('\n') || 'No linked Canon collections'
  return typeof value === 'string' ? value || 'Empty' : JSON.stringify(value, null, 2)
}

export function VersionDiff({ before, after }: { before?: AssetVersion; after: AssetVersion }) {
  const changes = versionChanges(before, after)
  const ids = [...new Set([...(before?.content.lorebook_versions ?? []), ...(after.content.lorebook_versions ?? [])])]
  const references = useReferences(ids)
  return <section className="version-diff" aria-label={`Version changes for ${after.name}`}>
    <p className="subtle">{before ? `v${before.number}` : 'Not attached'} → v{after.number}{after.note && ` · ${after.note}`}</p>
    <ErrorNotice message={references.error?.message} />
    {ids.length > 0 && references.isPending && <Loading label="Reading linked version names…" />}
    {!changes.length && <p className="subtle">The name and content are unchanged.</p>}
    {changes.map((change) => <div className="version-field-change" key={change.key}><h4>{change.label}</h4><div className="version-diff-columns">
      <div><span className="eyebrow">Before</span><ChangedValue field={change.key} value={change.before} label={`${change.label} before`} references={references.data ?? []} /></div>
      <div><span className="eyebrow">After</span><ChangedValue field={change.key} value={change.after} label={`${change.label} after`} references={references.data ?? []} /></div>
    </div></div>)}
  </section>
}

function ChangedValue({ field, value, label, references }: { field: string; value: unknown; label: string; references: VersionReference[] }) {
  if (field === 'artwork_sha256') return typeof value === 'string' ? <img className="artwork-comparison" src={artworkUrl(value)} alt={label} /> : <p>No artwork</p>
  return <pre tabIndex={0} aria-label={label}>{showValue(field, value, references)}</pre>
}

export function VersionDiffDialog({ before, after, onClose }: { before?: AssetVersion; after: AssetVersion; onClose: () => void }) {
  return <Modal open wide onClose={onClose} title={`Compare ${after.name}`} description="Review changed fields. Comparing versions does not update a Story."><div className="dialog-body"><VersionDiff before={before} after={after} /></div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}
