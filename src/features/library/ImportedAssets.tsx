import { useId } from 'react'
import type { ImportAsset, ImportPreview } from './importTypes'
import { artworkUrl } from './artworkUrl'

export function ImportedAssets({ preview }: { preview: ImportPreview }) {
  if (!preview.assets?.length) return null
  return <details className="import-attached-assets"><summary>Attached assets ({preview.assets.length})</summary>
    <p className="subtle">Images shown here use safe local previews. Other media stays in the original package. External references are never fetched.</p>
    <div className="import-asset-grid">{preview.assets.map((asset, index) => <div className="import-asset-item form-stack" key={index}>
      {asset.status === 'image' && asset.sha256 && <img src={artworkUrl(asset.sha256, 'thumbnail')} alt={asset.label || 'Imported artwork'} loading="lazy" />}
      <strong>{asset.label || `Asset ${index + 1}`}</strong><small>{asset.kind} · {asset.status === 'image' ? `${asset.width} × ${asset.height}` : asset.status}</small>
      <small>{asset.uri}</small>{asset.reason && <p className="subtle">{asset.reason}</p>}
      {asset.path && asset.status !== 'missing' && <a className="text-button" href={`/api/library-imports/${preview.id}/assets/${index}`} download>Download original asset</a>}
    </div>)}</div>
  </details>
}

export function ImportedArtworkChoice({ assets, value, onChange }: { assets?: ImportAsset[]; value?: string | null; onChange: (value: string | null) => void }) {
  const id = useId()
  const images = assets?.filter(asset => asset.status === 'image') ?? []
  if (!images.length) return null
  return <label className="field" htmlFor={id}><span id={`${id}-label`}>Artwork from this container</span><select id={id} aria-labelledby={`${id}-label`} aria-describedby={`${id}-hint`} value={value ?? ''} onChange={event => onChange(event.target.value || null)}>
    <option value="">No container artwork</option>{value && !images.some(image => image.sha256 === value) && <option value={value}>Separately chosen artwork</option>}
    {images.map((image, index) => <option key={index} value={image.sha256}>{image.label || image.path} · {image.kind}</option>)}
  </select><small id={`${id}-hint`}>Choose which image becomes this version’s artwork. Other attached assets remain available as preserved sources.</small></label>
}
