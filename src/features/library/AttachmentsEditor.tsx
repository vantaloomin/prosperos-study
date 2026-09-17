import { assetLabel } from './kinds'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AssetVersion, Attachment, AttachedAsset, Story } from '../../types'
import { VersionSelect } from './VersionSelect'
import { VersionDiffDialog } from './VersionDiff'
import { useVersions } from './versionQueries'

export function AttachmentsEditor({ story, onClose }: { story: Story; onClose: () => void }) {
  const { data: assets = [] } = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const [selected, setSelected] = useState<Attachment[]>(story.attachments.map(({ asset_id, version_id, enabled, priority }) => ({ asset_id, version_id, enabled, priority })))
  const action = useAction()
  function toggle(asset: AssetVersion) {
    const exists = selected.some((item) => item.asset_id === asset.asset_id)
    setSelected(exists ? selected.filter((item) => item.asset_id !== asset.asset_id) : [...selected, { asset_id: asset.asset_id, version_id: asset.id, enabled: true, priority: 0 }])
  }
  const save = () => action.run(async () => {
    await api(`/stories/${story.id}/attachments`, { operation_id: operationId(), expected_revision: story.revision, attachments: selected }, 'PUT')
    onClose()
  })
  return <Modal open onClose={onClose} title="Bring your library into this story" description="Library items are shared; this story keeps the versions selected here."><div className="dialog-body form-stack">
    {assets.map((asset) => <AttachmentChoice key={asset.asset_id} asset={asset} story={story} selected={selected} onToggle={() => toggle(asset)} onChange={(change) => setSelected(selected.map((item) => item.asset_id === asset.asset_id ? { ...item, ...change } : item))} />)}
    {!assets.length && <p className="subtle">Create a character or Canon collection in Library first.</p>}
    <ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Past snapshots keep their versions.</span><button className="button primary" onClick={save} disabled={action.busy}>Save story library</button></footer></Modal>
}

function AttachmentChoice({ asset, story, selected, onToggle, onChange }: { asset: AssetVersion; story: Story; selected: Attachment[]; onToggle: () => void; onChange: (change: Partial<Attachment>) => void }) {
  const item = selected.find((entry) => entry.asset_id === asset.asset_id)
  const old = story.attachments.find((entry) => entry.asset_id === asset.asset_id)
  return <div className="attachment-choice"><label className="check-row"><input type="checkbox" checked={!!item} onChange={onToggle} /><span>{asset.name}<small>{assetLabel(asset.kind)}</small></span></label>{item && <AttachmentControls asset={asset} item={item} old={old} onChange={onChange} />}</div>
}

function AttachmentControls({ asset, item, old, onChange }: { asset: AssetVersion; item: Attachment; old?: AttachedAsset; onChange: (change: Partial<Attachment>) => void }) {
  const query = useVersions(asset.asset_id)
  const [compare, setCompare] = useState(false)
  const selected = query.data?.find((version) => version.id === item.version_id)
  return <div className="attachment-controls"><VersionSelect assetId={asset.asset_id} name={asset.name} value={item.version_id} onChange={(version_id) => onChange({ version_id })} />
    <div className="attachment-activation"><label className="check-row"><input type="checkbox" checked={item.enabled} onChange={(event) => onChange({ enabled: event.target.checked })} />Use in context</label><label className="field"><span>Priority</span><input type="number" aria-label={`Context priority for ${asset.name}`} value={item.priority} step={1} onChange={(event) => onChange({ priority: Number(event.target.value) })} /></label></div>
    <button className="text-button" disabled={!selected} onClick={() => setCompare(true)}>Compare with Story version</button>
    {compare && selected && <VersionDiffDialog before={old?.version} after={selected} onClose={() => setCompare(false)} />}
  </div>
}
