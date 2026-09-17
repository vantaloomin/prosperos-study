import { assetLabel } from '../library/kinds'
import { useState } from 'react'
import type { AssetVersion } from '../../types'
import { AssetEditor } from '../library/AssetEditor'
import { pinAsset, selectedAssets, type SetupAsset, type SetupDraft } from './setup'
import { Participation } from './WritingPreferences'
import { SetupOpening } from './SetupOpening'

export function SetupPeople({ draft, patch, library }: { draft: SetupDraft; patch: (next: Partial<SetupDraft>) => void; library: AssetVersion[] }) {
  const [creating, setCreating] = useState(false)
  const selected = selectedAssets(draft, library)
  const choose = (asset: SetupAsset) => patch({ assets: [...selected.filter((item) => item.asset_id !== asset.asset_id), asset], legacyAssets: [] })
  const toggle = (asset: AssetVersion) => {
    const existing = selected.some((item) => item.asset_id === asset.asset_id)
    patch({ assets: existing ? selected.filter((item) => item.asset_id !== asset.asset_id) : [...selected, pinAsset(asset)], legacyAssets: [] })
  }
  return <div className="form-stack"><Participation value={draft} onChange={patch} /><div className="setup-section-heading"><div><h3>Bring your world with you</h3><p className="subtle">Optional. Choose characters and Canon collections; each keeps its selected version.</p></div><button className="button" onClick={() => setCreating(true)}>Create Library item</button></div>
    <div className="asset-choices setup-library">{library.map((asset) => <LibraryChoice key={asset.asset_id} asset={asset} pinned={selected.find((item) => item.asset_id === asset.asset_id)} onToggle={() => toggle(asset)} onUpdate={() => choose(pinAsset(asset))} />)}</div>
    {library.length === 0 && <p className="subtle">Your Library is empty. Create an item here, or add one after you begin.</p>}
    {draft.legacyAssets.some((id) => !library.some((item) => item.asset_id === id)) && <div className="setup-callout"><p>A Library selection from your older setup is unavailable.</p><button className="text-button" onClick={() => patch({ assets: selected, legacyAssets: [] })}>Remove unavailable selections</button></div>}
    <SetupOpening draft={draft} selected={selected} patch={patch} />
    {creating && <AssetEditor onClose={() => setCreating(false)} onSaved={(asset) => choose(pinAsset(asset))} />}
  </div>
}

function LibraryChoice({ asset, pinned, onToggle, onUpdate }: { asset: AssetVersion; pinned?: SetupAsset; onToggle: () => void; onUpdate: () => void }) {
  return <div><label className="check-row"><input type="checkbox" checked={!!pinned} onChange={onToggle} /><span>{pinned?.name ?? asset.name}<small>{assetLabel(asset.kind)} · version v{pinned?.number ?? asset.number}</small></span></label>{pinned && pinned.version_id !== asset.id && <button className="text-button" onClick={onUpdate}>Use newer version v{asset.number} of {asset.name}</button>}</div>
}
