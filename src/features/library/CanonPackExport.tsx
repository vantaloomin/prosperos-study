import { useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AssetVersion } from '../../types'

export function CanonPackExport({ asset, onClose }: { asset: AssetVersion; onClose: () => void }) {
  const [overview, setOverview] = useState(true)
  const [selected, setSelected] = useState<string[]>([])
  const [reviewed, setReviewed] = useState(false)
  const [search, setSearch] = useState('')
  const [downloaded, setDownloaded] = useState(false)
  const action = useAction()
  const entries = asset.content.lore_definition?.entries ?? []
  const matches = entries.filter((entry) => entry.title.toLowerCase().includes(search.toLowerCase()))
  const toggle = (id: string) => { setSelected((old) => old.includes(id) ? old.filter((key) => key !== id) : [...old, id]); setReviewed(false); setDownloaded(false) }
  const download = () => action.run(async () => {
    const pack = await api<{ id: string }>(`/versions/${asset.id}/brain-pack`, { include_overview: overview, entry_ids: selected, reviewed_rules: reviewed })
    downloadPack(pack); setDownloaded(true)
  })
  return <Modal open title="Share a Canon reference pack" description={`Export the published ${asset.name} v${asset.number}. Unsaved editor changes are excluded.`} onClose={onClose}>
    <div className="dialog-body form-stack"><label className="check-row"><input type="checkbox" checked={overview} onChange={(event) => { setOverview(event.target.checked); setDownloaded(false) }} />Include the published Markdown overview</label>
      {entries.length > 0 && <><label className="field"><span>Find an entry to include</span><input value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <fieldset className="form-stack canon-export-entries"><legend>Optional entry prose · {selected.length} selected</legend>{matches.slice(0, 80).map((entry) => <label className="check-row" key={entry.id}><input type="checkbox" checked={selected.includes(entry.id)} onChange={() => toggle(entry.id)} /><span>{entry.title}<small>{entry.enabled ? 'Enabled' : 'Off'} · {entry.activation} · {entry.kind}</small></span></label>)}</fieldset>
        {matches.length > 80 && <p className="subtle">Showing 80 matching entries. Narrow the search to find others; selections remain.</p>}</>}
      <p className="subtle">The SGC pack contains reference text and search cues. Native entry activation, timing, chance and placement rules are not portable. Selecting an entry exports its prose even if it is currently off.</p>
      {selected.length > 0 && <label className="check-row"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I reviewed that selected entries become ordinary reference prose without their native rules.</label>}
      <p className="subtle">The native collection, original imports and all Story versions remain intact.</p><ErrorNotice message={action.error} />{downloaded && <p role="status">The SGC pack is ready in your downloads.</p>}
    </div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Done</button><button className="button primary" disabled={exportUnavailable(action.busy, overview, selected.length, reviewed)} onClick={download}>{action.busy ? 'Preparing…' : 'Download SGC pack'}</button></footer>
  </Modal>
}

function downloadPack(pack: { id: string }) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2) + '\n'], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url; link.download = pack.id + '.json'; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function exportUnavailable(busy: boolean, overview: boolean, count: number, reviewed: boolean) {
  return busy || (!overview && count === 0) || (count > 0 && !reviewed)
}
