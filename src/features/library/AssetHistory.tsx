import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { AdoptionPreview, AssetVersion } from '../../types'
import { AdoptionDialog } from './AdoptionDialog'
import { VersionDiff } from './VersionDiff'
import { useVersions } from './versionQueries'

export function AssetHistory({ asset, onUse }: { asset: AssetVersion; onUse: (version: AssetVersion) => void }) {
  const query = useVersions(asset.asset_id)
  const [adopt, setAdopt] = useState<AssetVersion | null>(null)
  const [compare, setCompare] = useState<AssetVersion | null>(null)
  return <section className="version-history"><h4>Version history</h4><ErrorNotice message={query.error?.message} />
    {query.isPending && <Loading label="Opening version history…" />}
    {query.data?.map((version) => <div key={version.id}><strong>v{version.number}</strong><small>{version.note || 'Published version'} · {new Date(version.created_at).toLocaleDateString()}</small><div className="row-actions">
      <button className="text-button" onClick={() => onUse({ ...version, kind: asset.kind })}>Use as draft</button>
      <button className="text-button" onClick={() => setCompare(version)}>Compare versions</button>
      <button className="text-button" onClick={() => setAdopt(version)}>Update stories</button>
      {asset.kind === 'lorebook' && <a className="text-button" href={`/api/versions/${version.id}/markdown`} download>Markdown</a>}
    </div></div>)}
    {adopt && <AdoptionDialog version={adopt} onClose={() => setAdopt(null)} />}
    {compare && <HistoryComparison versions={query.data ?? []} before={compare} after={asset} onClose={() => setCompare(null)} />}
  </section>
}

function HistoryComparison({ versions, before, after, onClose }: { versions: AssetVersion[]; before: AssetVersion; after: AssetVersion; onClose: () => void }) {
  const [left, setLeft] = useState(before.id)
  const [right, setRight] = useState(after.id)
  return <Modal open wide onClose={onClose} title={`Compare ${after.name}`} description="Choose two published versions. This view does not change any Story.">
    <div className="dialog-body"><div className="version-comparison-controls">{[{ label: 'Before version', value: left, set: setLeft }, { label: 'After version', value: right, set: setRight }].map((field) => <label className="field" key={field.label}><span>{field.label}</span><select value={field.value} onChange={(event) => field.set(event.target.value)}>{versions.map((version) => <option key={version.id} value={version.id}>v{version.number} · {version.name}</option>)}</select></label>)}</div>
      <VersionDiff before={versions.find((item) => item.id === left) ?? before} after={versions.find((item) => item.id === right) ?? after} />
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer>
  </Modal>
}

export function AssetUsage({ asset }: { asset: AssetVersion }) {
  const query = useQuery({ queryKey: ['adoption', asset.id, []], queryFn: () => api<AdoptionPreview>(`/versions/${asset.id}/adoption`) })
  if (query.isPending) return <p className="subtle">Checking Story usage…</p>
  if (query.error) return <ErrorNotice message={query.error.message} />
  const targets = query.data?.targets ?? []
  return <details className="asset-usage"><summary>Used by {targets.length} {targets.length === 1 ? 'Story' : 'Stories'}</summary>
    {targets.map((item) => <p key={item.story_id}>{item.title} · v{item.old_version}{item.archived && ' · archived'}</p>)}
    {!targets.length && <p>No existing Stories use this item.</p>}
  </details>
}
